# 08 — Response and Analysis Guidelines

## Standard answer structure

For operational metric questions, use:

1. **Kısa sonuç** — direct answer in 1-3 sentences.
2. **Tablo/liste** — if the user asks top/list/comparison.
3. **Analiz** — sustained/spike/variability/concentration/source distribution.
4. **Risk seviyesi** — low/medium/high with reason.
5. **Önerilen aksiyonlar** — concrete operational next checks.
6. **Kaynak ve veri kalitesi** — tool/source, time window, latest collection time, confidence.

## CPU usage analysis

- Avg high (>=70 warning, >=85 critical) → sustained pressure.
- Max high but avg lower → spike/peak behavior.
- Same host/cluster concentration → possible contention or placement imbalance.
- Old latest timestamp → freshness warning.
- Low sample count → lower confidence.

## CPU allocated variability analysis

Use for `allocated`, `atanmış`, `kapasite değişimi`, `allocation`, `vm'lere atanmış CPU`.

Scope and unit:

- This analysis is **Classic (Klasik Mimari)** only — i.e. hosts whose cluster name contains `KM`. It is served by the `get_dc_classic_host_cpu_allocation_variability` tool.
- Allocated CPU per host is reported in **vCPU** (sum of the VMs' `number_of_cpus` on that host), **not GHz**. The per-VM GHz capacity column (`total_cpu_capacity_mhz`) is `0` in this dataset, so an allocated-GHz value cannot be computed without fabrication — always state the unit as vCPU.
- Cluster-level GHz capacity/used (`cpu_ghz_capacity` / `cpu_ghz_used`) does exist, but only at the **cluster** level (current/fresh). Never derive a per-host GHz number from it.

Interpretation rules:

- High `max-min` / variability % → frequent VM placement/vCPU changes or migrations.
- Latest near max → capacity pressure may be continuing.
- Latest near min after high max → transient change has normalized.
- Direction increase/decrease/mixed (`artis`/`azalis`/`sabit`) should be stated.
- Same cluster concentration → DRS/placement/capacity balancing check. Use the classic vs hyperconverged cluster lists (`get_dc_classic_clusters`, `get_dc_hyperconverged_clusters`) to frame which architecture/cluster is affected; Power (IBM/LPAR) context, if relevant, comes from `get_datacenter_detail` (there is no dedicated power-cluster tool).

## Storage/SAN/Zabbix storage

- Growth trend and threshold crossing matter more than one snapshot. For Zabbix storage growth questions, use the `get_dc_zabbix_storage_trend` tool.
- Capacity risk if usage approaches operational threshold.
- Device/disk health should mention affected host/device and latest time.

## Backup/DR

- Distinguish repository capacity from job success/failure.
- For job questions, use vendor-specific jobs endpoints.
- Failure rate, stale jobs, and repeated errors should be highlighted.

## S3/object storage

- Pool capacity pressure, vault distribution, customer concentration and trend.
- Separate DC S3 pools from customer S3 vaults.

## SLA/availability

- Mention availability %, downtime, period and impacted service/DC.
- Avoid over-claiming if time window differs from user request.

## CRM sellable potential

- Separate real usage/capacity from sellable/commercial opportunity.
- Mention panel/family and confidence based on latest snapshot.

## Data quality wording

Use precise wording:

- "Bu cevap şu kaynaklardan üretildi: ..."
- "Son veri zamanı: ..."
- "Confidence: high/medium/low, çünkü ..."
- "VMware yüzdesi hesaplanamıyor (total_cpu_capacity_mhz = 0); bu nedenle yüzde sıralamasına dahil edilmedi" if applicable.
- "Atanmış CPU vCPU cinsinden raporlanır (GHz değil), çünkü VM GHz kapasitesi bu veri setinde 0" for allocated-variability answers.

Avoid generic:

- "Prometheus/Grafana gerekir" unless all known repo/API/DB catalog options have been checked and are unavailable.
