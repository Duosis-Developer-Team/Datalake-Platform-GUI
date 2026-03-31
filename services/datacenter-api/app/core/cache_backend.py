import json
import logging
import threading
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional, cast

from cachetools import TTLCache

from app.config import settings
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_memory_lock = threading.RLock()

_memory_cache: TTLCache = TTLCache(
    maxsize=settings.cache_max_memory_items,
    ttl=settings.cache_ttl_seconds,
)


class _CustomEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _serialize(value: Any) -> Optional[str]:
    try:
        return json.dumps(value, cls=_CustomEncoder)
    except TypeError as exc:
        logger.warning("Cache serialize error: %s", exc)
        return None


def cache_get(key: str) -> Any:
    redis_client = get_redis_client()
    if redis_client:
        try:
            raw = redis_client.get(key)
            if isinstance(raw, (str, bytes, bytearray)):
                return json.loads(raw)
        except Exception as exc:
            logger.warning("Redis GET error: %s", exc)

    with _memory_lock:
        value = _memory_cache.get(key)
    if value is not None:
        if redis_client:
            try:
                serialized = _serialize(value)
                if serialized:
                    redis_client.setex(key, settings.cache_ttl_seconds, serialized)
            except Exception as exc:
                logger.warning("Redis backfill error: %s", exc)
        return value

    return None


def cache_set(key: str, value: Any, ttl: Optional[int] = None) -> None:
    effective_ttl = ttl if ttl is not None else settings.cache_ttl_seconds
    redis_client = get_redis_client()
    if redis_client:
        try:
            serialized = _serialize(value)
            if serialized:
                redis_client.setex(key, effective_ttl, serialized)
        except Exception as exc:
            logger.warning("Redis SET error: %s", exc)
    with _memory_lock:
        _memory_cache[key] = value


def cache_delete(key: str) -> None:
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.delete(key)
        except Exception as exc:
            logger.warning("Redis DELETE error: %s", exc)
    with _memory_lock:
        _memory_cache.pop(key, None)


def cache_delete_prefix(prefix: str) -> None:
    """Remove keys starting with prefix from Redis (SCAN) and in-memory cache."""
    if not prefix:
        return
    redis_client = get_redis_client()
    pattern = f"{prefix}*"
    if redis_client:
        try:
            cursor = 0
            while True:
                scan_result = cast(tuple[int, list[str]], redis_client.scan(cursor=cursor, match=pattern, count=100))
                cursor, keys = scan_result
                if keys:
                    redis_client.delete(*keys)
                if cursor == 0:
                    break
        except Exception as exc:
            logger.warning("Redis SCAN delete_prefix error: %s", exc)
    with _memory_lock:
        to_remove = [k for k in list(_memory_cache.keys()) if isinstance(k, str) and k.startswith(prefix)]
        for k in to_remove:
            _memory_cache.pop(k, None)


def cache_flush_pattern(pattern: str) -> None:
    redis_client = get_redis_client()
    if redis_client:
        try:
            cursor = 0
            while True:
                scan_result = cast(tuple[int, list[str]], redis_client.scan(cursor=cursor, match=pattern, count=100))
                cursor, keys = scan_result
                if keys:
                    redis_client.delete(*keys)
                if cursor == 0:
                    break
        except Exception as exc:
            logger.warning("Redis SCAN/flush error: %s", exc)
    with _memory_lock:
        _memory_cache.clear()


def cache_stats() -> dict:
    redis_client = get_redis_client()
    redis_available = False
    redis_keys = 0
    if redis_client:
        try:
            redis_client.ping()
            redis_available = True
            redis_keys = redis_client.dbsize()
        except Exception:
            pass
    return {
        "redis_available": redis_available,
        "redis_keys": redis_keys,
        "memory_size": len(_memory_cache),
        "memory_max": _memory_cache.maxsize,
        "ttl": settings.cache_ttl_seconds,
    }
