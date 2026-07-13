# Grafana Faro — frontend RUM (GUI stack)

Browser telemetry via the [Grafana Faro Web SDK](https://grafana.com/oss/faro/) is sent to the **same OpenTelemetry Collector** used by server-side OTEL ([OTEL_COLLECTOR.md](OTEL_COLLECTOR.md)), using **OTLP HTTP** (`:4318` `/v1/traces` and `/v1/logs`).

Server processes use **OTLP gRPC `:4317`**. Faro uses **OTLP HTTP `:4318`** on the **same host**. Distinction in Grafana is by **labels** (not a separate collector service):

| Signal | Protocol | Typical `service.name` / app | Extra label |
|--------|----------|------------------------------|-------------|
| Server OTEL | gRPC `:4317` | `datalake-webui`, `customer-api`, … | (resource attrs from `OTEL_*`) |
| Browser Faro | HTTP `:4318` | `datalake-webui-browser` | `telemetry.source=faro` |

Authoritative decision: [`ADR-0023`](../../datalake-platform-knowledge-base/adrs/ADR-0023-grafana-faro-frontend-rum.md).

---

## Architecture

```text
Browser (Faro + OtlpHttpTransport)
  --OTLP HTTP :4318 /v1/{traces,logs}-->  OTEL Collector (same host as server OTEL)
Dash / FastAPI (OTEL SDK)
  --OTLP gRPC :4317--------------------->  OTEL Collector
Browser XHR (Dash)
  --traceparent-------------------------->  Flask → FastAPI (shared trace id)
Collector --> Tempo / Loki (Grafana Enterprise)
```

---

## Quick start (`.env`)

```bash
# Server OTEL (gRPC) — enable when the collector is up
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://10.134.16.63:4317
OTEL_EXPORTER_OTLP_INSECURE=true

# Faro — same collector host; OTLP HTTP derived as http://{host}:4318
FARO_ENABLED=true
FARO_APP_NAME=datalake-webui-browser
FARO_ENVIRONMENT=production
# Optional override if HTTP is not on :4318 of the OTEL host:
# FARO_OTLP_HTTP_ENDPOINT=http://10.134.16.63:4318
```

When `FARO_ENABLED` is false or the OTEL host cannot be resolved, `/telemetry/faro-config.json` returns `{"enabled":false}`.

---

## What is instrumented

| Signal | How |
|--------|-----|
| Exceptions / unhandled rejections | Faro web instrumentations → OTLP logs |
| Web Vitals | Faro → OTLP |
| Sessions / SPA views | `setView` + `view_changed` |
| XHR/fetch traces + `traceparent` | TracingInstrumentation |
| PDF / DC tab / login | custom `pushEvent` |

Query strings are scrubbed via `beforeSend`.

---

## Source files

| Component | File |
|-----------|------|
| Env → public JSON | [`src/telemetry/faro_config.py`](../src/telemetry/faro_config.py) |
| Config endpoint | `GET /telemetry/faro-config.json` |
| Browser bootstrap | [`assets/faro-init.js`](../assets/faro-init.js) |
| Compose | [`docker-compose.yml`](../docker-compose.yml) `app` service |

Tests: [`tests/test_faro_config.py`](../tests/test_faro_config.py).

---

## CSP note

Allow `cdn.jsdelivr.net` (Faro IIFE + OTLP transport) and `connect-src` to the OTEL collector host `:4318`.
