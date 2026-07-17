import logging
from typing import Any, Callable, Optional

from app.core.cache_backend import (
    cache_get,
    cache_get_last_good,
    cache_get_stale,
    cache_set,
    cache_delete,
    cache_delete_prefix,
    cache_flush_pattern,
    cache_run_singleflight,
    cache_scan_prefix,
    cache_stats as _backend_stats,
)

logger = logging.getLogger(__name__)


def get_last_good(key: str) -> Optional[Any]:
    return cache_get_last_good(key)


def get(key: str) -> Optional[Any]:
    return cache_get(key)


def get_stale(key: str) -> Optional[Any]:
    return cache_get_stale(key)


def set(key: str, value: Any, ttl: Optional[int] = None) -> None:
    cache_set(key, value, ttl=ttl)
    logger.debug("Cache SET: %s", key)


def delete(key: str) -> None:
    cache_delete(key)
    logger.debug("Cache DELETE: %s", key)


def delete_prefix(prefix: str) -> None:
    cache_delete_prefix(prefix)
    logger.debug("Cache DELETE_PREFIX: %s", prefix)


def scan_prefix(prefix: str) -> list[str]:
    """Return every cache key starting with prefix."""
    return cache_scan_prefix(prefix)


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
# Stale-while-revalidate primitives (mirrors datacenter-api's
# app/services/cache_service.get_with_stale / set_with_stale).
#
# customer-api's cache_backend already writes every cache_set as both the
# primary key and a long-TTL ":last_good" shadow key (ADR-0007). These
# primitives just expose "did we hit the primary (fresh) key or fall back to
# last_good (stale)?" so unique-jobs-style callers can decide whether to kick
# off a background revalidate, without needing a second "stale:" key prefix
# like datacenter-api uses.
# ---------------------------------------------------------------------------

_DEFAULT_STALE_TTL_SECONDS = 86400  # 24h — matches LAST_GOOD_TTL_SECONDS floor


def get_with_stale(key: str) -> tuple[Optional[Any], bool]:
    """(value, is_stale). Primary (Redis or memory) hit -> (value, False).
    last_good-only hit -> (value, True). Neither -> (None, False)."""
    from app.core.cache_backend import (
        _memory_cache,
        _memory_lock,
        _read_redis_json,
        cache_get_last_good,
        get_redis_client,
        last_good_key,
    )

    rc = get_redis_client()
    if rc:
        primary = _read_redis_json(rc, key)
        if primary is not None:
            return primary, False
        last_good = cache_get_last_good(key)
        if last_good is not None:
            return last_good, True

    with _memory_lock:
        if key in _memory_cache:
            return _memory_cache[key], False
        lg_key = last_good_key(key)
        if lg_key in _memory_cache:
            return _memory_cache[lg_key], True

    return None, False


def set_with_stale(
    key: str,
    value: Any,
    fresh_ttl: Optional[int] = 2100,
    stale_ttl: int = _DEFAULT_STALE_TTL_SECONDS,
) -> None:
    """Write the primary key with `fresh_ttl`. cache_set already writes the
    ":last_good" shadow key with `max(fresh_ttl * 2, LAST_GOOD_TTL_SECONDS)`
    (>= 24h for any reasonable fresh_ttl), which is what get_with_stale reads
    on a primary miss — `stale_ttl` is accepted for signature parity with
    datacenter-api's set_with_stale but the default last_good TTL already
    satisfies it in the common case."""
    cache_set(key, value, ttl=fresh_ttl)
