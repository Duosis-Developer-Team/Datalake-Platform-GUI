"""Freshness gating (item 2, no-stale): a cached entry is served only while fresh
(age <= TTL, or TTL disabled). Stale entries are refetched, never served.

One rule reversed here. This file used to assert that an entry with no recorded
timestamp is *fresh*, justified as "warm-job entries are written directly via
cache_service.set, with no timestamp". That justification does not hold: the
warm jobs in app_background_warm call the same api_client functions user
requests do, and those stamp every write. The only genuinely unstamped `api:`
writes came from api_client itself (get_auranotify_customer_options and the
dc_avail_sla_item last-good store), and treating those as eternally fresh is
precisely what froze them — the alias editor never picked up a new AuraNotify
customer until the process restarted. Both now stamp, and an unknown age counts
as stale: one wasted refetch is cheaper than a value that never refreshes again.

See test_swr_atomic_freshness.py for why the timestamp moved inside the entry.
"""
import time

import pytest

from tests.conftest import seed_cache_entry, seed_unstamped_entry
from src.services import api_client as api
from src.services import cache_service


@pytest.fixture(autouse=True)
def clean_cache():
    cache_service.clear()
    yield
    cache_service.clear()


def test_fresh_entry_served_without_refetch(monkeypatch):
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    seed_cache_entry("fresh", {"v": 1}, age_seconds=10)  # well under TTL
    called = []

    out = api._api_cache_get_with_stale("fresh", lambda: called.append(1) or {"v": 2}, {})

    assert out == {"v": 1}
    assert called == [], "fresh entry served, no refetch"


def test_stale_entry_is_refetched_not_served(monkeypatch):
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    seed_cache_entry("stale", {"v": 1}, age_seconds=310)  # older than TTL

    out = api._api_cache_get_with_stale("stale", lambda: {"v": 2}, {})

    assert out == {"v": 2}, "stale entry must be refetched, never served stale"


def test_ttl_zero_treats_cache_as_always_fresh(monkeypatch):
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 0.0)
    seed_cache_entry("any", {"v": 1}, age_seconds=99999)
    called = []

    out = api._api_cache_get_with_stale("any", lambda: called.append(1) or {"v": 2}, {})

    assert out == {"v": 1}
    assert called == [], "TTL<=0 disables freshness expiry -> serve cached"


def test_entry_without_a_timestamp_is_refetched(monkeypatch):
    """The reversal. A bare value left by the previous release has no known age;
    serving it as fresh is what let entries freeze permanently."""
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    seed_unstamped_entry("legacy", {"v": 1})
    called = []

    out = api._api_cache_get_with_stale("legacy", lambda: called.append(1) or {"v": 2}, {})

    assert out == {"v": 2}
    assert called == [1], "unknown age must refetch, not serve forever"


def test_the_refetch_restamps_so_it_happens_once(monkeypatch):
    """The one-time cost is bounded: after the refetch the entry has an age."""
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    seed_unstamped_entry("legacy", {"v": 1})
    called = []

    api._api_cache_get_with_stale("legacy", lambda: called.append(1) or {"v": 2}, {})
    out = api._api_cache_get_with_stale("legacy", lambda: called.append(1) or {"v": 3}, {})

    assert out == {"v": 2}
    assert called == [1], "second call served from cache"


def test_leader_fetch_records_a_timestamp():
    api._api_cache_get_with_stale("missk", lambda: {"v": 9}, {})

    value, age = api._cache_load("missk")

    assert value == {"v": 9}
    assert age is not None and age < 5, "leader stamped the entry it wrote"


def test_is_fresh_helper():
    seed_cache_entry("k", {"v": 1}, age_seconds=10)
    assert api._is_fresh("k") is True

    seed_cache_entry("k", {"v": 1}, age_seconds=100000)
    assert api._is_fresh("k") is False
