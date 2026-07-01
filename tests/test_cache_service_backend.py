"""Tests for the cache_service backend abstraction (item 1.1).

cache_service is being refactored from a bare module-level OrderedDict into a
pluggable backend: an `InProcessBackend` (the existing behavior) plus, later, a
Redis backend. These tests pin the InProcessBackend semantics and verify the
module-level functions delegate to whatever backend is active, so no caller has
to change.
"""
import importlib

import pytest

cache_service = importlib.import_module("src.services.cache_service")


@pytest.fixture(autouse=True)
def _restore_backend():
    """Each test runs against a clean, isolated backend and restores the default."""
    original = cache_service.get_backend()
    yield
    cache_service.set_backend(original)
    cache_service.clear()


def test_inprocess_backend_set_and_get():
    b = cache_service.InProcessBackend(max_size=8)
    b.set("k", {"v": 1})
    assert b.get("k") == {"v": 1}


def test_inprocess_backend_missing_key_returns_none():
    b = cache_service.InProcessBackend(max_size=8)
    assert b.get("nope") is None


def test_inprocess_backend_delete():
    b = cache_service.InProcessBackend(max_size=8)
    b.set("k", 1)
    b.delete("k")
    assert b.get("k") is None


def test_inprocess_backend_delete_prefix():
    b = cache_service.InProcessBackend(max_size=8)
    b.set("api:a:1", 1)
    b.set("api:a:2", 2)
    b.set("api:b:1", 3)
    b.delete_prefix("api:a:")
    assert b.get("api:a:1") is None
    assert b.get("api:a:2") is None
    assert b.get("api:b:1") == 3


def test_inprocess_backend_lru_eviction():
    b = cache_service.InProcessBackend(max_size=2)
    b.set("a", 1)
    b.set("b", 2)
    b.get("a")  # a is now most-recently-used
    b.set("c", 3)  # should evict least-recently-used = b
    assert b.get("b") is None
    assert b.get("a") == 1
    assert b.get("c") == 3


def test_inprocess_backend_size_and_clear():
    b = cache_service.InProcessBackend(max_size=8)
    b.set("a", 1)
    b.set("b", 2)
    assert b.size() == 2
    b.clear()
    assert b.size() == 0


def test_module_functions_delegate_to_active_backend():
    b = cache_service.InProcessBackend(max_size=8)
    cache_service.set_backend(b)
    cache_service.set("k", 42)
    # Written through the module API, readable directly on the backend.
    assert b.get("k") == 42
    # And readable back through the module API.
    assert cache_service.get("k") == 42


def test_default_backend_is_inprocess():
    assert isinstance(cache_service.get_backend(), cache_service.InProcessBackend)
