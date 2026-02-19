# Module-level TTL cache service.
# Replaces the broken instance-level lru_cache pattern.
# Uses cachetools.TTLCache so entries expire automatically after TTL seconds.

import threading
import logging
from typing import Any, Callable, Optional
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Default TTL for all cache entries (seconds).
# Metrics dashboards update every few minutes; 5 min is a safe balance.
DEFAULT_TTL = 300  # 5 minutes

# Module-level cache — shared across all instances of DatabaseService.
# maxsize=50 covers 9 DCs + global overview + headroom for future keys.
_cache: TTLCache = TTLCache(maxsize=50, ttl=DEFAULT_TTL)
_lock = threading.Lock()


def get(key: str) -> Optional[Any]:
    """Return cached value or None if the key is missing / expired."""
    with _lock:
        return _cache.get(key)


def set(key: str, value: Any) -> None:
    """Store a value in the cache under the given key."""
    with _lock:
        _cache[key] = value
    logger.debug("Cache SET: %s", key)


def delete(key: str) -> None:
    """Explicitly evict a single key."""
    with _lock:
        _cache.pop(key, None)
    logger.debug("Cache DELETE: %s", key)


def clear() -> None:
    """Flush the entire cache (e.g. on config reload or forced refresh)."""
    with _lock:
        _cache.clear()
    logger.info("Cache cleared.")


def cached(key_fn: Callable[..., str]):
    """
    Decorator factory for caching function results.

    Usage:
        @cached(lambda dc_code: f"dc_details:{dc_code}")
        def get_dc_details(self, dc_code):
            ...
    """
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
    """Return cache statistics for observability / debugging."""
    with _lock:
        return {
            "current_size": len(_cache),
            "max_size": _cache.maxsize,
            "ttl_seconds": _cache.ttl,
            "keys": list(_cache.keys()),
        }
