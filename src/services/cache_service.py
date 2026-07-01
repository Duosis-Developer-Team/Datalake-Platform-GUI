# Module-level cache service with a pluggable storage backend.
#
# The public module functions (get/set/delete/delete_prefix/clear/cached/size/
# stats) are unchanged so existing callers keep working. Internally they now
# delegate to an active *backend*:
#   - InProcessBackend: the original per-process OrderedDict + LRU (default).
#   - RedisBackend (added later): shared across pods.
#
# Cache entries never disappear until explicitly overwritten by fresh data.
# TTL is only used as a staleness hint (not for eviction). InProcessBackend
# eviction is LRU (OrderedDict + move_to_end on get/set) so interactive paths
# (e.g. rack clicks) are not displaced by long global prefetch key streams.

import logging
import threading
from collections import OrderedDict
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Room for global-view prefetch (many rack_device keys) without evicting MRU API keys.
MAX_SIZE = 2048


class InProcessBackend:
    """Per-process cache: OrderedDict with LRU eviction, guarded by an RLock.

    This is the original cache_service behavior, extracted so it can sit behind
    the same interface as a future shared (Redis) backend.
    """

    def __init__(self, max_size: int = MAX_SIZE) -> None:
        self._max_size = max_size
        self._cache: "OrderedDict[str, Any]" = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None
            val = self._cache[key]
            self._cache.move_to_end(key, last=True)
            return val

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._cache:
                self._cache[key] = value
                self._cache.move_to_end(key, last=True)
            else:
                while len(self._cache) >= self._max_size:
                    evicted, _ = self._cache.popitem(last=False)
                    logger.debug("Cache evicted LRU key: %s", evicted)
                self._cache[key] = value

    def delete(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def delete_prefix(self, prefix: str) -> int:
        with self._lock:
            to_remove = [k for k in self._cache if isinstance(k, str) and k.startswith(prefix)]
            for k in to_remove:
                self._cache.pop(k, None)
            return len(to_remove)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._cache)

    def stats(self) -> dict:
        with self._lock:
            return {
                "backend": "in_process",
                "current_size": len(self._cache),
                "max_size": self._max_size,
                "keys": list(self._cache.keys()),
            }


# The active backend. Swapped at startup (item 1.3) when REDIS_URL is set, and
# swappable in tests via set_backend().
_backend: Any = InProcessBackend(MAX_SIZE)


def get_backend() -> Any:
    """Return the currently active cache backend."""
    return _backend


def set_backend(backend: Any) -> None:
    """Replace the active cache backend (startup selection / tests)."""
    global _backend
    _backend = backend


def get(key: str) -> Optional[Any]:
    """Return cached value or None if not present. Never expires."""
    return _backend.get(key)


def set(key: str, value: Any) -> None:
    """Store / overwrite a value in the cache."""
    _backend.set(key, value)
    logger.debug("Cache SET: %s", key)


def delete(key: str) -> None:
    """Explicitly evict a single key."""
    _backend.delete(key)
    logger.debug("Cache DELETE: %s", key)


def delete_prefix(prefix: str) -> None:
    """Remove all keys that start with prefix (used after raw dataset refresh)."""
    if not prefix:
        return
    n = _backend.delete_prefix(prefix)
    if n:
        logger.debug("Cache DELETE_PREFIX %s (%d keys)", prefix, n)


def clear() -> None:
    """Flush the entire cache (e.g. on config reload or forced refresh)."""
    _backend.clear()
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
    return _backend.size()


def stats() -> dict:
    """Return cache statistics for observability / debugging."""
    return _backend.stats()
