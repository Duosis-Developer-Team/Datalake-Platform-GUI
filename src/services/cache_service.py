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
import os
import pickle
import threading
import time
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
        self._locks: dict[str, float] = {}  # lock_key -> expiry epoch

    def try_acquire(self, lock_key: str, ttl: float) -> bool:
        """Atomic acquire: True if the lock was free (per-process), else False."""
        with self._lock:
            now = time.time()
            exp = self._locks.get(lock_key)
            if exp is not None and exp > now:
                return False
            self._locks[lock_key] = now + ttl
            return True

    def release(self, lock_key: str) -> None:
        with self._lock:
            self._locks.pop(lock_key, None)

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


class RedisBackend:
    """Shared cache backed by Redis, so all frontend pods hit one warm cache
    instead of per-pod islands.

    Values are pickled (faithful round-trip of arbitrary cached Python objects —
    unlike JSON, which coerces tuples to lists and dict int-keys to strings).
    The client must be a *binary* redis client (decode_responses=False).

    Every operation degrades gracefully: if Redis is unreachable, reads return a
    miss and writes are dropped (logged), so a Redis outage can only slow the
    app down, never crash it.
    """

    def __init__(self, client: Any, namespace: str = "dl:fecache:") -> None:
        self._r = client
        self._ns = namespace

    def _k(self, key: str) -> str:
        return self._ns + key

    def get(self, key: str) -> Optional[Any]:
        try:
            raw = self._r.get(self._k(key))
        except Exception as exc:
            logger.warning("Redis cache GET failed for %s: %s", key, exc)
            return None
        if raw is None:
            return None
        try:
            return pickle.loads(raw)
        except Exception as exc:
            logger.warning("Redis cache decode failed for %s: %s", key, exc)
            return None

    def set(self, key: str, value: Any) -> None:
        try:
            self._r.set(self._k(key), pickle.dumps(value))
        except Exception as exc:
            logger.warning("Redis cache SET failed for %s: %s", key, exc)

    def delete(self, key: str) -> None:
        try:
            self._r.delete(self._k(key))
        except Exception as exc:
            logger.warning("Redis cache DELETE failed for %s: %s", key, exc)

    def delete_prefix(self, prefix: str) -> int:
        count = 0
        try:
            for k in self._r.scan_iter(match=self._k(prefix) + "*"):
                self._r.delete(k)
                count += 1
        except Exception as exc:
            logger.warning("Redis cache DELETE_PREFIX failed for %s: %s", prefix, exc)
        return count

    def clear(self) -> None:
        try:
            for k in self._r.scan_iter(match=self._ns + "*"):
                self._r.delete(k)
        except Exception as exc:
            logger.warning("Redis cache CLEAR failed: %s", exc)

    def size(self) -> int:
        try:
            return sum(1 for _ in self._r.scan_iter(match=self._ns + "*"))
        except Exception as exc:
            logger.warning("Redis cache SIZE failed: %s", exc)
            return 0

    def stats(self) -> dict:
        return {"backend": "redis", "namespace": self._ns, "current_size": self.size()}

    def try_acquire(self, lock_key: str, ttl: float) -> bool:
        """Atomic cross-pod acquire via SET NX EX. On a Redis error, act as the
        leader (return True) so the caller fetches rather than blocking forever."""
        try:
            return bool(self._r.set(self._k("__lock__:" + lock_key), b"1", nx=True, ex=int(max(1, ttl))))
        except Exception as exc:
            logger.warning("Redis lock acquire failed for %s: %s", lock_key, exc)
            return True

    def release(self, lock_key: str) -> None:
        try:
            self._r.delete(self._k("__lock__:" + lock_key))
        except Exception as exc:
            logger.warning("Redis lock release failed for %s: %s", lock_key, exc)


def make_backend_from_env(env: Optional[dict] = None) -> Any:
    """Pick the cache backend from the environment.

    REDIS_URL set and reachable -> shared RedisBackend (binary client for
    pickle). Otherwise (unset, empty, or Redis unreachable) -> per-process
    InProcessBackend. A bad REDIS_URL degrades to per-pod cache, never crashes.
    """
    env = env if env is not None else os.environ
    url = (env.get("REDIS_URL") or "").strip()
    if not url:
        return InProcessBackend(MAX_SIZE)
    try:
        import redis

        client = redis.Redis.from_url(url, decode_responses=False)
        client.ping()
        logger.info("cache_service: using shared Redis backend (REDIS_URL set)")
        return RedisBackend(client)
    except Exception as exc:
        logger.warning(
            "cache_service: REDIS_URL set but Redis unavailable (%s); "
            "falling back to in-process cache",
            exc,
        )
        return InProcessBackend(MAX_SIZE)


# The active backend, selected from the environment at import. Swappable in
# tests via set_backend().
_backend: Any = make_backend_from_env()


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


def try_acquire(lock_key: str, ttl: float) -> bool:
    """Atomic single-flight lock (shared across pods when the backend is Redis).
    True => caller is the leader and should fetch; False => someone else holds it."""
    return _backend.try_acquire(lock_key, ttl)


def release(lock_key: str) -> None:
    """Release a lock acquired via try_acquire."""
    _backend.release(lock_key)


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
