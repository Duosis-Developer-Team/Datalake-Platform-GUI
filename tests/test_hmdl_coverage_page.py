"""Smoke test for HMDL Datalake Coverage page builder."""

from unittest.mock import patch

from src.pages.settings.integrations import hmdl_coverage as page


@patch("src.pages.settings.integrations.hmdl_coverage.api.get_hmdl_coverage")
@patch("src.pages.settings.integrations.hmdl_coverage.api.get_hmdl_locations")
def test_hmdl_coverage_page_builds(mock_locations, mock_coverage):
    mock_locations.return_value = {
        "items": [{"dc_code": "DC13", "environment_status": "connected"}],
    }
    mock_coverage.return_value = {
        "summary": {"cluster": {"all": {"total": 0, "collected": 0, "missing": 0, "live": 0}}},
        "clusters": [],
        "ibm_hosts": [],
        "locations": ["DC13"],
    }
    layout = page.build_layout(search="?dc=DC13")
    assert layout is not None
