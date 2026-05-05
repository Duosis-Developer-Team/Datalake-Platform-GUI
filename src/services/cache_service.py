# Module-level cache service with stale-while-revalidate semantics.
# Cache entries never disappear until explicitly overwritten by fresh data.
# TTL is only used as a staleness hint (not for eviction).
#
# Eviction is LRU (OrderedDict + move_to_end on get/set) so interactive paths
# (e.g. rack clicks) are not displaced by long global prefetch key streams.

import logging
import threading
from collections import OrderedDict
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Room for global-view prefetch (many rack_device keys) without evicting MRU API keys.
MAX_SIZE = 2048

_cache: OrderedDict[str, Any] = OrderedDict()
_lock = threading.RLock()


def get(key: str) -> Optional[Any]:
    """Return cached value or None if not present. Never expires."""
    with _lock:
        if key not in _cache:
            return None
        val = _cache[key]
        _cache.move_to_end(key, last=True)
        return val


def set(key: str, value: Any) -> None:
    """Store / overwrite a value in the cache."""
    with _lock:
        if key in _cache:
            _cache[key] = value
            _cache.move_to_end(key, last=True)
        else:
            while len(_cache) >= MAX_SIZE:
                evicted, _ = _cache.popitem(last=False)
                logger.debug("Cache evicted LRU key: %s", evicted)
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


def size() -> int:
    """Current entry count (cheap; avoids copying key list)."""
    with _lock:
        return len(_cache)


def stats() -> dict:
    """Return cache statistics for observability / debugging."""
    with _lock:
        return {
            "current_size": len(_cache),
            "max_size": MAX_SIZE,
            "keys": list(_cache.keys()),
        }
