"""Tests for cache stampede protection (single-flight)."""

import threading
import uuid
from unittest.mock import patch

import pytest

from app.core.cache_backend import cache_delete, cache_run_singleflight


def test_singleflight_runs_factory_once_for_concurrent_misses():
    key = f"sf:test:key:{uuid.uuid4().hex}"
    cache_delete(key)

    calls = {"n": 0}
    barrier = threading.Barrier(4)

    def factory():
        calls["n"] += 1
        return {"data": calls["n"]}

    results: list[dict] = []
    errors: list[BaseException] = []

    def worker():
        try:
            barrier.wait()
            r = cache_run_singleflight(key, factory, ttl=60)
            results.append(r)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert calls["n"] == 1
    assert len(results) == 4
    assert all(r == {"data": 1} for r in results)


def test_singleflight_returns_cached_without_factory():
    with patch("app.core.cache_backend.cache_get", return_value={"cached": True}):
        calls = {"n": 0}

        def factory():
            calls["n"] += 1
            return {"fresh": True}

        out = cache_run_singleflight("sf:test:key:2", factory, ttl=60)
    assert out == {"cached": True}
    assert calls["n"] == 0


def test_singleflight_uses_ttl_on_set():
    key = f"sf:test:key:{uuid.uuid4().hex}"
    cache_delete(key)
    with patch("app.core.cache_backend.cache_get", return_value=None), \
         patch("app.core.cache_backend.cache_set") as m:
        cache_run_singleflight(key, lambda: {"v": 1}, ttl=42)
    m.assert_called_once_with(key, {"v": 1}, ttl=42)


def test_singleflight_does_not_cache_when_factory_raises():
    from psycopg2 import OperationalError

    key = f"sf:test:key:{uuid.uuid4().hex}"
    cache_delete(key)

    def _boom():
        raise OperationalError("eof")

    with patch("app.core.cache_backend.cache_get", return_value=None), \
         patch("app.core.cache_backend.cache_set") as m:
        with pytest.raises(OperationalError):
            cache_run_singleflight(key, _boom, ttl=60)
    m.assert_not_called()
