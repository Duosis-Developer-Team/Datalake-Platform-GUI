"""Freshness gating (item 2, no-stale): a cached entry is served only while fresh
(age <= TTL, TTL disabled, or warm-written with no timestamp). Stale entries are
refetched, never served. Replaces the old stale-while-revalidate behavior.
"""
import time

from src.services import api_client as api
from src.services import cache_service


def _set_with_age(key, value, age_seconds):
    cache_service.set(key, value)
    cache_service.set(api._fetched_ts_key(key), time.time() - age_seconds)


def test_fresh_entry_served_without_refetch(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    _set_with_age("fresh", {"v": 1}, age_seconds=10)  # well under TTL
    called = []
    out = api._api_cache_get_with_stale("fresh", lambda: called.append(1) or {"v": 2}, {})
    assert out == {"v": 1}
    assert called == [], "fresh entry served, no refetch"


def test_stale_entry_is_refetched_not_served(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    _set_with_age("stale", {"v": 1}, age_seconds=310)  # older than TTL
    out = api._api_cache_get_with_stale("stale", lambda: {"v": 2}, {})
    assert out == {"v": 2}, "stale entry must be refetched, never served stale"


def test_ttl_zero_treats_cache_as_always_fresh(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 0.0)
    _set_with_age("any", {"v": 1}, age_seconds=99999)
    called = []
    out = api._api_cache_get_with_stale("any", lambda: called.append(1) or {"v": 2}, {})
    assert out == {"v": 1}
    assert called == [], "TTL<=0 disables freshness expiry -> serve cached"


def test_warm_written_entry_without_timestamp_is_fresh(monkeypatch):
    """Warm-job entries (set directly, no timestamp) are treated as fresh and served."""
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    cache_service.set("warm", {"v": 1})  # no freshness timestamp
    called = []
    out = api._api_cache_get_with_stale("warm", lambda: called.append(1) or {"v": 2}, {})
    assert out == {"v": 1}
    assert called == []


def test_leader_fetch_records_timestamp(monkeypatch):
    cache_service.clear()
    api._api_cache_get_with_stale("missk", lambda: {"v": 9}, {})
    assert cache_service.get(api._fetched_ts_key("missk")) is not None  # leader stamped it


def test_is_fresh_helper():
    cache_service.clear()
    cache_service.set(api._fetched_ts_key("k"), time.time() - 10)
    assert api._is_fresh("k") is True
    cache_service.set(api._fetched_ts_key("k"), time.time() - 100000)
    assert api._is_fresh("k") is False
