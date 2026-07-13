"""Grafana Faro (browser RUM) configuration from environment variables."""

from __future__ import annotations

import os
from typing import Any


def is_faro_enabled() -> bool:
    return os.environ.get("FARO_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _app_version() -> str:
    explicit = (os.environ.get("FARO_APP_VERSION") or "").strip()
    if explicit:
        return explicit
    return (os.environ.get("APP_BUILD_ID") or "dev").strip() or "dev"


def get_faro_public_config() -> dict[str, Any]:
    """
    Browser-safe Faro config JSON.

    When disabled, returns ``{"enabled": false}`` only (no collector URL / API key).
    The Faro collector API key is a public rate-limit credential (Sentry DSN-like),
    not a user secret — still omit it when Faro is off.
    """
    if not is_faro_enabled():
        return {"enabled": False}

    url = (os.environ.get("FARO_COLLECTOR_URL") or "").strip()
    if not url:
        return {"enabled": False}

    cfg: dict[str, Any] = {
        "enabled": True,
        "url": url,
        "app": {
            "name": (os.environ.get("FARO_APP_NAME") or "datalake-webui").strip() or "datalake-webui",
            "version": _app_version(),
            "environment": (os.environ.get("FARO_ENVIRONMENT") or "production").strip()
            or "production",
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
