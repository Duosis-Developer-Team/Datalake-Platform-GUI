# 09 — Known Limitations and Safe Fallbacks

## Known limitations

- `get_datacenters_summary` is normalized to compact `ranking_rows` for every datacenter (not a 3-item `_sample`). Global busiest-DC answers must use this full list or map-reduce detail workers — never rank from a truncated sample alone.
- Ambiguous "en yoğun datacenter" questions without a metric should trigger clarification (CPU / memory / VM / composite) before ranking.
- Some data is delayed; anchor time windows to latest available source data when UI semantics require it.
- VMware VM CPU percent may be unavailable if denominator/capacity is zero/missing. Report MHz or exclude from percent ranking rather than inventing `%`.
- Per-host classic (KM) **allocated CPU** is reported in **vCPU** (sum of VMs' `number_of_cpus` per host), NOT GHz. The allocated-GHz value cannot be computed in this dataset because `vmware_vm_performance_metrics.total_cpu_capacity_mhz` is `0`, so a GHz figure would have to be fabricated. (`cluster_metrics.cpu_ghz_capacity` / `cpu_ghz_used` do exist, but only at the **cluster** level — not per host.) The `get_dc_classic_host_cpu_allocation_variability` tool therefore returns `unit = 'vCPU'`.
- API endpoints may expose summaries only; host/VM-level ranking often requires DB templates.
- Customer API resources are customer-scoped and can mislead if used for DC/host questions.
- Some write endpoints exist (refresh/cache/config) but chatbot should remain read-only.
- DB access is read-only: only allowlisted query templates run (NO LLM-generated SQL), with a row cap and statement timeout enforced.
- There is no dedicated power-cluster endpoint or tool. `/datacenters/{dc_code}/clusters/power` does not exist and there is no `get_dc_power_context` tool. IBM Power context is part of the datacenter detail (`get_datacenter_detail` → `/api/v1/datacenters/{dc_code}`).
- **UI table readability:** narrow panel (400px) truncates markdown tables; use the **Genişlet** drawer (~68vw) or structured `blocks` with native `html.Table` rendering. See [[15_chatbot_evaluation_harness.md]] and `format_dashboard_overview`.
- **datalake-mcp:** tools can run in-process (`CHATBOT_TOOL_BACKEND=local`) or via optional MCP server. See [[16_datalake_mcp.md]].

## When to ask clarification

Ask short clarification if required scope is missing:

- User asks "en değişken hostlar" without DC/customer/context.
- User asks "bu müşterinin" without selected/previous customer.
- User asks "bunlar" without previous structured entity list.

Do not ask clarification if user explicitly gives required scope.

## When data-not-found is valid

Only after:

1. Matching metric catalog entry was found or attempted.
2. API tools that should contain data were checked where relevant.
3. DB tools were checked if detail/timeseries is expected and DB enabled.
4. Optional LLM ReAct loop and catalog fallbacks exhausted or budget cap (150) reached.
5. `investigation_trace` lists attempted tools with status/error.
6. Empty/error reasons are included in answer.

Answer should say what was checked and why it was insufficient. See [[13_executive_investigation]].

## Forbidden generic fallbacks before checking catalog

Do not say:

- "Prometheus/Grafana/vCenter gerekir"
- "Bu veri setinde yok"
- "DB sorgusu çalıştırılamıyor"
- "Erişemiyorum"

unless the specific catalog-planned tools were actually attempted or required params are missing.

Tools that are available and should be attempted before falling back to a generic "not available" answer (where relevant to the question):

- `get_dc_classic_clusters` → `/api/v1/datacenters/{dc_code}/clusters/classic` (Classic / KM cluster list).
- `get_dc_hyperconverged_clusters` → `/api/v1/datacenters/{dc_code}/clusters/hyperconverged` (Nutanix / HCI cluster list).
- `get_dc_zabbix_storage_trend` → `/api/v1/datacenters/{dc_code}/zabbix-storage/trend` (Zabbix storage capacity trend).
- For IBM Power context, use `get_datacenter_detail` (there is no separate power-cluster tool).

## Secret safety

Knowledge pack and catalog must never contain real:

- API tokens
- DB passwords
- connection strings
- JWT secrets
- LDAP bind credentials
