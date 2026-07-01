"""Tests for the shared Redis cache backend (item 1.2).

RedisBackend makes the frontend data cache shared across the 2-6 pods instead
of per-pod. It must faithfully round-trip arbitrary cached Python values, scope
all keys under a namespace, and degrade gracefully (return a miss, never crash)
when Redis is unreachable — so a Redis outage can only slow the app, never break
it.
"""
import importlib

import pytest

fakeredis = pytest.importorskip("fakeredis")
cache_service = importlib.import_module("src.services.cache_service")


@pytest.fixture
def client():
    # Binary client (decode_responses=False) so pickled bytes round-trip intact.
    return fakeredis.FakeStrictRedis()


@pytest.fixture
def backend(client):
    return cache_service.RedisBackend(client, namespace="dl:fecache:")


def test_set_and_get_roundtrip(backend):
    backend.set("k", {"a": 1, "b": [1, 2, 3]})
    assert backend.get("k") == {"a": 1, "b": [1, 2, 3]}


def test_missing_key_returns_none(backend):
    assert backend.get("nope") is None


def test_roundtrip_is_faithful_for_tuples(backend):
    # pickle preserves tuple identity; JSON would silently coerce to list.
    backend.set("t", ("x", 2, (3, 4)))
    assert backend.get("t") == ("x", 2, (3, 4))


def test_keys_are_namespaced(backend, client):
    backend.set("k", 1)
    assert client.exists("dl:fecache:k")
    assert not client.exists("k")


def test_delete(backend):
    backend.set("k", 1)
    backend.delete("k")
    assert backend.get("k") is None


def test_delete_prefix_removes_only_matching(backend):
    backend.set("api:a:1", 1)
    backend.set("api:a:2", 2)
    backend.set("api:b:1", 3)
    backend.delete_prefix("api:a:")
    assert backend.get("api:a:1") is None
    assert backend.get("api:a:2") is None
    assert backend.get("api:b:1") == 3


def test_clear_only_touches_namespace(backend, client):
    backend.set("k", 1)
    client.set("someone-elses-key", b"keep")  # not under our namespace
    backend.clear()
    assert backend.get("k") is None
    assert client.get("someone-elses-key") == b"keep"


def test_size_counts_namespaced_keys(backend):
    backend.set("a", 1)
    backend.set("b", 2)
    assert backend.size() == 2


def test_get_degrades_gracefully_on_redis_error():
    class BrokenClient:
        def get(self, *a, **k):
            raise ConnectionError("redis down")

    backend = cache_service.RedisBackend(BrokenClient(), namespace="dl:fecache:")
    # A miss, not an exception — the app then fetches fresh from source.
    assert backend.get("k") is None


def test_set_degrades_gracefully_on_redis_error():
    class BrokenClient:
        def set(self, *a, **k):
            raise ConnectionError("redis down")

    backend = cache_service.RedisBackend(BrokenClient(), namespace="dl:fecache:")
    backend.set("k", 1)  # must not raise
