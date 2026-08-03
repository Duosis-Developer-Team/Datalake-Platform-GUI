"""A bare `*` flush must never run against the GUI's Redis database.

`POST /admin/cache/refresh` flushes with `cache_flush_pattern("*")`, which is a
SCAN+DELETE over the *whole* database. That is fine now that datacenter-api owns
db 3, and catastrophic if the service is ever put back on db 0, where the GUI
keeps its `dl:fecache:*` keys: one operator refresh wipes the front end's cache
too (measured: 1390 keys -> 9).

The guard exists for that regression. It refuses loudly rather than quietly
narrowing the flush, because a silent no-op would leave the operator believing
the cache had been refreshed.
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


def test_admin_refresh_surfaces_the_guard(client, mock_db):
    """The endpoint must not swallow it: a misconfigured service should fail visibly."""
    with patch.object(cache_backend.settings, "redis_db", 0), patch(
        "app.core.cache_backend.get_redis_client", return_value=MagicMock()
    ):
        with pytest.raises(ValueError):
            client.post("/api/v1/admin/cache/refresh")

    mock_db.warm_cache.assert_not_called()
