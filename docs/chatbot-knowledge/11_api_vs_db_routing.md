# 11 — API vs DB Routing

## Principle

1. **API-first:** Use existing read-only microservice endpoints when they return the required **granularity**.
2. **DB fallback:** When no API exposes the needed grain (per-host, per-VM, per-cluster ranking), use an **allowlisted read-only DB template** (`CHATBOT_DB_ENABLED=true`).
3. **Never:** LLM-generated SQL, write endpoints, or inventing a new REST route per question.

## API tool matrix (granularity)

| Tool | Endpoint | Granularity | Example question |
|------|----------|-------------|------------------|
| `get_dashboard_overview` | `GET /api/v1/dashboard/overview` | Platform totals | Global capacity overview |
| `get_datacenters_summary` | `GET /api/v1/datacenters/summary` | Per-DC summary | Busiest datacenter |
| `get_datacenter_detail` | `GET /api/v1/datacenters/{dc_code}` | Single DC (classic/hyperconv/power) | DC13 overview |
| `get_dc_classic_clusters` | `GET .../clusters/classic` | Cluster **names** only | List KM clusters in DC13 |
| `get_dc_compute_classic` | `GET .../compute/classic` | DC-level **aggregate** (all KM clusters summed) | DC13 classic RAM summary |
| `get_dc_compute_hyperconverged` | `GET .../compute/hyperconverged` | DC-level aggregate | Nutanix compute summary |
| `get_dc_host_cpu_*` | — | N/A at API | Use DB tools |
| `get_dc_vm_cpu_*` | — | N/A at API | Use DB tools |
| `get_global_km_cluster_memory_top` | — | N/A at API | Top N KM clusters by memory (all DCs) |

## DB tool matrix

Requires `CHATBOT_DB_ENABLED=true` and `chatbot_readonly` DB user.

| Tool | Query key | Tables | Required params |
|------|-----------|--------|-----------------|
| `get_dc_host_cpu_latest` | `db_get_dc_host_cpu_latest` | vmware/nutanix/ibm host perf | `dc_code` |
| `get_dc_host_cpu_top` | `db_get_dc_host_cpu_top` | same | `dc_code` |
| `get_dc_host_cpu_summary` | `db_get_dc_host_cpu_summary` | same | `dc_code` |
| `get_dc_vm_cpu_top` | `db_get_dc_vm_cpu_top` | nutanix/ibm VM perf | `dc_code`, `days`, `limit` |
| `get_dc_vm_cpu_latest` | `db_get_dc_vm_cpu_latest` | same | `dc_code` |
| `get_dc_vm_cpu_summary` | `db_get_dc_vm_cpu_summary` | same | `dc_code`, `days` |
| `get_dc_classic_host_cpu_allocation_variability` | `db_get_dc_classic_host_cpu_allocation_variability` | vmware_vm_performance_metrics | `dc_code` |
| `get_dc_vmware_clusters_from_db` | `db_get_dc_vmware_clusters` | cluster_metrics | `dc_code` |
| `get_global_km_cluster_memory_top` | `db_get_global_km_cluster_memory_top` | cluster_metrics (KM) | optional `dc_code`, `limit` |

## Security (DB)

- Only `SELECT` / `WITH ... SELECT` templates in `db_query_registry.py`
- `statement_timeout`, `db_max_rows`, `default_transaction_read_only=on`
- Forbidden: passwords, tokens, write/DDL keywords

## Routing examples

| User question | API sufficient? | Tool |
|---------------|-----------------|------|
| Top 5 KM cluster memory across all DCs | No (API aggregates only) | `get_global_km_cluster_memory_top` |
| DC13 classic RAM summary | Yes | `get_dc_compute_classic` |
| DC13 top host CPU | No | `get_dc_host_cpu_top` |
| DC13 top VM CPU last 7 days | No | `get_dc_vm_cpu_top` |

## Production note

K8s default: `CHATBOT_DB_ENABLED=false` in `k8s/chatbot-api/configmap.yaml`. DB fallback tools return `skipped: db_disabled` until an operator enables read-only DB access. See [[12_conversation_session]] for chat history behaviour.
