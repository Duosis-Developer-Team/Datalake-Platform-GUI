"""OpenTelemetry SDK bootstrap for datalake-webui (OTLP gRPC to external collector)."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_logger = logging.getLogger(__name__)

_initialized = False


def _is_otel_enabled() -> bool:
    return os.environ.get("OTEL_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _parse_otlp_endpoint() -> tuple[str, bool]:
    """
    Return (host:port, insecure) for gRPC OTLP exporter.
    Honors OTEL_EXPORTER_OTLP_ENDPOINT (URL or host:port).
    """
    raw = (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "localhost:4317").strip()
    insecure = os.environ.get("OTEL_EXPORTER_OTLP_INSECURE", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if "://" in raw:
        parsed = urlparse(raw)
        host = parsed.hostname or "localhost"
        port = parsed.port or 4317
        return f"{host}:{port}", insecure
    return raw, insecure


def _service_name() -> str:
    return (os.environ.get("OTEL_SERVICE_NAME") or "datalake-webui").strip()


def _resource_attributes() -> dict:
    attrs: dict = {"service.name": _service_name()}
    extra = os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "").strip()
    if not extra:
        return attrs
    for part in extra.split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            attrs[k.strip()] = v.strip()
    return attrs


def setup_telemetry_sdk() -> None:
    """
    Configure TracerProvider, OTLP gRPC exporter, and auto-instrument httpx / requests / psycopg2.
    Call once at process startup before HTTP clients or DB are used.
    Flask instrumentation is separate: call instrument_flask_server(server) after the Flask app exists.
    """
    global _initialized
    if _initialized:
        return
    if not _is_otel_enabled():
        _logger.info("OpenTelemetry disabled (OTEL_ENABLED is not true)")
        _initialized = True
        return

    endpoint, insecure = _parse_otlp_endpoint()
    resource = Resource.create(_resource_attributes())

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
    except Exception as exc:
        _logger.warning("OpenTelemetry OTLP trace exporter init failed: %s", exc)
        _initialized = True
        return

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        HTTPXClientInstrumentor().instrument()
        RequestsInstrumentor().instrument()
        Psycopg2Instrumentor().instrument()
    except Exception as exc:
        _logger.warning("OpenTelemetry client instrumentation failed: %s", exc)

    _setup_logging_export(endpoint, insecure, resource)
    _initialized = True
    _logger.info(
        "OpenTelemetry enabled service=%s otlp_endpoint=%s insecure=%s",
        _service_name(),
        endpoint,
        insecure,
    )


def _setup_logging_export(endpoint: str, insecure: bool, resource: Resource) -> None:
    """Attach OTLP log handler to root logger when logs SDK is available."""
    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    except Exception as exc:
        _logger.debug("OpenTelemetry logs SDK not fully available: %s", exc)
        return

    try:
        log_exporter = OTLPLogExporter(endpoint=endpoint, insecure=insecure)
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        set_logger_provider(logger_provider)
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
        root = logging.getLogger()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        root.addHandler(handler)
    except Exception as exc:
        _logger.warning("OpenTelemetry logging handler setup failed: %s", exc)


def instrument_flask_server(server) -> None:
    """Instrument the Flask application used by Dash (call after server is created)."""
    if not _is_otel_enabled():
        return
    try:
        from opentelemetry.instrumentation.flask import FlaskInstrumentor

        FlaskInstrumentor().instrument_app(server)
    except Exception as exc:
        _logger.warning("OpenTelemetry Flask instrumentation failed: %s", exc)
