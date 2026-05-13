# Gaps & Actions — Datalake Platform GUI

Cutoff: 2026-05-12. Branch: `feature/customer-view-availability` (HEAD `a4fdc19`).
All references use file paths relative to the repo root.

---

## 1. Missing mappings (endpoint exists but no callback / page reference found, or vice versa)

| ID | Item | Evidence | Notes |
|----|------|----------|-------|
| M-01 | `BE-039 GET /api/v1/datacenters/{dc_code}/sales-potential` (v1) | `services/datacenter-api/app/routers/datacenters.py:316` and `src/services/api_client.py:1091 get_dc_sales_potential` — only used as v1 reference; the live UI now calls `/sales-potential/v2` (`api_client.py:1102`). The v1 endpoint has no remaining callback referencing it. | Candidate for deprecation. Confirm zero callers (grep -rn `get_dc_sales_potential(` ) and remove v1 router + service helper. |
| M-02 | `BE-018 phys-inv overview by-role`, `BE-020 manufacturer`, `BE-021 location` consumed only by `update_phys_inv_chart` (`app.py:958-1015`) | Same. | OK — covered by FE-009/10/11. |
| M-03 | `api_client.get_panel_definitions` mapped to PUT in CRM Panels page; but the **GET** sister call `api.get_panel_definitions` is also used in CRM Thresholds (`crm_thresholds.py`) and CRM Infra Sources (`crm_infra_sources.py`) pages. | api_client.py:1398, multiple page imports. | OK — emitted as FE-140 + reused for FE-138/FE-142. |
| M-04 | `auranotify_client` calls `GET /api/sla/datacenter-services` directly from the GUI (`src/services/auranotify_client.py:37`), **and** datacenter-api also exposes `GET /api/v1/sla/datacenter-services` (`routers/datacenters.py:51`) which proxies the same upstream. | Two parallel code paths to the same external. | The home, datacenters, global_view, and availability_annual pages call the datacenter-api proxy via `api.get_dc_availability_sla_items_for_dcs` (`api_client.py:971`). Direct AuraNotify call only inside `auranotify_client.get_customer_availability_bundle` and `get_dc_availability_sla_item`. Recommend consolidating: route everything through datacenter-api so caching, auth, and rate-limiting live in one place. |
| M-05 | `BE-019 GET /api/v1/physical-inventory/customer` is mapped on the customers_list page (FE-088). No other consumer. | OK. | None. |
| M-06 | `api.refresh_platform_redis_caches` calls **three** services' `POST /api/v1/admin/cache/refresh` (datacenter-api, customer-api, crm-engine). The admin-api **has no `/admin/cache/refresh`** route. | `api_client.py:1599-1626` lists targets; `services/admin-api/app/routers/` has no admin_cache module. | Intentional (admin-api has no warm cache), but document explicitly so future ops do not expect it. |
| M-07 | Settings → Auth Settings page (`src/pages/settings/iam/auth_settings.py`) → no callbacks identified, no obvious API integration. | Frontend pages inventory phase. | **Action**: confirm whether this is a stub page or whether dynamic controls (JWT TTL, session timeout) are missing. |
| M-08 | LDAP upsert/mapping CRUD (`admin_client.upsert_ldap_config`, `add_ldap_group_mapping`, `delete_ldap_group_mapping`) — only the *test connection* callback was found in `ldap_callbacks.py:37`. The save/add/delete operations are presumed to go through Flask form handlers but were not located in scope. | FE-125, FE-127, FE-128 are marked low-confidence assumptions. | **Action**: read `src/pages/settings/integrations/ldap.py` end-to-end and confirm whether form submit is a Dash callback or a Flask `@auth_bp.route("/auth/ldap-settings/save", methods=["POST"])` handler. |
| M-09 | The home page calls `api.get_sla_by_dc` (FE-015) but the SLA "by_dc" payload is read from `data.get("by_dc")` of `GET /api/v1/sla`. Confirm the backend response includes the `by_dc` key when an upstream SLA service is unreachable; otherwise fallback returns `_EMPTY_SLA_BY_DC`. | api_client.py:324-333. | Low risk — already handled by stale-while-error, but worth a regression test. |
| M-10 | dc_detail page (`src/pages/dc_detail.py`) registers **zero callbacks**. It is a static read-only layout that calls `api.get_dc_details` and `api.get_dc_racks` at build time. Many DC-related dynamic actions live on `/datacenter/<id>` (dc_view) instead. | Page inventory. | **Action**: document the difference between `/datacenter/<id>` and `/dc-detail/<id>` paths or merge them; current dual-page model is confusing. |
| M-11 | `floor_map.py` and `region_drilldown.py` register zero callbacks; the rack-detail click handler lives in `app.py:1340` instead. | OK by design but split-brain (callback in app.py for component owned by floor_map page). | Consider moving `show_rack_detail` callback into `floor_map.py` for cohesion. |
| M-12 | Backend response shape for `GET /api/v1/dashboard/overview` (BE-041) — `_EMPTY_DASHBOARD` in `api_client.py:26-70` lists nested keys `overview`, `platforms`, `energy_breakdown`, `classic_totals`, `hyperconv_totals`, `ibm_totals`. Confirm dc_service.get_global_dashboard returns the same nested layout under load — schema drift would silently degrade home cards. | api_client.py:26-70. | **Action**: write a contract test against `GlobalOverview` pydantic model in `services/datacenter-api/app/models/schemas.py`. |

## 2. Low-confidence mappings

| ID | Flow / row | Reason | Recommended verification |
|----|------------|--------|--------------------------|
| L-01 | FE-125, FE-127, FE-128 (LDAP CRUD) | Page-side wiring not in scope reads; admin_client exposes the functions but no Dash callback found. | Open `src/pages/settings/integrations/ldap.py` and locate the form submit hook. |
| L-02 | FE-152 (CRM Overview page) | Crm_overview.layout wiring not deeply read. | Open file and confirm it really calls `api.get_crm_discovery_counts`. |
| L-03 | FE-153 (AuraNotify settings page) | Page not deeply read. | Open `src/pages/settings/integrations/auranotify.py`. |
| L-04 | BE-039 dc_sales_potential (v1) | Service fn signature inferred; inline body in dc_service. | Search for `def dc_sales_potential` in dc_service.py to confirm. |
| L-05 | FE-105 region_drilldown | Page returns a static layout; only callable api fn assumed. | Confirm by reading `src/pages/region_drilldown.py`. |
| L-06 | BE-124/125 Flask `/auth/login` / `/auth/logout` | Inferred from `app.py:80 register_blueprint(auth_bp)`. | Read `src/auth/routes.py`. |
| L-07 | Auth scopes used by visible_sections | `render_main_content` calls `get_visible_sections(uid, page_code)` (`app.py:574`) — the set of supported `page_code` values is not enumerated here. | Read `src/auth/permission_service.py:resolve_pathname_to_page_code`. |

## 3. Risks

### R-01 Cache invalidation is one-sided after settings PUT/DELETE
`api_client._invalidate_sellable_caches` (api_client.py:1549-1559) deletes **only** the GUI-side in-memory LRU. The crm-engine's own Redis (`db=2`) snapshot at `sellable_snapshot:*` is not invalidated. Until the next scheduler tick or until `POST /admin/cache/refresh` is called explicitly, the recalculated values may not appear. The Settings page invitations to "refresh cache" (FE-107) are a workaround but not enforced after each PUT.

**Action**: change the PUT/DELETE callbacks on Thresholds / Panels / Infra-sources / Ratios / Unit-conversions / Price-overrides to **also** POST `/api/v1/admin/cache/refresh` to crm-engine when the operator confirms. Otherwise document the lag in the Settings UI.

### R-02 Schedulers do not propagate the authenticated user identity
`scheduler_service.py:start_scheduler` runs jobs in background threads (no Flask request context). `api._auth_headers()` (api_client.py:183-197) returns an empty dict outside of request context, meaning the scheduler-driven HTTP calls hit backend services WITHOUT a JWT. This works today because `API_AUTH_REQUIRED` defaults to false. The moment auth is turned on in production, scheduler warmup will silently fail (or 401) and the cache will not warm.

**Action**: provide a service-account JWT or a backend-only bypass for the prefetch scheduler. Best implemented in `api_client.py` by allowing an injected `subject_id` parameter that creates a token for a "system" user.

### R-03 Per-process customer availability cache is not shared across Gunicorn workers
`api_client.get_customer_availability_bundle` uses an in-process dict (`_CUSTOMER_AVAIL_CACHE`, api_client.py:887). With 4 Gunicorn workers, the first customer-view request to each worker may take seconds while AuraNotify cold-fetches. The `_warm_worker_local_customer_availability_cache()` thread (app.py:146) addresses this at startup, but only for WARMED_CUSTOMERS × cache_time_ranges. New customers / new ranges still cold-hit per worker.

**Action**: either (a) move this cache to Redis on customer-api side and have the GUI proxy through customer-api, or (b) accept the cost and document. The current task name (`feature/customer-view-availability`) suggests this is being worked on.

### R-04 crm-engine ↔ datacenter-api Redis coupling
`sellable_service.compute_summary` reads `dc_details:*` keys from datacenter-api's Redis db=0. This works because both services share the same Redis instance via env vars, but means crm-engine **cannot** be deployed against a different Redis than datacenter-api. If someone scales them apart, sellable values silently fall back to HTTP `/compute/{kind}` which is slower and only handles the cluster-filtered path.

**Action**: document this explicitly in TOPOLOGY_AND_SETUP.md (it is implicit today). Add an integration test that injects a separate Redis URL and verifies sellable summary still works.

### R-05 update_phys_inv_chart drill-down uses Plotly label string as endpoint param
`app.py:1000` passes `clicked_label` (the y-axis text) directly to `api.get_physical_inventory_overview_manufacturer(role=clicked_label)`. If the role string contains a slash or special char, the chart label may not match the backend's expected exact string. Currently URL-encoded by `quote()` inside api_client (api_client.py:528 — `quote(role, safe='')`).

**Action**: confirm the backend `get_physical_inventory_overview_manufacturer` does a case-insensitive lookup, or normalize roles to a slug. Add a test.

### R-06 admin-api not exposed via ingress
`k8s/ingress.yaml` has no rule for `/api/v1/users|roles|teams|ldap|audit`. The GUI pod calls admin-api over the internal K8s service DNS. This is OK while admin features are accessed through the Dash UI but blocks any external admin tooling.

**Action**: confirm with platform team whether external admin tooling is planned. If yes, add an ingress rule (with stricter authz).

### R-07 query_overrides allow arbitrary SQL via Query Explorer
`src/pages/query_explorer.py:on_save / on_add` writes to `src/services/query_overrides.py`. Behind that, query-api `/api/v1/queries/{key}` will execute it. The override path is local to the GUI container. This is a **privileged surface** — anyone with `can_view(query_explorer)` can ship SQL into the registry.

**Action**: gate Save/Add behind an admin permission (today it relies only on the page-level `can_view`). Also log every save to admin-api `audit_log`.

### R-08 `_client_crm` httpx client is process-shared but other clients are thread-local
`api_client.py:161 _client_crm` is a single httpx.Client at module scope, while dc/cust/query clients are thread-local (`api_client.py:130-156`). httpx.Client is documented as not safe to share across threads. Under Gunicorn gthread workers this is racy.

**Action**: convert `_client_crm` to the same thread-local pattern.

## 4. Validation checklist (15 critical flows to run end-to-end)

These represent the **golden paths** to verify after any backend change or Redis flush.

1. **Home overview loads** within 3s — `GET /api/v1/dashboard/overview` + `GET /api/v1/datacenters/summary` + `GET /api/v1/sla` + `GET /api/v1/sla/datacenter-services` + `GET /api/v1/physical-inventory/overview/by-role` (FE-012/13/14/15/16).
2. **DC view full render** for an active DC code (e.g. `DC13`) — ~15 endpoint fan-out (FE-021..036). Tabs should all show data.
3. **Cluster filter on DC view** — Classic and Hyperconv selectors should re-render the compute panel + the sellable card in lock-step (FE-037/038/039/040/041).
4. **Globe pin click** → DC info card without page navigation (FE-059). Must also trigger background `warm_dc_priority` (FE-060). Subsequent click should be instant.
5. **Building → floor map → rack click** sequence — FE-064 → FE-065 → FE-067 → rack devices panel populates.
6. **Customer view ITSM tab** — three endpoints (summary/extremes/tickets) must populate consistently with the same time range.
7. **Customer view Sales tab** — five endpoints (summary/items/efficiency/catalog-valuation/efficiency-by-category). Verify catalog price overrides take effect after FE-150.
8. **Customer view Availability bundle** — AuraNotify badges should show service + VM outage counts for selected customer (FE-084).
9. **Customer list grid** + search filter (FE-087/088/089) — physical inventory column should show device count per customer.
10. **Query Explorer Run** for a known registry key (e.g. `nutanix_host_count`) returns a value. Then Save an override and Reset (FE-094/096/097).
11. **CRM Sellable Potential dashboard** for `dc_code=*` and for one specific DC (FE-099/100). Switching DC re-fetches summary + by-panel.
12. **Settings → CRM Service Mapping**: select a row, change page assignment, Save. Verify the corresponding sales/efficiency-by-category endpoint result changes after the next cache window.
13. **Settings → CRM Thresholds**: PUT a new threshold, verify the Sellable Potential card on dc_view updates within one cache cycle or after FE-107 (Refresh Cache).
14. **Settings → IAM**: AD search + import a user; the imported user should appear in `GET /api/v1/users`; assign roles; logout/login as that user and confirm permissions reflect (touches admin-api + auth-db + Flask login).
15. **Settings → Cache Refresh** (FE-107): button click must show success for all three target services within ~10 minutes (the documented warm budget) and home page should render with hot cache after.

## 5. Recommended next steps (ordered)

| # | Step | Owner | Output | Done criteria | Est. effort |
|---|------|-------|--------|---------------|-------------|
| S-01 | Resolve M-08 (LDAP CRUD wiring): read `src/pages/settings/integrations/ldap.py` fully and document the Flask vs Dash callback split. | FE-arch | Updated frontend_flows.csv rows for FE-125/127/128 with confidence=high. | All LDAP CRUD flows traced to either a Dash callback or a Flask route. | 0.5d |
| S-02 | Resolve L-01..L-07: open the seven low-confidence files, replace any "assumption" notes. | FE-arch | Confidence upgrades in master CSV. | No `low` confidence rows remain. | 0.5d |
| S-03 | Fix R-08: convert `_client_crm` to thread-local pattern in api_client.py. | FE-arch | Patch + test under gthread workers. | Under load test, no `httpx.HTTPError: connection_busy` / `RuntimeError: Cannot reuse client`. | 0.25d |
| S-04 | Fix R-02 properly: introduce `SYSTEM_USER_ID` env var + `api_client._auth_headers(subject_override=...)`; have scheduler pass it. | Platform | Patch + test with `API_AUTH_REQUIRED=true`. | Scheduler jobs continue warming when auth is on. | 0.5d |
| S-05 | Decide & implement R-01 (PUT → cache refresh): either auto-call `/admin/cache/refresh` after PUTs that invalidate sellable, or surface a "Pending changes — Apply" CTA in the Settings UI. | Product + FE | UX decision + patch. | After a PUT, the related Sellable card reflects the change within one user-visible operation. | 1d |
| S-06 | Deprecate v1 sales-potential (M-01): remove `BE-039` and `api.get_dc_sales_potential` if no remaining callers (grep verifies). | BE | PR. | `grep -rn get_dc_sales_potential\\(` returns only the api_client export. | 0.25d |
| S-07 | Add contract test for `GlobalOverview` payload (M-12): pytest comparing `_EMPTY_DASHBOARD` shape vs `services/datacenter-api/app/models/schemas.py:GlobalOverview`. | BE | New test in `services/datacenter-api/tests/`. | CI green. | 0.25d |
| S-08 | Consolidate AuraNotify access (M-04): route `customer_view` availability through a new `customer-api` endpoint that wraps `auranotify_client`. | BE + FE | Backend route + GUI swap. | `src/services/auranotify_client.py` no longer imported outside backend tests. | 1d |
| S-09 | Add `dc_detail` callbacks or document why empty (M-10/M-11). Decide whether to merge `/dc-detail/` and `/datacenter/`. | Product + FE | Decision doc. | Either page deleted or callbacks added. | 0.5d |
| S-10 | Document R-04 (Redis coupling) in `docs/TOPOLOGY_AND_SETUP.md`. Add integration test that runs crm-engine with a separate Redis URL. | BE | Docs update + test. | docs PR merged; test passes. | 0.5d |
| S-11 | Gate Query Explorer Save/Add behind admin permission (R-07) + audit-log every save. | FE + BE | Patch in `query_explorer.py` and `query_service.py`. | Non-admin sees disabled buttons; admin saves emit `audit_log` entry. | 0.5d |
| S-12 | Produce the full Draw.io diagram from `drawio_blueprint.md`. | Technical writer | `architecture.drawio` file in `docs/`. | Diagram renders 4 pages, all nodes labeled, edges colored per legend. | 1d |
| S-13 | Run the 15-flow validation checklist on a fresh deploy. | QA | Test report. | All 15 flows pass; failures triaged. | 1d |
| S-14 | Decide R-06 (admin-api ingress). | Platform | Either ingress rule or "internal-only" doc note. | k8s/ingress.yaml updated or doc note added. | 0.25d |
| S-15 | Address R-03 if customer-view-availability branch is to be promoted: choose either Redis-shared cache or document per-worker model. | FE + BE | Patch or doc. | Merge of `feature/customer-view-availability` includes the decision. | 1d |

## 6. Coverage Report

### Frontend
- **Total UI flows captured**: 165 (FE-001..FE-165), of which ~98 distinct user-triggered click/page-load actions and 8 scheduler/background flows.
- **Pages covered**: home, datacenters, dc_view, dc_detail, customer_view, customers_list, global_view, floor_map, query_explorer, crm_sellable_potential, availability_annual, region_drilldown, login, settings/dashboard, settings/iam/{users,teams,roles,permissions,audit,auth_settings}, settings/integrations/{ldap,crm_aliases,crm_thresholds,crm_panels,crm_infra_sources,crm_resource_ratios,crm_unit_conversions,crm_calc_config,crm_price_overrides,crm_overview,auranotify}, settings/crm_service_mapping.
- **Pages with zero callbacks**: dc_detail, floor_map (callback lives in app.py), region_drilldown, login (Flask-driven).
- **Confidence distribution**: high 152 / medium 8 / low 5.

### Backend
- **Total endpoints captured**: 125 across 5 microservices + AuraNotify external + Flask auth.
- Per service:
  - **datacenter-api**: 42 endpoints — coverage ~95% (v1 sales-potential is shadow; admin-cache/refresh covered).
  - **customer-api**: 17 endpoints — **100%**.
  - **crm-engine**: 28 endpoints — **100%**.
  - **query-api**: 2 endpoints (`/queries/{key}` + health) + 38 registry keys — **100%**.
  - **admin-api**: 31 endpoints — **100%**.
  - **AuraNotify external**: 3 endpoints inventoried, 0 backend wrapper — **partial** (proxy missing for customer downtimes).
  - **Flask auth**: 2 inferred routes (`/auth/login`, `/auth/logout`) — **low confidence** until S-02 resolves.

### End-to-end
- **Total master rows**: 100+ ui_action → endpoint chains.
- **Status**: complete 91 / partial 8 / missing 1.
- **Missing**: FE-156 (Auth Settings page) — only flow with `status=missing`.
- **Partial**: FE-082 (catalog-valuation, productpricelevels potentially empty), FE-105/152/153 (assumption-tier), FE-125/127/128 (LDAP CRUD wiring), FE-156 (auth-settings).

### Cache, scheduler & auth surface
- 3-tier cache stack mapped: in-memory LRU (GUI) → backend Redis (per-service db 0/1/2) → backend in-process TTL fallback.
- 11 scheduler jobs mapped (15m / 30m / 60m intervals + startup warmers).
- All JWT-protected endpoints flagged with `auth_dependency` (verify_api_user / verify_api_jwt).

### Outstanding open questions
1. Permission codes vs pathname mapping (referenced by `resolve_pathname_to_page_code` — needs an enumeration to verify access-denied behavior on each route).
2. Whether `auth-db` is a Postgres or sqlite per env — code paths exist for both (`src/auth/migration.py`).
3. Concrete Redis DB usage table per service — inferred but not asserted in code or docs.
