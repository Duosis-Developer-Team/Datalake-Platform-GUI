"""Tests for Data Centers virt sellable loading helpers."""
from __future__ import annotations

from unittest.mock import patch

from src.utils import datacenters_virt_sellable as dvs


def test_resolve_virt_sellable_loading_when_cache_empty(monkeypatch):
    monkeypatch.setattr(dvs, "_VIRT_TL_CACHE", {})
    monkeypatch.setattr(dvs, "_VIRT_CACHE_TR_KEY", "")
    monkeypatch.setattr(dvs, "_VIRT_CACHE_WARMING", False)

    with patch.object(dvs, "start_virt_cache_warm", return_value=True):
        state = dvs.resolve_virt_sellable_for_dcs(["DC1", "DC2"], {"preset": "30d"})
    assert state["loading"] is True
    assert state["virt_tl_by_dc"]["DC1"] == 0.0


def test_resolve_virt_sellable_complete_when_cache_warm(monkeypatch):
    monkeypatch.setattr(dvs, "_VIRT_TL_CACHE", {"DC1": 100.0, "DC2": 200.0})
    monkeypatch.setattr(dvs, "_VIRT_CACHE_TR_KEY", "30d||")
    monkeypatch.setattr(dvs, "_VIRT_CACHE_WARMING", False)

    state = dvs.resolve_virt_sellable_for_dcs(["DC1", "DC2"], {"preset": "30d"})
    assert state["loading"] is False
    assert state["total_potential_tl"] == 300.0
