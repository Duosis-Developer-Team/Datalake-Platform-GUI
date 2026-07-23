"""Unit tests for the hmdl-api AWX client helpers."""

from app.config import settings
from app.services import awx_client


def _awx_settings(monkeypatch, *, enabled=True, auth=True):
    monkeypatch.setattr(settings, "awx_enabled", enabled)
    monkeypatch.setattr(settings, "api_auth_required", auth)
    monkeypatch.setattr(settings, "awx_api_url", "https://awx/api/v2")
    monkeypatch.setattr(settings, "awx_token", "tok")
    monkeypatch.setattr(settings, "awx_netbox_zabbix_jt_id", "42")


def test_is_configured_false_when_disabled(monkeypatch):
    _awx_settings(monkeypatch, enabled=False)
    assert awx_client.is_configured() is False


def test_is_configured_true_when_all_present(monkeypatch):
    _awx_settings(monkeypatch)
    assert awx_client.is_configured() is True


def test_is_configured_false_when_auth_not_required(monkeypatch):
    """AWX control is remote execution; refuse it while verify_api_user is a
    no-op (API_AUTH_REQUIRED=false), which is the default in config/.env/compose."""
    _awx_settings(monkeypatch, enabled=True, auth=False)
    assert awx_client.is_configured() is False


def test_not_configured_reason_names_api_auth_required(monkeypatch):
    _awx_settings(monkeypatch, enabled=True, auth=False)
    reason = awx_client.not_configured_reason()
    assert reason.startswith(awx_client.NOT_CONFIGURED_PREFIX)
    assert "API_AUTH_REQUIRED" in reason and "AWX_ENABLED" in reason


def test_not_configured_reason_names_missing_settings(monkeypatch):
    _awx_settings(monkeypatch, enabled=False, auth=True)
    reason = awx_client.not_configured_reason()
    assert reason.startswith(awx_client.NOT_CONFIGURED_PREFIX)
    assert "AWX_API_URL" in reason
    assert "API_AUTH_REQUIRED" not in reason


def test_filter_allowed_keeps_whitelist_drops_unknown_and_secrets():
    raw = {
        "dry_run": True,
        "device_limit": 5,
        "zabbix_url": "https://z/api_jsonrpc.php",
        "zabbix_password": "hunter2",   # secret -> dropped
        "netbox_token": "abc",          # secret -> dropped
        "totally_unknown": "x",         # not whitelisted -> dropped
    }
    out = awx_client.filter_allowed(raw)
    assert out == {"dry_run": True, "device_limit": 5, "zabbix_url": "https://z/api_jsonrpc.php"}


def test_is_secret_key():
    assert awx_client.is_secret_key("zabbix_password") is True
    assert awx_client.is_secret_key("netbox_token") is True
    assert awx_client.is_secret_key("discovery_db_password") is True
    assert awx_client.is_secret_key("device_source") is False


def test_client_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "awx_enabled", False)
    try:
        awx_client._client()
        assert False, "expected AwxUnavailable"
    except awx_client.AwxUnavailable:
        pass
