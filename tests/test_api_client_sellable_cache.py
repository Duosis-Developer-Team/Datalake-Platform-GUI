"""Tests for sellable API client cache guard."""
from __future__ import annotations

from unittest.mock import patch

from src.services import api_client as api
from src.services import cache_service


def test_sellable_panels_have_data_detects_infra_flag():
    assert api._sellable_panels_have_data([{"has_infra_source": True, "potential_tl": 0}])
    assert not api._sellable_panels_have_data([{"has_infra_source": False, "potential_tl": 0}])


def test_api_cache_get_sellable_panels_skips_transient_zero(monkeypatch):
    cache_service.clear()
    calls = {"fetch": 0}

    def fetch():
        calls["fetch"] += 1
        return [{"panel_key": "x", "potential_tl": 0, "has_infra_source": False}]

    with patch.object(api, "get_sellable_snapshot_meta", return_value={"computed_at": None}):
        out1 = api._api_cache_get_sellable_panels("k1", fetch, "DC1", "virt_classic", None)
        out2 = api._api_cache_get_sellable_panels("k1", fetch, "DC1", "virt_classic", None)
    assert out1 == [{"panel_key": "x", "potential_tl": 0, "has_infra_source": False}]
    assert calls["fetch"] == 2
    assert cache_service.get("k1") is None
    assert out2 == [{"panel_key": "x", "potential_tl": 0, "has_infra_source": False}]


def test_api_cache_get_sellable_panels_returns_stale_on_empty_refresh(monkeypatch):
    """Empty backend response during refresh must not replace a warm LRU entry."""
    cache_service.clear()
    stale_row = [{"panel_key": "dc_cpu", "potential_tl": 1200.0, "has_infra_source": True}]
    cache_service.set("k-stale", stale_row)

    def fetch():
        return []

    with patch.object(api, "get_sellable_snapshot_meta", return_value={"computed_at": None}):
        out = api._api_cache_get_sellable_panels("k-stale", fetch, "DC13", "virt_classic", None)
    assert out == stale_row
    assert cache_service.get("k-stale") == stale_row
