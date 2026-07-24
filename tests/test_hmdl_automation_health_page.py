"""Smoke test for HMDL Automation Health page builder."""

from unittest.mock import patch

from src.pages.settings.integrations import hmdl_automation_health as page

MOCK_AH = {
    "generated_at": "2026-07-23T12:17:05+00:00",
    "automations": [
        {
            "key": "collector_sync",
            "label": "Datalake Collector Sync",
            "cadence": "günlük 02:00",
            "last_run_at": "2026-07-21T02:01:54+00:00",
            "age_hours": 58.2,
            "status": "dead",
            "warn_hours": 26,
            "dead_hours": 50,
            "extra": {"proxy_coverage": "4/23", "last_run_proxies": 4, "total_proxies": 23},
        },
        {
            "key": "zabbix_sync",
            "label": "NetBox → Zabbix Sync",
            "cadence": "~8 saatte bir",
            "last_run_at": "2026-07-23T12:10:47+00:00",
            "age_hours": 0.1,
            "status": "fresh",
            "warn_hours": 12,
            "dead_hours": 24,
            "extra": {},
        },
    ],
    "counts": {"fresh": 1, "stale": 0, "dead": 1, "unknown": 0, "alert": 1},
    "proxies": [
        {
            "proxy_id": "DC15-NIFI1",
            "dc_code": "DC15",
            "proxy_nifi_host": "10.40.16.250",
            "last_seen_at": "2026-07-16T02:02:44+00:00",
            "age_hours": 178.2,
            "status": "dead",
        }
    ],
    "proxy_summary": {"total": 23, "fresh": 4, "stale": 0, "dead": 19},
    "data_gaps": {"cluster_missing": 5, "ibm_missing": 8, "by_source": {"vmware": 4, "nutanix": 1}},
}


@patch("src.pages.settings.integrations.hmdl_automation_health.api.get_hmdl_automation_health")
def test_automation_health_page_builds(mock_ah):
    mock_ah.return_value = MOCK_AH
    layout = page.build_layout()
    assert layout is not None


@patch("src.pages.settings.integrations.hmdl_automation_health.api.get_hmdl_automation_health")
def test_automation_health_page_builds_when_api_down(mock_ah):
    # api_client returns the empty shape when hmdl-api is unavailable.
    mock_ah.return_value = {
        "generated_at": None,
        "automations": [],
        "counts": {"fresh": 0, "stale": 0, "dead": 0, "unknown": 0, "alert": 0},
        "proxies": [],
        "proxy_summary": {"total": 0, "fresh": 0, "stale": 0, "dead": 0},
        "data_gaps": {"cluster_missing": 0, "ibm_missing": 0, "by_source": {}},
    }
    layout = page.build_layout()
    assert layout is not None
