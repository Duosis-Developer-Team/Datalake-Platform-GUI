"""Backup coverage rows join collector_target by exact source IP."""

from unittest.mock import patch

from app.db.queries import coverage as cov_q


def test_enrich_backup_with_collectors_by_ip():
    rows = [
        {
            "source": "netbackup",
            "endpoint_ip": "10.132.1.137",
            "endpoint_name": "Equinix IL2-Netbackup-DC13_3",
            "dc": "DC13",
            "collector_check_status": None,
        },
        {
            "source": "veeam",
            "endpoint_ip": "10.99.0.1",
            "endpoint_name": "orphan",
            "dc": "DC99",
            "collector_check_status": None,
        },
    ]
    with patch(
        "app.db.queries.coverage._fetch_platform_endpoints",
        return_value=[
            {
                "entity_name": "Equinix IL2-Netbackup-DC13_3",
                "ip": "10.132.1.137",
                "last_check_status": "ok",
            }
        ],
    ):
        cov_q._enrich_backup_with_collectors(rows)

    assert rows[0]["collector_check_status"] == "ok"
    assert rows[1]["collector_check_status"] is None


def test_enrich_backup_fills_empty_name_from_collector():
    rows = [
        {
            "source": "zerto",
            "endpoint_ip": "10.50.9.15",
            "endpoint_name": None,
            "dc": "DC14",
            "collector_check_status": None,
        }
    ]
    with patch(
        "app.db.queries.coverage._fetch_platform_endpoints",
        return_value=[
            {
                "entity_name": "KKB-Zerto-DC14-Site01",
                "ip": "10.50.9.15",
                "last_check_status": "telnet_fail",
            }
        ],
    ):
        cov_q._enrich_backup_with_collectors(rows)

    assert rows[0]["endpoint_name"] == "KKB-Zerto-DC14-Site01"
    assert rows[0]["collector_check_status"] == "telnet_fail"
