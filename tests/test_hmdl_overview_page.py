"""Smoke test for HMDL overview page builder."""

from unittest.mock import patch

from src.pages.settings.integrations import hmdl_overview as page


def _base_mocks(mock_topology, mock_summary, mock_coverage):
    mock_topology.return_value = {
        "nodes": [],
        "synced_dc_count": 1,
        "total_dc_count": 1,
        "configured_location_count": 1,
        "no_configured_proxy_count": 0,
        "hub_dc": "DC13",
    }
    mock_summary.return_value = {"synced_dc_count": 1, "total_dc_count": 1}
    mock_coverage.return_value = {
        "summary": {"cluster": {"all": {"total": 0, "collected": 0, "missing": 0, "live": 0}}},
    }


@patch("src.pages.settings.integrations.hmdl_overview.api.get_hmdl_automation_health")
@patch("src.pages.settings.integrations.hmdl_overview.api.get_hmdl_coverage")
@patch("src.pages.settings.integrations.hmdl_overview.api.get_hmdl_sync_summary")
@patch("src.pages.settings.integrations.hmdl_overview.api.get_hmdl_topology")
def test_hmdl_overview_page_builds(mock_topology, mock_summary, mock_coverage, mock_ah):
    _base_mocks(mock_topology, mock_summary, mock_coverage)
    mock_ah.return_value = {"counts": {"alert": 0, "stale": 0, "dead": 0}}
    layout = page.build_layout()
    assert layout is not None


@patch("src.pages.settings.integrations.hmdl_overview.api.get_hmdl_automation_health")
@patch("src.pages.settings.integrations.hmdl_overview.api.get_hmdl_coverage")
@patch("src.pages.settings.integrations.hmdl_overview.api.get_hmdl_sync_summary")
@patch("src.pages.settings.integrations.hmdl_overview.api.get_hmdl_topology")
def test_hmdl_overview_shows_staleness_banner_when_stale(mock_topology, mock_summary, mock_coverage, mock_ah):
    _base_mocks(mock_topology, mock_summary, mock_coverage)
    mock_ah.return_value = {"counts": {"alert": 3, "stale": 1, "dead": 2}}
    layout = page.build_layout()
    # The red staleness banner text must appear somewhere in the rendered tree.
    assert "HMDL otomasyonu schedule" in str(layout)
