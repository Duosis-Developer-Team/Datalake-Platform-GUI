import logging
from typing import Any, Callable, Optional

from app.core.cache_backend import (
    cache_get,
    cache_set,
    cache_delete,
    cache_delete_prefix,
    cache_flush_pattern,
    cache_run_singleflight,
    cache_stats as _backend_stats,
)

logger = logging.getLogger(__name__)


def get(key: str) -> Optional[Any]:
    return cache_get(key)


def set(key: str, value: Any, ttl: Optional[int] = None) -> None:
    cache_set(key, value, ttl=ttl)
    logger.debug("Cache SET: %s", key)


def delete(key: str) -> None:
    cache_delete(key)
    logger.debug("Cache DELETE: %s", key)


def delete_prefix(prefix: str) -> None:
    cache_delete_prefix(prefix)
    logger.debug("Cache DELETE_PREFIX: %s", prefix)


def clear() -> None:
    cache_flush_pattern("*")
    logger.info("Cache cleared.")


def run_singleflight(key: str, factory: Callable[[], Any], ttl: Optional[int] = None) -> Any:
    """Run factory only once for concurrent cache misses on the same key."""
    return cache_run_singleflight(key, factory, ttl=ttl)


def cached(key_fn: Callable[..., str], ttl: Optional[int] = None):
    def decorator(fn: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            cache_key = key_fn(*args, **kwargs)
            hit = get(cache_key)
            if hit is not None:
                logger.debug("Cache HIT: %s", cache_key)
                return hit
            logger.debug("Cache MISS: %s", cache_key)
            result = fn(*args, **kwargs)
            if result is not None:
                set(cache_key, result, ttl=ttl)
            return result

        wrapper.__wrapped__ = fn
        return wrapper

    return decorator


def stats() -> dict:
    return _backend_stats()


# ---------------------------------------------------------------------------
# Stale-while-revalidate primitives
# ---------------------------------------------------------------------------
#
# Çoğu endpoint için varsayılan davranış yeterli (fresh hit veya cold miss).
# Ama backup-jobs gibi aggregation maliyeti yüksek olan path'lerde, fresh
# expire olduğu anda kullanıcıya cold SQL beklemesini dayatmak yerine, eski
# (stale) bir snapshot'tan instant yanıt verip arka planda revalidate etmek
# isteriz. Bunu sağlamak için her cache.set, hem fresh key'i hem de daha uzun
# TTL'li bir "stale:..." key'i yazar; get_with_stale ikisini sırasıyla okur.

_STALE_PREFIX = "stale:"
_DEFAULT_STALE_TTL_SECONDS = 86400  # 24 saat


def set_with_stale(
    key: str,
    value: Any,
    fresh_ttl: Optional[int] = None,
    stale_ttl: int = _DEFAULT_STALE_TTL_SECONDS,
) -> None:
    """
    Hem fresh hem 'stale:' snapshot'unu yazar. Stale TTL fresh'ten uzun olmalı.

    Önemli: cache_backend'in memory-LRU katmanı per-key TTL bilmiyor (global ~20dk).
    Bu, fresh_ttl > 1200s olduğunda backfill yolundan TTL'i kısaltabiliyordu.
    Çözüm: bu primitive cache_backend.cache_set'i bypass eder ve sadece Redis'e
    yazar. Cache okuma yine Redis'ten gelir (memory miss → Redis fallback).
    """
    from app.core.cache_backend import _serialize  # type: ignore
    from app.core.redis_client import get_redis_client

    rc = get_redis_client()
    if rc is None:
        # Redis yoksa fallback olarak normal cache_set (memory only)
        cache_set(key, value, ttl=fresh_ttl)
        cache_set(f"{_STALE_PREFIX}{key}", value, ttl=stale_ttl)
        return
    serialized = _serialize(value)
    if serialized is None:
        return
    try:
        effective_fresh_ttl = fresh_ttl if fresh_ttl is not None else 1200
        rc.setex(key, effective_fresh_ttl, serialized)
        rc.setex(f"{_STALE_PREFIX}{key}", stale_ttl, serialized)
    except Exception as exc:
        logger.warning("set_with_stale Redis error for %s: %s", key, exc)


def get_with_stale(key: str) -> tuple[Optional[Any], bool]:
    """
    (value, is_stale) döner. Hiç yoksa (None, False).

    is_stale=True → fresh expire, stale snapshot kullanılıyor → arayan kişi
    arka planda revalidate tetiklemeli.

    Direkt Redis'e bakar (memory-LRU katmanını bypass eder) — böylece memory
    backfill'inin default TTL ile yanlış key yazması engellenir.
    """
    from app.core.redis_client import get_redis_client
    import json as _json

    rc = get_redis_client()
    if rc is None:
        # Redis yoksa cache_get (memory only) ile fallback
        fresh = cache_get(key)
        if fresh is not None:
            return fresh, False
        stale = cache_get(f"{_STALE_PREFIX}{key}")
        if stale is not None:
            return stale, True
        return None, False

    try:
        raw_fresh = rc.get(key)
        if isinstance(raw_fresh, (str, bytes, bytearray)):
            return _json.loads(raw_fresh), False
        raw_stale = rc.get(f"{_STALE_PREFIX}{key}")
        if isinstance(raw_stale, (str, bytes, bytearray)):
            return _json.loads(raw_stale), True
    except Exception as exc:
        logger.warning("get_with_stale Redis error for %s: %s", key, exc)
    return None, False
