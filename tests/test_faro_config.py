"""Tests for Grafana Faro browser RUM config (OTLP HTTP → same collector as OTEL)."""

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
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.example:4317")
    monkeypatch.setenv("FARO_API_KEY", "secret-key")
    from src.telemetry.faro_config import get_faro_public_config

    cfg = get_faro_public_config()
    assert cfg == {"enabled": False}
    assert "tracesURL" not in cfg
    assert "apiKey" not in cfg


def test_get_faro_public_config_enabled_without_otel_host(monkeypatch):
    monkeypatch.setenv("FARO_ENABLED", "true")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("FARO_OTLP_HTTP_ENDPOINT", raising=False)
    from src.telemetry.faro_config import get_faro_public_config

    assert get_faro_public_config() == {"enabled": False}


def test_get_faro_public_config_derives_otlp_http_from_otel(monkeypatch):
    monkeypatch.setenv("FARO_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://10.134.16.63:4317")
    monkeypatch.delenv("FARO_OTLP_HTTP_ENDPOINT", raising=False)
    monkeypatch.delenv("FARO_APP_NAME", raising=False)
    monkeypatch.setenv("FARO_APP_VERSION", "1.2.3")
    monkeypatch.setenv("FARO_ENVIRONMENT", "staging")
    from src.telemetry.faro_config import get_faro_public_config

    cfg = get_faro_public_config()
    assert cfg["enabled"] is True
    assert cfg["transport"] == "otlp-http"
    assert cfg["tracesURL"] == "http://10.134.16.63:4318/v1/traces"
    assert cfg["logsURL"] == "http://10.134.16.63:4318/v1/logs"
    assert cfg["app"]["name"] == "datalake-webui-browser"
    assert cfg["attributes"]["telemetry.source"] == "faro"
    assert "url" not in cfg


def test_get_faro_public_config_explicit_otlp_http_override(monkeypatch):
    monkeypatch.setenv("FARO_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://ignored:4317")
    monkeypatch.setenv("FARO_OTLP_HTTP_ENDPOINT", "https://collector.example:4318")
    monkeypatch.setenv("FARO_APP_NAME", "custom-browser")
    from src.telemetry.faro_config import get_faro_public_config

    cfg = get_faro_public_config()
    assert cfg["tracesURL"] == "https://collector.example:4318/v1/traces"
    assert cfg["logsURL"] == "https://collector.example:4318/v1/logs"
    assert cfg["app"]["name"] == "custom-browser"


def test_get_faro_public_config_otel_plain_host_port(monkeypatch):
    monkeypatch.setenv("FARO_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "otel.local:4317")
    from src.telemetry.faro_config import get_faro_public_config

    cfg = get_faro_public_config()
    assert cfg["tracesURL"] == "http://otel.local:4318/v1/traces"


def test_faro_config_endpoint(monkeypatch):
    monkeypatch.setenv("FARO_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://10.134.16.63:4317")
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
    assert body["tracesURL"].endswith("/v1/traces")
    assert body["app"]["name"] == "datalake-webui-browser"
    assert "apiKey" not in body


def test_telemetry_path_is_public():
    from src.auth.middleware import _is_public_path

    assert _is_public_path("/telemetry/faro-config.json") is True
    assert _is_public_path("/customers") is False
