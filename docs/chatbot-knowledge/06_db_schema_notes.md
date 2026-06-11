# 06 — DB Schema Notes

This document is not a full schema dump. It lists known operational tables and semantic pitfalls for chatbot planning. The chatbot never writes SQL: DB access is read-only, restricted to allowlisted query templates (`db_query_registry.py`), with a row cap and a statement timeout. The tables below are the ones those templates and the backend routers actually read.

## VMware / Classic / KM

Known aggregate/query sources:

- `public.datacenter_metrics`
  - DC/hypervisor aggregated VMware legacy metrics.
  - Columns used by existing query registry include `datacenter`, `timestamp`, `total_cluster_count`, `total_host_count`, `total_vm_count`, `total_memory_capacity_gb`, `total_memory_used_gb`, `total_storage_capacity_gb`, `total_used_storage_gb`, `total_cpu_ghz_capacity`, `total_cpu_ghz_used`.
- `public.cluster_metrics`
  - Cluster-level VMware metrics used to split Classic vs Hyperconverged.
  - Classic split: `cluster ILIKE '%KM%'` (Klasik Mimari). Hyperconverged = Nutanix, i.e. non-KM cluster names.
  - Columns include `vhost_count`, `vm_count`, `cpu_ghz_capacity`, `cpu_ghz_used`, `memory_capacity_gb`, `memory_used_gb`, `total_capacity_gb`, `total_freespace_gb`, `cpu_usage_avg_perc`, `memory_usage_avg_perc`.
  - NOTE: GHz capacity/used (`cpu_ghz_capacity` / `cpu_ghz_used`) exist **only at the CLUSTER level here** and are current/fresh. There is no per-host allocated-GHz column anywhere (see the vCPU note below).
- `vmware_host_metrics`, `vmhost_metrics`
  - Host-level VMware tables. `vmhost_metrics` is read by the datacenter-api queries for per-host VMware data. (There is **no** `vmware_cluster_metrics` table — cluster-level VMware data lives in `cluster_metrics`, host-level in `vmware_host_metrics` / `vmhost_metrics`. Inspect live schema before an exact query.)
- `vmware_host_performance_metrics`
  - Per-host VMware CPU performance (`cpu_usage_avg_perc`, `cpu_ghz_used`, `cpu_ghz_capacity`, GHz). Backs the host-CPU DB tools.
- `vmware_vm_performance_metrics`
  - VM-level data. Reliable for CPU **usage** in MHz (`cpu_usage_avg_mhz`) and for VM `number_of_cpus`, but its CPU **capacity** denominator `total_cpu_capacity_mhz` is **0 in this dataset**.
  - Consequence 1: a VM CPU **percentage** cannot be derived from this table — report MHz or exclude from percent ranking; do not invent a `%`. (VMware VM is therefore excluded from the VM-CPU DB unions.)
  - Consequence 2: per-host **allocated CPU** for classic (KM) hosts is reported in **vCPU** — the sum of each host's VMs' `number_of_cpus` — **not GHz**, because allocated GHz cannot be computed without fabricating a capacity. This is exactly what `db_get_dc_classic_host_cpu_allocation_variability` (tool `get_dc_classic_host_cpu_allocation_variability`) returns: per-host allocated-vCPU avg/min/max/stddev/range with unit `'vCPU'`.

## Nutanix / HCI

- `public.nutanix_cluster_metrics`
  - Cluster summary/source mapping; columns include `cluster_name`, `cluster_uuid`, `num_nodes`, `total_vms`, `total_memory_capacity`, `used_memory`, `total_cpu_capacity`, `cpu_usage_avg`, storage fields and `collection_time`.
  - DC match commonly by `cluster_name ILIKE '%DC13%'`.
- `nutanix_host_performance_metrics`
  - Host-level CPU/performance source; join/resolve `cluster_uuid` to `nutanix_cluster_metrics.cluster_name` for the DC mapping.
- `nutanix_vm_performance_metrics`
  - VM-level CPU source; `cpu_usage_avg`/`cpu_usage_max` are in ppm (1e6 = 100%), so convert with `/10000` to get percent. Resolve the DC via `cluster_uuid` against `nutanix_cluster_metrics`.
- `nutanix_vm_metrics`
  - Nutanix (Acropolis) VM inventory used by the customer/compute hyperconverged queries.

## IBM Power

- `public.ibm_server_general`
  - Server/host-level data. DC often extracted from `server_details_servername` regex/ILIKE.
  - CPU fields include `server_processor_totalprocunits`, `server_processor_availableprocunits`, `server_processor_utilizedprocunits`, `server_physicalprocessorpool_assignedprocunits`. Timestamp column is `time`.
- `public.ibm_lpar_general`
  - LPAR count/inventory. DC from `lpar_details_servername` or related server name.
- `ibm_lpar_performance_metrics`
  - LPAR performance; the VM-like Power CPU source. Columns include `lpar_name`, `server_name`, `utilized_proc_units`, `entitled_proc_units`, and a `timestamp` column. CPU% = `utilized_proc_units / entitled_proc_units * 100`; uncapped LPARs may exceed 100%.
- `public.ibm_vios_general`
  - VIOS inventory/counts.

> Architecture mapping recap: Classic = cluster name contains `KM`; Hyperconverged = Nutanix (non-KM cluster names); Power = IBM / LPAR.

## Timestamp columns

Common names:

- VMware aggregate / `cluster_metrics` / `vmware_*_performance_metrics`: `timestamp`
- Nutanix: `collection_time`
- IBM `ibm_server_general`: `time`; IBM `ibm_lpar_performance_metrics`: `timestamp`
- Newer performance / ingest tables: `collectiontime`, `collection_time`, `inserted_at`

Do not assume `now() - interval '7 days'` if ingestion is delayed; anchor to each source's max collection timestamp when appropriate (the VM-CPU and classic-variability templates anchor to each table's own `max(...)` rather than `now()`).

## Sensitive fields guard

Do not query or include:

- password, passwd, pwd, password_hash
- token, api_key, secret
- bind_password
- salt, private_key
- connection strings
- LDAP bind credentials

## Available DB / API tools for host- and VM-level work

API endpoints often aggregate data, so host/VM-level top lists and variability come from read-only DB tools:

- Host CPU: `get_dc_host_cpu_latest`, `get_dc_host_cpu_top`, `get_dc_host_cpu_summary` (VMware GHz, Nutanix GHz, IBM cores).
- VM CPU: `get_dc_vm_cpu_top`, `get_dc_vm_cpu_latest`, `get_dc_vm_cpu_summary` (Nutanix percent, IBM LPAR cores; VMware VM excluded — zero capacity).
- Classic allocation: `get_dc_classic_host_cpu_allocation_variability` (per-KM-host allocated **vCPU** variability).

Cluster lists and Zabbix storage trend are exposed via dedicated tools/endpoints:

- `get_dc_classic_clusters` → `/api/v1/datacenters/{dc_code}/clusters/classic`
- `get_dc_hyperconverged_clusters` → `/api/v1/datacenters/{dc_code}/clusters/hyperconverged`
- `get_dc_zabbix_storage_trend` → `/api/v1/datacenters/{dc_code}/zabbix-storage/trend`

There is **no** `/power` cluster endpoint and no `get_dc_power_context` tool. IBM Power context is part of `get_datacenter_detail` (`/api/v1/datacenters/{dc_code}`).

## Known limitations

- VMware VM CPU percent is **not** derivable: `vmware_vm_performance_metrics.total_cpu_capacity_mhz = 0`. Report MHz or exclude from percent ranking rather than hallucinating `%`.
- Per-host classic allocated CPU is in **vCPU** (sum of `number_of_cpus`), not GHz — there is no per-host GHz capacity to divide by. Fresh per-cluster GHz lives only in `cluster_metrics`.
- IBM LPAR CPU can exceed 100% in uncapped/entitled-unit semantics.
- API endpoints often aggregate data; the read-only DB tools above are required for host/VM-level top lists and variability.
