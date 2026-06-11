"""API test for the datalake coverage endpoint (mocked query layer)."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

MOCK_COVERAGE = {
    "summary": {
        "cluster": {
            "all": {"total": 2, "collected": 1, "missing": 1, "live": 1},
            "vmware": {"total": 2, "collected": 1, "missing": 1, "live": 1},
        },
        "ibm_host": {"total": 1, "collected": 1, "missing": 0, "live": 1},
    },
    "clusters": [
        {
            "source": "vmware",
            "cluster_name": "DC13-G3-CLS",
            "dc": "DC13",
            "collected": False,
            "expected": True,
            "is_live": False,
            "last_collected": None,
            "status": "missing",
            "reason": "Toplanmıyor — DC13/VmWare: 3 collector erişilemiyor (telnet_fail)",
            "target_issues": [
                {"dc_code": "DC13", "platform": "VmWare", "check_status": "telnet_fail"}
            ],
        }
    ],
    "ibm_hosts": [
        {
            "servername": "G2HV12DC13",
            "dc": "DC13",
            "collected": True,
            "expected": True,
            "is_live": True,
            "last_collected": None,
            "status": "live",
            "reason": "Canlı",
            "target_issues": [],
        }
    ],
    "locations": ["DC13"],
    "dc_filter": None,
    "source_filter": None,
}


@patch("app.db.queries.coverage.build_coverage", return_value=MOCK_COVERAGE)
def test_coverage_endpoint(mock_build):
    client = TestClient(app)
    resp = client.get("/api/v1/collectors/coverage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["cluster"]["all"]["missing"] == 1
    assert body["clusters"][0]["status"] == "missing"
    assert "telnet_fail" in body["clusters"][0]["reason"]
    assert body["ibm_hosts"][0]["status"] == "live"
    assert body["locations"] == ["DC13"]


@patch("app.db.queries.coverage.build_coverage", return_value=MOCK_COVERAGE)
def test_coverage_endpoint_passes_filters(mock_build):
    client = TestClient(app)
    resp = client.get("/api/v1/collectors/coverage?dc=DC13&source=vmware")
    assert resp.status_code == 200
    mock_build.assert_called_once_with(dc="DC13", source="vmware")
