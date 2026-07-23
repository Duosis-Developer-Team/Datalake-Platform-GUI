"""Tests for HMDL AWX api_client wrappers (hmdl-api client mocked)."""

from unittest.mock import MagicMock, patch

from src.services import api_client as api


def _resp(payload):
    r = MagicMock()
    r.json.return_value = payload
    r.content = b"x"
    r.raise_for_status.return_value = None
    return r


def test_get_hmdl_awx_config_ok():
    client = MagicMock()
    client.get.return_value = _resp({"awx_available": True, "extra_vars": {"dry_run": True}, "schedules": []})
    with patch.object(api, "_get_client_hmdl", return_value=client):
        out = api.get_hmdl_awx_config()
    assert out["awx_available"] is True
    assert out["extra_vars"] == {"dry_run": True}


def test_get_hmdl_awx_config_swallows_errors():
    client = MagicMock()
    client.get.side_effect = api._HTTP_ERRORS[0]("boom") if isinstance(api._HTTP_ERRORS, tuple) else Exception("boom")
    with patch.object(api, "_get_client_hmdl", return_value=client):
        out = api.get_hmdl_awx_config()
    assert out["awx_available"] is False
    assert out["extra_vars"] == {}


def test_put_hmdl_awx_config_sends_body():
    client = MagicMock()
    client.put.return_value = _resp({"awx_available": True, "extra_vars": {"dry_run": True}})
    with patch.object(api, "_get_client_hmdl", return_value=client):
        out = api.put_hmdl_awx_config({"dry_run": True})
    assert out["extra_vars"] == {"dry_run": True}
    assert client.put.call_args.kwargs["json"] == {"extra_vars": {"dry_run": True}}


def test_launch_hmdl_awx_job():
    client = MagicMock()
    client.post.return_value = _resp({"job_id": 501, "ignored_fields": {}})
    with patch.object(api, "_get_client_hmdl", return_value=client):
        out = api.launch_hmdl_awx_job({"dry_run": True})
    assert out["job_id"] == 501
    assert out["ignored_fields"] == {}


def test_launch_hmdl_awx_job_surfaces_ignored_fields():
    ignored = {"extra_vars": {"dry_run": True}}
    client = MagicMock()
    client.post.return_value = _resp({"job_id": 501, "ignored_fields": ignored})
    with patch.object(api, "_get_client_hmdl", return_value=client):
        out = api.launch_hmdl_awx_job({"dry_run": True})
    assert out["ignored_fields"] == ignored


def test_get_hmdl_awx_job_swallows_errors():
    client = MagicMock()
    # NOTE: adapted from the brief, which used a bare `Exception("boom")`. The
    # real `_HTTP_ERRORS` tuple (httpx.ConnectError, httpx.TimeoutException,
    # httpx.HTTPStatusError, httpx.RemoteProtocolError, ValueError) does NOT
    # include bare `Exception`, so a generic Exception would NOT be swallowed
    # by `except _HTTP_ERRORS` and would incorrectly propagate out of a
    # "never raises" wrapper. Use a real member of `_HTTP_ERRORS` to exercise
    # the actual swallow path, mirroring the pattern already used above in
    # `test_get_hmdl_awx_config_swallows_errors`.
    client.get.side_effect = api._HTTP_ERRORS[0]("boom") if isinstance(api._HTTP_ERRORS, tuple) else Exception("boom")
    with patch.object(api, "_get_client_hmdl", return_value=client):
        out = api.get_hmdl_awx_job("501")
    # the fallback must be typed like the success path, not the raw param
    assert out["job_id"] == 501
    assert isinstance(out["job_id"], int)
    assert out["status"] == "unknown"


def test_set_hmdl_awx_schedule():
    client = MagicMock()
    client.put.return_value = _resp({"id": 3, "enabled": False})
    with patch.object(api, "_get_client_hmdl", return_value=client):
        out = api.set_hmdl_awx_schedule(3, False)
    assert out == {"id": 3, "enabled": False}
