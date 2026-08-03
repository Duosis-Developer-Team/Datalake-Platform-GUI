"""Stale-while-error: empty fetch must not mask last-good cache entries."""
import time

from tests.conftest import seed_cache_entry
from src.services import api_client as api
from src.services import cache_service


def test_empty_fetch_serves_last_good_stale(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    stale_payload = {"totals": {"vm_count": 4}, "assets": {"vm": []}}
    seed_cache_entry("k", stale_payload, age_seconds=310)

    out = api._api_cache_get_with_stale("k", lambda: {"totals": {}, "assets": {}}, {"totals": {}, "assets": {}})

    assert out == stale_payload
    assert api._cache_load("k")[0] == stale_payload


def test_empty_fetch_without_stale_returns_empty(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)

    out = api._api_cache_get_with_stale("cold", lambda: {"totals": {}, "assets": {}}, {"totals": {}, "assets": {}})

    assert out == {"totals": {}, "assets": {}}


def test_prefer_stale_over_empty_fetch_helper():
    """The stale entry's age is now an argument: preferring it over an empty
    fetch only holds while it is young enough to still mean something (see
    test_last_good_age_bound). A recent one is what this test is about."""
    recent = 60.0
    empty = {"totals": {}, "assets": {}}
    stale = {"totals": {"vm_count": 1}, "assets": {}}
    fresh = {"totals": {}, "assets": {}}
    assert api._prefer_stale_over_empty_fetch("key", stale, recent, fresh, empty) is stale
    good = {"totals": {"vm_count": 2}, "assets": {}}
    assert api._prefer_stale_over_empty_fetch("key", stale, recent, good, empty) is good
