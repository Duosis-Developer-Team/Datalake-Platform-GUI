# OpenTelemetry → external Collector (GUI stack)

This document describes how the **Datalake-Platform-GUI** stack sends telemetry to an **external** OpenTelemetry Collector, how that maps to **Java OpenTelemetry Java agent** settings, and what is **not** implemented in Python.

Authoritative architecture decision: [`datalake-platform-knowledge-base/adrs/ADR-0005-opentelemetry-instrumentation.md`](../../datalake-platform-knowledge-base/adrs/ADR-0005-opentelemetry-instrumentation.md).

---

## Prerequisites

- A reachable **OpenTelemetry Collector** exposing **OTLP gRPC** (default port **4317**).
- Network path from each process (Dash container, API containers, or host) to that endpoint.
- For **plaintext** gRPC (no TLS), keep `OTEL_EXPORTER_OTLP_INSECURE=true` (default in this repo).

The Collector’s own pipelines (sampling, exporters to Jaeger/Tempo, etc.) are **out of scope** for this repository.

---

## Quick start (Docker Compose)

[`docker-compose.yml`](../docker-compose.yml) injects `OTEL_*` into every service. Add the following to your **`.env`** (same directory as `docker-compose.yml`):

```bash
# Enable SDK and point at your collector (replace host/port)
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector-host:4317
# Or: OTEL_EXPORTER_OTLP_ENDPOINT=your-collector-host:4317

# Plaintext gRPC (typical for internal collectors without TLS)
OTEL_EXPORTER_OTLP_INSECURE=true

# Optional: resource attributes (comma-separated key=value)
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=prod
```

Then start the stack (e.g. `docker compose --profile microservice up -d`). Each service receives a **fixed** logical name via Compose (not from `.env`):

| Service (Compose) | `service.name` in traces |
|-------------------|--------------------------|
| `app` | `datalake-webui` |
| `datacenter-api` | `datacenter-api` |
| `customer-api` | `customer-api` |
| `query-api` | `query-api` |
| `admin-api` | `admin-api` |

To rename a service in traces, change `OTEL_SERVICE_NAME` in **`docker-compose.yml`** for that service (or your Helm values), not a single shared `.env` key.

---

## Local development without Compose

| Process | Loading `.env` |
|---------|----------------|
| **Dash** (`python app.py`) | [`app.py`](../app.py) calls `load_dotenv()` — add `OTEL_*` to **`.env`** at repo root. |
| **FastAPI** (`uvicorn ...`) | No `load_dotenv()` in services — export variables in the shell, use IDE run config, or run via Compose. |

---

## Java OpenTelemetry agent → this Python stack

Example JVM flags (NiFi / Java):

```text
-Dotel.service.name=nifi-proxy-dc11
-Dotel.resource.attributes=deployment.environment=prod
-Dotel.traces.exporter=otlp
-Dotel.logs.exporter=none
-Dotel.metrics.exporter=none
-Dotel.exporter.otlp.endpoint=http://10.134.16.63:4317
-Dotel.exporter.otlp.protocol=grpc
-Dotel.javaagent.debug=false
-Dotel.traces.sampler=parentbased_traceidratio
-Dotel.traces.sampler.arg=0.1
```

| Goal | Java (`-Dotel.*`) | GUI stack (Python) |
|------|-------------------|---------------------|
| Enable / disable | Load agent vs not | `OTEL_ENABLED=true` (or `1`, `yes`, `on`) |
| Service name | `otel.service.name` | Set in code/Compose per process; **`OTEL_SERVICE_NAME`** is read by [`src/telemetry/setup.py`](../src/telemetry/setup.py) and `services/*/app/telemetry.py`, but **Compose pins** each service name — see table above |
| Resource attributes | `otel.resource.attributes` | `OTEL_RESOURCE_ATTRIBUTES` — comma-separated `key=value` (e.g. `deployment.environment=prod`) |
| OTLP endpoint | `otel.exporter.otlp.endpoint` | `OTEL_EXPORTER_OTLP_ENDPOINT` — `host:port` or `http(s)://host:port` (parsed in code) |
| Protocol | `otel.exporter.otlp.protocol=grpc` | **Fixed OTLP gRPC** in code; HTTP/protobuf is not selectable |
| Trace exporter | `otel.traces.exporter=otlp` | Traces always use OTLP gRPC when enabled |
| Log exporter | `otel.logs.exporter=none` | **datalake-webui**: may attach OTLP log handler if logs SDK initializes; **FastAPI services**: **no** OTLP log exporter — traces only |
| Metrics exporter | `otel.metrics.exporter=none` | **No** metrics exporter in this stack |
| Agent debug | `otel.javaagent.debug` | Not used; use Python `logging` level |
| JDBC noise | `otel.instrumentation.jdbc.enabled=false` | **psycopg2** auto-instrumentation; **no** env flag to disable in repo code |
| Sampling | `parentbased_traceidratio` + `0.1` | **`TracerProvider` uses default `AlwaysOn`** — `OTEL_TRACES_SAMPLER` is **not** read. Use **Collector-side** sampling/processors, or extend code to configure a ratio sampler |

---

## What gets instrumented (summary)

- **datalake-webui**: Flask, httpx, requests, psycopg2; optional OTLP logs; custom spans (auth, Dash callbacks) — see ADR-0005.
- **FastAPI services**: FastAPI, httpx, requests, psycopg2; Redis on **datacenter-api** and **customer-api** only.

---

## Limitations and operational notes

1. **Sampling**: Prefer **tail-based or head-based sampling in the Collector** to match something like 10% trace volume without code changes here.
2. **Metrics**: Not exported from these apps; use Collector receivers or other agents if needed.
3. **TLS**: For TLS gRPC to the Collector, you would need code or dependency updates beyond `OTEL_EXPORTER_OTLP_INSECURE` (currently geared to insecure internal endpoints).

---

## Source files

| Component | File |
|-----------|------|
| Dash / Flask | [`src/telemetry/setup.py`](../src/telemetry/setup.py) |
| admin-api | [`services/admin-api/app/telemetry.py`](../services/admin-api/app/telemetry.py) |
| datacenter-api | [`services/datacenter-api/app/telemetry.py`](../services/datacenter-api/app/telemetry.py) |
| customer-api | [`services/customer-api/app/telemetry.py`](../services/customer-api/app/telemetry.py) |
| query-api | [`services/query-api/app/telemetry.py`](../services/query-api/app/telemetry.py) |
| Compose wiring | [`docker-compose.yml`](../docker-compose.yml) |

Tests (no live Collector): [`tests/test_telemetry_setup.py`](../tests/test_telemetry_setup.py).
