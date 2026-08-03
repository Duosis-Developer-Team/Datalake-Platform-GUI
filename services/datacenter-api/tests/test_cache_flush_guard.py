"""A bare `*` flush must never run against the GUI's Redis database.

`cache_flush_pattern("*")` is a SCAN+DELETE over the *whole* database. That is
fine now that datacenter-api owns db 3, and catastrophic if the service is ever
put back on db 0, where the GUI keeps its `dl:fecache:*` keys: the flush takes
the front end's cache with it (measured: 1390 keys -> 9).

`POST /admin/cache/refresh` used to be the caller that made this reachable in
production. It no longer flushes at all — see test_admin_cache_refresh.py — so
the only bare-`*` caller left is `cache_service.clear()`, which nothing invokes
today. The guard stays because the danger is in the function, not in any
particular caller: the next one to reach for it inherits the protection.

It refuses loudly rather than quietly narrowing the flush, because a silent
no-op would leave the operator believing the cache had been refreshed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core import cache_backend


@pytest.fixture
def fake_redis():
    client = MagicMock()
    client.scan.return_value = (0, [])
    with patch("app.core.cache_backend.get_redis_client", return_value=client):
        yield client


@pytest.mark.parametrize("pattern", ["*", " * ", ""])
def test_bare_wildcard_flush_on_the_guis_db_raises(fake_redis, pattern):
    with patch.object(cache_backend.settings, "redis_db", 0):
        with pytest.raises(ValueError, match="db 0"):
            cache_backend.cache_flush_pattern(pattern)

    fake_redis.scan.assert_not_called()
    fake_redis.delete.assert_not_called()


def test_refused_flush_leaves_the_memory_cache_intact(fake_redis):
    """Refuse the whole operation — a half-done flush is worse than none."""
    cache_backend._memory_cache["dc_details:DC11"] = {"vms": 50}

    with patch.object(cache_backend.settings, "redis_db", 0):
        with pytest.raises(ValueError):
            cache_backend.cache_flush_pattern("*")

    assert "dc_details:DC11" in cache_backend._memory_cache
    cache_backend._memory_cache.pop("dc_details:DC11", None)


def test_bare_wildcard_flush_on_an_owned_db_is_allowed(fake_redis):
    """db 3 is this service's own; flushing all of it is the intended behaviour."""
    with patch.object(cache_backend.settings, "redis_db", 3):
        cache_backend.cache_flush_pattern("*")

    fake_redis.scan.assert_called()


def test_scoped_pattern_is_allowed_even_on_the_guis_db(fake_redis):
    """Only the unbounded flush is dangerous; a prefixed one cannot reach dl:fecache:*."""
    with patch.object(cache_backend.settings, "redis_db", 0):
        cache_backend.cache_flush_pattern("dc_details:*")

    fake_redis.scan.assert_called()


def test_cache_service_clear_is_covered_by_the_guard(fake_redis):
    """clear() is the remaining bare-`*` caller, so it must inherit the refusal.

    It has no callers today. That is exactly why it is worth pinning: an unused
    wholesale flush is the kind of thing someone wires up later without noticing
    which database it lands in.
    """
    from app.services import cache_service

    with patch.object(cache_backend.settings, "redis_db", 0):
        with pytest.raises(ValueError, match="db 0"):
            cache_service.clear()

    fake_redis.scan.assert_not_called()
    fake_redis.delete.assert_not_called()
