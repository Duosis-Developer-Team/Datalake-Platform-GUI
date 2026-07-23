"""API tests for the AWX router with awx_client mocked."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


def test_config_returns_unavailable_when_not_configured():
    with patch("app.routers.awx.awx_client.is_configured", return_value=False):
        client = TestClient(app)
        resp = client.get("/api/v1/awx/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["awx_available"] is False
    assert body["extra_vars"] == {}


def test_config_returns_data_when_configured():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.get_extra_vars", return_value={"dry_run": True}), \
         patch("app.routers.awx.awx_client.list_schedules", return_value=[{"id": 1, "enabled": True}]):
        client = TestClient(app)
        resp = client.get("/api/v1/awx/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["awx_available"] is True
    assert body["extra_vars"] == {"dry_run": True}
    assert body["schedules"] == [{"id": 1, "enabled": True}]


def test_put_config_rejected_when_not_configured():
    with patch("app.routers.awx.awx_client.is_configured", return_value=False):
        client = TestClient(app)
        resp = client.put("/api/v1/awx/config", json={"extra_vars": {"dry_run": True}})
    assert resp.status_code == 503


def test_put_config_patches_when_configured():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.patch_extra_vars", return_value={"dry_run": True}) as mp:
        client = TestClient(app)
        resp = client.put("/api/v1/awx/config", json={"extra_vars": {"dry_run": True}})
    assert resp.status_code == 200
    assert resp.json()["extra_vars"] == {"dry_run": True}
    mp.assert_called_once_with({"dry_run": True})


def test_launch_returns_job_id():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.launch", return_value=501):
        client = TestClient(app)
        resp = client.post("/api/v1/awx/launch", json={"extra_vars": {"dry_run": True}})
    assert resp.status_code == 200
    assert resp.json()["job_id"] == 501


def test_get_job_status():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.get_job", return_value={"job_id": 501, "status": "running"}):
        client = TestClient(app)
        resp = client.get("/api/v1/awx/jobs/501")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_put_schedule_toggle():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.set_schedule_enabled", return_value={"id": 3, "enabled": False}):
        client = TestClient(app)
        resp = client.put("/api/v1/awx/schedules/3", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
