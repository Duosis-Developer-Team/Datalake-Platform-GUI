# Module-level cache service with a pluggable storage backend.
#
# The public module functions (get/set/delete/delete_prefix/clear/cached/size/
# stats) are unchanged so existing callers keep working. Internally they now
# delegate to an active *backend*:
#   - InProcessBackend: the original per-process OrderedDict + LRU (default).
#   - RedisBackend (added later): shared across pods.
#
# Cache entries are not expired on a freshness schedule — staleness is decided by
# the caller (api_client's SWR window), not by this layer. They are still bounded:
# every Redis entry carries MAX_ENTRY_AGE_SECONDS so the server can reclaim memory
# under `volatile-lru` instead of dropping arbitrary keys under `allkeys-lru`.
#
# That distinction is the whole point. An entry written without an expiry is not
# "permanent" on a Redis with a maxmemory budget — it is merely evicted at a
# moment nobody chose. Declaring the TTL puts the bound where it can be reasoned
# about, and lets `volatile-lru` protect anything that genuinely must not vanish.
#
# InProcessBackend eviction is LRU (OrderedDict + move_to_end on get/set) so
# interactive paths (e.g. rack clicks) are not displaced by long global prefetch
# key streams.

import logging
import os
import pickle
import threading
import time
import uuid
from collections import OrderedDict
from typing import Any, Optional


def new_lock_token() -> str:
    """A value that identifies one lock holder.

    Locks are released by compare-and-delete, so the token has to be unique
    across every worker and every acquisition — otherwise a holder whose lease
    expired mid-fetch can pass the ownership check and free somebody else's lock.
    """
    return uuid.uuid4().hex

logger = logging.getLogger(__name__)

# Room for global-view prefetch (many rack_device keys) without evicting MRU API keys.
MAX_SIZE = 2048

# Expiry stamped on every Redis entry. Deliberately far above the SWR window
# (api_client._SWR_TTL_SECONDS, 300 s) — this is an eviction bound, not a
# freshness one, and an entry that expired while it was still the best value we
# had would leave the stale-over-empty fallback with nothing to serve. Bounded
# all the same: six hours without a successful refresh means the upstream is
# down, and a value that old should not be presented as data.
MAX_ENTRY_AGE_SECONDS = int(os.environ.get("CACHE_MAX_ENTRY_AGE_SECONDS", "21600") or "21600")


class InProcessBackend:
    """Per-process cache: OrderedDict with LRU eviction, guarded by an RLock.

    This is the original cache_service behavior, extracted so it can sit behind
    the same interface as a future shared (Redis) backend.
    """

    def __init__(self, max_size: int = MAX_SIZE) -> None:
        self._max_size = max_size
        self._cache: "OrderedDict[str, Any]" = OrderedDict()
        self._lock = threading.RLock()
        self._locks: dict[str, tuple[float, str]] = {}  # lock_key -> (expiry epoch, token)

    def try_acquire(self, lock_key: str, ttl: float) -> Optional[str]:
        """Atomic acquire. Returns the holder's token, or None if already held."""
        with self._lock:
            now = time.time()
            held = self._locks.get(lock_key)
            if held is not None and held[0] > now:
                return None
            token = new_lock_token()
            self._locks[lock_key] = (now + ttl, token)
            return token

    def release(self, lock_key: str, token: str) -> None:
        with self._lock:
            held = self._locks.get(lock_key)
            if held is not None and held[1] == token:
                self._locks.pop(lock_key, None)

    def is_locked(self, lock_key: str) -> bool:
        with self._lock:
            held = self._locks.get(lock_key)
            return held is not None and held[0] > time.time()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None
            val = self._cache[key]
            self._cache.move_to_end(key, last=True)
            return val

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        # ttl is accepted so both backends share one interface; this cache is
        # bounded by max_size + LRU instead, and dies with the process anyway.
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

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        # Always write an expiry: under `volatile-lru` a key with no TTL is
        # never reclaimed, so writes would start failing with OOM once the
        # budget filled. See MAX_ENTRY_AGE_SECONDS for why the default is long.
        try:
            self._r.set(self._k(key), pickle.dumps(value), ex=ttl or MAX_ENTRY_AGE_SECONDS)
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

    def try_acquire(self, lock_key: str, ttl: float) -> Optional[str]:
        """Atomic cross-pod acquire via SET NX EX. Returns the holder's token, or
        None if another holder has it.

        On a Redis error the caller becomes the leader (a token is returned) so
        it fetches rather than blocking forever on a lock nobody can grant.
        """
        token = new_lock_token()
        try:
            ok = self._r.set(
                self._k("__lock__:" + lock_key),
                token.encode(),
                nx=True,
                ex=int(max(1, ttl)),
            )
            return token if ok else None
        except Exception as exc:
            logger.warning("Redis lock acquire failed for %s: %s", lock_key, exc)
            return token

    def release(self, lock_key: str, token: str) -> None:
        """Delete the lock only if `token` still holds it.

        An unconditional DELETE is the classic broken release: a holder whose
        lease expired mid-fetch would delete whichever holder came after it,
        admitting a third fetcher to a key that is supposed to be single-flighted.

        The compare and the delete have to be one atomic step — a plain GET/DEL
        pair can be preempted between the two calls, which is the same bug with a
        smaller window. WATCH does that: if the key changes between the GET and
        the EXEC (expired, then re-acquired by someone else), EXEC aborts and we
        leave their lock alone. Chosen over EVAL because it needs no scripting
        support on the server.
        """
        redis_key = self._k("__lock__:" + lock_key)
        expected = token.encode()
        try:
            with self._r.pipeline() as pipe:
                pipe.watch(redis_key)
                if pipe.get(redis_key) != expected:
                    pipe.unwatch()
                    return  # not ours anymore; whoever holds it now gets to keep it
                pipe.multi()
                pipe.delete(redis_key)
                pipe.execute()
        except Exception as exc:
            # Includes WatchError — the key changed under us, so it is no longer
            # ours to delete and doing nothing is the correct outcome.
            logger.warning("Redis lock release failed for %s: %s", lock_key, exc)

    def is_locked(self, lock_key: str) -> bool:
        """Whether someone currently holds this lock.

        Errors report True. This answer is used to decide whether to keep
        waiting, and an unknown that read as False would release every waiter at
        once the moment Redis wobbled — the stampede the lock exists to prevent.
        """
        try:
            return bool(self._r.exists(self._k("__lock__:" + lock_key)))
        except Exception as exc:
            logger.warning("Redis lock probe failed for %s: %s", lock_key, exc)
            return True


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

# R7: if a pod boots before Redis is reachable, the import-time selection above
# falls back to the per-pod InProcessBackend. Without a retry it would stay per-pod
# for the whole process lifetime (cache "never holds" across the fleet). So when
# REDIS_URL is set but we're on in-process, cache ops retry the connection at most
# once per _REDIS_RETRY_INTERVAL_SECONDS and upgrade to the shared RedisBackend
# once Redis is reachable.
_REDIS_RETRY_INTERVAL_SECONDS = float(os.getenv("CACHE_REDIS_RETRY_INTERVAL", "30") or "30")
_last_backend_attempt: float = time.monotonic()


def _maybe_upgrade_backend() -> None:
    global _backend, _last_backend_attempt
    if not isinstance(_backend, InProcessBackend):
        return
    if not (os.environ.get("REDIS_URL") or "").strip():
        return  # no Redis configured — per-pod cache is correct here
    now = time.monotonic()
    if (now - _last_backend_attempt) < _REDIS_RETRY_INTERVAL_SECONDS:
        return
    _last_backend_attempt = now
    candidate = make_backend_from_env()
    if isinstance(candidate, RedisBackend):
        _backend = candidate
        logger.info("cache_service: upgraded to shared Redis backend on retry")


def get_backend() -> Any:
    """Return the currently active cache backend."""
    return _backend


def set_backend(backend: Any) -> None:
    """Replace the active cache backend (startup selection / tests)."""
    global _backend
    _backend = backend


def get(key: str) -> Optional[Any]:
    """Return cached value or None if not present. Never expires."""
    _maybe_upgrade_backend()
    return _backend.get(key)


def set(key: str, value: Any, ttl: Optional[int] = None) -> None:
    """Store / overwrite a value in the cache.

    ttl bounds how long Redis keeps the entry; omit it for the default
    (MAX_ENTRY_AGE_SECONDS). It is an eviction bound, not a freshness one —
    callers decide staleness themselves.
    """
    _maybe_upgrade_backend()
    _backend.set(key, value, ttl=ttl)
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


def try_acquire(lock_key: str, ttl: float) -> Optional[str]:
    """Atomic single-flight lock (shared across pods when the backend is Redis).

    Returns the holder's token — truthy, so `if try_acquire(...)` reads the same
    as it did when this returned a bool — or None when someone else holds it.
    Pass the token back to release(); it is what proves the lock is still yours.
    """
    return _backend.try_acquire(lock_key, ttl)


def release(lock_key: str, token: str) -> None:
    """Release a lock acquired via try_acquire, if `token` still holds it."""
    _backend.release(lock_key, token)


def is_locked(lock_key: str) -> bool:
    """Whether a single-flight lock is currently held (by anyone, including us)."""
    return _backend.is_locked(lock_key)


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
