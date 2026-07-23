"""API tests for the AWX router with awx_client mocked."""

from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.services import awx_client


def _http_error(status=502):
    return httpx.HTTPStatusError(
        f"{status} from AWX",
        request=httpx.Request("GET", "https://awx/api/v2/job_templates/42/"),
        response=httpx.Response(status),
    )


def test_config_returns_unavailable_when_not_configured():
    with patch("app.routers.awx.awx_client.is_configured", return_value=False):
        client = TestClient(app)
        resp = client.get("/api/v1/awx/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["awx_available"] is False
    assert body["extra_vars"] == {}
    assert body["reason"].startswith(awx_client.NOT_CONFIGURED_PREFIX)


def test_config_reason_names_api_auth_required_when_auth_off(monkeypatch):
    """AWX_ENABLED=true + API_AUTH_REQUIRED=false must be reported specifically,
    so the UI banner tells the operator what to actually change."""
    from app.config import settings

    monkeypatch.setattr(settings, "awx_enabled", True)
    monkeypatch.setattr(settings, "api_auth_required", False)
    monkeypatch.setattr(settings, "awx_api_url", "https://awx/api/v2")
    monkeypatch.setattr(settings, "awx_token", "tok")
    monkeypatch.setattr(settings, "awx_netbox_zabbix_jt_id", "42")
    client = TestClient(app)
    resp = client.get("/api/v1/awx/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["awx_available"] is False
    assert "API_AUTH_REQUIRED" in body["reason"]
    # and the write routes stay closed in that combination
    assert client.put("/api/v1/awx/config", json={"extra_vars": {"dry_run": True}}).status_code == 503
    assert client.post("/api/v1/awx/launch", json={}).status_code == 503
    assert client.put("/api/v1/awx/schedules/3", json={"enabled": True}).status_code == 503


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


def test_config_reports_real_reason_when_awx_call_fails():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.get_extra_vars", side_effect=_http_error(401)):
        client = TestClient(app)
        resp = client.get("/api/v1/awx/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["awx_available"] is False
    assert body["extra_vars"] == {} and body["schedules"] == []
    # the real failure, NOT the not-configured wording
    assert "401" in body["reason"]
    assert not body["reason"].startswith(awx_client.NOT_CONFIGURED_PREFIX)


def test_config_includes_last_job_when_configured():
    last_job = {"job_id": 501, "status": "successful", "started": "t1", "finished": "t2", "failed": False}
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.get_extra_vars", return_value={"dry_run": True}), \
         patch("app.routers.awx.awx_client.list_schedules", return_value=[]), \
         patch("app.routers.awx.awx_client.get_last_job", return_value=last_job):
        client = TestClient(app)
        resp = client.get("/api/v1/awx/config")
    assert resp.status_code == 200
    assert resp.json()["last_job"] == last_job


def test_config_last_job_none_when_not_configured():
    with patch("app.routers.awx.awx_client.is_configured", return_value=False):
        client = TestClient(app)
        resp = client.get("/api/v1/awx/config")
    assert resp.status_code == 200
    assert resp.json()["last_job"] is None


def test_config_last_job_failure_degrades_gracefully_without_breaking_config():
    """A get_last_job failure must not break the rest of the config response —
    extra_vars and schedules still render, last_job just degrades to None."""
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.get_extra_vars", return_value={"dry_run": True}), \
         patch("app.routers.awx.awx_client.list_schedules", return_value=[{"id": 1, "enabled": True}]), \
         patch("app.routers.awx.awx_client.get_last_job", side_effect=RuntimeError("boom")):
        client = TestClient(app)
        resp = client.get("/api/v1/awx/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["awx_available"] is True
    assert body["extra_vars"] == {"dry_run": True}
    assert body["schedules"] == [{"id": 1, "enabled": True}]
    assert body["last_job"] is None


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


def test_put_config_502_when_awx_write_fails():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.patch_extra_vars", side_effect=_http_error(400)):
        client = TestClient(app)
        resp = client.put("/api/v1/awx/config", json={"extra_vars": {"dry_run": True}})
    assert resp.status_code == 502
    assert "AWX update failed" in resp.json()["detail"]


def test_launch_returns_job_id():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.launch", return_value={"job_id": 501, "ignored_fields": {}}):
        client = TestClient(app)
        resp = client.post("/api/v1/awx/launch", json={"extra_vars": {"dry_run": True}})
    assert resp.status_code == 200
    assert resp.json()["job_id"] == 501
    assert resp.json()["ignored_fields"] == {}


def test_launch_passes_ignored_fields_through():
    ignored = {"extra_vars": {"dry_run": True}}
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.launch", return_value={"job_id": 502, "ignored_fields": ignored}):
        client = TestClient(app)
        resp = client.post("/api/v1/awx/launch", json={"extra_vars": {"dry_run": True}})
    assert resp.status_code == 200
    assert resp.json() == {"job_id": 502, "ignored_fields": ignored}


def test_launch_502_when_awx_launch_fails():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.launch", side_effect=RuntimeError("connect timeout")):
        client = TestClient(app)
        resp = client.post("/api/v1/awx/launch", json={"extra_vars": {"dry_run": True}})
    assert resp.status_code == 502
    assert "AWX launch failed" in resp.json()["detail"]


def test_get_job_status():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.get_job", return_value={"job_id": 501, "status": "running"}):
        client = TestClient(app)
        resp = client.get("/api/v1/awx/jobs/501")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_get_job_502_when_awx_fetch_fails():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.get_job", side_effect=_http_error(404)):
        client = TestClient(app)
        resp = client.get("/api/v1/awx/jobs/501")
    assert resp.status_code == 502
    assert "AWX job fetch failed" in resp.json()["detail"]


def test_get_schedules_unavailable_when_not_configured():
    with patch("app.routers.awx.awx_client.is_configured", return_value=False):
        client = TestClient(app)
        resp = client.get("/api/v1/awx/schedules")
    assert resp.status_code == 200
    body = resp.json()
    assert body["awx_available"] is False and body["items"] == []
    assert body["reason"].startswith(awx_client.NOT_CONFIGURED_PREFIX)


def test_get_schedules_unavailable_when_awx_call_fails():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.list_schedules", side_effect=_http_error(500)):
        client = TestClient(app)
        resp = client.get("/api/v1/awx/schedules")
    assert resp.status_code == 200
    body = resp.json()
    assert body["awx_available"] is False and body["items"] == []
    assert "500" in body["reason"]


def test_put_schedule_toggle():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.set_schedule_enabled", return_value={"id": 3, "enabled": False}):
        client = TestClient(app)
        resp = client.put("/api/v1/awx/schedules/3", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_put_schedule_502_when_awx_write_fails():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.set_schedule_enabled", side_effect=_http_error(403)):
        client = TestClient(app)
        resp = client.put("/api/v1/awx/schedules/3", json={"enabled": False})
    assert resp.status_code == 502
    assert "AWX schedule update failed" in resp.json()["detail"]
