"""Write-path tests for awx_client using a mocked httpx.Client."""

import json
from unittest.mock import MagicMock, patch

from app.services import awx_client


def _fake_client_cm(mock_client):
    cm = MagicMock()
    cm.__enter__.return_value = mock_client
    cm.__exit__.return_value = False
    return cm


def test_patch_extra_vars_merges_whitelist_only():
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


def test_launch_returns_job_id():
    mock_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"job": 501, "id": 999}
    mock_client.post.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        job_id = awx_client.launch({"dry_run": True})
    assert job_id == 501
    body = mock_client.post.call_args.kwargs["json"]
    assert body["extra_vars"] == {"dry_run": True}


def test_set_schedule_enabled():
    mock_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"id": 3, "enabled": False}
    mock_client.patch.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        out = awx_client.set_schedule_enabled(3, False)
    assert out == {"id": 3, "enabled": False}
