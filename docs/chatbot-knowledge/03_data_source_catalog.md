# 03 — Data Source Catalog

## Source selection strategy

1. Prefer existing API tools when an endpoint already returns the exact semantic metric.
2. Use PostgreSQL read-only DB tools when API lacks detail or aggregation needed by the user.
3. Use API + DB hybrid when the API gives metadata/filter context and DB gives timeseries/detail.
4. Never execute arbitrary SQL. Only developer-defined, allowlisted query templates (read-only, row cap + statement timeout). No LLM-generated SQL — ever.

## Provider domains

| Provider/domain | Typical source tables | API surface | Notes |
|---|---|---|---|
| VMware / Classic / KM | `datacenter_metrics`, `cluster_metrics`, `vmware_host_metrics`, `vmhost_metrics`, `vmware_host_performance_metrics`, `vmware_vm_performance_metrics` | classic cluster/compute endpoints | Classic/KM cluster names usually include `KM`; `cluster_metrics` is the main aggregated source (cluster-level only) and holds `cpu_ghz_capacity` / `cpu_ghz_used`. Per-host detail comes from `vmware_host_metrics` / `vmware_host_performance_metrics`. (Note: there is no `vmware_cluster_metrics` table — use `cluster_metrics`.) |
| Nutanix / HCI | `nutanix_cluster_metrics`, `nutanix_host_performance_metrics`, `nutanix_vm_performance_metrics`, `nutanix_vm_metrics` | hyperconverged cluster/compute endpoints | `cluster_name` contains DC code; some perf values can be ppm-like and require conversion (e.g. Nutanix VM `cpu_usage_avg` is ppm: 1e6 = 100%) |
| IBM Power | `ibm_server_general`, `ibm_lpar_general`, `ibm_lpar_performance_metrics`, `ibm_vios_general` | DC detail (power context is part of `get_datacenter_detail`) | DC code often extracted from server/lpar name using regex (`DC[0-9]+|AZ[0-9]+|ICT[0-9]+`). There is no dedicated `/power` cluster endpoint and no `get_dc_power_context` tool — Power context is surfaced via `get_datacenter_detail` (`/api/v1/datacenters/{dc_code}`). |
| S3/Object | S3 pool/vault source tables through API | DC S3 pools, customer S3 vaults | Prefer API tools |
| Backup/DR | NetBackup/Zerto/Veeam source tables through API | backup summary/jobs endpoints | Prefer API tools; job refresh is write-ish, avoid by chatbot |
| Storage/SAN | IBM storage/SAN/Zabbix source tables | storage, SAN, zabbix-storage endpoints | Prefer API tools; DB only for missing trend/detail |
| Network | port/interface/p95 source tables through API | network endpoints | Prefer API tools |
| ITSM | ServiceCore/ITSM source through customer-api | customer ITSM endpoints | Prefer API |
| CRM/Sellable | `gui_*`, `discovery_crm_*`, CRM config tables | crm-engine/customer-api sales endpoints | Prefer crm-engine APIs |

## Important DB tools already required by chatbot

| Tool | Query key | Use case |
|---|---|---|
| `get_dc_host_cpu_latest` | `db_get_dc_host_cpu_latest` | latest host CPU snapshot by DC |
| `get_dc_host_cpu_top` | `db_get_dc_host_cpu_top` | top host CPU usage |
| `get_dc_host_cpu_summary` | `db_get_dc_host_cpu_summary` | host CPU summary by source |
| `get_dc_vm_cpu_top` | `db_get_dc_vm_cpu_top` | top VM CPU usage over a window |
| `get_dc_vm_cpu_latest` | `db_get_dc_vm_cpu_latest` | latest VM CPU snapshot |
| `get_dc_vm_cpu_summary` | `db_get_dc_vm_cpu_summary` | VM CPU summary/source distribution |
| `get_dc_classic_host_cpu_allocation_variability` | `db_get_dc_classic_host_cpu_allocation_variability` | classic/KM host allocated CPU **vCPU** variability |

> **Unit note (classic host allocated CPU):** per-host classic/KM "allocated CPU" is reported in **vCPU** (sum of each host's VMs' `number_of_cpus`), **not GHz**. Allocated GHz cannot be computed here because `vmware_vm_performance_metrics.total_cpu_capacity_mhz` is `0` in this dataset, so a GHz figure would have to be fabricated. `cluster_metrics` does expose `cpu_ghz_capacity` / `cpu_ghz_used`, but only at the **cluster** level (and that is fresh/current).

## Newly available API-wrapper tools

These wrap confirmed read-only backend endpoints and should be used instead of raw endpoint calls:

| Tool | Endpoint | Use case |
|---|---|---|
| `get_dc_classic_clusters` | `GET /api/v1/datacenters/{dc_code}/clusters/classic` | List classic/KM cluster names for a datacenter |
| `get_dc_hyperconverged_clusters` | `GET /api/v1/datacenters/{dc_code}/clusters/hyperconverged` | List hyperconverged (Nutanix) cluster names for a datacenter |
| `get_dc_zabbix_storage_trend` | `GET /api/v1/datacenters/{dc_code}/zabbix-storage/trend` | Zabbix storage capacity/usage trend for a datacenter (optional `host` filter) |

## API + DB hybrid examples

### Classic host CPU allocated variability

- API can provide the classic/KM cluster list via the `get_dc_classic_clusters` tool (`GET /api/v1/datacenters/{dc_code}/clusters/classic`).
- DB should compute the host-level timeseries aggregate of VM allocated CPU (**vCPU**, i.e. `SUM(number_of_cpus)` per host) by host/cluster, restricted to classic/KM clusters.
- Metric is allocation/capacity, **not usage**.
- Answer should include min/max/latest/avg allocated **vCPU**, direction (artış/azalış/sabit), variability (stddev / min-max range), sample count and source. Do **not** report this in GHz — `total_cpu_capacity_mhz` is `0`, so GHz would be fabricated.

### VM CPU top list

- DB primary because the existing API may only expose category/DC/customer summary, not a VM top list.
- Union/normalize Nutanix/IBM/VMware only when the fields are semantically valid.
- VMware VM is intentionally excluded from the VM-CPU DB templates: `vmware_vm_performance_metrics` has no usable CPU capacity denominator (`total_cpu_capacity_mhz = 0`), so a percentage cannot be computed without fabricating. If VMware has MHz but no valid capacity denominator, do not invent a percentage; present MHz or exclude it from percent ranking with an explicit limitation note.

## DB source windows

Some data may be delayed. For performance tables, anchor windows to each source's max timestamp if the latest data is older than `now()`. Do not say "no data in last 7 days" merely because ingestion is delayed if latest-source-anchored data exists and the UI uses that logic.