# Project Standards – S3 Dashboards and Caching

This document defines the standards introduced with the S3 (IBM iCOS) dashboards. New features should follow these rules unless there is a strong reason not to.

---

## 1. Time Range and Trend Bucketing

- **Single global time range**: All dashboards use the shared `app-time-range` store.
- **Date presets**:
  - `1d`  → last day
  - `7d`  → last 7 days
  - `30d` → last 30 days
- **Trend bucket interval (S3 only)**:
  - Range ≤ 1 day   → **1 hour**
  - Range ≤ 7 days  → **6 hours**
  - Range ≤ 30 days → **12 hours**
  - Range > 30 days → **24 hours** (1 day)
- The helper `_s3_trend_interval_hours(start_ts, end_ts)` in `src/services/db_service.py` is the single source of truth for this logic.

---

## 2. Caching Behaviour

- **Global cache implementation**:
  - `src/services/cache_service.py` provides a **process-wide `TTLCache`**.
  - Default TTL is **20 minutes**, slightly longer than the main **15 minute** refresh cycle.
  - Cache access must always be **thread-safe** via the provided helper functions.
- **Scheduler**:
  - Implemented in `src/services/scheduler_service.py` with `APScheduler.BackgroundScheduler`.
  - `refresh_all_data()` is called every **15 minutes** for core dashboards (Overview, Datacenters, main compute views).
  - `refresh_s3_cache()` is called every **30 minutes** for S3 dashboards.
- **Write-through pattern** (S3 and all non-main tabs):
  - Scheduled jobs **never clear cache before fetching**.
  - New data is written using `cache.set(key, value)` **only after queries complete successfully**.
  - UI always sees the previous cache until new data is ready — no empty states caused by refresh.
  - This applies to:
    - S3 DC pools (`dc_s3_pools:*` keys)
    - S3 customer vaults (`customer_s3:*` keys)
    - Any future non-main tabs.
- **Main sections**:
  - Overview (`/`)
  - Datacenters (`/datacenters`, `/datacenter/<dc>`)
  - Virtualization tabs
  - These already use a warm‑and‑refresh model via `warm_cache()`, `warm_additional_ranges()`, and `refresh_all_data()`.

---

## 3. Visibility Rules for Panels

- **Datacenter pages**:
  - If a DC has **no S3 pools**, the **S3 tab must not be rendered**.
  - `service.get_dc_s3_pools(dc_code, tr)` returns an object with a `"pools"` list.
  - `src/pages/dc_view.py` checks `bool(s3_data["pools"])` before adding the S3 tab and panel.
- **Customer pages**:
  - If a customer has **no S3 vaults**, the **S3 tab must not be rendered**.
  - `service.get_customer_s3_vaults(customer_name, tr)` returns an object with a `"vaults"` list.
  - `src/pages/customer_view.py` checks `bool(s3_data["vaults"])` before adding the S3 tab and panel.
- **General rule for new panels**:
  - If there is no underlying asset for the current scope (DC or customer), the panel and its tab **must be hidden entirely**, not shown as an empty chart.

---

## 4. Pool and Vault Selection UX

- **Datacenter S3 pools**:
  - Selector: `dmc.MultiSelect` with id `s3-dc-pool-selector`.
  - Location: in the S3 DC panel header (`src/components/s3_panel.py`).
  - Behaviour:
    - All pools are selected by default.
    - User can select:
      - A single pool
      - Multiple pools
      - All pools
    - Metrics and trend charts aggregate **only over the selected pools**.
  - Callback:
    - Defined in `app.py` (`update_s3_dc_panel`).
    - Reads `app-time-range` and URL, calls `service.get_dc_s3_pools`, and renders `build_dc_s3_panel`.
- **Customer S3 vaults**:
  - Selector: horizontal `dmc.ChipGroup` with id `s3-customer-vault-selector`.
  - Location: in the S3 customer panel header (`src/components/s3_panel.py`).
  - Behaviour:
    - All vaults for the customer are selected by default.
    - User can select a single vault, multiple vaults, or all vaults.
  - Callback:
    - Defined in `app.py` (`update_s3_customer_panel`).
    - Reads `app-time-range` and `customer-select`, calls `service.get_customer_s3_vaults`, and renders `build_customer_s3_panel`.

---

## 5. SQL Query Patterns

- **Source tables**:
  - Datacenter S3: `public.raw_s3icos_pool_metrics`
  - Customer S3: `public.raw_s3icos_vault_metrics`
- **Location filters**:
  - Datacenter: `pool_name ILIKE '%DC13%'` etc. (pattern built from DC code).
  - Customer: `vault_name ILIKE '%<customer_name>%'`.
- **Grouping semantics**:
  - Pool metrics are stored **per vault–pool pair**, so rows must be **aggregated per pool and timestamp**.
  - Vault metrics are stored **per vault**, so rows must be aggregated per vault, timestamp.
- **Standard CTE patterns**:
  - Use `DISTINCT ON` or row-numbering to get **latest / first** records.
  - Aggregate per timestamp first, then deduplicate:
    - DC pools: `POOL_LATEST`, `POOL_FIRST_LAST`, `POOL_TREND_TEMPLATE`.
    - Customer vaults: `VAULT_LATEST`, `VAULT_FIRST_LAST`, `VAULT_TREND_TEMPLATE`.
- **Shared query module**:
  - All S3 queries live in `src/queries/s3.py`.
  - New S3‑related queries should be added there, following the existing naming style.

---

## 6. Data Structures Returned by S3 Service

### 6.1 Datacenter S3 (`get_dc_s3_pools`)

Returned object shape:

- `pools`: `list[str]`
- `latest`: `dict[pool_name, {"usable_bytes": int, "used_bytes": int, "timestamp": datetime}]`
- `growth`: `dict[pool_name, {"first_used_bytes": int, "last_used_bytes": int, "delta_used_bytes": int, "first_timestamp": datetime, "last_timestamp": datetime}]`
- `trend`: `list[{"bucket": datetime, "pool": str, "usable_bytes": int, "used_bytes": int}]`

### 6.2 Customer S3 (`get_customer_s3_vaults`)

Returned object shape:

- `vaults`: `list[str]`
- `latest`: `dict[vault_name, {"vault_id": int, "hard_quota_bytes": int, "used_bytes": int, "timestamp": datetime}]`
- `growth`: `dict[vault_name, {"vault_id": int, "first_used_bytes": int, "last_used_bytes": int, "delta_used_bytes": int, "first_timestamp": datetime, "last_timestamp": datetime, "hard_quota_bytes": int}]`
- `trend`: `list[{"bucket": datetime, "vault": str, "used_bytes": int, "hard_quota_bytes": int}]`

All new code consuming S3 metrics should rely on these structures instead of re-querying the database directly.

---

## 7. Naming and Comments

- **Naming**:
  - All variables, functions, classes, and IDs must be named in **English**.
  - UI labels may be localised later, but the internal code always uses English naming.
- **Comments**:
  - Comments should explain **intent, constraints, and trade‑offs**, not restate obvious code.
  - Keep comments in **English** and focused on non-trivial logic (e.g. caching rules, aggregation semantics).

---

## See also

- [TOPOLOGY_AND_SETUP.md](TOPOLOGY_AND_SETUP.md) — microservice Redis cache, service boundaries, and how Dash `cache_service` relates to API-side caching.
