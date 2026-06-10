"""API tests with mocked DB layer."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

MOCK_TOPOLOGY = {
    "hub_dc": "DC13",
    "source_node": {"id": "LOKI", "label": "Loki Inventory", "role": "source"},
    "generated_at": "2026-06-10T00:00:00Z",
    "last_prod_run_id": "run-1",
    "last_prod_run_at": "2026-06-10T00:00:00Z",
    "nodes": [
        {
            "location_id": 10,
            "location_name": "DC13",
            "dc_code": "DC13",
            "description": None,
            "site_name": "IST",
            "role": "hub",
            "proxy_config_status": "configured",
            "loki_sync_status": "loki_synced",
            "proxies": [
                {
                    "proxy_id": "DC13-NIFI1",
                    "proxy_nifi_host": "10.134.16.10",
                    "loki_sync_status": "loki_synced",
                    "target_count": 5,
                    "distributed_count": 5,
                    "last_sync_at": None,
                    "last_sync_status": "completed",
                    "last_run_id": "run-1",
                }
            ],
        }
    ],
    "edges": [
        {"from_dc": "LOKI", "to_dc": "DC13", "edge_type": "collection"},
        {"from_dc": "DC13", "to_dc": "DC13-NIFI1", "edge_type": "distribution"},
    ],
    "synced_dc_count": 1,
    "total_dc_count": 1,
    "configured_location_count": 1,
    "no_configured_proxy_count": 0,
    "dc_statuses": {"DC13": "loki_synced"},
}


@patch("app.db.queries.collectors.build_topology", return_value=MOCK_TOPOLOGY)
def test_topology_endpoint(mock_build):
    client = TestClient(app)
    resp = client.get("/api/v1/collectors/topology")
    assert resp.status_code == 200
    body = resp.json()
    assert body["hub_dc"] == "DC13"
    assert body["synced_dc_count"] == 1


@patch("app.db.queries.collectors.build_sync_summary")
def test_sync_summary_endpoint(mock_summary):
    mock_summary.return_value = {
        "generated_at": "2026-06-10T00:00:00Z",
        "last_prod_run_id": "run-1",
        "last_prod_run_at": "2026-06-10T00:00:00Z",
        "synced_dc_count": 9,
        "total_dc_count": 10,
        "configured_location_count": 9,
        "no_configured_proxy_count": 1,
        "synced_proxy_count": 17,
        "total_proxy_count": 17,
        "dc_statuses": {"DC13": "loki_synced"},
    }
    client = TestClient(app)
    resp = client.get("/api/v1/collectors/sync-summary")
    assert resp.status_code == 200
    assert resp.json()["synced_dc_count"] == 9


@patch("app.db.queries.collectors.list_root_locations")
def test_locations_endpoint(mock_locations):
    mock_locations.return_value = [
        {
            "location_id": 20,
            "location_name": "DC20",
            "dc_code": "DC20",
            "site_name": "ANK",
            "description": None,
            "proxy_config_status": "no_configured_proxy",
            "loki_sync_status": None,
            "proxy_count": 0,
        }
    ]
    client = TestClient(app)
    resp = client.get("/api/v1/collectors/locations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["proxy_config_status"] == "no_configured_proxy"


def test_health_endpoint():
    with patch("app.main.pool.fetch_one", return_value={"?column?": 1}):
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
