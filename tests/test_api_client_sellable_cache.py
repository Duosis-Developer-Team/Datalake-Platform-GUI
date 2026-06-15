"""Sellable API client cache (Sprint 4: negative-result caching + SWR).

Empty results ARE cached now (so DCs without a snapshot don't re-pay the CRM call
every build); transient empties self-heal via the SWR background refresh after TTL.
The separate get_sellable_snapshot_meta probe was removed.
"""
from unittest.mock import patch
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
    assert cache_service.get("kp") == []


def test_panels_data_cached_and_stamped(monkeypatch):
    cache_service.clear()
    rows = [{"panel_key": "x", "potential_tl": 1200.0, "has_infra_source": True}]
    out = api._api_cache_get_sellable_panels("kd", lambda: rows, "DC13", "virt_classic", None)
    assert out == rows
    assert cache_service.get("kd") == rows
    assert "kd" in api._fetched_at  # stamped for SWR


def test_stale_panels_schedule_swr_refresh(monkeypatch):
    import time as _t
    cache_service.clear()
    monkeypatch.setattr(api, "_SWR_TTL_SECONDS", 300.0)
    cache_service.set("ks", [{"panel_key": "x"}])
    api._fetched_at["ks"] = _t.monotonic() - 999  # stale
    scheduled = []
    monkeypatch.setattr(api, "_schedule_swr_refresh", lambda k, f: scheduled.append(k))
    out = api._api_cache_get_sellable_panels("ks", lambda: [], "DC13", "virt_classic", None)
    assert out == [{"panel_key": "x"}]  # served stale immediately
    assert scheduled == ["ks"]


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
    assert cache_service.get("ksum") == {}
