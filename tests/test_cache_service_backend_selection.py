"""Tests for env-driven backend selection (item 1.3).

At startup cache_service picks a backend from REDIS_URL: shared Redis when set
and reachable, otherwise the in-process backend. A set-but-unreachable Redis
must fall back to in-process (same philosophy as permission_service) so a bad
REDIS_URL degrades to per-pod cache instead of crashing the app.
"""
import importlib

import pytest

fakeredis = pytest.importorskip("fakeredis")
cache_service = importlib.import_module("src.services.cache_service")


def test_no_redis_url_returns_inprocess():
    b = cache_service.make_backend_from_env({})
    assert isinstance(b, cache_service.InProcessBackend)


def test_empty_redis_url_returns_inprocess():
    b = cache_service.make_backend_from_env({"REDIS_URL": "  "})
    assert isinstance(b, cache_service.InProcessBackend)


def test_redis_url_set_and_reachable_returns_redis(monkeypatch):
    import redis

    fake = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(redis.Redis, "from_url", lambda *a, **k: fake)
    b = cache_service.make_backend_from_env({"REDIS_URL": "redis://x:6379/0"})
    assert isinstance(b, cache_service.RedisBackend)


def test_redis_url_set_but_unreachable_falls_back_to_inprocess(monkeypatch):
    import redis

    class PingFails:
        def ping(self):
            raise ConnectionError("redis down")

    monkeypatch.setattr(redis.Redis, "from_url", lambda *a, **k: PingFails())
    b = cache_service.make_backend_from_env({"REDIS_URL": "redis://x:6379/0"})
    assert isinstance(b, cache_service.InProcessBackend)
