"""Stale-while-error: empty fetch must not mask last-good cache entries."""
import time

from src.services import api_client as api
from src.services import cache_service


def test_empty_fetch_serves_last_good_stale(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    stale_payload = {"totals": {"vm_count": 4}, "assets": {"vm": []}}
    cache_service.set("k", stale_payload)
    cache_service.set(api._fetched_ts_key("k"), time.time() - 310)  # stale

    out = api._api_cache_get_with_stale("k", lambda: {"totals": {}, "assets": {}}, {"totals": {}, "assets": {}})

    assert out == stale_payload
    assert cache_service.get("k") == stale_payload


def test_empty_fetch_without_stale_returns_empty(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)

    out = api._api_cache_get_with_stale("cold", lambda: {"totals": {}, "assets": {}}, {"totals": {}, "assets": {}})

    assert out == {"totals": {}, "assets": {}}


def test_prefer_stale_over_empty_fetch_helper():
    empty = {"totals": {}, "assets": {}}
    stale = {"totals": {"vm_count": 1}, "assets": {}}
    fresh = {"totals": {}, "assets": {}}
    assert api._prefer_stale_over_empty_fetch("key", stale, fresh, empty) is stale
    good = {"totals": {"vm_count": 2}, "assets": {}}
    assert api._prefer_stale_over_empty_fetch("key", stale, good, empty) is good
