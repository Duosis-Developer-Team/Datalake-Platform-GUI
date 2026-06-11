# 04 — Metric Semantics

## CPU terms

| Term | Meaning | Unit examples | Do not confuse with |
|---|---|---|---|
| CPU usage / utilization / tüketim / kullanım | How much CPU is actually consumed over time | %, MHz, GHz, proc units | allocated/capacity |
| CPU allocated / atanmış CPU / CPU allocation | How much CPU/vCPU/GHz is assigned to VMs/LPARs | vCPU (classic per-host), GHz (cluster-level), MHz, proc units | actual usage |
| CPU capacity | Total available CPU capacity | GHz, cores, proc units | used/allocated |
| CPU used | Used/consumed CPU | GHz, %, proc units | allocated |
| CPU ready/demand | virtualization performance signals | ms/%/MHz | capacity |

> **Allocated-CPU unit guard (repo-validated):** Classic (KM) **per-host** allocated CPU is reported in **vCPU** — the sum of each host's VMs' `number_of_cpus` (`vmware_vm_performance_metrics`). It is **not** reported in GHz, because `vmware_vm_performance_metrics.total_cpu_capacity_mhz` is `0` in this dataset, so allocated GHz cannot be computed without fabrication. GHz allocation/capacity values (`cpu_ghz_capacity`, `cpu_ghz_used`) exist only at **cluster level** in the `cluster_metrics` table.

## Usage vs allocation examples

- "en çok CPU tüketen VM" → VM CPU usage/performance top list.
- "VM'lere atanmış CPU miktarı" → allocation/capacity aggregate.
- "CPU kapasite değişimi allocated" → allocation variability, not utilization. (Classic per-host: tool `get_dc_classic_host_cpu_allocation_variability`, reported in **vCPU** — label the unit as vCPU, never GHz.)
- "utilization" → used/capacity ratio.
- "allocation" tab toggle → assigned/allocated resources.

## Architecture names

| User says | Canonical architecture | Provider |
|---|---|---|
| Klasik Mimari, Classic, KM | `classic` | VMware |
| Hyperconverged, HCI, Nutanix | `hyperconverged` | Nutanix |
| Power, Power Mimari, LPAR | `power` | IBM Power |

> **Power note (repo-validated):** There is **no** dedicated `/power` or `/clusters/power` endpoint and **no** `get_dc_power_context` tool. Power/IBM/LPAR context is served by `get_datacenter_detail` (`/api/v1/datacenters/{dc_code}`). Cluster enumeration tools exist only for the other two architectures: `get_dc_classic_clusters` (`/api/v1/datacenters/{dc_code}/clusters/classic`) and `get_dc_hyperconverged_clusters` (`/api/v1/datacenters/{dc_code}/clusters/hyperconverged`).

## Entity hierarchy

```text
Datacenter (DC13)
  ├─ Architecture/platform (classic/hyperconverged/power)
  │   ├─ Cluster
  │   │   ├─ Host
  │   │   │   └─ VM / LPAR
  └─ Customer usage/sales/etc. (customer-scoped, not default for DC queries)
```

- Classic / Hyperconverged cluster lists are available via `get_dc_classic_clusters` and `get_dc_hyperconverged_clusters`. Power (IBM/LPAR) has no separate cluster-list tool — use `get_datacenter_detail`.

## Calculations

| User phrase | Calculation |
|---|---|
| en yüksek, top, en çok | top list sorted descending |
| değişken, değişim, dalgalanma, variance | variability/trend: max-min, pct, direction |
| son değer, anlık, latest | latest snapshot |
| trend, zaman içinde | time series or aggregated window |
| karşılaştır | compare sources/entities |
| riskli, kritik | threshold/risk analysis |
| sürekli yüksek | sustained high: high average and enough samples |
| peak/spike | max high but average lower |

> For storage-capacity-over-time ("trend, zaman içinde") questions, the available time-window tool is `get_dc_zabbix_storage_trend` (`/api/v1/datacenters/{dc_code}/zabbix-storage/trend`).

## Units and conversion guard

- Do not invent `%` if only MHz/GHz exists and no capacity denominator is available.
- **Classic per-host allocated CPU is vCPU, not GHz.** Report it as a vCPU count (sum of VMs' `number_of_cpus`). Do not fabricate GHz — `vmware_vm_performance_metrics.total_cpu_capacity_mhz` is `0`. GHz allocation/capacity figures come only from the **cluster-level** `cluster_metrics` table (`cpu_ghz_capacity` / `cpu_ghz_used`), which is fresh/current.
- If Nutanix CPU usage is stored in ppm-like values, use documented conversion only.
- IBM uncapped LPAR utilization may exceed 100%; explain "uncapped/entitled units" rather than clamping.
- Always label units: GHz, MHz, %, proc units, vCPU, cores.
