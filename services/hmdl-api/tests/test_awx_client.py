"""Unit tests for the hmdl-api AWX client helpers."""

from app.config import settings
from app.services import awx_client


def test_is_configured_false_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "awx_enabled", False)
    monkeypatch.setattr(settings, "awx_api_url", "https://awx/api/v2")
    monkeypatch.setattr(settings, "awx_token", "tok")
    monkeypatch.setattr(settings, "awx_netbox_zabbix_jt_id", "42")
    assert awx_client.is_configured() is False


def test_is_configured_true_when_all_present(monkeypatch):
    monkeypatch.setattr(settings, "awx_enabled", True)
    monkeypatch.setattr(settings, "awx_api_url", "https://awx/api/v2")
    monkeypatch.setattr(settings, "awx_token", "tok")
    monkeypatch.setattr(settings, "awx_netbox_zabbix_jt_id", "42")
    assert awx_client.is_configured() is True


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
