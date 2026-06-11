# 02 — API Endpoint Catalog

All service paths below are internal service paths. In Kubernetes/ingress many of these are exposed under `/api/v1`; in Docker internal service URLs are `http://datacenter-api:8000`, `http://customer-api:8000`, `http://query-api:8000`, `http://crm-engine:8000`, `http://admin-api:8000`.

## datacenter-api

Primary service for DC-level infrastructure.

| Endpoint | Purpose | Chatbot use |
|---|---|---|
| `GET /api/v1/dashboard/overview` | global dashboard overview | global capacity/usage summary |
| `GET /api/v1/datacenters/summary` | per-DC summary list | compare DCs, busiest DCs, SLA badges |
| `GET /api/v1/datacenters/{dc_code}` | DC detail | DC summary, platforms, meta, energy; also the source of IBM Power/LPAR (Power Mimari) context — tool `get_datacenter_detail` |
| `GET /api/v1/sla` | SLA by DC | availability questions |
| `GET /api/v1/sla/datacenter-services` | service-level SLA | service availability questions |
| `GET /api/v1/datacenters/{dc_code}/clusters/classic` | classic/KM cluster list | classic/KM architecture planning — tool `get_dc_classic_clusters` |
| `GET /api/v1/datacenters/{dc_code}/clusters/hyperconverged` | HCI/Nutanix cluster list | hyperconverged planning — tool `get_dc_hyperconverged_clusters` |
| `GET /api/v1/datacenters/{dc_code}/compute/classic` | classic compute metrics | classic virtualization cards; may take `clusters=` |
| `GET /api/v1/datacenters/{dc_code}/compute/hyperconverged` | Nutanix compute metrics | HCI virtualization cards; may take `clusters=` |
| `GET /api/v1/datacenters/{dc_code}/s3/pools` | object storage pools | S3 capacity/risk by DC |
| `GET /api/v1/datacenters/{dc_code}/backup/netbackup` | NetBackup pool/status | backup summary |
| `GET /api/v1/datacenters/{dc_code}/backup/zerto` | Zerto site/status | DR summary |
| `GET /api/v1/datacenters/{dc_code}/backup/veeam` | Veeam repo/status | backup summary |
| `GET /api/v1/datacenters/{dc_code}/backup/{vendor}/jobs` | job stats | failed/success job analysis |
| `POST /api/v1/datacenters/{dc_code}/backup/jobs/refresh` | refresh backup cache | not for chatbot unless admin action; read-only chatbot should not invoke write actions |
| `GET /api/v1/datacenters/{dc_code}/storage/capacity` | storage capacity | storage risk/capacity |
| `GET /api/v1/datacenters/{dc_code}/storage/performance` | storage performance | storage latency/IOPS/performance |
| `GET /api/v1/datacenters/{dc_code}/san/*` | SAN switches/port/health/trend/bottleneck | SAN health and bottleneck analysis |
| `GET /api/v1/datacenters/{dc_code}/network/*` | network filters/ports/p95/interface table | network utilization and p95 questions |
| `GET /api/v1/datacenters/{dc_code}/zabbix-storage/*` | Zabbix storage capacity/trend/devices/disk | Intel/Zabbix storage detail; `/zabbix-storage/trend` is exposed as tool `get_dc_zabbix_storage_trend` |
| `GET /api/v1/datacenters/{dc_code}/physical-inventory` | physical inventory by DC | device/rack/manufacturer questions |
| `GET /api/v1/physical-inventory/*` | physical inventory overview/customer | inventory overview/customer device questions |
| `GET /api/v1/datacenters/{dc_code}/sales-potential` | legacy DC sales potential | CRM/capacity opportunity |
| `GET /api/v1/datacenters/{dc_code}/sales-potential/v2` | v2 DC sellable potential | preferred sellable/capacity opportunity |

> Architecture note: Classic = cluster name contains `KM` (Klasik Mimari). Hyperconverged = Nutanix (non-KM cluster names). IBM Power (Power Mimari = IBM/LPAR) has **no** dedicated `/clusters/power` (or `/power`) endpoint; only `/clusters/classic` and `/clusters/hyperconverged` exist. Power/LPAR context is delivered as part of `GET /api/v1/datacenters/{dc_code}` (tool `get_datacenter_detail`), so there is no `get_dc_power_context` tool.

## customer-api

Primary for customer-scoped data. Do not choose this service for DC/host/cluster questions unless the user explicitly asks a customer question.

| Endpoint | Purpose | Chatbot use |
|---|---|---|
| `GET /api/v1/customers` | customer list | customer name discovery |
| `GET /api/v1/customers/{customer_name}/resources` | customer resource usage | customer CPU/RAM/storage/category summaries |
| `GET /api/v1/customers/{customer_name}/s3/vaults` | customer S3 vaults | customer object storage |
| `GET /api/v1/customers/{customer_name}/itsm/summary` | ticket summary | ITSM questions |
| `GET /api/v1/customers/{customer_name}/itsm/extremes` | ticket extremes | best/worst ticket durations |
| `GET /api/v1/customers/{customer_name}/itsm/tickets` | ticket list | ticket detail/top list |
| `GET /api/v1/customers/{customer_name}/sales/*` | customer sales/valuation/efficiency | CRM/sales by customer |
| `GET /api/v1/crm/aliases` (collection); `PUT/DELETE /api/v1/crm/aliases/{crm_accountid}` | CRM aliases | config/admin; read-only chatbot may GET the aliases collection only |

## query-api

`GET /api/v1/queries/{query_key}` executes registered query keys. Chatbot must not let LLM invent query keys. Use only explicit allowlist (the chatbot's `run_registered_query` tool ships with an empty allowlist by default).

## crm-engine

CRM sellable potential and config.

| Endpoint | Purpose |
|---|---|
| `/api/v1/crm/sellable-potential/snapshot-meta` | snapshot metadata |
| `/api/v1/crm/sellable-potential/summary` | summary by DC/global |
| `/api/v1/crm/sellable-potential/by-panel` | panel grouping |
| `/api/v1/crm/sellable-potential/by-family` | family grouping |
| `/api/v1/crm/metric-tags`, `/api/v1/crm/metric-tags/snapshots` | metric tags/history |
| `/api/v1/crm/panels`, `/api/v1/crm/panels/{panel_key}/infra-source` | panel definitions and infra source mapping |
| `/api/v1/crm/resource-ratios`, `/api/v1/crm/unit-conversions` | resource conversion config |
| `/api/v1/crm/service-mapping` | CRM service mapping |
| `/api/v1/crm/config/*` | thresholds, price overrides, variables, discovery counts |

## admin-api

IAM/LDAP/admin; not generally used for business data answers except admin questions. Be careful: many endpoints mutate state; chatbot should not call write actions.