"""Item 2.2: no-stale read semantics.

A cached entry is served only while fresh (age <= TTL). A stale entry is NOT
served — it is refetched and the fresh value returned. The stale value survives
only as last-good if the refetch hard-fails (Seçenek A: last-good + as-of stamp).
"""
import time

import httpx

from src.services import api_client as api
from src.services import cache_service


def test_stale_entry_is_refetched_not_served(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    cache_service.set("k", {"v": 1})
    cache_service.set(api._fetched_ts_key("k"), time.time() - 310)  # stale
    out = api._api_cache_get_with_stale("k", lambda: {"v": 2}, {})
    assert out == {"v": 2}, "stale entry must be refetched fresh, never served stale"


def test_fresh_entry_served_without_refetch(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    cache_service.set("k", {"v": 1})
    cache_service.set(api._fetched_ts_key("k"), time.time() - 10)  # fresh
    called = []

    def fetch():
        called.append(1)
        return {"v": 2}

    out = api._api_cache_get_with_stale("k", fetch, {})
    assert out == {"v": 1}
    assert called == [], "fresh entry must be served without refetch"


def test_stale_served_as_last_good_only_on_hard_failure(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    cache_service.set("k", {"v": 1})
    cache_service.set(api._fetched_ts_key("k"), time.time() - 310)  # stale

    def boom():
        raise httpx.ConnectError("backend down")

    out = api._api_cache_get_with_stale("k", boom, {})
    assert out == {"v": 1}, "on hard fetch failure, serve last-good (stale) fallback"


def test_sellable_panels_stale_is_refetched(monkeypatch):
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    cache_service.set("kp", [{"panel_key": "old"}])
    cache_service.set(api._fetched_ts_key("kp"), time.time() - 999)  # stale
    out = api._api_cache_get_sellable_panels(
        "kp", lambda: [{"panel_key": "new"}], "DC13", "virt_classic", None
    )
    assert out == [{"panel_key": "new"}], "stale sellable panels must be refetched"
