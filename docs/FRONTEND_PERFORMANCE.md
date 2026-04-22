# Frontend Performance Optimisation

This document covers all client-side and server-render-side optimisation targets for the Datalake-Platform-GUI Dash application. It is scoped to the existing **Dash (Python) + Gunicorn + NGINX Ingress** stack and explicitly notes what is achievable within that stack versus what requires migration to a different technology.

Related: [PROD_ARCHITECTURE.md](PROD_ARCHITECTURE.md) | [CACHE_STRATEGY_COMPARISON.md](CACHE_STRATEGY_COMPARISON.md)

---

## 1. Current bottlenecks at a glance

| # | Bottleneck | Location | Impact |
|---|-----------|----------|--------|
| 1 | 4 sequential blocking HTTP calls per customer page render | `src/pages/customer_view.py:1214-1228` | TTFB = sum of all 4 call durations |
| 2 | `_build_customer_export_sheets` runs on every page load | `customer_view.py` | CPU + memory waste for users who never export |
| 3 | Single gunicorn gthread worker (`--workers 1 --threads 4`) | `Dockerfile:32` | Long callbacks block all other requests on the same pod |
| 4 | Per-process `cache_service` dict (512 keys max) | `src/services/cache_service.py` | Cache lost on restart; not shared across replicas |
| 5 | No browser caching headers on Dash routes or API responses | ingress config | Every page navigation re-fetches all data |
| 6 | No gzip/brotli on API JSON responses | ingress config | 5-10× payload size overhead |
| 7 | Large VM tables rendered fully server-side on load | `customer_view.py:_vm_table` | Generates thousands of `html.Td` elements per render |
| 8 | Static assets (Plotly, Mantine JS/CSS) served without long-cache | NGINX / CDN | Re-downloaded on every session |

---

## 2. What can be optimised within the existing stack

The Dash + Gunicorn stack has real constraints (no true async callbacks, SSR only, no native HTTP/2 push), but the following improvements are significant and implementable without changing the core technology.

### 2.1 Parallel API fetches in customer page callback

**File:** `src/pages/customer_view.py`, function `_customer_content`

**Current behaviour:** four HTTP calls execute sequentially. Total latency = T1 + T2 + T3 + T4.

**Target:** execute all four calls concurrently. Total latency = max(T1, T2, T3, T4).

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def _customer_content(customer_name: str, time_range: dict | None = None):
    tr = time_range or default_time_range()
    name = (customer_name or "").strip()

    with ThreadPoolExecutor(max_workers=4) as pool:
        f_resources    = pool.submit(api.get_customer_resources, name, tr)
        f_avail        = pool.submit(api.get_customer_availability_bundle, name, tr)
        f_s3           = pool.submit(api.get_customer_s3_vaults, name, tr)
        f_phys         = pool.submit(api.get_physical_inventory_customer)

        data           = f_resources.result()
        avail_bundle   = f_avail.result()
        s3_data        = f_s3.result()
        phys_inv_devices = f_phys.result()
    # ... rest of function unchanged
```

**Expected gain:** If each call takes ~1 s (cached), total drops from ~4 s to ~1 s. On cold cache (worst case 8-10 s each) the gain is ~3-4×.

**Constraint:** Dash callbacks are synchronous Python. `ThreadPoolExecutor` is the correct approach inside a sync callback — do not use `asyncio` (Gunicorn gthread does not run an event loop).

### 2.2 Tab-lazy loading (progressive render)

**Current behaviour:** all tab content is computed in a single `_customer_content` call and returned as one large HTML tree. The browser receives the complete document before displaying anything.

**Target:** render the Summary tab immediately with a skeleton; other tabs load content only when the user clicks them.

Implementation pattern:
1. `build_customer_layout` returns Summary with pre-loaded data and empty placeholder `Div` elements for other tab panels.
2. A second Dash callback fires on `Input("customer-tabs", "value")` and populates only the active tab's placeholder.
3. Each placeholder has a `dcc.Loading` wrapper so the user sees a spinner rather than empty content.

```python
# In layout builder — return skeleton for non-summary tabs:
dmc.TabsPanel(value="virt", children=html.Div(id="virt-tab-content"))

# Separate callback:
@callback(
    Output("virt-tab-content", "children"),
    Input("customer-tabs", "value"),
    State("url", "search"),
    prevent_initial_call=True,
)
def load_virt_tab(active_tab, search):
    if active_tab != "virt":
        raise PreventUpdate
    # ... fetch only virtualisation data
```

**Expected gain:** First paint drops from ~4-8 s to ~1-2 s (Summary only). Subsequent tab clicks load independently.

### 2.3 Export lazy-load

**File:** `customer_view.py`, function `_build_customer_export_sheets`

**Current behaviour:** called unconditionally on every `_customer_content` invocation. Builds pandas DataFrames and serialises data even when the user never clicks Export.

**Target:** call `_build_customer_export_sheets` only inside the `customer-export-xlsx` and `customer-export-csv` button callbacks.

```python
@callback(
    Output("customer-download-xlsx", "data"),
    Input("customer-export-xlsx", "n_clicks"),
    State("customer-store", "data"),   # dcc.Store holds the serialised page data
    prevent_initial_call=True,
)
def export_xlsx(n_clicks, stored_data):
    if not n_clicks:
        raise PreventUpdate
    sheets = _build_customer_export_sheets(**stored_data)
    return dash_send_excel_workbook(sheets, ...)
```

Store the raw data payload in a `dcc.Store` component populated by the initial callback. Export callbacks read from the store instead of re-fetching.

**Expected gain:** removes pandas DataFrame construction (~100-300 ms CPU) from the critical render path on every page load.

### 2.4 `dcc.Store` for client-side data snapshot

Use a page-level `dcc.Store(id="customer-store", storage_type="memory")` to hold the serialised API response for the currently viewed customer. Benefits:
- Tab callbacks read local store data instead of re-calling the API.
- Browser tab switching becomes instant.
- Export callbacks share the same data.

```python
# In initial callback:
Output("customer-store", "data"),

# Return from _customer_content:
store_payload = {
    "name": name,
    "tr": tr,
    "totals": totals,
    "assets": assets,
    # ... lightweight fields only; omit large vm_list arrays
}
```

Keep the store payload small (omit `vm_list` arrays; load them per-tab). Large arrays should remain server-side and be fetched tab-by-tab.

### 2.5 VM table pagination / virtual scroll

**File:** `customer_view.py`, function `_vm_table`

**Current behaviour:** renders the full VM list as `html.Table` / `html.Tr` / `html.Td`. For a customer with 500 VMs, this generates ~2 500 DOM nodes before the browser can paint.

**Target:** replace with `dash_table.DataTable` using `page_action="native"`, `page_size=50`, or `virtualization=True`.

```python
from dash import dash_table

def _vm_table_paginated(vm_list, columns, ...):
    return dash_table.DataTable(
        data=vm_list,
        columns=[{"name": c, "id": c} for c in columns],
        page_action="native",
        page_size=50,
        sort_action="native",
        style_table={"overflowX": "auto"},
    )
```

**Expected gain:** DOM size decreases 10-50×. First-paint time for customer pages with large VM lists drops significantly.

### 2.6 Client-side callbacks for UI state

Tab switching, filter dropdown selection, and time range picker updates currently trigger round-trips to the Python server. These can be handled entirely in the browser using Dash client-side callbacks.

```python
app.clientside_callback(
    """
    function(tab) {
        // Tab selection only updates URL hash; no server round-trip
        return tab;
    }
    """,
    Output("active-tab-store", "data"),
    Input("customer-tabs", "value"),
)
```

Move all state-only interactions (no data fetch needed) to client-side callbacks. Keep server callbacks only for data loading.

### 2.7 Gunicorn worker configuration

**Current (`Dockerfile`):** `--workers 1 --threads 4`

**Target (prod):** `--workers 4 --threads 8 --worker-class gthread`

This requires the K8s pod CPU limit to be raised to ≥ 2 cores (currently 500m). With `workers=4` on a 2-core pod, Gunicorn can handle 4 concurrent callback chains in parallel; threads within each worker handle concurrent simple requests (health checks, static assets).

**Note:** `workers > 1` with Dash requires `--preload` disabled (Dash registers callbacks at module load, which is safe with `gthread`). The existing `use_reloader=False` is already set.

---

## 3. Browser caching configuration

### 3.1 Static assets

Dash serves its own JS/CSS bundles via `/_dash-component-suites/`. These files include content hashes in their filenames and never change for a given version.

Configure NGINX Ingress to add long-cache headers:

```nginx
location ~* /_dash-component-suites/ {
    proxy_pass http://bulutistan-frontend;
    add_header Cache-Control "public, max-age=31536000, immutable";
}

location ~* \.(js|css|woff2|png|svg|ico)$ {
    proxy_pass http://bulutistan-frontend;
    add_header Cache-Control "public, max-age=86400";
}
```

This prevents re-downloading Plotly (~3 MB), Mantine, and other bundles on every session.

### 3.2 API response caching

| Route | Cache-Control | Rationale |
|-------|---------------|-----------|
| `GET /api/v1/customers` | `private, max-age=60, stale-while-revalidate=300` | Customer list changes rarely |
| `GET /api/v1/customers/{name}/resources` | `private, max-age=30, stale-while-revalidate=120` | Core metrics, refresh every 15 min on server |
| `GET /api/v1/customers/{name}/s3/vaults` | `private, max-age=30, stale-while-revalidate=120` | Same as resources |
| `GET /api/v1/dashboard/overview` | `private, max-age=30, stale-while-revalidate=120` | Global aggregate |
| `GET /api/v1/sla` | `private, max-age=60, stale-while-revalidate=300` | SLA data refreshes infrequently |
| `GET /health`, `GET /ready` | `no-store` | Health probes must always be fresh |

Add these headers in FastAPI response middleware or via NGINX `proxy_hide_header` + `add_header`. `stale-while-revalidate` tells the browser to serve the cached response immediately while revalidating in the background, eliminating perceived latency on navigation.

### 3.3 Gzip / Brotli compression

Add to NGINX Ingress ConfigMap:

```nginx
gzip on;
gzip_types application/json text/plain text/css application/javascript;
gzip_min_length 1024;
gzip_comp_level 6;
```

A typical `/customers/{name}/resources` JSON response (100-150 KB) compresses to 15-25 KB — a 6-8× reduction in transfer time on slow connections.

### 3.4 CDN for static assets (optional, high value)

If a CDN is available (e.g., Cloudflare, Akamai), configure it to cache `/_dash-component-suites/` paths globally. All users receive JS/CSS from edge nodes, reducing latency for geographically distributed users and offloading origin server bandwidth.

---

## 4. Stack limitations and honest trade-offs

Dash on Gunicorn has architectural constraints that cannot be fully solved without changing the technology stack. These are documented here so that future decisions are made with full awareness.

| Limitation | Root cause | Mitigation within Dash | Alternative (requires migration) |
|-----------|------------|------------------------|----------------------------------|
| No true async callbacks | Gunicorn sync workers | `ThreadPoolExecutor` for parallel fetches | FastAPI + WebSocket or React SPA |
| No HTTP streaming / SSE | Dash protocol is request-response | Progressive tabs (tab-lazy) | React SPA with streaming backend |
| All callbacks block until complete | Gunicorn thread model | Increase `--threads`, optimise callback CPU usage | Celery background tasks + polling callback |
| No native code splitting | Dash serves all JS as one bundle | CDN + long-cache headers | Custom Webpack split |
| Global layout re-render on state change | Dash renders entire layout subtrees | `dcc.Store` + targeted `Output` components | React fine-grained reconciliation |

**Conclusion:** Within the Dash stack, the improvements in §2 and §3 can realistically reduce customer view load time from 4-10 s to under 1 s (warm cache) and 2-3 s (cold first load). Beyond that, further gains require either a React SPA frontend consuming the existing FastAPI microservices, or moving to a server-side streaming approach (FastAPI StreamingResponse + client-side rendering of partial data).

---

## 5. Implementation priority order

| Priority | Task | Expected gain | Complexity |
|----------|------|--------------|------------|
| 1 | Parallel API fetch (§2.1) | 3-4× TTFB reduction | Low |
| 2 | Export lazy-load (§2.3) | ~200 ms per render removed | Low |
| 3 | Gzip on ingress (§3.3) | 6-8× payload reduction | Very low |
| 4 | Static asset browser cache (§3.1) | Eliminates repeat JS downloads | Low |
| 5 | Gunicorn worker config (§2.7) | Concurrency improvement | Low |
| 6 | Tab-lazy loading (§2.2) | First paint 2-3× faster | Medium |
| 7 | `dcc.Store` data snapshot (§2.4) | Instant tab switching | Medium |
| 8 | VM table pagination (§2.5) | Large customer DOM fix | Medium |
| 9 | Client-side callbacks (§2.6) | Eliminates server round-trips | Medium |
| 10 | API Cache-Control headers (§3.2) | Browser reuse across navigations | Medium |

---

## 6. Measuring success

Use the following metrics before and after each change:

| Metric | Tool | Baseline | Target |
|--------|------|----------|--------|
| Customer page TTFB p95 | k6 / Chrome DevTools | Measure baseline | < 800 ms warm, < 2 500 ms cold |
| Total page load time | Chrome DevTools Waterfall | Measure baseline | < 3 s warm |
| JS/CSS transfer size | Chrome DevTools Network | ~5-8 MB | < 500 KB (cached) |
| API JSON transfer size | Chrome DevTools Network | ~100-150 KB | < 25 KB (gzipped) |
| Gunicorn worker queue depth | Prometheus | Measure baseline | < 2 waiting requests |

See [PROD_ARCHITECTURE.md §7](PROD_ARCHITECTURE.md#7-observability) for Grafana dashboard configuration.
