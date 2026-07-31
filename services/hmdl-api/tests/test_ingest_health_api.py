"""API test for ingest-health endpoint (mocked query layer)."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

MOCK_INGEST = {
    "summary": {
        "healthy": 1,
        "no_network": 0,
        "network_ok_no_data": 1,
        "stale": 0,
        "unmatched": 0,
        "total": 2,
    },
    "items": [
        {
            "endpoint_ip": "10.1.1.1",
            "collector_type": "Veeam",
            "proxy_id": "",
            "entity_name": "Veeam-A",
            "dc_code": "DC13",
            "tenant_name": None,
            "network_access": True,
            "check_status": "ok",
            "last_check_at": None,
            "match_mode": "ip",
            "match_key": "10.1.1.1",
            "bridge_via": "metric_ip",
            "bridge_resolved": "10.1.1.1",
            "last_ingest_at": None,
            "ingest_age_hours": None,
            "ingest_stale": False,
            "stale_after_hours": 6,
            "verdict": "network_ok_no_data",
            "detail_message": "[DC13] Veeam 10.1.1.1 (Veeam-A): network_ok_no_data",
            "checked_at": None,
        }
    ],
    "dc_filter": None,
    "collector_type_filter": None,
    "verdict_filter": None,
}


@patch("app.db.queries.ingest_health.build_ingest_health", return_value=MOCK_INGEST)
def test_ingest_health_endpoint(mock_build):
    client = TestClient(app)
    resp = client.get("/api/v1/collectors/ingest-health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["network_ok_no_data"] == 1
    assert body["items"][0]["verdict"] == "network_ok_no_data"


@patch("app.db.queries.ingest_health.build_ingest_health", return_value=MOCK_INGEST)
def test_ingest_health_passes_filters(mock_build):
    client = TestClient(app)
    resp = client.get(
        "/api/v1/collectors/ingest-health?dc=DC13&collector_type=IBM-HMC&verdict=stale"
    )
    assert resp.status_code == 200
    mock_build.assert_called_once_with(
        dc="DC13", collector_type="IBM-HMC", verdict="stale"
    )
