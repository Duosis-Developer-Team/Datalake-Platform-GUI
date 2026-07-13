"""Tests for Grafana Faro browser RUM config (no live collector required)."""

from __future__ import annotations

import json

import pytest


def test_is_faro_enabled_false_by_default(monkeypatch):
    monkeypatch.delenv("FARO_ENABLED", raising=False)
    from src.telemetry.faro_config import is_faro_enabled

    assert is_faro_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on"])
def test_is_faro_enabled_truthy(monkeypatch, val):
    monkeypatch.setenv("FARO_ENABLED", val)
    from src.telemetry.faro_config import is_faro_enabled

    assert is_faro_enabled() is True


def test_get_faro_public_config_disabled(monkeypatch):
    monkeypatch.setenv("FARO_ENABLED", "false")
    monkeypatch.setenv("FARO_COLLECTOR_URL", "https://alloy.example:12345/collect")
    monkeypatch.setenv("FARO_API_KEY", "secret-key")
    from src.telemetry.faro_config import get_faro_public_config

    cfg = get_faro_public_config()
    assert cfg == {"enabled": False}
    assert "url" not in cfg
    assert "apiKey" not in cfg


def test_get_faro_public_config_enabled_without_url(monkeypatch):
    monkeypatch.setenv("FARO_ENABLED", "true")
    monkeypatch.delenv("FARO_COLLECTOR_URL", raising=False)
    from src.telemetry.faro_config import get_faro_public_config

    assert get_faro_public_config() == {"enabled": False}


def test_get_faro_public_config_enabled(monkeypatch):
    monkeypatch.setenv("FARO_ENABLED", "true")
    monkeypatch.setenv("FARO_COLLECTOR_URL", "https://alloy.example:12345/collect")
    monkeypatch.setenv("FARO_APP_NAME", "datalake-webui")
    monkeypatch.setenv("FARO_APP_VERSION", "1.2.3")
    monkeypatch.setenv("FARO_ENVIRONMENT", "staging")
    monkeypatch.setenv("FARO_API_KEY", "collector-key")
    from src.telemetry.faro_config import get_faro_public_config

    cfg = get_faro_public_config()
    assert cfg["enabled"] is True
    assert cfg["url"] == "https://alloy.example:12345/collect"
    assert cfg["apiKey"] == "collector-key"
    assert cfg["app"] == {
        "name": "datalake-webui",
        "version": "1.2.3",
        "environment": "staging",
    }


def test_get_faro_public_config_version_falls_back_to_app_build_id(monkeypatch):
    monkeypatch.setenv("FARO_ENABLED", "true")
    monkeypatch.setenv("FARO_COLLECTOR_URL", "http://localhost:12345/collect")
    monkeypatch.delenv("FARO_APP_VERSION", raising=False)
    monkeypatch.setenv("APP_BUILD_ID", "abc1234")
    from src.telemetry.faro_config import get_faro_public_config

    cfg = get_faro_public_config()
    assert cfg["app"]["version"] == "abc1234"


def test_faro_config_endpoint(monkeypatch):
    monkeypatch.setenv("FARO_ENABLED", "true")
    monkeypatch.setenv("FARO_COLLECTOR_URL", "https://alloy.example:12345/collect")
    monkeypatch.setenv("FARO_APP_NAME", "datalake-webui")
    monkeypatch.delenv("FARO_API_KEY", raising=False)

    from flask import Flask

    from src.telemetry.faro_config import register_faro_routes

    app = Flask(__name__)
    register_faro_routes(app)
    client = app.test_client()
    res = client.get("/telemetry/faro-config.json")
    assert res.status_code == 200
    body = json.loads(res.data)
    assert body["enabled"] is True
    assert body["url"] == "https://alloy.example:12345/collect"
    assert "apiKey" not in body


def test_telemetry_path_is_public():
    from src.auth.middleware import _is_public_path

    assert _is_public_path("/telemetry/faro-config.json") is True
    assert _is_public_path("/telemetry/") is True
    assert _is_public_path("/customers") is False
