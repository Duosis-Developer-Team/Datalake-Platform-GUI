# Draw.io Blueprint — Datalake Platform GUI

This file gives a step-by-step recipe for producing a 4-page Draw.io diagram from
the inventories in `frontend_flows.csv`, `backend_lineage.csv`, `end_to_end_master.csv`.

## Page count
Build 7 pages, all in the same `.drawio` file:
1. **UI Map** — high-level page navigation + sidebar.
2. **API Map** — every UI flow → api_client fn → endpoint.
3. **Backend Lineage** — endpoint → router → service → DB tables.
4. **Controls** — cache layers, schedulers, auth, external integrations.
5. **Data Model (ERD)** — auth-db / webui-db / bulutlake table relationships.
6. **Observability flow** — OTEL traces/logs path, Prometheus scrape, Loki aggregation.
7. **Security boundaries** — CORS, JWT path, secrets flow, rate-limit (missing).

## Color & shape standard (apply to every page)

| Element type | Shape | Fill | Stroke | Notes |
|--------------|-------|------|--------|-------|
| Page route (URL) | Rounded rectangle | `#E0F2FE` | `#0369A1` | One per pathname. |
| Page module (build_*) | Rectangle | `#FEF3C7` | `#B45309` | The Python builder fn. |
| Callback | Hexagon | `#F3E8FF` | `#7C3AED` | `@app.callback` or `@callback`. |
| api_client fn | Parallelogram | `#DCFCE7` | `#15803D` | The `src/services/*.py` HTTP wrapper. |
| Backend endpoint | Rectangle (rounded right) | `#FFE4E6` | `#BE123C` | `METHOD /path`. |
| Backend service fn | Rectangle | `#FFEDD5` | `#C2410C` | dc_service / customer_service / etc. |
| DB table | Cylinder | `#E0E7FF` | `#3730A3` | `bulutlake`/`webui-db`/`auth-db`. |
| Redis instance | Cylinder (dashed) | `#FCE7F3` | `#9D174D` | per-service db number. |
| External system | Cloud | `#F3F4F6` | `#374151` | AuraNotify, SLA, LDAP/AD, Datalake PG. |
| Scheduler job | Diamond | `#FEF9C3` | `#A16207` | APScheduler entries. |
| User click | Stick figure + arrow | `#F1F5F9` | `#1F2937` | start node. |
| Auth boundary | Container (subdued) | `#F9FAFB` border-dashed | `#6B7280` | groups protected endpoints. |
| Cache layer | Container (light blue) | `#EFF6FF` | `#1D4ED8` | groups LRU/Redis. |

Edge colors:
- **black solid** = synchronous request (HTTP / fn call).
- **green dashed** = cache hit / read.
- **orange dashed** = cache write / invalidation.
- **purple solid** = JWT propagation (Authorization header).
- **gray dotted** = scheduler / background path (non-click).
- **red solid** = external HTTP boundary call (out of cluster).

Legend block: put one in the bottom-left of every page.

---

## Page 1 — UI Map

### Nodes
- 13 page-route boxes (pathname): `/`, `/datacenters`, `/datacenter/{id}`, `/dc-detail/{id}`, `/global-view`, `/availability-annual`, `/customers`, `/customer-view`, `/query-explorer`, `/crm/sellable-potential`, `/region-drilldown`, `/login`, `/settings/...`.
- 1 sidebar nav (rectangle): "Sidebar (create_sidebar_nav)".
- 1 shell controller: "render_main_content (app.py:541)".
- 1 access guard: "can_view / get_visible_sections" with arrow into shell.
- 13 page builder boxes (one per page builder fn, e.g. `home.build_overview`, `datacenters.build_datacenters`, etc.).
- 1 store cluster (vertical stack of 5 dcc.Store IDs): `app-time-range`, `auth-user-store`, `auth-permissions-store`, `customer-select`, `selected-region-store`, etc.
- 1 clientside PDF export trigger (hexagon, dashed).

### Edges (URL → builder)
- `/` → `home.build_overview`
- `/datacenters` → `datacenters.build_datacenters`
- `/datacenter/{id}` → `dc_view.build_dc_view`
- `/dc-detail/{id}` → `dc_detail.build_dc_detail`
- `/global-view` → `global_view.build_global_view`
- `/availability-annual` → `availability_annual.build_availability_annual_layout`
- `/customers` → `customers_list.build_customers_list`
- `/customer-view` → `customer_view.build_customer_layout`
- `/query-explorer` → `query_explorer.layout`
- `/crm/sellable-potential` → `crm_sellable_potential.build_layout`
- `/region-drilldown` → `region_drilldown.build_region_drilldown`
- `/login` → `login.build_login_layout`
- `/settings/*` → `settings_shell.build_settings_page`

Plus:
- Sidebar → "Top-level pages" (set of all routes).
- `app-time-range` store → shell controller (used to recompute page on time change).
- Access guard → shell controller (blocks routes when permission denied → build_access_denied).
- All page builder boxes → shared store reads/writes (small dashed arrows).

---

## Page 2 — API Map

This page is **the** big map. Show **page-by-page** what HTTP a user action triggers.

### Nodes per page block
For each of the 13 pages, create a swimlane (vertical container) with 3 columns:
1. **UI action** (hexagon) — taken from frontend_flows.csv `ui_action` column.
2. **api_client fn** (parallelogram) — from `api_client_fn`.
3. **Endpoint** (rectangle rounded-right) — from `endpoint`.

Plus, on the right edge of the page, a vertical strip of `Target service` boxes (datacenter-api / customer-api / crm-engine / query-api / admin-api / AuraNotify). Endpoints connect to their service.

### Suggested swimlane content (sample — Customer View)
- "open /customer-view" → `customer_view.build_customer_layout` → multiple parallel arrows to:
  - `api.get_customer_list` → `GET /api/v1/customers` → customer-api
  - `api.get_customer_resources` → `GET /api/v1/customers/{name}/resources` → customer-api
  - `api.get_customer_s3_vaults` → `GET /api/v1/customers/{name}/s3/vaults` → customer-api
  - `api.get_customer_itsm_summary` → `GET /api/v1/customers/{name}/itsm/summary` → customer-api
  - `api.get_customer_itsm_extremes` → `GET /api/v1/customers/{name}/itsm/extremes` → customer-api
  - `api.get_customer_itsm_tickets` → `GET /api/v1/customers/{name}/itsm/tickets` → customer-api
  - `api.get_customer_sales_summary` → `GET /api/v1/customers/{name}/sales/summary` → customer-api
  - `api.get_customer_sales_items` → `GET /api/v1/customers/{name}/sales/items` → customer-api
  - `api.get_customer_sales_efficiency` → `GET /api/v1/customers/{name}/sales/efficiency` → customer-api
  - `api.get_customer_catalog_valuation` → `GET /api/v1/customers/{name}/sales/catalog-valuation` → customer-api
  - `api.get_customer_efficiency_by_category` → `GET /api/v1/customers/{name}/sales/efficiency-by-category` → customer-api
  - `api.get_customer_availability_bundle` → AuraNotify external (3 calls inside)

Build the same swimlane for each page using rows from `frontend_flows.csv`. Suggested grouping order:
1. shell (`FE-001..FE-008`, `FE-157`)
2. home (`FE-009..FE-017`)
3. datacenters (`FE-018..FE-020`)
4. dc_view (`FE-021..FE-054`)
5. dc_detail (`FE-055`)
6. global_view (`FE-056..FE-072`)
7. floor_map (`FE-067` only)
8. customer_view (`FE-073..FE-086`)
9. customers_list (`FE-087..FE-089`)
10. query_explorer (`FE-090..FE-098`)
11. crm_sellable_potential (`FE-099..FE-102`)
12. availability_annual (`FE-103..FE-104`)
13. settings/* (`FE-107..FE-156`)

### Edges to label
- Solid black with method+path on each api_client → endpoint arrow.
- Purple solid arrow from a small "JWT" badge (top-right of API Map) into every endpoint with `auth_dependency=verify_api_*`.

### Implicit non-click paths
At the bottom of Page 2, add a small section labeled "Non-click flows" with arrows from `dcc.Interval(global-prefetch-interval, 900s)` → `refresh_global_view_prefetch` → `global_view_prefetch.trigger_background` → fan-out to dc summary + dc_details + racks + rack devices.

---

## Page 3 — Backend Lineage

For each of the 5 backend services + AuraNotify, build a layered swimlane:

### Layers (top-to-bottom)
1. Endpoint (METHOD /path).
2. Router fn (router_file:line).
3. Service fn (service_file:line).
4. DB pattern (one of: pg_pool, pg_pool+redis_cache, redis_only, webui_db, ldap_external, composite, http_proxy).
5. Query source (registry key or queries/{file}.py::FN).
6. Tables (cylinder per table).

Connect every endpoint top-down through the layers using **black solid** arrows; show **green dashed** arrow at the Service → DB step where Redis cache is read; **orange dashed** at the Service → Redis step where cache is written.

### Datacenter-API (BE-001..BE-042)
- Endpoints group A "Datacenters core": summary, {dc_code}, compute/classic, compute/hyperconverged → tables `loki_locations`, `nutanix_cluster_metrics`, `vmware_cluster_metrics`, `ibm_*_general`, `raw_energy_metrics`.
- Endpoints group B "SAN/Storage": san/*, storage/* → `raw_brocade_switch_metrics`, `raw_ibm_storage_system`.
- Endpoints group C "Network": network/* → `raw_zabbix_network_devices`, `raw_zabbix_network_metrics`.
- Endpoints group D "Backup/S3": backup/*, s3/pools → `raw_backup_*`, `raw_s3icos_pool_metrics`.
- Endpoints group E "Zabbix Storage": zabbix-storage/* → `raw_zabbix_storage_metrics`.
- Endpoints group F "Physical Inventory + Racks": racks, physical-inventory/* → `discovery_netbox_inventory_rack`, `discovery_netbox_inventory_device` (webui-db).
- Endpoints group G "Sales Potential": sales-potential, sales-potential/v2 → `discovery_crm_salesorder*` (datalake) + `gui_crm_threshold_config` (webui-db).
- Endpoints group H "SLA": /sla, /sla/datacenter-services → external SLA + AuraNotify.
- Endpoints group I "Dashboard": /dashboard/overview → big fan-in from groups A.
- Admin: POST /admin/cache/refresh → all warmers.

### Customer-API (BE-043..BE-059)
- /customers, /customers/{name}/resources → `discovery_infrastructure_*` (bulutlake) + composite (customer_adapter).
- /customers/{name}/s3/vaults → `discovery_s3_vaults`, `discovery_s3_buckets`.
- /customers/{name}/itsm/* → `discovery_servicecore_incidents`, `discovery_servicecore_servicerequests`, `discovery_servicecore_users`.
- /customers/{name}/sales/* → `discovery_crm_salesorders`, `discovery_crm_salesorderdetails`, `discovery_crm_products`, `discovery_crm_productpricelevels`, plus `gui_crm_customer_alias`, `gui_crm_price_override`, `gui_crm_service_mappings`.
- /crm/aliases CRUD → `gui_crm_customer_alias` (webui-db).
- POST /admin/cache/refresh → Redis(db=1).

### CRM-Engine (BE-060..BE-087)
- Top: `/sellable-potential/{summary,by-panel,by-family}` → sellable_service.compute_summary.
- Reads (green dashed): webui-db (gui_panel_*, gui_panel_infra_source, gui_panel_threshold, gui_unit_conversion, gui_panel_resource_ratio, gui_price_override, gui_calc_config) + datalake (per gui_panel_infra_source.source_table) + datacenter-api Redis(db=0) `dc_details:*`.
- Falls back to `GET /api/v1/datacenters/{dc}/compute/{kind}` (HTTP) when cluster CSV passed.
- Config CRUD endpoints group (/panels, /panels/{key}/infra-source, /resource-ratios, /unit-conversions, /config/thresholds, /config/price-overrides, /config/variables, /service-mapping, /aliases-related rows live in customer-api side).
- POST /admin/cache/refresh → flush Redis(db=2) + snapshot_all.

### Query-API (BE-088..BE-089)
- One endpoint `GET /api/v1/queries/{query_key}` → registry lookup.
- Registry list (38 keys) — show 6 "family" sub-clouds: nutanix.*, vmware.*, ibm.*, energy.*, customer.*, and a stub "overrides" pulling from query_overrides.json.

### Admin-API (BE-090..BE-120)
- Group "users": /users, /users/{id}, /users/{id}/roles, /users/{id}/teams, /users/{id}/active, /users/import-ldap → `users`, `user_roles`, `team_members`.
- Group "roles": /roles, /roles/{id}, /roles/{id}/permissions, /roles/{id}/matrix → `roles`, `role_permissions`.
- Group "permissions": /permissions → `permissions`.
- Group "teams": /teams, /teams/{id}, /teams/{id}/members → `teams`, `team_roles`, `team_members`.
- Group "ldap": /ldap, /ldap/{id}/mappings, /ldap/mappings/{mid}, /ldap/search, /ldap/test → `ldap_config`, `ldap_group_role_mapping` + LDAP external cloud.
- Group "audit": /audit → `audit_log`.

### AuraNotify (BE-121..BE-123)
- Three external endpoints in a single cloud node — `GET /api/sla/datacenter-services`, `GET /api/customers/list`, `GET /api/customers/{id}/downtimes?source=service|vm`. X-API-Key header.

---

## Page 4 — Controls

This page shows orthogonal concerns: cache layers, scheduler, auth, external systems.

### Nodes
- **Cache stack** (vertical container):
  - L1: `cache_service` LRU (OrderedDict, MAX_SIZE=2048) per Gunicorn worker.
  - L2: `_api_response_cache` (`src/services/cache_service.py`) with `_api_cache_get_with_stale` policy in api_client.py.
  - L3 (per service): Redis instances per service db number.
    - datacenter-api → Redis db=0, key prefix `dc_*`.
    - customer-api → Redis db=1, key prefix `customer_assets:*`, `customer_s3:*`, `cluster_arch_map:*`.
    - crm-engine → Redis db=2, key prefix `sellable_snapshot:*`.
  - L4: backend in-process TTLCache fallback if Redis unavailable.

- **Scheduler box** (single APScheduler instance in GUI):
  - DB cache refresh — every 15 min (`scheduler_service.py:80-92`).
  - SLA refresh — every 60 min (`scheduler_service.py:111-122`).
  - DC long-range warm — startup (`scheduler_service.py:126-137`).
  - Customer warm — startup + every 15 min (`scheduler_service.py:140-168`).
  - AuraNotify warm — startup + every 15 min (`scheduler_service.py:171-198`).
  - S3 cache — startup + every 30 min (`scheduler_service.py:200-226`).
  - Backup cache — every 30 min (`scheduler_service.py:228-240`).
  - Physical inventory — every 30 min (`scheduler_service.py:242-254`).
  - In addition: `_warm_worker_local_customer_availability_cache` (`app.py:146-164`) per-worker startup.

- **Global view prefetch** (`global_view_prefetch.py`):
  - `trigger_background` (called from `/global-view` page builder + 900s Interval) — Phase 1 critical (summary + details + racks + figures) → Phase 2 devices (24/batch, 12 workers).
  - `warm_dc_priority(dc_id)` — pin click priority warmer.
  - `set_phase2_pause(True)` — when entering building/floor_map.

- **Auth & permissions**:
  - Flask auth-bp (`/auth/login`, `/auth/logout`) issues session cookie → middleware sets `g.auth_user_id`.
  - `api_client._auth_headers()` reads g and creates per-request JWT via `src.auth.api_jwt.create_api_token` (HS256).
  - Every backend service has `verify_api_user/verify_api_jwt` dependency in `core/api_auth.py`.
  - `permission_service.user_effective_map` + `can_view` + `resolve_pathname_to_page_code` gate `render_main_content` (`app.py:573-586`).

- **External systems** (clouds):
  - AuraNotify `http://10.34.8.154:5001` — X-API-Key authentication.
  - SLA API (datacenter-api wraps this).
  - LDAP / Active Directory — bind DN + password (Fernet-encrypted in `ldap_config`).
  - Datalake Postgres (`bulutlake`) — psycopg2 ThreadedConnectionPool.
  - WebUI Postgres (`webui-db`) — separate pool for gui_* tables.
  - Auth Postgres (`auth-db`) — separate database for users/roles/teams/audit/ldap_config.

### Edges
- Scheduler diamonds → Redis cylinders (orange dashed: writes).
- GUI api_client → L1/L2 LRU (green dashed: reads on cache hit) → backend endpoint (black solid: cache miss).
- All backend endpoints → verify_api_jwt (purple solid).
- crm-engine → datacenter-api Redis db=0 (green dashed). crm-engine → datacenter-api `/compute/{kind}` (black solid, fallback).
- GUI auranotify_client → AuraNotify cloud (red solid).
- datacenter-api sla_service → external SLA + AuraNotify (red solid).
- admin-api ldap router → LDAP/AD cloud (red solid).
- All backends → their PG / webui-db / auth-db cylinders (black solid).

### Notes
- Mark cache invalidation paths with the orange dashed style. There is currently NO arrow from "settings PUT/DELETE callbacks" → backend Redis flush, except via the explicit `POST /admin/cache/refresh` button (FE-107). Highlight this gap in red text on the Controls page (matches gaps_and_actions.md R-01) with a red star marker labeled "R-01: backend Redis stale until manual refresh".
- The clientside PDF callback (`window.triggerPagePDF` in `app.py:337-375`) should appear as a small box with arrows from each page's "Export PDF" button — show that it never touches the network.
- Add a small "Telemetry overlay" group (dashed gray cloud labeled "OTLP gRPC :4317") with light-gray dotted arrows from every backend service + frontend → the overlay. This avoids cluttering the main flow lines while showing that telemetry is universal. Full detail goes on Page 6.

---

## Page 5 — Data Model (ERD)

Visualize the three Postgres databases with their tables and FK relationships (per ARCHITECTURE.md §16).

### Layout (3 cluster groups on one page)
Top-left: **auth-db (bulutauth)** — 13 tables.
Top-right: **webui-db (bulutwebui)** — 12 tables.
Bottom (full width): **bulutlake** — 50+ tables shown as 13 category clusters (not individual tables).

### Auth-db nodes & FK edges
Use entity-relationship shapes (Draw.io's "Entity Relation" shape library).

Tables (one box each; PK underlined; FK fields italicized):
- `users` (id PK, username UQ, email, password_hash, source, ldap_dn, is_active)
- `roles` (id PK, name UQ, is_system)
- `permissions` (id PK, code UQ, *parent_id*, resource_type, route_pattern, is_dynamic) — self-ref FK to itself.
- `role_permissions` (composite PK: *role_id*, *permission_id*; can_view, can_edit, can_export)
- `user_roles` (composite PK: *user_id*, *role_id*)
- `teams` (id PK, name, *parent_id* self-ref, *created_by*)
- `team_roles` (composite PK: *team_id*, *role_id*)
- `team_members` (composite PK: *team_id*, *user_id*)
- `ldap_config` (id PK, name, server_primary, bind_dn, bind_password)
- `ldap_group_role_mapping` (id PK, *ldap_config_id*, ldap_group_dn, *role_id*)
- `sessions` (id PK VARCHAR(64), *user_id*, expires_at, ip_address)
- `audit_log` (id PK, user_id, action, detail, ip_address)
- `schema_migrations` (version PK)

FK edges (use Draw.io "many-to-one" connector with crow's foot):
- `permissions.parent_id → permissions.id` (self-ref, CASCADE) — draw as loop.
- `role_permissions.role_id → roles.id` (CASCADE)
- `role_permissions.permission_id → permissions.id` (CASCADE)
- `user_roles.user_id → users.id` (CASCADE)
- `user_roles.role_id → roles.id` (CASCADE)
- `ldap_group_role_mapping.ldap_config_id → ldap_config.id` (CASCADE)
- `ldap_group_role_mapping.role_id → roles.id` (CASCADE)
- `teams.parent_id → teams.id` (SET NULL, self-ref) — draw as loop.
- `teams.created_by → users.id`
- `team_roles.team_id → teams.id` (CASCADE)
- `team_roles.role_id → roles.id` (CASCADE)
- `team_members.team_id → teams.id` (CASCADE)
- `team_members.user_id → users.id` (CASCADE)
- `sessions.user_id → users.id` (CASCADE)

### Webui-db nodes & FK edges
Tables (12 boxes):
- `gui_panel_definition` (panel_key PK, label, family, resource_kind, display_unit, sort_order, enabled)
- `gui_panel_infra_source` (composite PK: *panel_key*, dc_code; source_table, total_column, allocated_table, ...)
- `gui_panel_threshold` (id PK; resource_type, dc_code, sellable_limit_pct, *panel_key*)
- `gui_panel_resource_ratio` (composite PK: family, dc_code; cpu_per_unit, ram_gb_per_unit, storage_gb_per_unit)
- `gui_unit_conversion` (composite PK: from_unit, to_unit; factor, operation, ceil_result)
- `gui_price_override` (productid PK, product_name, unit_price_tl, resource_unit, currency)
- `gui_calc_config` (config_key PK, config_value, value_type, description)
- `gui_crm_customer_alias` (crm_accountid PK, canonical_customer_key, netbox_musteri_value)
- `gui_crm_service_pages` (page_key PK, category_label, *panel_key*, route_hint)
- `gui_crm_service_mapping_seed` (productid PK, *page_key*)
- `gui_crm_service_mapping_override` (productid PK, *page_key*)
- `gui_metric_snapshot` (composite PK: metric_key, scope_type, scope_id, captured_at; value, unit)

FK edges:
- `gui_panel_infra_source.panel_key → gui_panel_definition.panel_key` (CASCADE)
- `gui_crm_service_pages.panel_key → gui_panel_definition.panel_key`
- `gui_panel_threshold.panel_key → gui_panel_definition.panel_key`
- `gui_crm_service_mapping_seed.page_key → gui_crm_service_pages.page_key`
- `gui_crm_service_mapping_override.page_key → gui_crm_service_pages.page_key`

### Bulutlake category clusters
Draw each category as a labeled rectangle (container) with ~5 sample table names inside; don't enumerate all 50+ tables. Categories:
- **Nutanix**: nutanix_cluster_metrics, nutanix_host_metrics, nutanix_vm_metrics
- **VMware**: datacenter_metrics, vmware_cluster_metrics, vmware_host_metrics, vmhost_metrics
- **IBM Power**: ibm_server_general, ibm_vios_general, ibm_lpar_general, ibm_server_power
- **Energy**: raw_energy_metrics
- **Storage/SAN**: raw_ibm_storage_system, raw_brocade_switch_metrics
- **Network (Zabbix)**: raw_zabbix_network_devices, raw_zabbix_network_metrics, raw_zabbix_storage_metrics
- **Backup**: raw_backup_netbackup_metrics, raw_backup_veeam_metrics, raw_backup_zerto_metrics
- **Object Storage**: raw_s3icos_pool_metrics, discovery_s3_vaults, discovery_s3_buckets
- **Inventory (Netbox)**: discovery_netbox_inventory_rack, discovery_netbox_inventory_device, discovery_netbox_virtualization_vm
- **CRM**: discovery_crm_salesorders, discovery_crm_salesorderdetails, discovery_crm_products, discovery_crm_productpricelevels
- **ITSM**: discovery_servicecore_incidents, discovery_servicecore_servicerequests, discovery_servicecore_users
- **Service mapping**: crm_service_mapping, crm_service_mapping_pages
- **Location**: loki_locations

### Cross-DB join callouts
Three dashed orange arrows (labeled "Python-layer join"):
- `discovery_netbox_virtualization_vm.custom_fields_musteri` (bulutlake) ↔ `gui_crm_customer_alias.netbox_musteri_value` (webui-db) → label: "customer-api service_mapping.RESOLVE_ALIAS_BY_NAME".
- `discovery_crm_salesorderdetails.productid` (bulutlake) ↔ `gui_crm_service_mapping_override.productid` (webui-db) → label: "customer-api sales_service.get_efficiency_by_category".
- `discovery_netbox_inventory_rack.site_name` (bulutlake) ↔ `loki_locations.dc_code` (bulutlake — same DB but cross-table join) → label: "datacenter-api discovery_rack.py".

### Notes for this page
- Use the same color palette as other pages: cylinders for tables (purple `#E0E7FF` / `#3730A3`).
- Show one entity-relationship style consistently — Draw.io has "Crow's Foot" shape stencil.
- Place a small text legend at the bottom: "Solid black = FK constraint enforced in SQL. Dashed orange = Python-layer join (no FK)."
- Highlight 4 critical indexes from §16.3 with a green icon next to the table name (gui_crm_customer_alias canonical+name, gui_panel_definition family, gui_metric_snapshot lookup+scope).

---

## Page 6 — Observability flow

Show the full OTLP signal path per ARCHITECTURE.md §14.

### Top half — Service emitters (6 sources)

Left column (6 boxes, one per emitter):
- **frontend (datalake-webui)** — Flask routes + Dash callbacks + httpx + psycopg2.
- **datacenter-api** — FastAPI + httpx + psycopg2 + Redis.
- **customer-api** — FastAPI + httpx + psycopg2 + Redis.
- **query-api** — FastAPI + httpx + psycopg2.
- **admin-api** — FastAPI + httpx + psycopg2.
- **crm-engine** — FastAPI + httpx + psycopg2 (no Redis instrumentation).

Inside each emitter box, list 3 things:
1. OTEL service.name (e.g. `datalake-webui`).
2. Custom spans (only frontend has `dash.callback.*`, `auth.login/logout`; dc-api + cust-api have `cache.get`, `cache.singleflight`).
3. Auto-instrumented libraries (icon row).

### Middle — Transport (single arrow)
One thick green arrow labeled `OTLP gRPC :4317` from each emitter box → collector node.
**Indicate gap**: red dashed line under the arrow with text "K8s deployments missing OTEL_EXPORTER_OTLP_ENDPOINT — see gap §14.6 / §14.9".

### Bottom half — Backends (3 targets)

Three target boxes:
1. **OTEL Collector** (gray cloud, labeled "otel-collector:4317") — receives traces + logs.
   - Fan-out arrows from collector → "Trace backend (Jaeger/Tempo)" + "Log backend".
2. **Loki** (`loki.bulutistan-monitoring.svc.cluster.local:3100`) — receives logs via Fluent Bit (NOT via OTLP).
   - Show parallel pipe: `Pod stdout → Fluent Bit DaemonSet → Loki`.
   - Labels carried: `job, namespace, pod, container, app`.
3. **Prometheus** (`bulutistan-monitoring` namespace) — pull-based; scrapes `/health` of dc-api, query-api, crm-engine every 15s (NOT customer-api or admin-api — flag this gap).
   - Job name: `bulutistan-backend-health`.

### Observability gaps callouts (red box overlay)
Place a "Known gaps" red box on the right side of the page:
- No application metrics (RED metrics) — no `prometheus_client` or `/metrics` endpoint.
- No trace_id/span_id in log format → manual log-to-trace correlation.
- No sampling policy (defaults to 100%).
- No `PrometheusRule` (SLO/alerts).
- customer-api + admin-api missing from health scrape job.
- No OTEL baggage for tenant/customer context.

### Important spans (panel at bottom)
List the top 10 spans an SRE should know (from §14.10) as a numbered list — these become annotation labels for the diagram.

### Edge styles
- Green solid: trace span path from emitter to collector.
- Blue dashed: log path (OTLP).
- Gray dotted: K8s stdout → Fluent Bit path (logs alternate route).
- Black solid: HTTP scrape (Prometheus → /health).

---

## Page 7 — Security boundaries

Visualize all security surfaces in one diagram per ARCHITECTURE.md §19.

### Layout
Use 3 horizontal zones (top to bottom):
1. **Untrusted zone** (Internet / external clients).
2. **Trust boundary 1** (ingress / Flask).
3. **Trusted zone** (cluster internal).

### Zone 1 — Untrusted (top band)
Nodes:
- Browser (user).
- External tools (potentially) — admin tool, monitoring probe.
- AuraNotify (external service).
- LDAP/Active Directory (external service).
- External SLA API.

### Zone 2 — Ingress / Edge (middle band)

**K8s ingress** (one box, labeled `bulutistan.local`):
- Routes: `/api/v1/sla`, `/api/v1/physical-inventory`, `/api/v1/datacenters`, `/api/v1/dashboard`, `/api/v1/customers`, `/api/v1/queries`, `/` (frontend).
- **Missing routes** (red strikethrough): `/api/v1/users|roles|teams|ldap|audit|permissions` (admin-api not in ingress).
- **Missing**: rate-limit annotation (red marker).
- **Missing**: WAF/CSP injection at this layer.

**Flask middleware** (frontend pod):
- After-request: `Cache-Control` set on `/_dash/*` and `/assets/*`.
- **Missing headers** (red list): `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`, `Referrer-Policy`, `Permissions-Policy`.
- Session cookie: `SECRET_KEY` signed, **missing flags** `Secure / HttpOnly / SameSite` (red).

### Zone 3 — Trusted (bottom, large band)

**Auth boundary** (dashed purple container around login/auth):
- Flask `auth_bp`: `/auth/login`, `/auth/logout`.
- LDAP bind (Fernet-decrypted password) — external red arrow.
- `audit_log` insert on success/failure.
- **Risk markers**:
  - "No CSRF token on form POST" → red star.
  - "LDAP password plaintext in POST body — requires HTTPS" → red star.

**JWT propagation** (purple solid arrows):
- Flask request → `g.auth_user_id` → `api_client._auth_headers()` → `create_api_token(uid)` → bearer header → backend `verify_api_user/_jwt`.
- Label: "HS256, signed by API_JWT_SECRET (falls back to SECRET_KEY — bad coupling)".

**Backend trust boundary** (5 boxes — datacenter-api, customer-api, query-api, crm-engine, admin-api):
- Each has CORS middleware → **red callout**: "`allow_origins=['*']` + `allow_credentials=True` (too permissive)".
- Each has FastAPI dependency `verify_api_user` / `verify_api_jwt` → green check.
- **Missing rate limit** → red star.

**Secrets flow** (dotted green container, off to the side):
- K8s Secret resource (referenced via `k8s/auth-secrets-reference.yaml`).
- Holds: `SECRET_KEY`, `API_JWT_SECRET`, `FERNET_KEY`, `AUTH_DB_PASS`, `WEBUI_DB_PASS`, `DB_PASS`, `AURANOTIFY_API_KEY`, `SLA_API_KEY`.
- **Missing**: sealed-secrets / external vault integration → orange label.
- **Risk**: defaults are `change_me_*` in code → red label.

**Fernet boundary** (small box):
- `services/admin-api/app/fernet_util.py`: SHA256(SECRET_KEY) → base64-urlsafe.
- **Risk**: derived from SECRET_KEY; rotation breaks LDAP password decryption (R-19.5).
- Used only for `ldap_config.bind_password` column.

**SQL injection surface** (orange callout):
- Parameterized queries everywhere (✓).
- Exception: `customer-api sellable_service.py` interpolates column names from `gui_panel_infra_source.total_column` — operator-controlled but no validation. Whitelist needed.
- Query Explorer: arbitrary SQL via `query_overrides.json` (R-07).

**Audit boundary**:
- All admin-api writes audit'e yazılıyor mu? — verify with PR-level test.
- Retention policy: **none**.
- Rotation: **none**.
- Immutability: **none**.

### Color overlays for severity
- 🔴 Red marker → high-severity gap (10+ items: missing headers, no rate limit, CORS *, no CSRF, etc.).
- 🟠 Orange marker → medium (Fernet coupling, audit retention, no vault).
- 🟢 Green check → in place (JWT, parameterized SQL, audit on login/logout).

### Legend (bottom)
- Solid black = traffic flow.
- Purple solid = JWT propagation.
- Red dashed = identified security gap.
- Dotted green = secrets reference (not actual traffic).
- Red star = high-priority remediation item.

---

## Implementation tip
You can paste each CSV from this audit directly into Draw.io ("Extras → Edit Diagram XML → Insert from CSV") to bootstrap the swimlanes:

- `frontend_flows.csv` → Page 2 UI Map (use columns `page`, `callback_fn`, `api_client_fn`, `endpoint`, `target_service`).
- `backend_lineage.csv` → Page 3 Backend Lineage (use columns `service_name`, `endpoint`, `router_fn`, `service_fn`, `query_source`, `main_tables_or_registry_keys`).
- `end_to_end_master.csv` → Page 4 Controls' "ui_action → response_component" overlay (useful for execution flow snapshots).

Group nodes by `target_service` color band, and the diagram will read like the audit document above.
