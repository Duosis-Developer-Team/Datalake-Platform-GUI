# 05 — Architecture Mapping

## Datacenter code patterns

Accept uppercase/lowercase and normalize uppercase:

- `DC13`, `dc13`
- `AZ11`, `az11`
- `ICT*`, `UZ*`, `DH*` when present

Regex family: `\b(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)\b` case-insensitive.

## Classic / KM / VMware

Canonical `architecture = classic`.

Signals:

- user text: `klasik`, `classic`, `KM`, `Klasik Mimari`
- endpoint: `/datacenters/{dc_code}/clusters/classic` — chatbot tool `get_dc_classic_clusters` (returns the classic/KM cluster name list)
- endpoint: `/datacenters/{dc_code}/compute/classic` — chatbot tool `get_dc_compute_classic`
- DB source: VMware/classic tables (`cluster_metrics`, `vmware_host_metrics`, `vmware_host_performance_metrics`, `vmware_vm_performance_metrics`, etc.). Note: cluster-level CPU GHz capacity/used (`cpu_ghz_capacity` / `cpu_ghz_used`) lives on `cluster_metrics` (fresh/current, cluster level only). There is no `vmware_cluster_metrics` table.
- cluster pattern: usually includes `KM` in cluster name (`DC13-KM2-CLS-NVME`, `DC13-KM3-CLS-NVME`, `DC13-KM4-CLS-SSD`, etc.)

Do not route Classic/KM questions to customer API unless customer is explicit.

## Hyperconverged / Nutanix / HCI

Canonical `architecture = hyperconverged`.

Signals:

- user text: `hyperconverged`, `hci`, `nutanix`
- endpoint: `/datacenters/{dc_code}/clusters/hyperconverged` — chatbot tool `get_dc_hyperconverged_clusters`
- endpoint: `/datacenters/{dc_code}/compute/hyperconverged` — chatbot tool `get_dc_compute_hyperconverged`
- DB source: `nutanix_cluster_metrics`, `nutanix_host_performance_metrics`, `nutanix_vm_performance_metrics`, `nutanix_vm_metrics`

## Power / IBM / LPAR

Canonical `architecture = power`.

Signals:

- user text: `power`, `ibm`, `lpar`, `power mimari`
- DB source: `ibm_server_general`, `ibm_lpar_general`, `ibm_lpar_performance_metrics`, `ibm_vios_general`

There is **no** `/power` cluster endpoint and **no** `get_dc_power_context` tool. Power context is delivered as part of `get_datacenter_detail` (`/api/v1/datacenters/{dc_code}`). Route Power/IBM/LPAR questions through the datacenter detail tool, not a non-existent power-cluster endpoint.

## Storage trends (Zabbix)

Storage capacity/performance trend questions for a datacenter map to the chatbot tool `get_dc_zabbix_storage_trend` (`/api/v1/datacenters/{dc_code}/zabbix-storage/trend`), alongside `get_dc_storage_capacity` and `get_dc_storage_performance`.

## Allocated-CPU unit (classic hosts)

Per-host classic (KM) "allocated CPU" is reported in **vCPU** — the sum of each host's VMs' `number_of_cpus` from `vmware_vm_performance_metrics`, surfaced via `get_dc_classic_host_cpu_allocation_variability`. It is **not** GHz: `vmware_vm_performance_metrics.total_cpu_capacity_mhz` is `0` in this dataset, so allocated GHz cannot be computed without fabrication. GHz capacity/used figures exist only at the **cluster** level on `cluster_metrics`.

## DB access guardrails

Read-only DB tools run through an allowlisted query-template registry only. No LLM-generated SQL, with a row cap and statement timeout enforced on every query.

## Route independence

Even if user is on `/customer-view`, a question containing `DC13`, `Klasik`, `host`, `allocated CPU` (vCPU) is a datacenter/classic host query and must ignore stale `selected_customer` context.