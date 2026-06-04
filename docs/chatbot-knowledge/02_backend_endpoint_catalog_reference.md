# Bulutistan Datalake Platform GUI — Backend Endpoint Catalog

Kaynak: Kullanıcının yüklediği `Datalake-Platform-GUI.zip` içindeki FastAPI router dosyaları ve Flask auth route dosyaları.

## Service map

| Service | Local/Docker role | Base path | Notes |
|---|---:|---|---|
| frontend | Dash/Flask WebUI | `/` | Port 8050, UI shell + local auth routes |
| datacenter-api | FastAPI | `/api/v1` | DC summary/detail, SLA, compute, storage, network, physical inventory, backup, S3, SAN, DC sales potential |
| customer-api | FastAPI | `/api/v1` | Customer resource view, customer S3 vaults, sales/CRM customer mappings, ITSM |
| query-api | FastAPI | `/api/v1` | Registry-based query explorer |
| crm-engine | FastAPI | `/api/v1` | CRM sellable potential, panels, thresholds, mapping, ratios, unit conversions |
| admin-api | FastAPI | `/api/v1` | IAM users, roles, permissions, teams, LDAP, audit |

---

## Cross-service health endpoints

All FastAPI microservices expose:

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness/basic dependency status |
| GET | `/ready` | Readiness/dependency gate |

---

## datacenter-api endpoints

Base: `/api/v1`

| Method | Endpoint | Main purpose / params |
|---|---|---|
| POST | `/admin/cache/refresh` | Refresh datacenter API cache |
| GET | `/dashboard/overview` | Global dashboard overview; uses time filter |
| GET | `/datacenters/summary` | Data center summary list; uses time filter |
| GET | `/datacenters/{dc_code}` | Single DC detail; uses time filter (also carries the Power/IBM context — there is no separate `/clusters/power` endpoint) |
| GET | `/sla` | SLA availability; uses time filter |
| GET | `/sla/datacenter-services` | SLA by datacenter services; uses time filter |
| GET | `/datacenters/{dc_code}/s3/pools` | DC S3 pool metrics; uses time filter |
| GET | `/datacenters/{dc_code}/backup/netbackup` | NetBackup summary |
| GET | `/datacenters/{dc_code}/backup/zerto` | Zerto summary |
| GET | `/datacenters/{dc_code}/backup/veeam` | Veeam summary |
| GET | `/datacenters/{dc_code}/backup/veeam/jobs` | Veeam job stats; `granularity` optional |
| GET | `/datacenters/{dc_code}/backup/zerto/jobs` | Zerto job stats; `granularity` optional |
| GET | `/datacenters/{dc_code}/backup/netbackup/jobs` | NetBackup job stats; `granularity` optional |
| POST | `/datacenters/{dc_code}/backup/jobs/refresh` | Refresh backup jobs; `vendor` parameter |
| GET | `/datacenters/{dc_code}/clusters/classic` | Classic cluster list — backs chatbot tool `get_dc_classic_clusters` |
| GET | `/datacenters/{dc_code}/clusters/hyperconverged` | Hyperconverged cluster list — backs chatbot tool `get_dc_hyperconverged_clusters` |
| GET | `/datacenters/{dc_code}/compute/classic` | Classic compute metrics; optional `clusters` |
| GET | `/datacenters/{dc_code}/compute/hyperconverged` | Hyperconverged compute metrics; optional `clusters` |
| GET | `/datacenters/{dc_code}/racks` | DC rack list/summary |
| GET | `/datacenters/{dc_code}/racks/{rack_name}/devices` | Devices in rack |
| GET | `/datacenters/{dc_code}/physical-inventory` | DC physical inventory |
| GET | `/physical-inventory/overview/by-role` | Physical inventory grouped by role |
| GET | `/physical-inventory/customer` | Customer physical inventory |
| GET | `/physical-inventory/overview/manufacturer` | Physical inventory by manufacturer; optional `role` |
| GET | `/physical-inventory/overview/location` | Physical inventory by location; optional `role`, `manufacturer` |
| GET | `/datacenters/{dc_code}/san/switches` | SAN switches |
| GET | `/datacenters/{dc_code}/san/port-usage` | SAN port usage |
| GET | `/datacenters/{dc_code}/san/health` | SAN health rows |
| GET | `/datacenters/{dc_code}/san/traffic-trend` | SAN traffic trend |
| GET | `/datacenters/{dc_code}/san/bottleneck` | SAN bottleneck summary |
| GET | `/datacenters/{dc_code}/storage/capacity` | Storage capacity metrics |
| GET | `/datacenters/{dc_code}/storage/performance` | Storage performance metrics |
| GET | `/datacenters/{dc_code}/network/filters` | Network dashboard filters |
| GET | `/datacenters/{dc_code}/network/port-summary` | Network port summary; filters: `manufacturer`, `device_role`, `device_name` |
| GET | `/datacenters/{dc_code}/network/95th-percentile` | Network 95th percentile; filters + `top_n` |
| GET | `/datacenters/{dc_code}/network/interface-table` | Paginated interface table; `page`, `page_size`, `search`, filters |
| GET | `/datacenters/{dc_code}/zabbix-storage/capacity` | Zabbix storage capacity; optional `host` |
| GET | `/datacenters/{dc_code}/zabbix-storage/trend` | Zabbix storage trend; optional `host` — backs chatbot tool `get_dc_zabbix_storage_trend` |
| GET | `/datacenters/{dc_code}/zabbix-storage/devices` | Zabbix storage device list |
| GET | `/datacenters/{dc_code}/zabbix-storage/disk-list` | Zabbix disk list; optional `host` |
| GET | `/datacenters/{dc_code}/zabbix-storage/disk-trend` | Zabbix disk trend; optional `host`, `disk` |
| GET | `/datacenters/{dc_code}/zabbix-storage/disk-health` | Zabbix disk health |
| GET | `/datacenters/{dc_code}/sales-potential` | Legacy DC sales potential |
| GET | `/datacenters/{dc_code}/sales-potential/v2` | New DC sales potential v2 |

> Chatbot tooling note: `/clusters/classic`, `/clusters/hyperconverged` and `/zabbix-storage/trend` are now also exposed as allowlisted read-only chatbot tools (`get_dc_classic_clusters`, `get_dc_hyperconverged_clusters`, `get_dc_zabbix_storage_trend`). Power/IBM mimari has **no** dedicated `/clusters/power` endpoint and no `get_dc_power_context` tool — Power context is returned as part of `/datacenters/{dc_code}` (chatbot tool `get_datacenter_detail`).

---

## customer-api endpoints

Base: `/api/v1`

| Method | Endpoint | Main purpose / params |
|---|---|---|
| POST | `/admin/cache/refresh` | Refresh customer API cache |
| GET | `/customers` | Customer list |
| GET | `/customers/{customer_name}/resources` | Customer resources; uses time filter |
| GET | `/customers/{customer_name}/s3/vaults` | Customer S3 vaults; uses time filter |
| GET | `/customers/{customer_name}/itsm/summary` | ITSM summary; uses time filter |
| GET | `/customers/{customer_name}/itsm/extremes` | ITSM extremes; uses time filter |
| GET | `/customers/{customer_name}/itsm/tickets` | ITSM ticket list; uses time filter |
| GET | `/customers/{customer_name}/sales/summary` | CRM/sales summary |
| GET | `/customers/{customer_name}/sales/items` | CRM/sales line items |
| GET | `/customers/{customer_name}/sales/efficiency` | Sales efficiency rows |
| GET | `/customers/{customer_name}/sales/efficiency-by-category` | Sales efficiency grouped by category |
| GET | `/customers/{customer_name}/sales/catalog-valuation` | Catalog valuation |
| GET | `/crm/aliases` | CRM customer alias list |
| PUT | `/crm/aliases/{crm_accountid}` | Update/upsert CRM alias |
| DELETE | `/crm/aliases/{crm_accountid}` | Delete CRM alias |

---

## query-api endpoints

Base: `/api/v1`

| Method | Endpoint | Main purpose / params |
|---|---|---|
| GET | `/queries/{query_key}` | Execute registered query; dynamic query params accepted |

---

## crm-engine endpoints

Base: `/api/v1`

| Method | Endpoint | Main purpose / params |
|---|---|---|
| POST | `/admin/cache/refresh` | Refresh CRM engine cache |
| GET | `/crm/sellable-potential/snapshot-meta` | Sellable snapshot metadata; `dc_code`, `family`, `clusters` |
| POST | `/crm/sellable-potential/refresh` | Recompute/refresh sellable potential snapshot |
| GET | `/crm/sellable-potential/summary` | Sellable summary; `dc_code`, `clusters` |
| GET | `/crm/sellable-potential/by-panel` | Sellable grouped by panel; `dc_code`, `family`, `clusters` |
| GET | `/crm/sellable-potential/by-family` | Sellable grouped by family; `dc_code`, `clusters` |
| GET | `/crm/metric-tags` | Metric tags; `prefix`, `scope_type`, `scope_id` |
| GET | `/crm/metric-tags/snapshots` | Metric snapshots; `metric_key`, `scope_id`, `hours` |
| GET | `/crm/panels` | CRM panel definitions |
| PUT | `/crm/panels/{panel_key}` | Upsert CRM panel definition |
| GET | `/crm/panels/{panel_key}/infra-source` | Get panel infra source; optional `dc_code` |
| PUT | `/crm/panels/{panel_key}/infra-source` | Upsert panel infra source |
| GET | `/crm/resource-ratios` | Resource ratio config list |
| PUT | `/crm/resource-ratios/{family}` | Upsert resource ratio by family |
| GET | `/crm/unit-conversions` | Unit conversion config list |
| PUT | `/crm/unit-conversions/{from_unit}/{to_unit}` | Upsert unit conversion |
| DELETE | `/crm/unit-conversions/{from_unit}/{to_unit}` | Delete unit conversion |
| GET | `/crm/service-mapping/pages` | Service mapping page catalog |
| GET | `/crm/service-mapping` | Product/service mapping list |
| PUT | `/crm/service-mapping/{productid}` | Upsert product mapping override |
| DELETE | `/crm/service-mapping/{productid}/override` | Delete product mapping override |
| GET | `/crm/config/thresholds` | CRM calculation thresholds |
| PUT | `/crm/config/thresholds` | Upsert CRM threshold |
| DELETE | `/crm/config/thresholds/{threshold_id}` | Delete CRM threshold |
| GET | `/crm/config/price-overrides` | CRM price overrides |
| PUT | `/crm/config/price-overrides/{productid}` | Upsert price override |
| DELETE | `/crm/config/price-overrides/{productid}` | Delete price override |
| GET | `/crm/config/variables` | CRM calculation variables |
| PUT | `/crm/config/variables/{config_key}` | Upsert calculation variable |
| GET | `/crm/config/discovery-counts` | Discovery counts for CRM config UI |

---

## admin-api endpoints

Base: `/api/v1`

| Method | Endpoint | Main purpose / params |
|---|---|---|
| GET | `/users` | List IAM users |
| POST | `/users` | Create IAM user |
| GET | `/users/{user_id}` | User detail |
| PUT | `/users/{user_id}` | Update user profile fields |
| PUT | `/users/{user_id}/roles` | Set user roles |
| PUT | `/users/{user_id}/active` | Activate/deactivate user |
| PUT | `/users/{user_id}/teams` | Set user teams |
| POST | `/users/import-ldap` | Import LDAP users |
| GET | `/roles` | List roles |
| PUT | `/roles/{role_id}` | Update role |
| DELETE | `/roles/{role_id}` | Delete role |
| GET | `/roles/{role_id}/permissions` | Role permission matrix rows |
| POST | `/roles/{role_id}/matrix` | Save role permission matrix |
| GET | `/permissions` | List permissions; optional `limit` |
| POST | `/permissions` | Add permission |
| GET | `/teams` | List teams |
| POST | `/teams` | Create team |
| PUT | `/teams/{team_id}` | Update team |
| GET | `/teams/{team_id}/members` | List team members |
| POST | `/teams/{team_id}/members` | Add team members |
| DELETE | `/teams/{team_id}/members/{user_id}` | Remove member from team |
| GET | `/ldap/search` | Search LDAP users; `q` |
| GET | `/ldap` | List LDAP configs |
| POST | `/ldap/test` | Test LDAP connection |
| POST | `/ldap` | Upsert LDAP config |
| GET | `/ldap/{ldap_id}/mappings` | List LDAP group-role/team mappings |
| POST | `/ldap/{ldap_id}/mappings` | Add LDAP mapping |
| DELETE | `/ldap/mappings/{mapping_id}` | Delete LDAP mapping |
| GET | `/audit` | Audit log list; optional `limit` |

> Security note: LDAP bind/service credentials and any auth secrets are configured server-side via environment/config and are never exposed through these endpoints or this document.

---

## frontend Flask auth/settings POST routes

These are not FastAPI microservice endpoints; they live inside the Dash/Flask frontend app (`src/auth/routes.py`).

| Method | Endpoint | Main purpose |
|---|---|---|
| POST | `/login` | Login |
| GET/POST | `/logout` | Logout |
| POST | `/settings/create-user` | Legacy/local user create form action |
| POST | `/settings/role-matrix` | Legacy/local role matrix save |
| POST | `/settings/permission-add` | Legacy/local permission add |
| POST | `/settings/ldap-save` | Legacy/local LDAP config save |
| POST | `/settings/ldap-mapping-add` | Legacy/local LDAP mapping add |
| POST | `/settings/ldap-mapping-delete` | Legacy/local LDAP mapping delete |
| POST | `/settings/team-create` | Legacy/local team create |

---

## CTO notes for future development

1. New data dashboards should usually add/extend a FastAPI route in the relevant service, then add an API client wrapper in `src/services/api_client.py` or `src/services/admin_client.py`, then wire UI pages/components in `src/pages` and `src/components`.
2. `datacenter-api` owns infrastructure/DC-level metrics.
3. `customer-api` owns customer-specific resources, sales aliases, ITSM, and customer resource aggregations.
4. `crm-engine` owns sellable potential and CRM configuration/admin calculations.
5. `admin-api` owns IAM/LDAP/team/role/permission/audit APIs.
6. `query-api` is for generic registered query execution and Query Explorer style needs.
7. All FastAPI routers use `/api/v1` prefix and API auth dependencies in `main.py`.
8. The Dash frontend still contains some legacy Flask POST routes for auth/settings. Prefer admin-api for new IAM work unless the feature explicitly belongs in the frontend auth layer.
9. Chatbot tooling exposes a **read-only, allowlisted** subset of these GET endpoints (plus a few read-only DB query templates). The LLM never picks an arbitrary endpoint and never writes SQL; DB access is read-only with allowlisted query templates, a row cap and a statement timeout. When adding a chatbot tool, register it in `services/chatbot-api/app/services/tool_registry.py` against an existing backend endpoint or an allowlisted DB query — e.g. the newly added `get_dc_classic_clusters`, `get_dc_hyperconverged_clusters` and `get_dc_zabbix_storage_trend` tools wrap `/clusters/classic`, `/clusters/hyperconverged` and `/zabbix-storage/trend` respectively. There is intentionally no `get_dc_power_context` tool; use `get_datacenter_detail` (`/datacenters/{dc_code}`) for Power/IBM context.