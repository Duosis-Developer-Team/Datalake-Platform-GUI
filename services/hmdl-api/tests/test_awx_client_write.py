"""Write-path tests for awx_client using a mocked httpx.Client."""

import json
from unittest.mock import MagicMock, patch

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


def test_patch_extra_vars_merges_whitelist_only(jt_id):
    mock_client = MagicMock()
    get_resp = MagicMock()
    get_resp.json.return_value = {"extra_vars": "dry_run: false\nlocation_filter: DC13\n"}
    patch_resp = MagicMock()
    patch_resp.json.return_value = {"extra_vars": "dry_run: true\nlocation_filter: DC13\n"}
    mock_client.get.return_value = get_resp
    mock_client.patch.return_value = patch_resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        out = awx_client.patch_extra_vars({"dry_run": True, "netbox_token": "leak", "bogus": 1})
    # secret + unknown dropped; result reflects merged JT state
    assert out == {"dry_run": True, "location_filter": "DC13"}
    # the PATCH body merged onto current and serialized as a JSON string
    sent = mock_client.patch.call_args.kwargs["json"]["extra_vars"]
    merged = json.loads(sent)
    assert merged["dry_run"] is True
    assert merged["location_filter"] == "DC13"
    assert "netbox_token" not in merged and "bogus" not in merged
    assert _requested_path(mock_client.patch) == f"/job_templates/{jt_id}/"


def test_launch_returns_job_id(jt_id):
    mock_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"job": 501, "id": 999}
    mock_client.post.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        out = awx_client.launch({"dry_run": True})
    assert out["job_id"] == 501
    assert out["ignored_fields"] == {}
    body = mock_client.post.call_args.kwargs["json"]
    assert body["extra_vars"] == {"dry_run": True}
    assert _requested_path(mock_client.post) == f"/job_templates/{jt_id}/launch/"


def test_launch_reports_ignored_fields(jt_id):
    """AWX drops launch-time extra_vars unless ask_variables_on_launch is set;
    the caller must be able to see that the override never applied."""
    mock_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {
        "job": 502,
        "ignored_fields": {"extra_vars": {"dry_run": True}},
    }
    mock_client.post.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        out = awx_client.launch({"dry_run": True})
    assert out == {"job_id": 502, "ignored_fields": {"extra_vars": {"dry_run": True}}}


def test_set_schedule_enabled():
    mock_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"id": 3, "enabled": False}
    mock_client.patch.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        out = awx_client.set_schedule_enabled(3, False)
    assert out == {"id": 3, "enabled": False}
    # schedules are patched on the global collection, by schedule id
    assert _requested_path(mock_client.patch) == "/schedules/3/"
