"""Tests for OpenTelemetry bootstrap (no live collector required)."""

from __future__ import annotations


def test_parse_otlp_endpoint_url(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.example:4317")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_INSECURE", "true")
    from src.telemetry.setup import _parse_otlp_endpoint

    host, insecure = _parse_otlp_endpoint()
    assert host == "collector.example:4317"
    assert insecure is True


def test_parse_otlp_endpoint_plain(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "otel.local:4317")
    from src.telemetry.setup import _parse_otlp_endpoint

    host, _ = _parse_otlp_endpoint()
    assert host == "otel.local:4317"


def test_setup_telemetry_sdk_no_crash_when_disabled(monkeypatch):
    monkeypatch.setenv("OTEL_ENABLED", "false")
    from opentelemetry import trace
    from src.telemetry.setup import setup_telemetry_sdk

    setup_telemetry_sdk()
    assert trace.get_tracer_provider() is not None
