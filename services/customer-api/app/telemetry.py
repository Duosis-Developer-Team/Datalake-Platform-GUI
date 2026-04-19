"""OpenTelemetry SDK for customer-api (OTLP gRPC)."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_logger = logging.getLogger(__name__)

_sdk_initialized = False


def _enabled() -> bool:
    return os.environ.get("OTEL_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _parse_endpoint() -> tuple[str, bool]:
    raw = (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "localhost:4317").strip()
    insecure = os.environ.get("OTEL_EXPORTER_OTLP_INSECURE", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if "://" in raw:
        u = urlparse(raw)
        host = u.hostname or "localhost"
        port = u.port or 4317
        return f"{host}:{port}", insecure
    return raw, insecure


def _resource_attrs() -> dict:
    name = (os.environ.get("OTEL_SERVICE_NAME") or "customer-api").strip()
    attrs: dict = {"service.name": name}
    extra = os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "").strip()
    if not extra:
        return attrs
    for part in extra.split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            attrs[k.strip()] = v.strip()
    return attrs


def setup_sdk() -> None:
    global _sdk_initialized
    if _sdk_initialized:
        return
    _sdk_initialized = True
    if not _enabled():
        _logger.info("OpenTelemetry disabled for customer-api")
        return

    endpoint, insecure = _parse_endpoint()
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
    except Exception as exc:
        _logger.warning("OTLP trace exporter init failed: %s", exc)
        return

    resource = Resource.create(_resource_attrs())
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        HTTPXClientInstrumentor().instrument()
        RequestsInstrumentor().instrument()
        Psycopg2Instrumentor().instrument()
        RedisInstrumentor().instrument()
    except Exception as exc:
        _logger.warning("OpenTelemetry instrumentation failed: %s", exc)

    _logger.info("OpenTelemetry enabled customer-api endpoint=%s", endpoint)


def instrument_fastapi_app(app) -> None:
    if not _enabled():
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor().instrument_app(app)
    except Exception as exc:
        _logger.warning("FastAPI instrumentation failed: %s", exc)
