import logging
from typing import Any, Callable, Optional

from app.core.cache_backend import (
    cache_get,
    cache_set,
    cache_delete,
    cache_delete_prefix,
    cache_flush_pattern,
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
    return _backend_stats()
