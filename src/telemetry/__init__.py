"""OpenTelemetry bootstrap and helpers for datalake-webui."""

from src.telemetry.setup import instrument_flask_server, setup_telemetry_sdk

__all__ = ["instrument_flask_server", "setup_telemetry_sdk"]
