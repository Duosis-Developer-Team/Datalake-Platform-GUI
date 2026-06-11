# 01 — WebUI Pages and Context

## Page context yardımcıdır, zorunlu değildir

Chatbot kullanıcı sorusunu cevaplamak için current page context'e bağımlı olmamalıdır. Page context yalnızca ek sinyaldir:

- `pathname`
- `selected_datacenter`
- `selected_customer`
- `time_range`
- `page_title`
- visible sections / active tabs

Parametre çıkarma önceliği:

1. User message explicit values
2. Conversation structured context
3. Frontend page context
4. Domain defaults
5. Clarification question

User message explicit ise frontend context'i override eder. Örnek: customer page'de bile kullanıcı "DC13 Klasik host" derse customer tool seçilmemelidir.

## Ana sayfalar

| Route | Page | Domain | Typical data |
|---|---|---|---|
| `/` | Overview/Home | global platform overview | dashboard overview, DC summary, physical inventory |
| `/datacenters` | Data Centers | all DC list | datacenter summaries, SLA badges |
| `/datacenter/<dc>` | Data Center View | DC-scoped infra | summary, virtualization, storage, backup, physical inventory, network, availability |
| `/dc-detail/<dc>` | DC Detail / floor/rack detail | DC/rack/device | racks, physical inventory, floor map |
| `/global-view` | Global View | multi-DC comparison | summaries and per-DC details |
| `/availability-annual` | Availability | SLA/availability | annual SLA, per-DC service availability |
| `/customers` | Customers | customer list | customer names/search |
| `/customer-view` | Customer View | customer resources | resources, availability, S3, physical devices, ITSM, sales |
| `/query-explorer` | Query Explorer | registered SQL/queries | query-api `/api/v1/queries/{query_key}` |
| `/crm/sellable-potential` | CRM Sellable Potential | sales/capacity opportunity | sellable summary/by panel/by family, metric snapshots |
| `/settings/*` | Settings/IAM/CRM config | admin/config | IAM, roles, LDAP, CRM mapping/thresholds/ratios |

## Datacenter View tabs

`src/pages/dc_view.py` uses many `api_client` calls around the DC page. The right-hand column notes the matching read-only **chatbot tool** (if any) so the same DC data is reachable from chat:

- Summary → `get_dc_details`, `get_sla_by_dc`, `get_dc_sales_potential_v2`
  - Chatbot: `get_datacenter_detail` (`/api/v1/datacenters/{dc_code}`) — also carries the **Power (IBM/LPAR) architecture context**; there is no separate power-cluster tool. `get_sla`, `get_sellable_summary`/`get_sellable_by_panel`/`get_sellable_by_family`.
- Virtualization → `get_classic_cluster_list`, `get_hyperconv_cluster_list`, `get_classic_metrics_filtered`, `get_hyperconv_metrics_filtered`
  - Chatbot cluster lists: `get_dc_classic_clusters` (`/api/v1/datacenters/{dc_code}/clusters/classic`) and `get_dc_hyperconverged_clusters` (`/api/v1/datacenters/{dc_code}/clusters/hyperconverged`).
  - Chatbot compute metrics: `get_dc_compute_classic` (`/api/v1/datacenters/{dc_code}/compute/classic`) and `get_dc_compute_hyperconverged` (`/api/v1/datacenters/{dc_code}/compute/hyperconverged`).
  - Mimari ayrımı: **Klasik (KM)** = cluster adında `KM` geçenler (VMware), **Hyperconverged** = `KM` içermeyen Nutanix cluster'ları, **Power** = IBM/LPAR. Power için ayrı bir cluster endpoint'i yoktur; Power context `get_datacenter_detail` içinden gelir.
- Storage → `get_dc_storage_capacity`, `get_dc_storage_performance`, `get_dc_zabbix_storage_*`, SAN tools
  - Chatbot: `get_dc_storage_capacity` (`/api/v1/datacenters/{dc_code}/storage/capacity`), `get_dc_storage_performance` (`/api/v1/datacenters/{dc_code}/storage/performance`), and the Zabbix storage trend via `get_dc_zabbix_storage_trend` (`/api/v1/datacenters/{dc_code}/zabbix-storage/trend`).
- Backup & Replication → `get_dc_netbackup_pools`, `get_dc_zerto_sites`, `get_dc_veeam_repos`, backup jobs
  - Chatbot: `get_dc_backup_summary` and `get_dc_backup_jobs` (NetBackup + Zerto + Veeam), `get_dc_s3_pools`.
- Physical Inventory → `get_physical_inventory_dc`
- Network → `get_dc_network_filters`, `get_dc_network_port_summary`, `get_dc_network_95th_percentile`, `get_dc_network_interface_table`
  - Chatbot: `get_dc_network_summary` (port-summary + 95th-percentile multi-fetch).
- Availability → `get_dc_availability_sla_item`
  - Chatbot: `get_sla`.

## Context extraction rules

- `/datacenter/DC13` → `dc_code = DC13`
- `/dc-detail/DC13` → `dc_code = DC13`
- Text containing `DC13`, `AZ11`, `ICT`, `UZ`, `DH` patterns → extracted as `dc_code` (regex: `(?:DC|AZ|ICT|UZ|DH)\d+`)
- "son bir hafta", "son 7 gün" → `days=7`
- "son bir ay", "son 30 gün" → `days=30` (lookback `days` is bounded to 1–30)
- "en yüksek 3", "top 3" → `limit=3`
- "en yüksek 10", "top 10" → `limit=10`
- "Direkt DB", "PostgreSQL", "veritabanı" → `source_preference=db`
- "endpoint", "API", "WebUI'da görünen" → `source_preference=api`

## Stale context guard

If user asks a datacenter-scope metric (`DC13`, `classic`, `host`, `cluster`, `VM`, `SLA`, `backup`, `storage`, `network`) and the frontend still has a stale `selected_customer` (e.g. a customer left over from the previous page), ignore the customer context unless the user explicitly mentions that customer / a customer scope. The DC-scoped intent in the user message wins over the lingering frontend `selected_customer`.