"""Sellable API client cache (Sprint 4: negative-result caching + SWR).

Empty results ARE cached now (so DCs without a snapshot don't re-pay the CRM call
every build); transient empties self-heal via the SWR background refresh after TTL.
The separate get_sellable_snapshot_meta probe was removed.
"""
from unittest.mock import patch
from tests.conftest import seed_cache_entry
from src.services import api_client as api
from src.services import cache_service


def test_sellable_panels_have_data_detects_infra_flag():
    assert api._sellable_panels_have_data([{"has_infra_source": True, "potential_tl": 0}])
    assert not api._sellable_panels_have_data([{"has_infra_source": False, "potential_tl": 0}])


def test_empty_panels_are_cached_and_meta_not_probed(monkeypatch):
    cache_service.clear()
    calls = {"fetch": 0}
    def fetch():
        calls["fetch"] += 1
        return []  # DC with no snapshot -> empty
    with patch.object(api, "get_sellable_snapshot_meta") as meta:
        out1 = api._api_cache_get_sellable_panels("kp", fetch, "DC13", "virt_classic", None)
        out2 = api._api_cache_get_sellable_panels("kp", fetch, "DC13", "virt_classic", None)
    assert out1 == [] and out2 == []
    assert calls["fetch"] == 1, "empty result must be cached -> fetch only once"
    assert meta.call_count == 0, "snapshot-meta probe must be gone"
    assert api._cache_load("kp")[0] == []


def test_panels_data_cached_and_stamped(monkeypatch):
    cache_service.clear()
    rows = [{"panel_key": "x", "potential_tl": 1200.0, "has_infra_source": True}]
    out = api._api_cache_get_sellable_panels("kd", lambda: rows, "DC13", "virt_classic", None)
    assert out == rows
    value, age = api._cache_load("kd")
    assert value == rows
    assert age is not None, "stamped for SWR, in the same entry as the value"


def test_stale_panels_are_refetched_not_served(monkeypatch):
    import time as _t
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    seed_cache_entry("ks", [{"panel_key": "old"}], age_seconds=999)
    out = api._api_cache_get_sellable_panels(
        "ks", lambda: [{"panel_key": "fresh"}], "DC13", "virt_classic", None
    )
    assert out == [{"panel_key": "fresh"}], "stale panels refetched, never served stale"


def test_empty_summary_is_cached(monkeypatch):
    cache_service.clear()
    calls = {"fetch": 0}
    def fetch():
        calls["fetch"] += 1
        return {}
    with patch.object(api, "get_sellable_snapshot_meta") as meta:
        api._api_cache_get_sellable_summary("ksum", fetch, "DC13")
        api._api_cache_get_sellable_summary("ksum", fetch, "DC13")
    assert calls["fetch"] == 1
    assert meta.call_count == 0
    assert api._cache_load("ksum")[0] == {}
