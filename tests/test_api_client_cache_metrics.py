"""Item 7.1: cache observability. The api client records hit/miss/fetch counters
and fetch durations so we can see the shared cache actually working (hit rate)
and how slow the backend is on a miss — instead of guessing.
"""
from src.services import api_client as api
from src.services import cache_service


def test_metrics_count_hit_miss_and_fetch(monkeypatch):
    api.reset_cache_metrics()
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)

    # First call: miss -> fetch -> populate cache.
    api._api_cache_get_with_stale("mk", lambda: {"v": 1}, {})
    # Second call: fresh hit, no fetch.
    api._api_cache_get_with_stale("mk", lambda: {"v": 2}, {})

    m = api.get_cache_metrics()
    assert m["hits"] == 1
    assert m["misses"] == 1
    assert m["fetches"] == 1
    assert m["hit_rate"] == 0.5


def test_metrics_hit_rate_none_when_no_traffic():
    api.reset_cache_metrics()
    m = api.get_cache_metrics()
    assert m["hit_rate"] is None
    assert m["avg_fetch_seconds"] is None


def test_metrics_record_fetch_duration(monkeypatch):
    api.reset_cache_metrics()
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    api._api_cache_get_with_stale("mk2", lambda: {"v": 1}, {})
    m = api.get_cache_metrics()
    assert m["fetches"] == 1
    assert isinstance(m["avg_fetch_seconds"], float)
    assert m["avg_fetch_seconds"] >= 0.0
