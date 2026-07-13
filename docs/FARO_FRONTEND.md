# Grafana Faro — frontend RUM (GUI stack)

This document describes how **Datalake-Platform-GUI** (`datalake-webui`) sends **browser** telemetry via the [Grafana Faro Web SDK](https://grafana.com/oss/faro/) to a **Faro HTTP collector** (typically Grafana Alloy `faro.receiver`) that feeds the same **Grafana Enterprise** Loki/Tempo stack as server-side OpenTelemetry.

Authoritative decision: [`datalake-platform-knowledge-base/adrs/ADR-0023-grafana-faro-frontend-rum.md`](../../datalake-platform-knowledge-base/adrs/ADR-0023-grafana-faro-frontend-rum.md).

Server-side OTLP (gRPC `:4317`) remains documented in [OTEL_COLLECTOR.md](OTEL_COLLECTOR.md). **Faro does not speak OTLP from the browser** — it uses the Faro `/collect` HTTP protocol.

---

## Architecture

```text
Browser (Faro SDK)
  --HTTP POST /collect-->  Alloy faro.receiver  --> Loki + Tempo
Dash / FastAPI (OTEL)
  --OTLP gRPC :4317----->  OTEL Collector/Alloy --> Tempo (+ optional Loki)
Browser XHR (Dash callbacks)
  --traceparent---------->  Flask (OTEL) ---------> FastAPI (OTEL)
```

End-to-end traces: Faro `TracingInstrumentation` injects W3C `traceparent` on XHR/fetch; existing Flask/FastAPI instrumentation continues the trace.

---

## Quick start (`.env`)

```bash
FARO_ENABLED=true
FARO_COLLECTOR_URL=https://your-alloy-host:12345/collect
FARO_APP_NAME=datalake-webui
# Optional — defaults to APP_BUILD_ID
# FARO_APP_VERSION=
FARO_ENVIRONMENT=production
# Optional — Alloy faro.receiver api_key (public rate-limit credential)
# FARO_API_KEY=
```

Compose passes these into the `app` service (`docker-compose.yml`). When `FARO_ENABLED` is false or the collector URL is empty, `/telemetry/faro-config.json` returns `{"enabled":false}` and `assets/faro-init.js` does not load the SDK.

---

## What is instrumented

| Signal | How |
|--------|-----|
| Exceptions / unhandled rejections | Faro web instrumentations |
| Web Vitals (LCP, INP, CLS, …) | Faro web instrumentations |
| Sessions | Faro session instrumentation |
| Dash SPA views | Clientside callback on `url.pathname` → `setView` + `view_changed` event |
| XHR/fetch traces | `@grafana/faro-web-tracing` TracingInstrumentation |
| PDF export | `pdf_export` / `pdf_export_failed` events |
| DC tab change | `dc_tab_changed` event |
| Login success | Cookie `faro_evt_login` → `user_logged_in` event |

Query strings are scrubbed from Faro payloads via `beforeSend` (PII hygiene).

---

## Operator prerequisite (Grafana Enterprise / Alloy)

The collector is **out of scope** for this repository (same as OTEL). Example Alloy snippet:

```river
faro.receiver "frontend" {
  server {
    listen_address = "0.0.0.0"
    listen_port    = 12345
    cors_allowed_origins = [
      "http://localhost:8050",
      "http://10.134.52.250:8050",
      "http://10.134.52.251:8050",
    ]
    // api_key = "..."
  }
  output {
    logs   = [loki.write.default.receiver]
    traces = [otelcol.exporter.otlp.tempo.input]
  }
}
```

Requirements:

1. Browser must reach `FARO_COLLECTOR_URL` (not only Docker-internal DNS).
2. CORS must allow the GUI origin(s).
3. Alloy outputs should target the **same** Loki/Tempo used by backend OTEL.
4. Verify in Grafana Explore (Loki/Tempo) or Frontend Observability if licensed.

---

## Source files

| Component | File |
|-----------|------|
| Env → public JSON | [`src/telemetry/faro_config.py`](../src/telemetry/faro_config.py) |
| Config endpoint | `GET /telemetry/faro-config.json` (public path) |
| Browser bootstrap | [`assets/faro-init.js`](../assets/faro-init.js) |
| View + UI events | [`app.py`](../app.py) clientside callbacks |
| Login cookie | [`src/auth/routes.py`](../src/auth/routes.py) |
| PDF failure event | [`assets/export_pdf.js`](../assets/export_pdf.js) |
| Compose | [`docker-compose.yml`](../docker-compose.yml) `app` service |

Tests: [`tests/test_faro_config.py`](../tests/test_faro_config.py).

---

## CSP note

There is no strict Content-Security-Policy today. If CSP is added later, allow:

- `script-src`: `cdn.jsdelivr.net` (Faro IIFE bundles)
- `connect-src`: Faro collector host + same-origin `/telemetry/faro-config.json`
