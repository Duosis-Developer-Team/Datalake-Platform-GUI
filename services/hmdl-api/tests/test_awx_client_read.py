"""Read-path tests for awx_client using a mocked httpx.Client."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.config import settings
from app.services import awx_client


def _fake_client_cm(mock_client):
    cm = MagicMock()
    cm.__enter__.return_value = mock_client
    cm.__exit__.return_value = False
    return cm


@pytest.fixture()
def jt_id(monkeypatch):
    """Pin the job template id so tests can assert the exact AWX request path."""
    monkeypatch.setattr(settings, "awx_netbox_zabbix_jt_id", "42")
    return "42"


def _requested_path(mock_method):
    call = mock_method.call_args
    return call.args[0] if call.args else call.kwargs["url"]


def test_get_extra_vars_parses_and_filters(jt_id):
    mock_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {
        "extra_vars": "dry_run: true\ndevice_limit: 10\nzabbix_password: secret\n"
    }
    mock_client.get.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        out = awx_client.get_extra_vars()
    assert out == {"dry_run": True, "device_limit": 10}
    # a wrong endpoint (e.g. /job_template/ singular) must not pass silently
    assert _requested_path(mock_client.get) == f"/job_templates/{jt_id}/"


def test_get_job_normalizes_fields():
    mock_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {
        "id": 77, "status": "successful", "started": "t1", "finished": "t2", "failed": False,
    }
    mock_client.get.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        out = awx_client.get_job(77)
    assert out == {"job_id": 77, "status": "successful", "started": "t1", "finished": "t2", "failed": False}
    assert _requested_path(mock_client.get) == "/jobs/77/"


def test_list_schedules_shapes_rows(jt_id):
    mock_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"results": [
        {"id": 3, "name": "nightly", "enabled": True, "next_run": "t", "rrule": "FREQ=DAILY", "extra": "x"},
    ]}
    mock_client.get.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        out = awx_client.list_schedules()
    assert out == [{"id": 3, "name": "nightly", "enabled": True, "next_run": "t", "rrule": "FREQ=DAILY"}]
    # must be the job-template-scoped collection, not the global /schedules/
    assert _requested_path(mock_client.get) == f"/job_templates/{jt_id}/schedules/"


def test_get_extra_vars_propagates_http_error(jt_id):
    """raise_for_status is actually exercised: a 401/404 from AWX must surface."""
    mock_client = MagicMock()
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401 Unauthorized", request=httpx.Request("GET", "https://awx/api/v2/job_templates/42/"),
        response=httpx.Response(401),
    )
    mock_client.get.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        with pytest.raises(httpx.HTTPStatusError):
            awx_client.get_extra_vars()
    resp.raise_for_status.assert_called_once()
