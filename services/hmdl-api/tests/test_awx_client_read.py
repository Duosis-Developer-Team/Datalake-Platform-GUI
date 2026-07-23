"""Read-path tests for awx_client using a mocked httpx.Client."""

from unittest.mock import MagicMock, patch

from app.services import awx_client


def _fake_client_cm(mock_client):
    cm = MagicMock()
    cm.__enter__.return_value = mock_client
    cm.__exit__.return_value = False
    return cm


def test_get_extra_vars_parses_and_filters():
    mock_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {
        "extra_vars": "dry_run: true\ndevice_limit: 10\nzabbix_password: secret\n"
    }
    mock_client.get.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        out = awx_client.get_extra_vars()
    assert out == {"dry_run": True, "device_limit": 10}


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


def test_list_schedules_shapes_rows():
    mock_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"results": [
        {"id": 3, "name": "nightly", "enabled": True, "next_run": "t", "rrule": "FREQ=DAILY", "extra": "x"},
    ]}
    mock_client.get.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        out = awx_client.list_schedules()
    assert out == [{"id": 3, "name": "nightly", "enabled": True, "next_run": "t", "rrule": "FREQ=DAILY"}]
