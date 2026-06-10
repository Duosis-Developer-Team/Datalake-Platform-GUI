"""Tests for HMDL API client fallbacks (no Dash runtime required)."""

from src.services.api_client import _EMPTY_HMDL_TOPOLOGY, _EMPTY_HMDL_SUMMARY


def test_empty_hmdl_api_fallback_shapes():
    assert _EMPTY_HMDL_TOPOLOGY["hub_dc"] == "DC13"
    assert _EMPTY_HMDL_SUMMARY["synced_dc_count"] == 0
    assert "nodes" in _EMPTY_HMDL_TOPOLOGY
