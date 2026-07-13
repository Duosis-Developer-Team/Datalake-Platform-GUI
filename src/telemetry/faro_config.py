"""Grafana Faro (browser RUM) configuration from environment variables.

Faro sends to the **same OpenTelemetry Collector** as server-side OTEL
(OTLP HTTP ``:4318``), not a separate Faro ``/collect`` service. Browser
signals are distinguished with labels (``app.name`` / ``service.name`` and
``telemetry.source=faro``).
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse


def is_faro_enabled() -> bool:
    return os.environ.get("FARO_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _app_version() -> str:
    explicit = (os.environ.get("FARO_APP_VERSION") or "").strip()
    if explicit:
        return explicit
    return (os.environ.get("APP_BUILD_ID") or "dev").strip() or "dev"


def _host_from_otel_endpoint() -> str | None:
    """Extract hostname from OTEL_EXPORTER_OTLP_ENDPOINT (URL or host:port)."""
    raw = (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    return parsed.hostname


def _otlp_http_base() -> str | None:
    """
    OTLP HTTP base URL for Faro OtlpHttpTransport.

    Prefer ``FARO_OTLP_HTTP_ENDPOINT``; otherwise derive ``http://{otel-host}:4318``
    from the same collector host as server OTEL (gRPC ``:4317``).
    """
    explicit = (os.environ.get("FARO_OTLP_HTTP_ENDPOINT") or "").strip().rstrip("/")
    if explicit:
        return explicit
    host = _host_from_otel_endpoint()
    if not host:
        return None
    return f"http://{host}:4318"


def get_faro_public_config() -> dict[str, Any]:
    """
    Browser-safe Faro config JSON.

    When disabled or collector host cannot be resolved, returns ``{"enabled": false}``.
    """
    if not is_faro_enabled():
        return {"enabled": False}

    base = _otlp_http_base()
    if not base:
        return {"enabled": False}

    # Distinct from server OTEL service.name (datalake-webui / FastAPI names).
    app_name = (
        os.environ.get("FARO_APP_NAME") or "datalake-webui-browser"
    ).strip() or "datalake-webui-browser"

    cfg: dict[str, Any] = {
        "enabled": True,
        "transport": "otlp-http",
        "tracesURL": f"{base}/v1/traces",
        "logsURL": f"{base}/v1/logs",
        "app": {
            "name": app_name,
            "version": _app_version(),
            "environment": (os.environ.get("FARO_ENVIRONMENT") or "production").strip()
            or "production",
        },
        # Extra attributes → OTLP resource/log labels (distinct from server OTEL).
        "attributes": {
            "telemetry.source": "faro",
            "service.namespace": (
                os.environ.get("FARO_SERVICE_NAMESPACE") or "datalake-platform"
            ).strip()
            or "datalake-platform",
        },
    }
    api_key = (os.environ.get("FARO_API_KEY") or "").strip()
    if api_key:
        cfg["apiKey"] = api_key
    return cfg


def register_faro_routes(flask_app) -> None:
    """Register ``GET /telemetry/faro-config.json`` on the Flask (Dash) server."""
    from flask import jsonify

    @flask_app.get("/telemetry/faro-config.json")
    def faro_config_json():  # type: ignore[no-untyped-def]
        return jsonify(get_faro_public_config())
