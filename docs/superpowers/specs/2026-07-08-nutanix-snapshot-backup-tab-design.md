# Nutanix Snapshot — Backup tab (DC view + Customer view)

**Date:** 2026-07-08
**Status:** Approved design → ready for implementation plan
**Owner:** Arca

## Özet (TR)

Grafana'da hâlihazırda gösterilen Nutanix snapshot verilerini (`nutanix_snapshot_schedule_metrics`)
GUI'nin **DC view** ve **Customer view** sayfalarındaki **Backup & Replication** tab'ına, diğer
vendor'lar (Zerto / Veeam / NetBackup) ile aynı desende yeni bir **"Nutanix"** alt-tab'ı olarak ekliyoruz.
Panel: KPI kartları + schedule-type dağılım grafiği + durum paneli + **sayfalı per-snapshot tablo** +
açılır **Missing Entities** bölümü. Tüm DC/müşteri atıfı (attribution) DB-native'dir; Grafana'nın
dahili IP→isim eşlemesine bağımlılık yoktur.

---

## 1. Motivation & scope

The Nutanix snapshot data is already collected into the datalake and visualised in two Grafana
dashboards ("Nutanix Snapshots All", "Nutanix Snapshots Missing Entities"). The platform GUI's
Backup & Replication tab already shows Zerto / Veeam / NetBackup but **not** Nutanix snapshots — and
the DC view already contains a disabled stub for it (`has_nutanix_backup = False`).

**In scope**
- New "Nutanix" sub-tab under the Backup & Replication tab in **DC view** and **Customer view**.
- Rich panel: KPI cards, schedule-type breakdown chart, status panel, paginated per-snapshot table,
  and a collapsible **Missing Entities** section (parity with both Grafana dashboards).
- New backend query module, `DatabaseService` methods, router endpoints, and `api_client` wrappers,
  following the existing backup-vendor pattern exactly.

**Out of scope**
- Job-statistics time-series section (the `build_job_stats_section` used by other vendors). Nutanix
  snapshots have no jobs/sessions table; the snapshot list itself is the content.
- Any change to Grafana dashboards or to the collector/NiFi ingestion.
- Modifying the customer-perspective aggregation payload (we use a dedicated endpoint instead — see §6).

---

## 2. Data source & facts (verified against the live DB)

Table: `public.nutanix_snapshot_schedule_metrics` (26 columns). Relevant columns:

| Column | Meaning / use |
|---|---|
| `collection_time` (timestamp) | **Per-row** scrape time (microsecond precision, NOT a batch marker). "Current state" = `DISTINCT ON (snapshot_id) … ORDER BY collection_time DESC` within a lookback window. |
| `nutanix_ip` (varchar) | Prism Element IP. Join key to inventory for DC attribution. |
| `protection_domain_name` (varchar) | Schedule / PD name, e.g. `Alisan_Lojistik-1Day_30RP`. Customer prefix source. |
| `state` (varchar) | e.g. `AVAILABLE`. |
| `missing_entities_entity_name` / `_entity_type` / `_cg_name` (text) | Populated only for missing-entity rows → Missing Entities section. |
| `size_in_bytes` (bigint) | Snapshot size. |
| `vm_names` (text) | Comma-joined `Customer-VMName` list. Customer prefix + protected-VM count source. |
| `schedule_type` (varchar) | `DAILY` / `WEEKLY` / `MONTHLY`. |
| `schedule_local_max_snapshots` (int) | Retention policy (fallback: parse `\d+RP` from PD name). |
| `snapshot_create_time_usecs` (bigint) | epoch µs → `to_timestamp(x/1e6)`. |
| `snapshot_expiry_time_usecs` (bigint) | epoch µs → expiry. |
| `schedule_start_times_in_usecs` (bigint) | epoch µs → "Start time" column. |
| `snapshot_id`, `schedule_id` (varchar) | `snapshot_id` = stable physical-snapshot identity (dedup key). |

**Volume (measured):** ~1,200 distinct `snapshot_id` and ~128 distinct `protection_domain_name`
per Nutanix IP over ~12h; a DC (~16 IPs) can hold tens of thousands of physical snapshots.
`SELECT count(*)` on the full table times out → **every query MUST be `collection_time`-bounded**
and scoped to the DC's IP set first.

### Attribution (both DB-native)

**DC ← nutanix_ip.** There is no IP column in `nutanix_cluster_metrics`; the IP→cluster→DC link is
via the discovery inventory:
```
discovery_nutanix_inventory_cluster.nutanix_uuid = 'nutanix-' || snapshot.nutanix_ip
```
`discovery_nutanix_inventory_cluster.name` carries the DC code prefix (e.g. `DC13-G17-HYBRID`),
matching the existing Nutanix DC convention (`cluster_name LIKE '%DC13%'`). Verified 1:1 (one Prism
Element IP → one cluster). This `name` is also the "Cluster" column shown in the table.

**Customer ← protection_domain_name / vm_names.** Customer = substring before the first `-`
(customer names use `_`, schedule detail is `-`-separated), e.g. `Alisan_Lojistik-1Day_30RP` →
`Alisan_Lojistik`. Some rows do not parse cleanly (`Capa_Medikal_1Days_7RP`, generic `1Days_10RP`);
these are the "Missing Entities" of the Grafana Support dashboard and are surfaced in the Missing
Entities section rather than dropped.

---

## 3. Backend

### 3.1 `services/datacenter-api/app/db/queries/nutanix_snapshot.py` (new)
Time-bounded SQL constants, all scoped to a DC's IP set:
- `DC_NUTANIX_IPS` — resolve a DC's Nutanix IPs from `discovery_nutanix_inventory_cluster`
  (`name LIKE '%dc_code%'`, derive `ip = replace(nutanix_uuid, 'nutanix-', '')`), plus the
  `ip → cluster_name` map for the table's "Cluster" column.
- `SNAPSHOTS_LATEST` — `DISTINCT ON (snapshot_id)` over the window, `WHERE nutanix_ip = ANY(%s)`,
  ordered `snapshot_id, collection_time DESC`. Used for KPIs and (post-filter) the table.
- Aggregation and paging/search are applied in the service layer (Python) over the latest-per-snapshot
  set, mirroring how the vendor panels aggregate in Python. Missing-entities = rows with
  `missing_entities_entity_name` not null.

### 3.2 `services/datacenter-api/app/services/dc_service.py`
- `_resolve_dc_nutanix_ips(dc_code, start, end) -> (ips, ip_to_cluster)`
- `_fetch_dc_nutanix_snapshots(dc_code, start, end) -> dict` — latest-per-snapshot rows enriched with
  cluster name + parsed customer + µs→datetime + retention; returns rows, KPI totals, schedule-type
  breakdown, state breakdown, missing-entities list.
- `get_dc_nutanix_snapshots(dc_code, time_range) -> dict` — cached wrapper (same cache/SWR helper the
  vendor methods use).
- **Minimum lookback:** snapshot collection is sparse (measured: 0 rows in a 2h window for an active
  IP). Unlike capacity metrics, "current snapshots" must not vanish when the user picks a narrow UI
  range. The fetch therefore expands the effective window to at least a floor (e.g. last 48h) —
  `effective_end = end`, `effective_start = min(start, end - 48h)` — before the `DISTINCT ON
  (snapshot_id)` de-dup, so the panel reflects the latest scrape regardless of the UI time range.
- `_fetch_customer_nutanix_snapshots(customer, start, end)` / `get_customer_nutanix_snapshots(...)` —
  same fetch but filtered by customer prefix (no DC-IP restriction; scan bounded by window + prefix).

### 3.3 Router `services/datacenter-api/app/routers/datacenters.py`
Mirror the `network/interface-table` + `network/interface-export` pagination pattern:
- `GET /datacenters/{dc_code}/backup/nutanix` — KPI totals + breakdowns + first page.
- `GET /datacenters/{dc_code}/backup/nutanix/table` — `page`, `page_size` (≤200), `search`,
  optional `schedule_type` / `customer` filters → paged rows + `total`.
- `GET /datacenters/{dc_code}/backup/nutanix/missing` — missing-entities rows (paged).
- `GET /customers/{customer}/backup/nutanix` — customer-scoped equivalent (KPIs + rows; customer
  tables are small, single page acceptable).

Response models added to `models/schemas.py` as needed (or `dict[str, Any]` like the vendor endpoints).

### 3.4 `src/services/api_client.py`
- `get_dc_nutanix_snapshots(dc_code, tr)` → `…/backup/nutanix`
- `get_dc_nutanix_snapshot_table(dc_code, tr, page, page_size, search, ...)` → `…/backup/nutanix/table`
- `get_customer_nutanix_snapshots(customer, tr)` → `/customers/{customer}/backup/nutanix`
- `refresh_dc_nutanix_snapshots_cache(dc_code)` → `POST …/backup/nutanix/refresh` (mirrors
  `refresh_dc_backup_jobs_cache`), for the panel's "Yenile" (live-SQL) button.
- All wrappers go through `_api_cache_get_with_stale`; cache keys per §9.

> **Caching is a first-class requirement here — see §9.** This feature must match the platform's
> existing cache rigor (shared Redis, no-stale, cross-pod single-flight, warm). Do not ship an
> uncached or naively-cached path.

---

## 4. Frontend panel — `src/components/backup_panel.py`

New `build_nutanix_snapshot_panel(data, ...)` reusing this file's `_kpi_card`, `_gauge_card`,
`_pie_card`, `smart_bytes`, and the `nexus-card` / `dc-premium-table` styling. Same 3-column header
grid as the vendor panels:

1. **KPI cards (2×2):** Total Snapshots · Total Size (`smart_bytes`) · Protected VMs · Missing Entities.
2. **Chart (replaces the capacity gauge):** donut of snapshots by `schedule_type`
   (DAILY / WEEKLY / MONTHLY) — snapshots have no "capacity" to gauge.
3. **Status panel:** `state` breakdown (AVAILABLE vs other) + count expiring within N days
   (from `snapshot_expiry_time_usecs`).
4. **Snapshot table (paginated, per-snapshot):** columns
   `Nutanix IP · Cluster · Customer · Schedule (PD) · VMs · Entity Type · Schedule Type ·
   Retention · Start time · Snapshot Create Time · Snapshot Expiry Time · Size`.
   Server-side paging via the `…/table` endpoint (search box + page controls, `dc-premium-table`).
5. **▸ Missing Entities (n):** collapsible section — table of
   `Missing Entity · Entity Type · Customer · Schedule · Create · Expiry · Size` (Grafana Support parity).

Panel is agnostic to DC vs customer scope; both pass the same payload shape.

---

## 5. DC view wiring — `src/pages/dc_view.py`

- Add `nutanix` to the backup eager batch (`parallel_execute` near line 5241) via
  `api.get_dc_nutanix_snapshots(dc_id, tr)`.
- Set `has_nutanix_backup = bool(nutanix_data.get("rows"))` (replace the hardcoded `False` at 5338);
  include in `has_backup`.
- Add to `compute_has_backup` (line 5027) so the Backup tab lights up when only Nutanix data exists.
- Fill the already-present Nutanix `TabsPanel` (the `dmc.TabsTab("Nutanix", value="nutanix")` stub at
  5539) with `build_nutanix_snapshot_panel(nutanix_data, ...)`.
- Extend `_backup_rows_for_export` / export sheets to include a "Nutanix Snapshots" sheet.

Table pagination callback: a `dc_view_callbacks.py` callback (guarded by active-tab like the existing
backup job callbacks) that reads page/search and calls `get_dc_nutanix_snapshot_table`.

## 6. Customer view wiring — `src/pages/customer_view.py` (Approach A)

- Add a "Nutanix" entry to `_build_backup_tabs` (line 2060), fed by a **dedicated** call to
  `get_customer_nutanix_snapshots(customer, tr)` — **not** threaded through the heavy
  customer-perspective payload (lower risk, decoupled). Loads within the already-async backup tab.
- Reuse `build_nutanix_snapshot_panel` with the customer-scoped payload. Customer tables are small,
  so a single page (or client-side paging) is sufficient; server paging optional.
- Include Nutanix rows in the customer export path alongside the other vendors.

## 7. Testing

Unit tests for the pure/testable pieces, following `tests/test_backup_panels.py`,
`tests/test_dc_view_has_backup.py`, `tests/test_api_client_backup_jobs.py`:
- customer-prefix parse (clean, underscore-schedule, generic-no-customer cases);
- `usecs → datetime` conversion + retention parse/fallback;
- DC-IP resolution mapping (`nutanix-<ip>` ↔ cluster name/DC);
- aggregate KPIs (totals, schedule-type breakdown, missing-entities count) over a fixture set;
- `has_nutanix_backup` gating and `build_nutanix_snapshot_panel` structure (renders without error,
  empty-data path).

## 8. Risks & mitigations

- **Big-table scans / timeouts** → always window-bound + scope to the DC IP set first; reuse the
  vendor cache + SWR so cold cost is paid once. Server-side paging keeps payloads small.
- **Imperfect customer parse** → surfaced in Missing Entities, not silently dropped; customer-view
  filter uses `prefix = customer` so unmatched rows simply don't appear for that customer.
- **Inventory gaps** (passive/DR Prisms without active cluster inventory) → those IPs resolve to no DC
  and are excluded from DC view; logged, not fatal. Customer view still shows them (IP-independent).
- **DC-code convention drift** → reuse the exact `LIKE '%dc_code%'` approach already used by
  `queries/nutanix.py`, so behaviour matches existing Nutanix tabs.

---

## 9. Caching, single-flight & warm (cache rigor)

Caching is a **hard requirement**, not an afterthought. The panel fans out over a very large table,
so an uncached or per-request path would hammer the slow remote DB. We reuse the platform's existing
two-layer cache exactly, with the more rigorous variant (single-flight + stale-TTL) because the
`DISTINCT ON (snapshot_id)` scan is the expensive step.

### 9.1 Backend (`datacenter-api`, `cache_service`) — compute the heavy set ONCE

- **Base set, single-flight + stale-TTL.** `get_dc_nutanix_snapshots` computes the full DC
  latest-per-snapshot set (enriched: cluster name, parsed customer, µs→dt, retention, KPIs,
  schedule-type & state breakdowns, missing-entities list) via
  `cache.run_singleflight(key, factory, ttl)` and stores it with `cache.set_with_stale(key, val,
  fresh_ttl, stale_ttl)`. Key: `dc_nutanix_snap:{dc_code}:{start}:{end}`. The expensive SQL runs
  **once per (DC, effective-window)** even under a concurrent stampede — matching the compute path at
  `dc_service.py:1039–1048` (`_set_compute_cached` / `run_singleflight`), NOT the plain `cache.get/set`
  used by the vendor pool endpoints.
- **Pagination derives from the cached base set in-process** (slice + `search`/`schedule_type`
  filter in Python), then caches the page result under a page-scoped key
  `dc_nutanix_snap_tbl:{dc}:{start}:{end}:p={page}:ps={size}:q={search}` (matching the
  `network/interface-table` per-page key shape). ⇒ page N never re-runs the `DISTINCT ON`.
- **Inventory IP→cluster/DC map cached separately** under `nutanix_ip_dc_map` with a **long TTL
  (~6h)** — the discovery inventory changes rarely, so we don't re-scan it on every snapshot fetch
  (analogous to the existing `_brocade_switch_dc_cache` / `_ibm_storage_ip_dc_cache` maps).
- **Customer variant:** `cust_nutanix_snap:{customer}:{start}:{end}`, same single-flight + stale-TTL.
- **Refresh endpoint** `POST /datacenters/{dc}/backup/nutanix/refresh` → `cache.delete_prefix
  ("dc_nutanix_snap:{dc}:")` + `delete_prefix("dc_nutanix_snap_tbl:{dc}:")` so the next read runs live
  SQL. Mirrors the existing `/backup/jobs/refresh` handler.
- **Failure = last-good, never crash:** wrap fetch in the same `(OperationalError, PoolError)` guard
  the vendor `get_dc_*` methods use; on hard failure return the empty payload (DB hiccup never breaks
  the tab).

### 9.2 Frontend (`api_client`) — no-stale + cross-pod single-flight

- Every wrapper returns through `_api_cache_get_with_stale(ck, fetch, empty)` — inheriting: **no-stale**
  (never serve a stale entry; refetch, fall back to last-good only on hard failure), **per-process
  single-flight**, and the **cross-pod Redis lock** (`try_acquire` / `_wait_for_shared_result`) that
  kills the multi-pod stampede.
- Keys: `api:dc_nutanix_snap:{enc}:{tr}`, `api:dc_nutanix_snap_tbl:{enc}:{tr}:p{page}:q{search}`,
  `api:cust_nutanix_snap:{enc}:{tr}` — all via `_serialize_tr_cache_key(tr)` and `anchor_latest`-aware,
  exactly like `get_dc_netbackup_pools`.
- `refresh_dc_nutanix_snapshots_cache` also calls `cache_service.delete_prefix("api:dc_nutanix_snap")`
  on the GUI side so the "Yenile" button forces an end-to-end live run (GUI cache → backend cache →
  SQL), matching `refresh_dc_backup_jobs_cache`.

### 9.3 Warm scheduler (`scheduler_service`) — first load is instant

- Add a `warm_dc_nutanix_snapshots()` job mirroring `_warm_dc_network_for_range`: for each DC ×
  `cache_time_ranges` (default + the standard warmed ranges), call `api.get_dc_nutanix_snapshots(dc, tr)`
  and `api.get_dc_nutanix_snapshot_table(dc, tr, page=1, page_size=50)` **inside `warm_mode`** so the
  cache is populated without ever serving stale, and pre-warm `nutanix_ip_dc_map`.
- Register it alongside the existing initial + periodic warm steps (same cadence as the network warm),
  so cold-cache freezes (the "yüklenmiyor" class of issue) never surface on this tab.

### 9.4 Effective-window interaction with cache keys

The 48h minimum-lookback (§3.2) is applied **before** key derivation, so a narrow UI range and the
default range that both floor to the same effective window share one cache entry (no needless misses),
while still keying distinctly when the user genuinely widens the range.
