# Datalake Platform GUI — End-to-End Architecture Audit

Audit date: 2026-05-12
Branch: `feature/customer-view-availability` (HEAD `a4fdc19`)
Auditor: senior software architect role / static code analysis

## Deliverables in this folder
| File | Purpose |
|------|---------|
| `frontend_flows.csv` | Every UI action → callback → api_client fn → endpoint (165 rows). |
| `backend_lineage.csv` | Every backend endpoint → router → service → DB query → tables (125 rows). |
| `end_to_end_master.csv` | One row per ui_action → endpoint chain with response/error/cache/auth (100+ rows). |
| `gaps_and_actions.md` | Missing mappings, low-confidence rows, risks, validation checklist, prioritized action plan, coverage report. |
| `drawio_blueprint.md` | 4-page Draw.io build recipe (UI Map, API Map, Backend Lineage, Controls) with node lists, edge lists, color standard, legend. |
| `README.md` (this file) | Executive summary + coverage stats. |

## Executive summary (12 takeaways)

1. **Single Dash SPA**, routes resolved on the client at `app.py:541-619`. 13 top-level pathnames (`/`, `/datacenters`, `/datacenter/{id}`, `/dc-detail/{id}`, `/global-view`, `/availability-annual`, `/customers`, `/customer-view`, `/query-explorer`, `/crm/sellable-potential`, `/region-drilldown`, `/login`, `/settings/...`). All page builders accept a `tr` (time-range) parameter from `app-time-range` store, so every route re-renders on time-range change.

2. **Frontend talks to backend through one façade**: `src/services/api_client.py` (78 wrapper fns), plus `src/services/admin_client.py` (30 fns for admin-api with local fallback) and `src/services/auranotify_client.py` (5 fns calling AuraNotify directly). Every wrapper goes through `_api_cache_get_with_stale` for stale-while-error fallback.

3. **JWT propagation is in the request path**: Flask login populates `g.auth_user_id` via auth middleware; `api_client._auth_headers()` (api_client.py:183-197) creates a per-request HS256 JWT (`src.auth.api_jwt.create_api_token`) and adds it to every backend call. Every backend service guards routes with `verify_api_user`/`verify_api_jwt` (currently `API_AUTH_REQUIRED=false` by default).

4. **5 backend microservices** in `services/`:
   - **datacenter-api**: 42 endpoints — biggest service; covers dashboards, DC details, compute (classic/hyperconv), SAN/Brocade, Storage (IBM), Network (Zabbix), Backup (NetBackup/Zerto/Veeam), S3 pools, Physical Inventory, SLA proxy, Sales Potential v1/v2.
   - **customer-api**: 17 endpoints — customer list/resources/S3 vaults, ITSM (summary/extremes/tickets), Sales (summary/items/efficiency/catalog-valuation/efficiency-by-category), CRM Aliases CRUD.
   - **crm-engine**: 28 endpoints — sellable-potential summary/by-panel/by-family, metric-tags + snapshots, Panels/Infra-Sources/Ratios/Unit-Conversions CRUD, Config (thresholds/price-overrides/variables/discovery-counts), Service-Mapping CRUD.
   - **query-api**: 1 endpoint + 38 registry keys — dynamic query runner used by Query Explorer.
   - **admin-api**: 31 endpoints — users, roles, permissions, role matrix, teams + members, LDAP search/test/configs/mappings, audit log.

5. **Data stores**: `bulutlake` (Postgres — raw_*/discovery_* metrics tables, the data warehouse), `webui-db` (Postgres — gui_panel_*, gui_crm_*, discovery_netbox_inventory_*, gui_unit_conversion, gui_price_override, gui_calc_config, etc.), `auth-db` (Postgres — users/roles/teams/ldap_config/audit_log), Redis (3 logical DBs: dc=0, customer=1, crm=2). All API services optionally degrade to in-memory TTLCache when Redis is unavailable.

6. **Caching is a 4-tier stack**: (1) Per-Gunicorn-worker in-memory LRU `cache_service.OrderedDict` (`src/services/cache_service.py`, MAX_SIZE=2048) — used by api_client; (2) the same store as a stale-while-error fallback in `_api_cache_get_with_stale`; (3) per-service Redis (TTL 900s dev / 3600s prod); (4) backend in-process TTLCache fallback. Cache key namespacing is consistent: `api:<area>:<encoded args>` on the GUI side; `customer_assets:*` / `customer_s3:*` / `cluster_arch_map:*` on customer-api; `dc_details:*` on datacenter-api; `sellable_snapshot:*` on crm-engine.

7. **Non-click warming is extensive**: 11 APScheduler jobs in `src/services/scheduler_service.py` (start_scheduler) cover DB refresh (15m), SLA (60m), DC long-range warm (startup), customer warm (15m), AuraNotify (15m), S3 (30m), Backup (30m), Physical Inventory (30m). On `/global-view` first render + a 900s interval, `global_view_prefetch.trigger_background` runs a 2-phase warm (critical summary/details/racks/figures, then per-rack devices, max 12 workers). Pin clicks invoke `warm_dc_priority(dc_id)`; entering building/floor_map mode pauses Phase 2 fetches.

8. **One nontrivial intra-service coupling**: `crm-engine.sellable_service.compute_summary` reads `dc_details:*` keys directly from datacenter-api's Redis db=0, and falls back to HTTP `GET /api/v1/datacenters/{dc}/compute/{kind}` when cluster CSV is provided. This is the only known cross-service HTTP call from a backend (apart from sla_service's external SLA + AuraNotify HTTPs from datacenter-api).

9. **AuraNotify is accessed two ways**: directly from the GUI for *customer downtimes* (`src/services/auranotify_client.py` per-worker startup warm + scheduler 15m refresh + on-demand in customer-view) **AND** via the datacenter-api `/api/v1/sla/datacenter-services` proxy for *DC SLA group items* (`sla_service.get_dc_services_availability` with Redis cache). This dual path was flagged in `gaps_and_actions.md M-04`.

10. **Settings PUT/DELETE flows invalidate the GUI LRU by prefix but not the backend Redis**. The "Settings → Cache Refresh" button (FE-107) sends `POST /api/v1/admin/cache/refresh` to datacenter-api + customer-api + crm-engine, and additionally clears the GUI's `_api_response_cache`. This is the only path that clears backend Redis end-to-end. Without that click, edits to thresholds/ratios/etc. only take effect on the **next scheduler tick** for cached sellable values — see `gaps_and_actions.md R-01`.

11. **Static pages and split-brain callbacks**: `dc_detail.py`, `floor_map.py`, `region_drilldown.py`, `login.py` register zero local Dash callbacks. `floor_map`'s rack-click handler lives in `app.py:1340` rather than in the page module — a refactor target. Also, two routes (`/dc-detail/{id}` and `/datacenter/{id}`) exist for the same DC concept; reconcile.

12. **Operational gaps to land before production hardening**: (a) scheduler outbound HTTP has no JWT (R-02), (b) `_client_crm` is a process-shared httpx.Client (R-08) racy under gthread workers, (c) Query Explorer Save/Add can write arbitrary SQL through `query_overrides.json` without admin gating (R-07), (d) admin-api is not in `k8s/ingress.yaml` (R-06), (e) per-worker AuraNotify cache is not shared across Gunicorn workers (R-03). See `gaps_and_actions.md §3` and §5 for the ordered remediation plan (S-01..S-15).

## Coverage Report

### Frontend coverage (98 distinct UI actions + 8 background flows)
| Page | Flows | Confidence |
|------|------:|-----------|
| shell + app.py global | 38 | high |
| home | 9 | high |
| datacenters | 3 | high |
| dc_view (incl. dc_detail) | 35 | high |
| global_view | 17 | high (FE-105 medium) |
| customer_view + customers_list | 17 | high |
| query_explorer | 9 | high |
| crm_sellable_potential | 4 | high |
| availability_annual | 2 | high |
| login + region_drilldown | 2 | medium/low |
| settings/dashboard | 1 | high |
| settings/iam/* | 16 | high (LDAP CRUD partial) |
| settings/integrations/* (CRM + AuraNotify) | 22 | high (overview/auranotify medium) |
| settings/crm_service_mapping | 4 | high |

Pages with zero callbacks (verified): dc_detail, floor_map, region_drilldown, login.

### Backend coverage (per service)
| Service | Endpoints | Covered | % |
|---------|----------:|--------:|---:|
| datacenter-api | 42 | 42 | 100% |
| customer-api | 17 | 17 | 100% |
| crm-engine | 28 | 28 | 100% |
| query-api | 2 (+38 registry keys) | 2 (+38) | 100% |
| admin-api | 31 | 31 | 100% |
| AuraNotify (external) | 3 inventoried | 3 | 100% (client-only; no GUI wrapper for downtimes) |
| Flask /auth/* | 2 inferred | 2 | low confidence |

### End-to-end status
- complete: 91
- partial: 8 (one productpricelevels-empty fallback, four assumption-tier wirings, three LDAP CRUD callback unknowns)
- missing: 1 (FE-156 settings/iam/auth_settings)

### Confidence summary
- frontend_flows.csv: 152 high / 8 medium / 5 low (across 165 rows)
- backend_lineage.csv: 122 high / 2 medium / 1 low (across 125 rows)

## How to consume this audit

1. Engineers wanting "what does this button call?" — open `frontend_flows.csv` and grep on `page`/`callback_fn`/`ui_action`.
2. Backend / SRE wanting "what powers this endpoint?" — open `backend_lineage.csv` and grep on `endpoint` or `main_tables_or_registry_keys`.
3. Product / QA wanting a flow contract for a feature — open `end_to_end_master.csv` and filter by `ui_action` keyword. Status `complete` means traceability from click to DB.
4. Diagram author — follow `drawio_blueprint.md` to build the Draw.io file. CSVs can be pasted directly via Draw.io's "Insert from CSV".
5. Engineering lead — read `gaps_and_actions.md` for the ordered S-01..S-15 plan and the 15-flow validation checklist.

## Limitations & assumptions

- This is a static-code-only audit. No tests were run. Runtime SLAs (Redis TTL effectiveness, scheduler timing under load) are not verified.
- LDAP save/mapping CRUD wiring on the Settings page (`src/pages/settings/integrations/ldap.py` body) was not deeply read; relevant rows marked partial with confidence=medium.
- AuraNotify settings page (`src/pages/settings/integrations/auranotify.py`) was not deeply read.
- Inline SQL bodies in admin-api routers were not enumerated past the function level. Where the audit says "inline SQL", it means the query lives in the router/service file itself rather than a separate `db/queries/` module.
- Flask `/auth/*` route signatures inferred from app.py's blueprint registration — `src/auth/routes.py` was not read in this pass.

All other rows are based on direct file reads or grep-confirmed references.
