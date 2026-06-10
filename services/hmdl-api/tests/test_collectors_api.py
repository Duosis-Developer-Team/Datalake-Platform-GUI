"""API tests with mocked DB layer."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

MOCK_TOPOLOGY = {
    "hub_dc": "DC13",
    "generated_at": "2026-06-10T00:00:00Z",
    "last_prod_run_id": "run-1",
    "last_prod_run_at": "2026-06-10T00:00:00Z",
    "nodes": [
        {
            "dc_code": "DC13",
            "role": "hub",
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
    "edges": [],
    "synced_dc_count": 1,
    "total_dc_count": 1,
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
        "total_dc_count": 9,
        "synced_proxy_count": 17,
        "total_proxy_count": 17,
        "dc_statuses": {"DC13": "loki_synced"},
    }
    client = TestClient(app)
    resp = client.get("/api/v1/collectors/sync-summary")
    assert resp.status_code == 200
    assert resp.json()["synced_dc_count"] == 9


def test_health_endpoint():
    with patch("app.main.pool.fetch_one", return_value={"?column?": 1}):
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
