# 07 — Query Planning Rules

## Planning pipeline

1. Normalize text (Turkish/English aliases, lowercase for matching, preserve entity values).
2. Extract explicit entities/time/limit/source from user message.
3. Use conversation structured context for follow-up questions.
4. Use frontend context only as support, not dependency.
5. Match metric aliases from runtime catalog.
6. Select candidate tools from catalog.
7. Check required params.
8. If missing required params, ask short clarification.
9. Execute agentic tool loop.
10. Evaluate evidence and synthesize answer.

## User message overrides context

If user says `DC13`, use `DC13` even if page context has another DC or customer.
If user says `Boyner`, use customer flow only when customer is semantically relevant.

## Source preference

| User phrase | Source preference |
|---|---|
| direkt DB, veritabanı, postgre, PostgreSQL, SQL | DB first |
| endpoint, API, WebUI'da görünen, kart/grafik | API first |
| none | auto: API if exact; DB if detail/timeseries missing |

## Architecture mapping (for entity → tool routing)

When a question targets a specific architecture, map it deterministically:

- **Klasik Mimari (Classic / VMware)** = cluster name contains `KM`. Tools: `get_dc_compute_classic`, cluster list via `get_dc_classic_clusters` (`/api/v1/datacenters/{dc_code}/clusters/classic`).
- **Hyperconverged (Nutanix)** = non-`KM` cluster names. Tools: `get_dc_compute_hyperconverged`, cluster list via `get_dc_hyperconverged_clusters` (`/api/v1/datacenters/{dc_code}/clusters/hyperconverged`).
- **Power (IBM / LPAR)** = IBM server / LPAR data. There is **no** power cluster endpoint and **no** `get_dc_power_context` tool — Power context is returned as part of `get_datacenter_detail` (`/api/v1/datacenters/{dc_code}`). Do not invent a power-cluster tool.
- Storage trend over time: `get_dc_zabbix_storage_trend` (`/api/v1/datacenters/{dc_code}/zabbix-storage/trend`).

## Required clarification

Ask clarification only when a required parameter cannot be inferred from user message, conversation, or frontend context.

Examples:

- "Klasik host allocated değişkenliği en yüksek 3 host" with no DC anywhere → ask "Hangi veri merkezi için istiyorsun?"
- "DC13 Klasik host allocated değişkenliği" → no clarification; DC is explicit (route to `get_dc_classic_host_cpu_allocation_variability`).
- "Bunlardan hangileri sürekli yüksek?" after previous VM CPU top list → carry over DC/entity/metric/top entities from conversation.

## Tool anti-patterns

- Do not choose `get_customer_resources` for DC host/cluster questions just because stale `selected_customer` exists.
- Do not choose VM CPU **usage** tools (`get_dc_vm_cpu_top` / `get_dc_vm_cpu_latest` / `get_dc_vm_cpu_summary`) for CPU **allocated/capacity variability** questions — for "klasik host allocated değişkenliği" use `get_dc_classic_host_cpu_allocation_variability`.
- Do not report per-host classic **allocated CPU** in GHz. It is reported in **vCPU** (sum of each host's VMs' `number_of_cpus`), because `vmware_vm_performance_metrics.total_cpu_capacity_mhz` is `0` in this dataset, so an allocated-GHz value cannot be computed without fabrication. GHz capacity/used exists only at **cluster** level (`cluster_metrics.cpu_ghz_capacity` / `cpu_ghz_used`, fresh/current) — surface it via the cluster-level tools, not the per-host variability tool.
- Do not invent a `get_dc_power_context` or `/clusters/power` call — Power data comes from `get_datacenter_detail`.
- Do not choose API summary endpoints and stop if user requested DB and DB tool exists.
- Do not return generic Prometheus/Grafana suggestions until API + DB catalog tools were checked.

## Missing-data guard

If any tool returns success with `rows > 0`, final answer must not claim data is unavailable.
If LLM final response contradicts successful tool evidence, use deterministic fallback formatter.

## Agentic loop limits

Per-question investigation budget (executive deep-dive). See [[13_executive_investigation]].

| Env var | Default |
|---|---|
| `CHATBOT_AGENTIC_MODE` | `true` |
| `CHATBOT_LLM_REACT_MODE` | `true` |
| `CHATBOT_MAX_TOOL_CALLS_PER_TURN` | `150` |
| `CHATBOT_MAX_LLM_ROUNDS` | `150` |
| `CHATBOT_MAX_TOOL_ITERATIONS` | `50` |
| `CHATBOT_MAX_TOOL_CALLS_PER_ITERATION` | `10` |
| `CHATBOT_REQUEST_TIMEOUT_SECONDS` | `600` |
| `CHATBOT_CLIENT_TIMEOUT` (GUI) | `600` |

Always early-stop when evidence is sufficient. Never repeat same tool with same params.
