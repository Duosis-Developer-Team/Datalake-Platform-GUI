"""Unit tests for sync-driven proxy catalog."""

from app.services.proxy_catalog import build_catalog_from_rows


def test_build_catalog_from_rows_groups_by_dc_code():
    rows = [
        {
            "proxy_id": "DC18-NIFI1",
            "dc_code": "DC18",
            "proxy_nifi_host": "10.134.16.207",
            "ssh_user": "root",
            "conf_path": "/Datalake_Project/configuration_file.json",
            "gitea_audit_path": "proxies/dc18/nifi1/configuration_file.json",
        },
        {
            "proxy_id": "DC18-NIFI2",
            "dc_code": "DC18",
            "proxy_nifi_host": "10.134.16.208",
            "ssh_user": "root",
            "conf_path": "/Datalake_Project/configuration_file.json",
            "gitea_audit_path": "proxies/dc18/nifi2/configuration_file.json",
        },
        {
            "proxy_id": "ICT21-NIFI1",
            "dc_code": "ICT21",
            "proxy_nifi_host": "10.125.16.2",
            "ssh_user": "root",
            "conf_path": "/Datalake_Project/configuration_file.json",
            "gitea_audit_path": "",
        },
    ]

    catalog = build_catalog_from_rows(rows)

    assert set(catalog.keys()) == {"DC18", "ICT21"}
    assert len(catalog["DC18"]["proxies"]) == 2
    assert catalog["DC18"]["proxies"][0]["id"] == "DC18-NIFI1"
    assert catalog["ICT21"]["proxies"][0]["proxy_nifi_host"] == "10.125.16.2"
