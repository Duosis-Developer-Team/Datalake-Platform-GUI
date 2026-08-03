"""Tests for POST /api/v1/admin/cache/refresh.

The refresh used to flush before warming. That was safe for the data — every
write here goes through cache_set, which always applies settings.cache_ttl_seconds
(1200 s), so the flush removed nothing that would not have expired within twenty
minutes anyway. What it did create was a service-wide cold window: between the
DELETE and the end of a warm that takes minutes, every read missed and every
caller waited on the database. Callers that gave up saw empty panels where a
value had been a second earlier.

Warming over the top has the same end state and no window — the previous values
stay readable until their replacements land, key by key. customer-api and
crm-engine already refresh this way.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_admin_cache_refresh_warms_every_range(client: TestClient, mock_db):
    r = client.post("/api/v1/admin/cache/refresh")

    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    assert "cache" in body
    mock_db.warm_cache.assert_called_once()
    mock_db.warm_additional_ranges.assert_called_once()
    mock_db.warm_s3_cache.assert_called_once()
    mock_db.warm_network_cache.assert_called_once()


def test_admin_cache_refresh_deletes_nothing(client: TestClient, mock_db):
    """No cold window: the refresh overwrites, it does not empty first.

    Asserts against the Redis client rather than patching cache_flush_pattern.
    admin_cache binds its imports by name, so patching the function in the module
    that defines it never intercepts the call — that test passes whether or not
    the flush is there. What SCAN and DELETE were issued is not forgeable.
    """
    from app.core import cache_backend

    sentinel = "dc_details:__refresh_sentinel__"
    with patch("app.core.cache_backend.get_redis_client") as get_client:
        redis = get_client.return_value
        cache_backend._memory_cache[sentinel] = {"kept": True}
        try:
            r = client.post("/api/v1/admin/cache/refresh")

            assert r.status_code == 200
            redis.scan.assert_not_called()
            redis.delete.assert_not_called()
            # The flush also emptied the in-process cache; that must survive too.
            assert cache_backend._memory_cache.get(sentinel) == {"kept": True}
        finally:
            cache_backend._memory_cache.pop(sentinel, None)


def test_refresh_module_does_not_import_the_flush(client: TestClient):
    """Belt and braces: the endpoint cannot regress into flushing by accident.

    Patching the name only proves this call path does not use it; asserting the
    module never bound it proves no future edit can reach it without a new import
    that a reviewer would see.
    """
    from app.routers import admin_cache

    assert not hasattr(admin_cache, "cache_flush_pattern")
