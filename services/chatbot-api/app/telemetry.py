"""OpenTelemetry bootstrap — mirrors services/datacenter-api/app/telemetry.py.

Everything is gated on ``OTEL_ENABLED`` and wrapped in defensive try/except so
that a missing/incompatible otel package can never prevent the service from
starting.
"""

from __future__ import annotations

import logging
import os

_logger = logging.getLogger("chatbot-api.telemetry")
_sdk_initialized = False


def _enabled() -> bool:
    return os.getenv("OTEL_ENABLED", "false").lower() in ("1", "true", "yes")


def setup_sdk() -> None:
    """Initialize tracing/auto-instrumentation. Call once at process startup."""
    global _sdk_initialized
    if _sdk_initialized:
        return
    _sdk_initialized = True
    if not _enabled():
        _logger.info("OpenTelemetry disabled for chatbot-api")
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        service_name = os.getenv("OTEL_SERVICE_NAME", "chatbot-api")
        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure) if endpoint else OTLPSpanExporter(insecure=insecure)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        HTTPXClientInstrumentor().instrument()
        _logger.info("OpenTelemetry initialized for %s", service_name)
    except Exception as exc:  # pragma: no cover - defensive
        _logger.warning("OpenTelemetry setup failed: %s", exc)


def instrument_fastapi_app(app) -> None:
    if not _enabled():
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor().instrument_app(app)
    except Exception as exc:  # pragma: no cover - defensive
        _logger.warning("FastAPI instrumentation failed: %s", exc)
