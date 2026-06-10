"""HMDL topology UI helpers and empty-state contracts."""

from src.components.hmdl_topology import build_topology_legend_only
from src.services.api_client import _EMPTY_HMDL_SUMMARY, _EMPTY_HMDL_TOPOLOGY
from src.utils.hmdl_sync_ui import (
    environment_status_badge,
    node_status_badge,
    proxy_config_badge,
    sync_status_badge,
)


def test_empty_topology_contract():
    assert _EMPTY_HMDL_TOPOLOGY["hub_dc"] == "DC13"
    assert _EMPTY_HMDL_SUMMARY["synced_dc_count"] == 0
    assert "nodes" in _EMPTY_HMDL_TOPOLOGY
    assert "source_node" in _EMPTY_HMDL_TOPOLOGY
    assert "no_configured_proxy_count" in _EMPTY_HMDL_SUMMARY


def test_proxy_config_badge_renders():
    badge = proxy_config_badge()
    assert badge is not None


def test_node_status_badges():
    assert node_status_badge({"proxy_config_status": "no_configured_proxy"}) is not None
    assert node_status_badge({"proxy_config_status": "configured", "loki_sync_status": "loki_synced"}) is not None
    assert sync_status_badge(None) is not None


def test_topology_legend():
    legend = build_topology_legend_only()
    assert legend is not None


def test_environment_status_badges():
    assert environment_status_badge("connected") is not None
    assert environment_status_badge("connectivity_issue", issue_count=2) is not None
    assert environment_status_badge("no_configured_proxy") is not None
