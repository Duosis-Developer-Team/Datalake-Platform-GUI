"""Tests for Data Centers virt sellable loading helpers."""
from __future__ import annotations

from unittest.mock import patch

from src.utils import datacenters_virt_sellable as dvs


def test_resolve_virt_sellable_loading_when_cache_empty(monkeypatch):
    monkeypatch.setattr(dvs, "_VIRT_TL_CACHE", {})
    monkeypatch.setattr(dvs, "_VIRT_CACHE_TR_KEY", "")
    monkeypatch.setattr(dvs, "_VIRT_CACHE_WARMING", False)

    with patch.object(dvs, "_seed_from_api_cache", return_value={}), patch.object(
        dvs, "start_virt_cache_warm", return_value=True
    ):
        state = dvs.resolve_virt_sellable_for_dcs(["DC1", "DC2"], {"preset": "30d"})
    assert state["loading"] is True
    assert state["virt_tl_by_dc"]["DC1"] == 0.0


def test_resolve_virt_sellable_per_dc_loading(monkeypatch):
    monkeypatch.setattr(dvs, "_VIRT_TL_CACHE", {"DC1": 100.0})
    monkeypatch.setattr(dvs, "_VIRT_CACHE_TR_KEY", "30d||")
    monkeypatch.setattr(dvs, "_VIRT_CACHE_WARMING", True)

    with patch.object(dvs, "_seed_from_api_cache", return_value={}):
        state = dvs.resolve_virt_sellable_for_dcs(["DC1", "DC2"], {"preset": "30d"})
    assert state["loading_by_dc"]["DC1"] is False
    assert state["loading_by_dc"]["DC2"] is True


def test_resolve_virt_sellable_complete_when_cache_warm(monkeypatch):
    monkeypatch.setattr(dvs, "_VIRT_TL_CACHE", {"DC1": 100.0, "DC2": 200.0})
    monkeypatch.setattr(dvs, "_VIRT_CACHE_TR_KEY", "30d||")
    monkeypatch.setattr(dvs, "_VIRT_CACHE_WARMING", False)

    with patch.object(dvs, "_seed_from_api_cache", return_value={}):
        state = dvs.resolve_virt_sellable_for_dcs(["DC1", "DC2"], {"preset": "30d"})
    assert state["loading"] is False
    assert state["total_potential_tl"] == 300.0


def test_resolve_virt_sellable_serves_stale_while_warming(monkeypatch):
    """While background warm runs, last published values stay visible (not zeroed)."""
    monkeypatch.setattr(dvs, "_VIRT_TL_CACHE", {"DC1": 150.0, "DC2": 250.0})
    monkeypatch.setattr(dvs, "_VIRT_CACHE_TR_KEY", "old_range||")
    monkeypatch.setattr(dvs, "_VIRT_CACHE_WARMING", True)

    with patch.object(dvs, "_seed_from_api_cache", return_value={}):
        state = dvs.resolve_virt_sellable_for_dcs(["DC1", "DC2"], {"preset": "7d"})
    assert state["loading"] is False
    assert state["total_potential_tl"] == 400.0
    assert state["virt_tl_by_dc"]["DC1"] == 150.0


def test_publish_virt_cache_does_not_replace_on_empty():
    dvs._VIRT_TL_CACHE.clear()
    dvs._VIRT_TL_CACHE["DC1"] = 99.0
    dvs._publish_virt_cache({}, ["DC1", "DC2"], "new||")
    assert dvs._VIRT_TL_CACHE == {"DC1": 99.0}


def test_publish_virt_cache_merges_partial_warm():
    dvs._VIRT_TL_CACHE.clear()
    dvs._VIRT_TL_CACHE["DC1"] = 50.0
    dvs._publish_virt_cache({"DC2": 80.0}, ["DC1", "DC2"], "tr||")
    assert dvs._VIRT_TL_CACHE["DC1"] == 50.0
    assert dvs._VIRT_TL_CACHE["DC2"] == 80.0
    assert dvs._VIRT_CACHE_TR_KEY != "tr||"  # incomplete — tr_key not advanced


def test_virt_sellable_tl_for_dc_uses_by_panel_path():
    """List page virt TL must match DC detail Virt tab (by-panel, not summary rollup)."""
    panels = [
        {"potential_tl": 1_000_000.0},
        {"potential_tl": 750_000.0},
    ]
    with patch(
        "src.utils.datacenters_virt_sellable.collect_virt_sellable_panels",
        return_value=panels,
    ) as mock_collect:
        tl = dvs._virt_sellable_tl_for_dc("DC11", family_workers=2)
    assert tl == 1_750_000.0
    mock_collect.assert_called_once_with("DC11", None, None, max_family_workers=2)


def test_virt_sellable_tl_for_dc_does_not_use_summary_light():
    """Regression: list warm path must not call get_sellable_summary_light."""
    with patch(
        "src.utils.datacenters_virt_sellable.collect_virt_sellable_panels",
        return_value=[{"potential_tl": 100.0}],
    ), patch(
        "src.services.api_client.get_sellable_summary_light",
    ) as mock_summary:
        dvs._virt_sellable_tl_for_dc("DC11", family_workers=1)
    mock_summary.assert_not_called()


def test_seed_from_api_cache_uses_by_panel_path():
    with patch.object(dvs, "_virt_sellable_tl_for_dc", side_effect=[100.0, 200.0]) as mock_compute:
        seeded = dvs._seed_from_api_cache(["DC1", "DC2"], family_workers=1)
    assert seeded == {"DC1": 100.0, "DC2": 200.0}
    assert mock_compute.call_count == 2
