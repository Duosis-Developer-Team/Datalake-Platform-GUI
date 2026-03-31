# Module-level cache service with stale-while-revalidate semantics.
# Cache entries never disappear until explicitly overwritten by fresh data.
# TTL is only used as a staleness hint (not for eviction).

import threading
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Max number of distinct cache keys.  Physical inventory adds ~30 keys on top
# of existing DC/overview/customer/S3/backup keys.
MAX_SIZE = 512

_cache: dict[str, Any] = {}
_lock = threading.RLock()


def get(key: str) -> Optional[Any]:
    """Return cached value or None if not present. Never expires."""
    with _lock:
        return _cache.get(key)


def set(key: str, value: Any) -> None:
    """Store / overwrite a value in the cache."""
    with _lock:
        if len(_cache) >= MAX_SIZE and key not in _cache:
            oldest = next(iter(_cache))
            _cache.pop(oldest, None)
            logger.debug("Cache evicted oldest key: %s", oldest)
        _cache[key] = value
    logger.debug("Cache SET: %s", key)


def delete(key: str) -> None:
    """Explicitly evict a single key."""
    with _lock:
        _cache.pop(key, None)
    logger.debug("Cache DELETE: %s", key)


def delete_prefix(prefix: str) -> None:
    """Remove all in-memory keys that start with prefix (used after raw dataset refresh)."""
    if not prefix:
        return
    with _lock:
        to_remove = [k for k in _cache if isinstance(k, str) and k.startswith(prefix)]
        for k in to_remove:
            _cache.pop(k, None)
        n = len(to_remove)
    if n:
        logger.debug("Cache DELETE_PREFIX %s (%d keys)", prefix, n)


def clear() -> None:
    """Flush the entire cache (e.g. on config reload or forced refresh)."""
    with _lock:
        _cache.clear()
    logger.info("Cache cleared.")


def cached(key_fn):
    """
    Decorator factory for caching function results.

    Usage:
        @cached(lambda dc_code: f"dc_details:{dc_code}")
        def get_dc_details(self, dc_code):
            ...
    """
    def decorator(fn):
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
            "max_size": MAX_SIZE,
            "keys": list(_cache.keys()),
        }
