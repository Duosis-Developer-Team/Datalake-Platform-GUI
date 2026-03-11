import threading
import logging
from typing import Any, Callable, Optional
from cachetools import TTLCache

logger = logging.getLogger(__name__)

DEFAULT_TTL = 1200

_cache: TTLCache = TTLCache(maxsize=100, ttl=DEFAULT_TTL)
_lock = threading.Lock()


def get(key: str) -> Optional[Any]:
    with _lock:
        return _cache.get(key)


def set(key: str, value: Any) -> None:
    with _lock:
        _cache[key] = value
    logger.debug("Cache SET: %s", key)


def delete(key: str) -> None:
    with _lock:
        _cache.pop(key, None)
    logger.debug("Cache DELETE: %s", key)


def clear() -> None:
    with _lock:
        _cache.clear()
    logger.info("Cache cleared.")


def cached(key_fn: Callable[..., str]):
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
                set(cache_key, result)
            return result
        wrapper.__wrapped__ = fn
        return wrapper
    return decorator


def stats() -> dict:
    with _lock:
        return {
            "current_size": len(_cache),
            "max_size": _cache.maxsize,
            "ttl_seconds": _cache.ttl,
            "keys": list(_cache.keys()),
        }
