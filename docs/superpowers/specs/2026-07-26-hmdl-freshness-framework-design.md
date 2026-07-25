# HMDL Freshness Framework — Design Spec

**Date:** 2026-07-26
**Task:** TASK-69 (HMDL Kontrolü) — scale the automation/data health monitor from a few
hardcoded sources to the whole platform.

## Context

The platform has **167 collected tables** (public schema) carrying a freshness-like column
(raw 99, discovery 25, ibm 15, zabbix 8, nutanix 7, loki 5, vmware 4, …). The current
Automation Health monitors only 4 automation log-tables + 6 hand-picked data tables. The user
wants comprehensive coverage of both **automations** and **data sources**, done the same
scalable way.

**Landscape reality (live, 2026-07-26)** — pure auto-discovery would be too noisy:
- Legitimately **deprecated / replaced** tables read as "dead": `loki_platforms` (404d),
  `loki_device_types` (177d), `loki_devices/locations/racks` (104d) — superseded by `discovery_*`;
  `raw_ibm_storage_ports/vdisk_dumps` (456d); `nutanix_snapshot_schedule` (422d).
- **Dead pipelines** worth surfacing: all `*_performance_metrics` (vmware/nutanix/ibm) ~60d;
  `raw_panduit_pdu_*` ~61d; `zabbix_network_*` ~75d; many `raw_vmware_*` config/perf ~135d.
- **Active incident:** `raw_vmware_datastore_metrics_agg` / `_host_mount` ~9.5d (= Overview storage 0%).

So: **Hybrid** (chosen) — auto-discover everything, then a curated config excludes deprecated
tables and overrides labels/thresholds. New tables appear automatically; noise is curated out.

## Goals / Non-goals

- **Goal:** a platform-wide freshness view: auto-discovered + curated, grouped by family, with
  per-family fresh/stale/dead rollups and drill-down; automations use the same registry pattern;
  the sidebar badge + overview banner reflect data-freshness too.
- **Non-goal:** fixing the dead flows (ops/NiFi/AWX). No per-row data validation. No writes.
  Not a perfect classification of all 167 tables on day one — the curation config is seeded from
  what we know and is **team-refinable**.

## Design

### 1. Freshness registry (the "hybrid" config) — `services/hmdl-api/app/services/freshness_registry.py`

Pure, no DB. Declares how discovery + curation behave:

- `FRESHNESS_COLUMNS` — preference-ordered candidate columns:
  `["collection_time","collection_timestamp","checked_at","processed_at","finished_at",
    "check_time","last_seen_at","last_observed","timestamp","time","last_updated"]`
- `EXCLUDE` — table names / prefixes for deprecated or non-monitored tables. **Seeded** with the
  known-legacy set (all `loki_*` non-`discovery_loki_*`: `loki_platforms`, `loki_device_types`,
  `loki_devices`, `loki_locations`, `loki_racks`; `nutanix_snapshot_schedule`;
  `raw_ibm_storage_ports`, `raw_ibm_storage_vdisk_dumps`). Editable via env/config.
- `FAMILY_OF(table)` — maps a table to a friendly platform family (VMware / Nutanix / IBM /
  Zabbix / NetBox / Loki / Panduit / Other) by name prefix.
- `OVERRIDES` — per-table `{label?, family?, warn_hours?, dead_hours?}`.
- `DEFAULT_WARN_HOURS` / `DEFAULT_DEAD_HOURS` (26 / 50), with optional per-family defaults
  (e.g. inventory/discovery tables update less often → looser; metrics → tighter).
- Pure helpers: `is_excluded(table)`, `resolve(table, cols) -> spec|None` (picks the freshness
  column + applies family/label/thresholds), fully unit-testable.

### 2. Discovery + compute — `services/hmdl-api/app/db/queries/freshness.py`

- `discover_specs(cursor) -> list[spec]`: query `information_schema` for public BASE tables with a
  freshness column; drop excluded; `registry.resolve()` each → specs `{table, column, label,
  family, warn_hours, dead_hours}`.
- `compute_freshness(cursor) -> {families: [...], counts: {...}, generated_at}`:
  for each spec, `SELECT EXTRACT(EPOCH FROM (now() - max(col)::timestamptz))/3600 …` → age
  (clamp negatives to 0, as today) → `ah.build_data_source_row`; group rows by family; per-family
  fresh/stale/dead counts + overall `data_counts`.

### 3. Performance — background snapshot + cache (mandatory)

Maxing ~120 (post-exclude) tables exceeds the HTTP timeout, so this MUST NOT run on the request
path:
- A **background refresher** (daemon thread started on hmdl-api boot, like other services' warm
  threads) computes `compute_freshness()` every `HMDL_FRESHNESS_REFRESH_MIN` (default 30 min)
  and stores the snapshot in the shared cache under `hmdl_freshness_snapshot`.
- The endpoint serves the **cached snapshot** (instant). If none yet (cold boot), it returns
  `status: "computing"` with empty families so the UI shows "hesaplanıyor…" instead of blocking.
- Tables whose freshness column is unindexed are the slow ones; the background model makes their
  cost invisible to users. (A follow-up can add indexes; out of scope here.)

### 4. Automations as the same registry

Refactor the 4 hardcoded automations in `queries/automation_health.py` into an
`AUTOMATION_SPECS` list (in the registry module): `{key, label, cadence, schema, table, column,
warn_hours, dead_hours}`. `build_automation_health()` iterates the list. New automations are
added by one config entry. Behaviour and existing output shape unchanged.

### 5. Endpoint

Extend `GET /api/v1/collectors/automation-health` response:
- `data_families: [{ family, counts:{fresh,stale,dead,unknown}, sources:[AutomationRow…] }]`
- `data_counts: {fresh,stale,dead,unknown,alert}` (overall across families)
- `data_snapshot_at`, `data_status` ("ok" | "computing")

(The flat `data_sources` from the first cut is replaced by the grouped `data_families`.)

### 6. GUI — `hmdl_automation_health.py`

- Replace the flat "Data Collection Freshness" grid with **family rollup cards** (VMware, Nutanix,
  IBM, Zabbix, NetBox, Loki, Panduit …), each showing `fresh/stale/dead` counts and a colored
  bar; expandable drill-down lists the tables (label, last data, age, status) via `_automation_card`.
- Headline alert = automations alert + data alert.
- **Sidebar badge + overview banner** (`hmdl_sync_ui.staleness_alert_banner` and the sub-nav
  badge) include `data_counts.alert` so a data-only outage (e.g. datastore) turns them red.
- "computing" state renders a spinner/hint.

## Testing (TDD)

- registry: `is_excluded` (legacy loki_* excluded), `resolve` (column preference, family, overrides,
  default thresholds), `FAMILY_OF`.
- discovery: `discover_specs` filters excluded + resolves (mock information_schema rows).
- compute: `compute_freshness` groups by family + counts (mock pool.fetch_one), negative-age clamp.
- background refresher: writes snapshot to cache; endpoint serves cached / "computing" when cold.
- automations registry: build_automation_health still yields the same 4 rows from AUTOMATION_SPECS.
- GUI: family rollup cards render; drill-down; alert = automations+data; sidebar badge reflects data.

## Risks

- **Curation accuracy:** the seed EXCLUDE/threshold config reflects what we know (legacy loki_*,
  defaults); the team refines it over time via config. Mis-curation only affects noise, never data.
- **Perf/indexes:** mitigated by the background snapshot; unindexed huge tables cost only background
  time. Add indexes as a follow-up if refresh is too slow.
- **Text timestamps** (`last_observed` on some discovery/loki tables): cast `::timestamptz` in the
  age SQL; skip/mark unknown if the cast fails.
- **Scope:** larger than the first cut; if needed we phase it — (P1) registry+discovery+compute+
  cache+endpoint, (P2) GUI rollup + sidebar wiring, (P3) automations refactor.
