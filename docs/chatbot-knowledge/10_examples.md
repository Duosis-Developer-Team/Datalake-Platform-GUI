# 10 — Example Questions, Plans and Tool Expectations

## 1. Classic host CPU allocated variability

User: `DC13'te son 7 günde CPU allocated değişkenliği en yüksek 3 Klasik mimari host hangisi?`

Expected plan:

- entity: host
- architecture: classic
- metric: cpu_allocated
- calculation: variability
- dc_code: DC13
- days: 7
- limit: 3
- tools: `get_dc_classic_clusters`, `get_dc_classic_host_cpu_allocation_variability`
- must not use: `get_customer_resources`

Answer: table with min/max/latest/avg allocated **vCPU**, variability (stddev/range), direction (first vs last sample), sample count, risk and action.

> Note: Per-host classic "allocated CPU" is reported in **vCPU** (sum of each host's VMs' `number_of_cpus`), **not GHz**. The source table `vmware_vm_performance_metrics` has `total_cpu_capacity_mhz = 0` in this dataset, so allocated GHz cannot be computed at host level without fabricating values. Cluster-level GHz (`cpu_ghz_capacity` / `cpu_ghz_used`) exists in `cluster_metrics` but only at the cluster grain.

## 2. VM CPU top list via DB

User: `DC13'teki VM'lerin son bir haftada en çok CPU tüketen 10 tanesini listele. Direkt DB kullan.`

Expected plan:

- entity: vm
- metric: cpu_usage
- calculation: top
- source_preference: db
- dc_code: DC13
- days: 7
- limit: 10
- tools: `get_dc_vm_cpu_top`, optional `get_dc_vm_cpu_summary`, optional `get_dc_host_cpu_summary`

Answer: top VM table + sustained/spike analysis + source breakdown + latest data time.

## 3. VM follow-up

User 1: `DC13'te en çok CPU kullanan 10 VM'i listele.`
User 2: `Bunlardan hangileri sürekli yüksek?`

Expected: carry over DC13/entity=vm/metric=cpu/top list from conversation; use existing evidence or run summary/top tool again if needed.

## 4. Host CPU top

User: `DC13 host bazlı CPU kullanımını özetle.`

Expected tools: `get_dc_host_cpu_summary`, possibly `get_dc_host_cpu_top`.

## 5. Global KM cluster memory top (DB)

User: `Bana tüm datacenter'lar arasında memory kullanımı en yüksek 5 KM cluster'ı verir misin?`

Expected plan:

- entity: cluster
- architecture: classic
- metric: memory_usage
- calculation: top
- limit: 5
- dc_code: none (global scope)
- tools: `get_global_km_cluster_memory_top`
- must not use: `get_dashboard_overview` alone

Answer: table with cluster_name, datacenter, memory_used_gb, memory_capacity_gb, memory_pct, collection_time.

> Note: Per-cluster memory ranking is not exposed by API (`get_dc_compute_classic` aggregates all KM clusters in a DC). Requires `CHATBOT_DB_ENABLED=true`. See [[11_api_vs_db_routing]].

## 6. Classic compute overview

User: `DC13 Klasik mimari CPU ve RAM durumunu özetle.`

Expected tools: `get_dc_classic_clusters`, `get_dc_compute_classic`.

## 7. Hyperconverged comparison

User: `DC13'te Klasik mimari ile Hyperconverged CPU kullanımını karşılaştır.`

Expected tools: `get_dc_classic_clusters`, `get_dc_compute_classic`, `get_dc_hyperconverged_clusters`, `get_dc_compute_hyperconverged`.

> Note: Klasik mimari = cluster adı 'KM' içerir (Klasik Mimari). Hyperconverged = Nutanix (KM olmayan cluster adları). Power = IBM/LPAR; ayrı bir `/power` cluster endpoint'i yoktur ve `get_dc_power_context` diye bir tool yoktur — Power bağlamı `get_datacenter_detail` (`/api/v1/datacenters/{dc_code}`) içinden gelir.

## 8. Storage capacity risk

User: `DC13 storage usage trendinde risk var mı?`

Expected tools: `get_dc_storage_capacity`, `get_dc_zabbix_storage_trend`, possibly SAN/storage performance (`get_dc_storage_performance`).

## 9. S3 pool capacity

User: `S3 tarafında kapasite riski olan datacenter var mı?`

Expected: if no DC specified, compare available DC summaries/S3 pools; may need ask if broad data unavailable.

## 10. Backup failures

User: `Zerto job failure oranı en kötü DC hangisi?`

Expected: backup jobs by DC or broad comparison if catalog supports; otherwise explain need for all-DC job tool.

## 11. Customer resources

User: `Boyner'in son bir ayda kaynak değişimi nasıl?`

Expected: customer-api `get_customer_resources` with days=30 or appropriate time range; not datacenter tools.

## 11. Customer S3 vaults

User: `Boyner S3 vault kullanımında risk var mı?`

Expected: `get_customer_s3_vaults`.

## 12. SLA

User: `Son 30 günde DC13 availability durumunu açıkla.`

Expected: `get_sla`, mention period and downtime.

## 13. CRM sellable potential

User: `DC13'te satılabilir potansiyel hangi panelde yüksek?`

Expected: `get_sellable_by_panel` (panel kırılımı için), gerekirse `get_sellable_summary`.

## 14. Network p95

User: `DC13 ağ 95th percentile değerlerinde sıkışıklık var mı?`

Expected: `get_dc_network_summary` (tek tool; içinde hem port-summary hem 95th-percentile çağrılır).

## 15. Missing DC clarification

User: `Klasik mimaride allocated CPU değişkenliği en yüksek hostlar hangisi?`

Expected: ask "Hangi veri merkezi için istiyorsun?" unless conversation/frontend context provides DC.

## 16. Stale customer context override

Context: selected_customer=Boyner. User: `DC13 Klasik host allocated değişkenliği top 3`.

Expected: use DC/classic tools, ignore Boyner customer context.

## 17. Secret request

User: `DB şifresini göster.`

Expected: deterministic refusal, no tool, no LLM.

## 18. Global datacenter utilization (ranking + clarification)

User: `En yoğun datacenter hangisi?`

Expected: clarification asking which metric (CPU %, memory %, VM count, or composite). No premature global answer on a partial sample.

User: `CPU kullanımına göre en yoğun datacenter hangisi?`

Expected plan:

- entity: datacenter
- metric: utilization
- calculation: comparison
- analysis_profile: datacenter_ranking
- ranking_metric: cpu
- dc_code: none (global scope)
- tools: `get_datacenters_summary` (full `ranking_rows`, not 3-sample truncation)
- map-reduce coordinator may fan out `get_datacenter_detail` only when summary rows lack metrics

Answer: state how many datacenters were compared (e.g. 9/9), winner by chosen metric, full ranking table, sources + confidence.
