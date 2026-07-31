"""Smoke tests for HMDL Ingest Health page."""

from unittest.mock import patch

from src.pages.settings.integrations import hmdl_ingest_health as page

_EMPTY = {
    "summary": {
        "healthy": 0,
        "no_network": 0,
        "network_ok_no_data": 0,
        "stale": 0,
        "unmatched": 0,
        "total": 0,
    },
    "items": [],
}


@patch("src.pages.settings.integrations.hmdl_ingest_health.api.get_hmdl_ingest_health", return_value=_EMPTY)
@patch(
    "src.pages.settings.integrations.hmdl_ingest_health.api.get_hmdl_locations",
    return_value={"items": [{"dc_code": "DC13"}]},
)
def test_hmdl_ingest_health_page_builds(_loc, _ingest):
    layout = page.build_layout()
    assert layout is not None


@patch(
    "src.pages.settings.integrations.hmdl_ingest_health.api.get_hmdl_ingest_health",
    return_value={
        "summary": {
            "healthy": 1,
            "no_network": 1,
            "network_ok_no_data": 0,
            "stale": 0,
            "unmatched": 0,
            "total": 2,
        },
        "items": [
            {
                "endpoint_ip": "10.6.2.55",
                "collector_type": "Veeam",
                "dc_code": "DC11",
                "entity_name": "PremierDC-VeeamBR-DC11",
                "network_access": False,
                "last_ingest_at": None,
                "ingest_age_hours": None,
                "verdict": "no_network",
                "detail_message": "no route",
            }
        ],
    },
)
@patch(
    "src.pages.settings.integrations.hmdl_ingest_health.api.get_hmdl_locations",
    return_value={"items": [{"dc_code": "DC11"}]},
)
def test_hmdl_ingest_health_with_rows(_loc, mock_ingest):
    layout = page.build_layout("?dc=DC11&verdict=no_network")
    assert layout is not None
    mock_ingest.assert_called_once_with("DC11", collector_type=None, verdict="no_network")
