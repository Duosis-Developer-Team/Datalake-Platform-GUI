# Müşteri & CRM Sorguları (Sellable hariç)

> Bkz. [README](README.md) — mimari + ortak desenler. Bu dosya **Sellable Potential hesaplama pipeline'ını kapsamaz**;
> o iş [05-sellable-potential.md](05-sellable-potential.md)'de anlatılır. Burada CRM **konfigürasyon tabloları**
> (`gui_crm_*`) **tanımlanır**; bu konfigürasyonun Sellable tarafında nasıl **tüketildiği** 05'tedir.

---

## Genel Bakış

Bu doküman müşteri (tenant) odaklı tüm sorguları kapsar:

| Ekran | İçerik | Kaynak query dosyası |
|---|---|---|
| **customers_list** | Aktif müşteri (tenant) adları listesi | `customer-api/.../customer.py` (`CUSTOMER_NAME_LIST`) |
| **customer_view** | Müşterinin altyapı varlıkları (VM/LPAR/host), backup/DR, depolama; ITSM özeti; CRM YTD satış | `customer-api/.../customer.py`, `itsm.py`, `crm_sales.py` |
| **settings** (CRM config) | Service mapping (ürün→sayfa), müşteri alias, threshold, fiyat override, calc config | `customer-api/.../service_mapping.py`, `crm_config.py` |
| **CRM Overview** | Discovery satır sayıları, tüm ürün listesi | `customer-api/.../crm_sales.py` |
| **DC sales-potential (v1/v2)** | DC bazlı YTD satış + (legacy) katalog×kapasite | `datacenter-api/.../crm_potential.py` |

Müşteri varlıkları, ham datalake telemetri tablolarında **isim/desen (ILIKE pattern)** ile filtrelenir; örn.
`vmname ILIKE '%boyner%'`. CRM/satış verisi ise ham `discovery_crm_*` tablolarında **CRM accountid listesi** ile
filtrelenir. İsim → accountid eşleştirmesi (alias) ve ürün → kategori eşleştirmesi **webui-db**'de tutulur ve
servis katmanında (Python) çözülür — cross-DB join yoktur.

---

## Veri Kaynakları

### Datalake DB (ham telemetri / discovery, `public.*`)

| Tablo | Kullanım | Önemli kolonlar |
|---|---|---|
| `vm_metrics` | VMware VM telemetri (Classic = `cluster ILIKE '%KM%'`, Hyperconv = `NOT ILIKE`) | `vmname`, `cluster`, `number_of_cpus`, `total_memory_capacity_gb`, `provisioned_space_gb`, `used_space_gb`, `cpu_usage_*_mhz`, `memory_usage_*_perc`, `timestamp` |
| `nutanix_vm_metrics` | Nutanix (AHV) VM telemetri | `vm_name`, `cluster_uuid`, `cpu_count`, `memory_capacity`, `disk_capacity`, `used_storage`, `cpu_usage_*`, `memory_usage_*`, `collection_time` |
| `nutanix_cluster_metrics` | Nutanix cluster özeti / uuid çözümü | `cluster_name`, `cluster_uuid`, `datacenter_name`, `num_nodes`, `total_vms`, `collection_time` |
| `datacenter_metrics` | VMware DC özeti | `datacenter`, `total_cluster_count`, `total_host_count`, `total_vm_count`, `timestamp` |
| `cluster_metrics` | VMware cluster keşfi (arch_type) | `cluster`, `timestamp` |
| `ibm_lpar_general` | Power/HANA LPAR | `lparname`, `lpar_details_servername`, `lpar_details_state`, `lpar_processor_currentvirtualprocessors`, `lpar_processor_utilizedprocunits`, `lpar_memory_logicalmem`, `lpar_memory_backedphysicalmem`, `time` |
| `ibm_vios_general` | VIOS | `viosname`, `vios_details_servername`, `time` |
| `ibm_server_general` | Power host | `server_details_servername`, `time` |
| `vmhost_metrics` | vCenter host (güç) | `vmhost`, `power_usage`, `timestamp` |
| `raw_veeam_sessions` | Veeam yedekleme oturumları | `name`, `session_type`, `platform_name` |
| `raw_zerto_vpg_metrics` | Zerto VPG (DR) | `id`, `name`, `vmscount`, `provisioned_storage_mb`, `collection_timestamp` |
| `raw_netbackup_jobs_metrics` | NetBackup işleri | `workloaddisplayname`, `jobtype`, `percentcomplete`, `kilobytestransferred`, `dedupratio`, `collection_timestamp` |
| `raw_ibm_storage_vdisk` | IBM storage hacim kapasitesi | `name`, `capacity`, `timestamp` |
| `discovery_netbox_inventory_device` | NetBox envanter (tenant adı, fiziksel cihaz) | `name`, `tenant_name`, `status_value`, `tenant_id`, `site_id/name`, `location_id/name`, `device_type_*`, `collection_time` |
| `discovery_netbox_virtualization_vm` | NetBox VM → müşteri (custom field) | `site_name`, `custom_fields_musteri` |
| `discovery_loki_racks` | Rack kapasitesi (legacy v1) | `site_name`, `u_height` |
| `discovery_servicecore_users` | ITSM kullanıcıları | `user_id`, `full_name`, `email`, `is_enabled`, `soft_deleted` |
| `discovery_servicecore_incidents` | ITSM incident | `ticket_id`, `org_user_id`, `subject`, `state_text`, `status_name`, `priority_name`, `category_name`, `created_date`, `target_resolution_date`, `closed_and_done_date`, `is_deleted` |
| `discovery_servicecore_servicerequests` | ITSM service request | `service_request_id`, `requester_id`, `request_date`, `target_resolution_date`, ... |
| `discovery_crm_accounts` | CRM hesaplar (sayım) | — |
| `discovery_crm_products` | CRM ürün kataloğu | `productid`, `name`, `productnumber`, `defaultuomid_name`, `statecode` |
| `discovery_crm_salesorders` | Satış siparişleri | `salesorderid`, `customerid`, `statecode`, `statecode_text`, `totalamount`, `ordernumber`, `fulfilldate`, `submitdate`, `modifiedon`, `transactioncurrency_text` |
| `discovery_crm_salesorderdetails` | Sipariş satırları | `salesorderid`, `productid`, `product_name`, `productdescription`, `quantity`, `priceperunit`, `extendedamount`, `uomid_name` |
| `discovery_crm_pricelevels` / `discovery_crm_productpricelevels` | Fiyat listeleri (prod'da genelde boş) | `pricelevelid`, `productid`, `amount`, `uomid_name`, `name`, `statecode` |

### WebUI DB (uygulamaya özel `gui_crm_*` konfig tabloları)

| Tablo | Amaç | Önemli kolonlar |
|---|---|---|
| `gui_crm_service_pages` | GUI sayfa/kategori kayıt defteri (page_key registry) | `page_key`, `category_label`, `gui_tab_binding`, `resource_unit`, `icon`, `route_hint`, `tab_hint`, `sub_tab_hint` |
| `gui_crm_service_mapping_seed` | YAML türevli ürün→sayfa seed eşleştirmesi | `productid`, `page_key` |
| `gui_crm_service_mapping_override` | Operatör override eşleştirmesi | `productid`, `page_key`, `notes`, `updated_by`, `updated_at` |
| `gui_crm_customer_alias` | CRM hesap ↔ kanonik müşteri ↔ NetBox musteri değeri (legacy sales alias) | `crm_accountid`, `crm_account_name`, `canonical_customer_key`, `netbox_musteri_value`, `notes`, `source`, `created_at`, `updated_at` |
| `gui_crm_customer_source_mapping` | CRM müşteri ↔ veri kaynağı bazlı çoklu eşleştirme kuralları | `crm_accountid`, `data_source`, `match_method`, `match_value`, `priority`, `enabled`, `source`, `created_at`, `updated_at` |
| `gui_crm_threshold_config` | Sellable tavan % (kaynak tipi, opsiyonel DC) | `id`, `panel_key`, `resource_type`, `dc_code`, `sellable_limit_pct`, `notes`, `updated_by`, `updated_at` |
| `gui_crm_price_override` | Operatör birim fiyatları (boş price-level'a fallback) | `productid`, `product_name`, `unit_price_tl`, `resource_unit`, `currency`, `notes`, `updated_by`, `updated_at` |
| `gui_crm_calc_config` | Genel sayısal/string hesaplama değişkenleri | `config_key`, `config_value`, `value_type`, `description`, `updated_by`, `updated_at` |

> **Not:** `gui_crm_threshold_config`, `gui_crm_price_override` ve `gui_crm_calc_config` aynı zamanda Sellable
> pipeline'ı tarafından okunur — tablo/sorgu tanımları **burada**, tüketim mantığı **05**'tedir.

---

## Sorgular

### Customer (datalake — `customer-api` ve `datacenter-api`)

İki servis de neredeyse aynı müşteri sorgu setini barındırır. **Fark:** `datacenter-api` sürümü silinmiş VM
(`LEFT(name,1)='_'`) filtresi içermez ve Power memory böleni `/1024.0` kullanır; `customer-api` sürümü silinmiş VM
filtreleri (`<> '_'`), ayrı silinmiş-VM listeleri, util min/avg/max kolonları ve Power memory böleni `/1.048576`
içerir. Aşağıdaki SQL'ler aksi belirtilmedikçe `customer-api/.../customer.py`'den verbatim alınmıştır.

#### `CUSTOMER_NAME_LIST` — NetBox tenant names (legacy infra discovery)

Used for infra search-key resolution and physical inventory tenant matching. **Not** the primary source for `GET /api/v1/customers` since 2026-06.

#### `CRM_PROJECT_CUSTOMER_LIST` — CRM project customers (`GET /api/v1/customers`)

```sql
SELECT DISTINCT TRIM(a.name) AS name
FROM public.discovery_crm_accounts a
JOIN public.discovery_crm_salesorders so ON so.customerid = a.accountid
WHERE so.ordernumber LIKE 'PRJ-%'
  AND TRIM(COALESCE(a.name, '')) <> ''
ORDER BY name
```

Ne yapar: CRM'de en az bir `PRJ-*` sales order kaydı olan aktif customer hesap adlarını döner. Boyner CRM hesabı varsa legacy `Boyner` etiketi CRM account adıyla hizalanır; PRJ kaydı olmasa da Boyner pilot olarak listede kalabilir.

Satış/finans endpoint'leri (`crm_sales.py`) ayrı kapsamda **`statecode IN (3,4)`** realized-only filtresini kullanmaya devam eder — bkz. [[ADR-0010-crm-realized-sales-only-scope]].

#### `CUSTOMER_NAME_LIST` (NetBox) — verbatim

```sql
SELECT DISTINCT TRIM(tenant_name) AS name
FROM public.discovery_netbox_inventory_device
WHERE status_value = 'active'
  AND tenant_name IS NOT NULL
  AND BTRIM(tenant_name) <> ''
ORDER BY name
```

Ne yapar: NetBox envanter snapshot'ından aktif cihazların distinct tenant adlarını çeker — müşteri seçim listesi.
Parametreler: yok.

#### `CUSTOMER_VM_DEDUP` — VMware/Nutanix VM çakışma sayımı

```sql
WITH all_vmware_vms AS (
    SELECT DISTINCT ON (vmname) vmname
    FROM public.vm_metrics
    WHERE vmname ILIKE %s AND timestamp BETWEEN %s AND %s
    ORDER BY vmname, timestamp DESC
),
all_nutanix_vms AS (
    SELECT DISTINCT ON (vm_name) vm_name
    FROM public.nutanix_vm_metrics
    WHERE vm_name ILIKE %s AND collection_time BETWEEN %s AND %s
    ORDER BY vm_name, collection_time DESC
)
SELECT
    (SELECT COUNT(*)::int FROM all_vmware_vms v WHERE NOT EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname)) AS vmware_only,
    (SELECT COUNT(*)::int FROM all_vmware_vms v WHERE EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname)) AS in_both,
    (SELECT COUNT(*)::int FROM all_nutanix_vms n WHERE NOT EXISTS (SELECT 1 FROM all_vmware_vms v WHERE v.vmname = n.vm_name)) AS nutanix_only
```

Ne yapar: Bir VM hem VMware hem Nutanix'te görünebileceğinden (VMware-managed Nutanix), VM'leri tekilleştirerek
`vmware_only / in_both / nutanix_only` sayar — toplamda mükerrer saymayı önler.
Parametreler: `(vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts)`.

#### `CUSTOMER_INTEL_CPU_TOTALS` / `_MEMORY_TOTALS` / `_DISK_TOTALS`

Üç sorgu da aynı dedup mantığını kullanır: her VM'in en güncel satırı alınır, sonra `vmware_only + (in_both VMware
+ nutanix_only)` şeklinde toplanır. CPU örneği:

```sql
WITH all_vmware_vms AS (
    SELECT DISTINCT ON (vmname)
        vmname,
        number_of_cpus
    FROM public.vm_metrics
    WHERE vmname ILIKE %s AND "timestamp" BETWEEN %s AND %s
    ORDER BY vmname, "timestamp" DESC
),
all_nutanix_vms AS (
    SELECT DISTINCT ON (vm_name)
        vm_name,
        cpu_count
    FROM public.nutanix_vm_metrics
    WHERE vm_name ILIKE %s AND collection_time BETWEEN %s AND %s
    ORDER BY vm_name, collection_time DESC
)
SELECT
    (
        SELECT COALESCE(SUM(v.number_of_cpus), 0)
        FROM all_vmware_vms v
        WHERE NOT EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname)
    ) AS "Total CPU (VMware)",
    (
        (
            SELECT COALESCE(SUM(v.number_of_cpus), 0)
            FROM all_vmware_vms v
            WHERE EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname)
        )
        +
        (
            SELECT COALESCE(SUM(n.cpu_count), 0)
            FROM all_nutanix_vms n
            WHERE NOT EXISTS (SELECT 1 FROM all_vmware_vms v WHERE v.vmname = n.vm_name)
        )
    ) AS "Total CPU (Nutanix)",
    (
        (
            SELECT COALESCE(SUM(v.number_of_cpus), 0)
            FROM all_vmware_vms v
            WHERE NOT EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname)
        )
        +
        (
            (SELECT COALESCE(SUM(v.number_of_cpus), 0) FROM all_vmware_vms v WHERE EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname))
            +
            (SELECT COALESCE(SUM(n.cpu_count), 0) FROM all_nutanix_vms n WHERE NOT EXISTS (SELECT 1 FROM all_vmware_vms v WHERE v.vmname = n.vm_name))
        )
    ) AS "Total CPU"
```

Ne yapar: Müşterinin toplam vCPU / RAM / disk değerini, VMware+Nutanix arası mükerrerleri tekilleştirerek hesaplar.
Memory/Disk sorgularında Nutanix değerleri `(memory_capacity / 1024.0 / 1024.0 / 1024.0)` ve
`(disk_capacity / 1024.0 / 1024.0 / 1024.0)` ile GB'ye çevrilir. Disk sorgusunda "(Nutanix)" ve "Total"
kolonları tüm Nutanix VM'lerini ekler (in_both ayrımı yapmaz).
Parametreler: `(vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts)`.

#### `CUSTOMER_INTEL_VM_COUNTS` — VMware/Nutanix/Toplam VM adedi

```sql
WITH vmware_vms AS (
    SELECT DISTINCT vmname
    FROM public.vm_metrics
    WHERE vmname ILIKE %s AND "timestamp" BETWEEN %s AND %s
),
nutanix_vms AS (
    SELECT DISTINCT vm_name
    FROM public.nutanix_vm_metrics
    WHERE vm_name ILIKE %s AND collection_time BETWEEN %s AND %s
)
SELECT
    (
        SELECT COUNT(*)
        FROM vmware_vms v
        WHERE NOT EXISTS (SELECT 1 FROM nutanix_vms n WHERE n.vm_name = v.vmname)
    ) AS "VMware",
    (
        SELECT COUNT(*)
        FROM nutanix_vms
    ) AS "Nutanix",
    (
        SELECT COUNT(*) FROM (
            SELECT vmname AS vm_name FROM vmware_vms
            UNION
            SELECT vm_name FROM nutanix_vms
        ) AS all_unique_vms
    ) AS "Total"
```

Ne yapar: Üç kolon — sadece-VMware, tüm-Nutanix ve UNION ile tekil toplam VM sayısı.
Parametreler: `(vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts)`.

#### `CUSTOMER_INTEL_VM_SOURCES` ve `CUSTOMER_INTEL_VM_DETAIL_LIST`

`VM_SOURCES`: her VM için kaynak etiketi (`'Nutanix (Managed by VMware)'` / `'VMware'` / `'Nutanix'`) döner.
`VM_DETAIL_LIST`: aynı kaynak etiketine ek olarak `COALESCE(v..., n..., 0)` ile CPU / Memory (GB) / Disk (GB)
detayını döner (faturalama için).
Parametreler (her ikisi): `(vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts)` —
`VM_SOURCES` ek olarak CASE içinde EXISTS kontrolleri için aynı timestamp çiftlerini birkaç kez tekrar alır.

#### Compute tipi bazlı sorgular — Classic / Hyperconverged / Pure Nutanix

`customer-api` sürümü, compute tipini cluster ismine göre üçe ayırır:

- **Classic** (`cluster ILIKE '%KM%'`): `CUSTOMER_CLASSIC_VM_COUNT`, `_RESOURCE_TOTALS`, `_DELETED_VM_NAMES`, `_VM_LIST`.
- **Hyperconverged** (VMware `cluster NOT ILIKE '%KM%'` + Nutanix): `CUSTOMER_HYPERCONV_*`.
- **Pure Nutanix (AHV)** (yalnızca VMware-managed olmayan cluster'lar): `CUSTOMER_PURE_NUTANIX_*` —
  `cluster_uuid` listesi `cluster_name = ANY(%s::text[])` ile çözülür.

Hyperconv VM listesi (`CUSTOMER_HYPERCONV_VM_LIST`) min/avg/max util kolonlarını VMware ve Nutanix `agg` CTE'lerinden
`CASE WHEN v.vmname IS NOT NULL THEN va... ELSE na...` ile seçer. Nutanix util normalizasyonu: CPU `cpu_usage_*`,
memory `memory_usage_* / 10000.0` (yüzde), used disk `used_storage / 1073741824.0` (GiB).

Örnek (`CUSTOMER_CLASSIC_VM_COUNT`, customer-api sürümü):

```sql
SELECT COUNT(DISTINCT vmname) AS vm_count
FROM public.vm_metrics
WHERE vmname ILIKE %s
  AND cluster ILIKE '%%KM%%'
  AND LEFT(vmname, 1) <> '_'
  AND timestamp BETWEEN %s AND %s
```

Ne yapar: KM cluster'larındaki (Classic) silinmemiş VM'leri sayar. `datacenter-api` sürümünde `LEFT(vmname,1) <> '_'`
satırı yoktur.
Parametreler: `(vm_pattern, start_ts, end_ts)`.

Pure Nutanix sayım (`CUSTOMER_PURE_NUTANIX_VM_COUNT`):

```sql
WITH cluster_uuids AS (
    SELECT DISTINCT ON (cluster_name) cluster_uuid
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name = ANY(%s::text[])
    ORDER BY cluster_name, collection_time DESC
),
latest AS (
    SELECT DISTINCT ON (nvm.vm_name)
        nvm.vm_name
    FROM public.nutanix_vm_metrics nvm
    WHERE nvm.vm_name ILIKE %s
      AND LEFT(nvm.vm_name, 1) <> '_'
      AND nvm.collection_time BETWEEN %s AND %s
      AND nvm.cluster_uuid::text IN (SELECT cluster_uuid FROM cluster_uuids)
    ORDER BY nvm.vm_name, nvm.collection_time DESC
)
SELECT COUNT(*)::int FROM latest
```

Ne yapar: Yalnızca verilen cluster adlarına (pure-Nutanix) ait VM'leri sayar.
Parametreler: `(managed_cluster_names[], vm_pattern, start_ts, end_ts)`.

#### Cluster keşif sorguları (Python'da normalize)

- `ALL_VMWARE_CLUSTER_NAMES` — `cluster_metrics`'ten distinct cluster + `arch_type` (`'classic'` if `ILIKE '%KM%'` else `'hyperconv'`). Params: `(start_ts, end_ts)`.
- `ALL_NUTANIX_CLUSTER_NAMES` — `nutanix_cluster_metrics`'ten distinct `cluster_name`, `cluster_uuid`. Params: `(start_ts, end_ts)`.
- `ALL_NUTANIX_CLUSTER_NAMES_LATEST` — fallback, parametresiz (tüm zaman).

#### Power / HANA (IBM LPAR) sorguları

`CUSTOMER_POWER_CPU_TOTAL`, `CUSTOMER_POWER_MEMORY_TOTAL`, `CUSTOMER_POWER_VM_LIST`, `CUSTOMER_POWER_LPAR_DETAIL_LIST`,
`CUSTOMER_POWER_DELETED_LPAR_NAMES`. CPU = `SUM(lpar_processor_currentvirtualprocessors)`. Memory böleni:
`customer-api` → `/1.048576`, `datacenter-api` → `/1024.0`. `customer-api` sürümü `LEFT(lparname,1) <> '_'` filtresi
ve util pct kolonları (CPU `utilizedprocunits / NULLIF(currentvirtualprocessors,0) * 100`, memory
`backedphysicalmem / NULLIF(logicalmem,0) * 100`) içerir.

```sql
WITH latest_lpar_stats AS (
    SELECT DISTINCT ON (lparname)
        lpar_processor_currentvirtualprocessors
    FROM public.ibm_lpar_general
    WHERE lparname ILIKE %s
      AND LEFT(lparname, 1) <> '_'
      AND time BETWEEN %s AND %s
    ORDER BY lparname, time DESC
)
SELECT
    COALESCE(SUM(lpar_processor_currentvirtualprocessors), 0) AS "Total CPU (Power HMC)"
FROM latest_lpar_stats
```

Parametreler: `(lpar_pattern, start_ts, end_ts)`.

#### Toplam/host sayım yardımcıları

- `NUTANIX_TOTALS`, `NUTANIX_BY_DC` — `nutanix_cluster_metrics`'ten host/VM sayıları (latest-per-cluster).
- `VMWARE_TOTALS`, `VMWARE_BY_DC` — `datacenter_metrics`'ten cluster/host/VM.
- `IBM_*_TOTALS` / `IBM_*_BY_SERVER` — LPAR/VIOS/host distinct sayıları.
- `VCENTER_HOST_TOTALS`, `VCENTER_BY_HOST` — `vmhost_metrics` host sayısı + power_usage.

#### Backup / DR / Storage sorguları (faturalama paneli)

| Query | Tablo | Döndürür | Params |
|---|---|---|---|
| `CUSTOMER_VEEAM_DEFINED_SESSIONS` | `raw_veeam_sessions` | distinct oturum sayısı | `(name_pattern,)` |
| `CUSTOMER_VEEAM_SESSION_TYPES` | `raw_veeam_sessions` | tür dağılımı | `(name_pattern,)` |
| `CUSTOMER_VEEAM_SESSION_PLATFORMS` | `raw_veeam_sessions` | platform dağılımı | `(name_pattern,)` |
| `CUSTOMER_ZERTO_PROTECTED_VMS` | `raw_zerto_vpg_metrics` | korunan toplam VM (en güncel VPG kaydı, `rn=1`) | `(start_ts, end_ts, name_like_pattern)` |
| `CUSTOMER_ZERTO_PROVISIONED_STORAGE` | `raw_zerto_vpg_metrics` | son 30 günde VPG başına provisioned storage (GiB) | `(name_like_pattern,)` |
| `CUSTOMER_STORAGE_VOLUME_CAPACITY` | `raw_ibm_storage_vdisk` | toplam volume kapasite (GB) | `(name_like_pattern, start_ts, end_ts)` |
| `CUSTOMER_NETBACKUP_BACKUP_SUMMARY` | `raw_netbackup_jobs_metrics` | pre/post dedup boyut + dedup faktör | `(workload_pattern, start_ts, end_ts)` |

NetBackup dedup özeti (formül load-bearing):

```sql
SELECT
    COALESCE(CAST(SUM(kilobytestransferred) / 1024.0 / 1024.0 / 1024.0 AS NUMERIC(20, 2)), 0) AS "Pre Dedup Size (GiB)",
    COALESCE(
        CAST(SUM(kilobytestransferred / NULLIF(dedupratio, 0)) / 1024.0 / 1024.0 / 1024.0 AS NUMERIC(20, 2)),
        0
    ) AS "Post Dedup Size (GiB)",
    COALESCE(CAST(AVG(NULLIF(dedupratio, 0)) AS NUMERIC(20, 2)), 1) || 'x' AS "Deduplication Factor"
FROM filtered
```

Filtre: `jobtype = 'BACKUP' AND percentcomplete = 100`.

#### `PHYSICAL_INVENTORY_ALL_DEVICES` (datacenter-api)

```sql
SELECT DISTINCT ON (name, site_id, location_id)
    id, name, device_type_name, manufacturer_name, device_role_name,
    tenant_id, site_id, site_name, location_id, location_name
FROM public.discovery_netbox_inventory_device
WHERE status_value = 'active'
ORDER BY name, site_id, location_id, collection_time DESC NULLS LAST
```

Ne yapar: Aktif cihazların en güncel snapshot'ını (mantıksal cihaz başına) döner; tenant/lokasyon eşleştirme Python'da
(`dc_service`, in-memory `LOCATION_DC_MAP`) yapılır. Parametreler: yok.

---

### Service Mapping (webui-db — `service_mapping.py`)

#### `LIST_SERVICE_PAGES` — sayfa registry

```sql
SELECT page_key,
       category_label,
       gui_tab_binding,
       resource_unit,
       icon,
       route_hint,
       tab_hint,
       sub_tab_hint
FROM   gui_crm_service_pages
ORDER BY page_key;
```

Ne yapar: GUI kategori/sayfa kayıt defterini döner (override dropdown'unun geçerli page_key kümesi).
Parametreler: yok.

#### `LIST_SERVICE_MAPPINGS_WEBUI` — birleşik ürün→sayfa eşleştirmesi

```sql
SELECT
    COALESCE(o.productid, s.productid)                     AS productid,
    COALESCE(o.page_key, s.page_key)                       AS category_code,
    pg.category_label,
    pg.gui_tab_binding,
    NULLIF(TRIM(pg.resource_unit), '')                     AS resource_unit,
    CASE
        WHEN o.productid IS NOT NULL THEN 'override'
        WHEN s.productid IS NOT NULL THEN 'yaml'
        ELSE 'unmatched'
    END                                                     AS source
FROM       gui_crm_service_mapping_seed s
FULL JOIN  gui_crm_service_mapping_override o ON o.productid = s.productid
LEFT JOIN  gui_crm_service_pages pg
       ON  pg.page_key = COALESCE(o.page_key, s.page_key);
```

Ne yapar: Seed (YAML) ve override tablolarını `FULL JOIN` ile birleştirir; override varsa o öncelikli (`source='override'`),
yoksa seed (`'yaml'`), ikisi de yoksa veya page_key çözülemiyorsa `'unmatched'`. Ürün adları datalake'ten
(`ALL_PRODUCTS`) Python'da merge edilir (cross-DB join yok).
Parametreler: yok.

#### `UPSERT_SERVICE_MAPPING_OVERRIDE` / `DELETE_SERVICE_MAPPING_OVERRIDE` / `VALIDATE_PAGE_KEY`

```sql
INSERT INTO gui_crm_service_mapping_override (productid, page_key, notes, updated_by, updated_at)
VALUES (%s, %s, %s, %s, now())
ON CONFLICT (productid) DO UPDATE SET
    page_key   = EXCLUDED.page_key,
    notes      = COALESCE(EXCLUDED.notes, gui_crm_service_mapping_override.notes),
    updated_by = EXCLUDED.updated_by,
    updated_at = now();
```

Ne yapar: Operatör override'ı ekler/günceller. Params: `(productid, page_key, notes, updated_by)`.
`DELETE`: `(productid,)`. `VALIDATE_PAGE_KEY` (`SELECT 1 ... LIMIT 1`): `(page_key,)` — geçerlilik kontrolü.

#### Müşteri alias sorguları

- `GET_ALL_ALIASES` — tüm alias satırları (params yok).
- `RESOLVE_ALIAS_BY_NAME` — `canonical_customer_key = %s OR crm_account_name ILIKE %s`. Params: `(canonical_key, name_pattern)`.
- `UPSERT_ALIAS` — `ON CONFLICT (crm_accountid)` upsert, `source='manual'`. Params: `(crm_accountid, crm_account_name, canonical_customer_key, netbox_musteri_value, notes)`.
- `DELETE_ALIAS` — `(crm_accountid,)`.

#### Customer aliases GUI (`/settings/integrations/crm/aliases`)

Settings → Integrations → CRM → **Customer aliases** uses a **DataTable list + single-customer detail editor** (same UX pattern as CRM service mapping) for performance with ~100+ CRM project customers:

| UI area | Behaviour |
|---|---|
| Summary badges | Total CRM customers, configured count, empty count, Boyner seed mapping count |
| DataTable | Columns: CRM account name, short account id, mapping count, source coverage (`N/6`), status (`empty` / `configured` / `seed`); native filter, sort, pagination (25/page); single-row selection |
| Detail editor | Accordion per source group (Virtualization, Backup, Physical, Storage, S3, ITSM); add/remove mapping rows; notes; Save / Reset |
| API | `GET /api/v1/crm/aliases`, `PUT /api/v1/crm/aliases/{id}/source-mappings`, `POST /api/v1/crm/aliases/seed-boyner` |
| Local state | `alias-page-data` store holds API payload; save refreshes store + table row without full page reload |

Implementation: `src/pages/settings/integrations/crm_aliases.py`, pure helpers `src/utils/crm_source_mapping_ui.py`.

---

### ITSM (datalake — `itsm.py`)

Üç endpoint (`/itsm/summary`, `/itsm/extremes`, `/itsm/tickets`) ortak `_CUSTOMER_TICKETS_CTE` fragment'ını string
birleştirme ile yeniden kullanır.

Müşteri çözüm zinciri: `customer_name → email_needle → discovery_servicecore_users.user_id →
incidents.org_user_id / servicerequests.requester_id`.

#### Ortak `_CUSTOMER_TICKETS_CTE`

```sql
WITH customer_users AS (
    SELECT user_id, full_name, email
    FROM   discovery_servicecore_users
    WHERE  email ILIKE %(needle)s
      AND  COALESCE(is_enabled,    TRUE) = TRUE
      AND  COALESCE(soft_deleted, FALSE) = FALSE
),
customer_tickets AS (
    -- Incidents ---------------------------------------------------------
    SELECT
        'incident'::TEXT                                                   AS source,
        i.ticket_id                                                        AS id,
        i.subject,
        COALESCE(i.state_text, i.status_name)                             AS stage,
        i.state_text,
        i.status_name,
        i.priority_name,
        i.category_name,
        i.org_users_name                                                   AS customer_user,
        i.agent_group_name,
        i.created_date                                                     AS opened_at,
        i.target_resolution_date,
        i.closed_and_done_date,
        CASE
            WHEN i.closed_and_done_date IS NOT NULL
            THEN EXTRACT(EPOCH FROM (i.closed_and_done_date - i.created_date)) / 3600.0
            ELSE NULL
        END                                                                AS resolution_hours,
        CASE
            WHEN i.closed_and_done_date IS NULL
            THEN EXTRACT(EPOCH FROM (NOW() - i.created_date)) / 86400.0
            ELSE NULL
        END                                                                AS open_age_days
    FROM   discovery_servicecore_incidents i
    JOIN   customer_users u ON u.user_id = i.org_user_id
    WHERE  i.created_date BETWEEN %(start_ts)s AND %(end_ts)s
      AND  COALESCE(i.is_deleted, FALSE) = FALSE

    UNION ALL

    -- Service Requests --------------------------------------------------
    SELECT
        'servicerequest'::TEXT,
        sr.service_request_id,
        COALESCE(sr.subject, sr.service_request_name),
        COALESCE(sr.state_text, sr.status_name),
        sr.state_text,
        sr.status_name,
        sr.priority_name,
        COALESCE(sr.category_name, sr.service_category_name),
        COALESCE(sr.requester_full_name, sr.org_users_name),
        sr.agent_group_name,
        sr.request_date,
        sr.target_resolution_date,
        NULL::TIMESTAMPTZ,     -- SR has no closed_and_done_date
        NULL::FLOAT,           -- resolution_hours only for incidents
        CASE
            WHEN COALESCE(sr.state_text, sr.status_name) NOT IN ('Closed', 'Done', 'Resolved')
            THEN EXTRACT(EPOCH FROM (NOW() - sr.request_date)) / 86400.0
            ELSE NULL
        END
    FROM   discovery_servicecore_servicerequests sr
    JOIN   customer_users u ON u.user_id = sr.requester_id
    WHERE  sr.request_date BETWEEN %(start_ts)s AND %(end_ts)s
      AND  COALESCE(sr.is_deleted, FALSE) = FALSE
)
```

Ne yapar: Müşterinin kullanıcılarını e-posta deseniyle bulur, ardından incident + service request kayıtlarını
`UNION ALL` ile tek küme yapar. `resolution_hours` (saat) yalnızca incident'lar için (`closed_and_done_date` mevcut);
`open_age_days` (gün) açık kayıtlar için. SR'lerin kapanış timestamp'i yoktur → terminal durum kümesi
`('Closed','Done','Resolved')` ile açık/kapalı ayrılır.
Parametreler (named): `{needle, start_ts, end_ts}`.

#### `ITSM_SUMMARY`

Yukarıdaki CTE + `stats / priority_dist / state_dist / top_category` alt CTE'leri. Döndürdüğü temel metrikler:
`total_count`, `incident_count`, `sr_count`, `incident_open/closed`, `sr_open/closed`,
çözüm-süresi istatistikleri (`avg / median (PERCENTILE_CONT 0.5) / p95 (0.95) / stddev`), `sla_breach_count`,
`top_category`, ve JSON dağılımlar (`priority_distribution`, `state_distribution`).

SLA ihlali sayacı:

```sql
COUNT(*) FILTER (
    WHERE closed_and_done_date IS NULL
      AND COALESCE(state_text, status_name) NOT IN ('Closed', 'Done', 'Resolved')
      AND target_resolution_date IS NOT NULL
      AND target_resolution_date < NOW()
) AS sla_breach_count
```

Parametreler: `{needle, start_ts, end_ts}`.

#### `ITSM_EXTREMES`

İki küme `UNION ALL`:
- **`long_tail`**: incident'lar arasında `resolution_hours > (avg + COALESCE(stddev, 0))` olanlar (eşik
  `incident_stats` CROSS JOIN'den).
- **`sla_breach`**: açık + terminal-olmayan + `target_resolution_date < NOW()` kayıtlar.

```sql
WHERE t.source = 'incident'
  AND t.resolution_hours IS NOT NULL
  AND t.resolution_hours > (s.avg_rh + COALESCE(s.std_rh, 0))
```

Parametreler: `{needle, start_ts, end_ts}`.

#### `ITSM_TICKETS`

CTE + düz `SELECT ... FROM customer_tickets ORDER BY source, opened_at DESC NULLS LAST` — tüm bilet listesi.
Parametreler: `{needle, start_ts, end_ts}`.

---

### CRM Sales (datalake — `crm_sales.py`)

Tüm satış sorguları yalnızca **gerçekleşmiş** siparişleri kapsar: `statecode IN (3, 4)` (3=Fulfilled, 4=Invoiced) —
ADR-0010. Müşteri filtresi `so.customerid = ANY(%s)` ile çözülmüş CRM accountid `text[]` listesi alır.

#### `SALES_SUMMARY` — YTD gerçekleşen satış

```sql
WITH ytd_realized AS (
    SELECT COALESCE(SUM(so.totalamount), 0) AS ytd_revenue_total,
           COALESCE(COUNT(DISTINCT so.salesorderid), 0) AS ytd_order_count,
           MIN(so.transactioncurrency_text) AS currency
    FROM   discovery_crm_salesorders so
    WHERE  so.customerid = ANY(%s)
      AND  so.statecode IN (3, 4)
      AND  EXTRACT(YEAR FROM COALESCE(so.fulfilldate, so.submitdate, so.modifiedon::date))
           = EXTRACT(YEAR FROM CURRENT_DATE)
),
in_progress_orders AS (
    SELECT COALESCE(COUNT(*), 0) AS active_order_count,
           COALESCE(SUM(so.totalamount), 0) AS active_order_value
    FROM   discovery_crm_salesorders so
    WHERE  so.customerid = ANY(%s)
      AND  so.statecode IN (0, 1)
)
SELECT
    ytd_realized.ytd_revenue_total,
    ytd_realized.ytd_order_count,
    ytd_realized.currency,
    0.0::double precision AS pipeline_value,
    0::bigint AS opportunity_count,
    in_progress_orders.active_order_count,
    in_progress_orders.active_order_value,
    0::bigint AS active_contract_count,
    0.0::double precision AS total_contract_value,
    0.0::double precision AS estimated_mrr
FROM ytd_realized, in_progress_orders;
```

Ne yapar: Cari yıl gerçekleşen ciro/sipariş sayısı + aktif (statecode 0/1) sipariş sayı/değeri. Pipeline/opportunity/
contract/MRR alanları şu an sabit 0 (placeholder). YTD yılı `fulfilldate → submitdate → modifiedon` fallback
zincirinden alınır.
Parametreler: `(accountids[], accountids[])`.

#### `SALES_ITEMS` — gerçekleşen sipariş satırları

```sql
SELECT
    'salesorder'                       AS source_type,
    so.ordernumber                     AS reference_number,
    COALESCE(so.fulfilldate::text, so.submitdate::text, so.modifiedon::text) AS date,
    so.statecode_text                  AS status,
    d.product_name,
    d.productdescription,
    d.uomid_name                       AS unit,
    d.quantity,
    d.priceperunit                     AS unit_price,
    d.extendedamount                   AS line_total,
    so.transactioncurrency_text        AS currency,
    d.productid                        AS productid
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
WHERE  so.customerid = ANY(%s)
  AND  so.statecode IN (3, 4)
ORDER BY so.modifiedon DESC NULLS LAST, d.extendedamount DESC NULLS LAST;
```

Ne yapar: Müşterinin gerçekleşen sipariş satır kalemleri. Parametreler: `(accountids[],)`.

#### `SALES_EFFICIENCY_BILLED` — ürün bazında faturalanan miktar

```sql
SELECT
    d.productid,
    d.product_name,
    d.uomid_name                         AS unit,
    SUM(d.quantity)                      AS total_billed_qty,
    SUM(d.extendedamount)                AS total_billed_amount,
    MIN(so.transactioncurrency_text)     AS currency
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
WHERE  so.customerid = ANY(%s)
  AND  so.statecode IN (3, 4)
GROUP BY d.productid, d.product_name, d.uomid_name
ORDER BY total_billed_amount DESC NULLS LAST;
```

Ne yapar: Ürün başına toplam faturalanan miktar/tutar. Katalog fiyatı servis katmanında
`gui_crm_price_override` → `discovery_crm_productpricelevels` sırasıyla çözülür (price-level prod'da boş).
Parametreler: `(accountids[],)`.

#### `SALES_SOLD_RAW_BY_PRODUCT` — satılan miktar (productid bazında ham)

```sql
SELECT
    d.productid,
    d.product_name,
    COALESCE(NULLIF(TRIM(d.uomid_name), ''), 'Adet') AS resource_unit,
    SUM(d.quantity)::double precision     AS sold_qty,
    SUM(d.extendedamount)::double precision AS sold_amount_tl
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
WHERE  so.customerid = ANY(%s)
  AND  so.statecode IN (3, 4)
GROUP BY d.productid, d.product_name, COALESCE(NULLIF(TRIM(d.uomid_name), ''), 'Adet')
ORDER BY sold_amount_tl DESC NULLS LAST;
```

Ne yapar: `efficiency-by-category` için ham satılan miktar; productid → kategori eşleştirmesi Python'da webui-db'den
uygulanır. Birim boşsa `'Adet'` varsayılır. Parametreler: `(accountids[],)`.

#### `SALES_CATALOG_PRICES` — katalog fiyat (ikincil fallback)

```sql
SELECT
    p.productid,
    p.name                 AS product_name,
    ppl.uomid_name         AS unit,
    ppl.amount             AS catalog_unit_price,
    pl.name                AS price_list
FROM   discovery_crm_productpricelevels ppl
JOIN   discovery_crm_products p     ON p.productid = ppl.productid
JOIN   discovery_crm_pricelevels pl ON pl.pricelevelid = ppl.pricelevelid
WHERE  pl.statecode = 0;
```

Ne yapar: Price-level tablosu doluysa katalog fiyatları. Servis katmanı önce `gui_crm_price_override`'ı kullanır.
Parametreler: yok.

#### `ALL_PRODUCTS` — tüm CRM ürün listesi

```sql
SELECT
    productid,
    name                AS product_name,
    productnumber       AS product_number,
    defaultuomid_name   AS default_unit
FROM   discovery_crm_products
ORDER BY name NULLS LAST, productid;
```

Ne yapar: Service mapping sayfası ve fiyat override dropdown'ları için ürün listesi; mapping satırlarına ad/numara
merge etmek için kullanılır. Parametreler: yok.

#### `DISCOVERY_TABLE_COUNTS` — CRM Overview sayaçları

`discovery_crm_accounts/products/pricelevels/productpricelevels/salesorders/salesorderdetails` tablolarının
`row_count` ve `MAX(collection_time)` (last_collected) değerlerini `UNION ALL` ile döner. Parametreler: yok.

---

### CRM Config (webui-db — `crm_config.py`)

> Bu tablolar Sellable pipeline'ı tarafından da okunur. **Tüketim mantığı → [05-sellable-potential.md](05-sellable-potential.md).**

#### Threshold config (`gui_crm_threshold_config`)

- `LIST_THRESHOLDS` — tüm satırlar; sıralama `(panel_key IS NULL), panel_key, resource_type, dc_code`. Params: yok.
- `GET_THRESHOLD_FOR` — belirli kaynak tipi için tavan %, DC-özel öncelikli (wildcard `'*'` fallback):

```sql
SELECT sellable_limit_pct
FROM   gui_crm_threshold_config
WHERE  resource_type = %s
   AND (dc_code = %s OR dc_code = '*')
ORDER BY (dc_code = '*') ASC
LIMIT 1;
```

  Ne yapar: `dc_code = '*'` satırlarını `ASC` ile sona iter → DC'ye özel satır varsa onu seçer.
  Params: `(resource_type, dc_code)`.
- `UPSERT_THRESHOLD` — `ON CONFLICT (resource_type, dc_code)` upsert. Params: `(panel_key, resource_type, dc_code, sellable_limit_pct, notes, updated_by)`.
- `DELETE_THRESHOLD_BY_ID` — `(id,)`.

#### Price override (`gui_crm_price_override`)

- `LIST_PRICE_OVERRIDES` — tüm satırlar (params yok).
- `UPSERT_PRICE_OVERRIDE` — `ON CONFLICT (productid)` upsert. Params: `(productid, product_name, unit_price_tl, resource_unit, currency, notes, updated_by)`.
- `DELETE_PRICE_OVERRIDE` — `(productid,)`.

Bu tablo, `discovery_crm_productpricelevels` prod'da boş olduğu sürece **birincil** fiyat kaynağıdır.

#### Calc config (`gui_crm_calc_config`)

- `LIST_CALC_CONFIG` — `config_key, config_value, value_type, description, updated_by, updated_at` (params yok).
- `UPSERT_CALC_CONFIG` — `ON CONFLICT (config_key)` upsert. Params: `(config_key, config_value, value_type, description, updated_by)`.

Genel sayısal/string hesaplama değişkenleri; hesaplama katmanı tüketir.

---

### DC Sales Potential — legacy v1 / v2 (datalake — `datacenter-api/.../crm_potential.py`)

DC bazlı satış potansiyeli. **v2** = gerçekleşen CRM satış + `gui_crm_threshold_config` tavanları (ADR-0010);
**v1** = legacy katalog × kaba kapasite. Alias çözümü Python'da; bu sorgular ham datalake satırlarını döner.

#### `DC_TENANT_VALUES` — DC'deki VM tenant değerleri (alias girdisi)

```sql
SELECT DISTINCT lower(trim(coalesce(vm.custom_fields_musteri, ''))) AS tenant_value
FROM   discovery_netbox_virtualization_vm vm
WHERE  vm.site_name ILIKE %s
  AND  vm.custom_fields_musteri IS NOT NULL
  AND  trim(vm.custom_fields_musteri) <> '';
```

Ne yapar: Bir DC'deki VM'lerin distinct NetBox `custom_fields_musteri` değerlerini döner — alias çözümünün girdisi.
Parametreler: `(site_name_pattern,)`.

#### `DC_POTENTIAL_SUMMARY` — DC YTD faturalama özeti

```sql
WITH ytd_realized AS (
    SELECT COALESCE(SUM(so.totalamount), 0) AS total_billed_ytd,
           COUNT(DISTINCT so.salesorderid)  AS invoice_count
    FROM   discovery_crm_salesorders so
    WHERE  so.customerid = ANY(%s)
      AND  so.statecode IN (3, 4)
      AND  EXTRACT(YEAR FROM COALESCE(so.fulfilldate, so.submitdate, so.modifiedon::date))
           = EXTRACT(YEAR FROM CURRENT_DATE)
)
SELECT
    %s::TEXT                            AS dc_code,
    ytd.total_billed_ytd,
    ytd.invoice_count,
    0.0::double precision               AS total_pipeline_value,
    0::bigint                           AS open_opportunity_count,
    cardinality(%s::text[])             AS customer_count
FROM ytd_realized ytd;
```

Ne yapar: DC'ye atanmış müşterilerin (resolved accountid'ler) cari yıl gerçekleşen toplam faturası + müşteri sayısı.
Parametreler: `(accountids[], dc_code, accountids[])`.

#### `DC_SOLD_RAW_BY_PRODUCT_FOR_DC` — DC için son 12 ay satılan ürünler

`SALES_SOLD_RAW_BY_PRODUCT`'a benzer; ek olarak
`COALESCE(so.fulfilldate::date, so.submitdate::date, so.modifiedon::date) >= CURRENT_DATE - INTERVAL '12 months'`
filtresi vardır. Parametreler: `(accountids[],)`.

#### `DC_NUTANIX_CLUSTER_CAPACITY`, `DC_CATALOG_AVG_UNIT_PRICE`, `DC_SALES_POTENTIAL`, `WEBUI_ALIAS_ACCOUNTIDS_FOR_TENANTS`

- `DC_NUTANIX_CLUSTER_CAPACITY` — son 7 gün, DC adına göre Nutanix `total_cpu_capacity` + `total_memory_capacity / 1073741824.0` (GB). Params: `(datacenter_name_pattern,)`.
- `DC_CATALOG_AVG_UNIT_PRICE` — `pl.name ILIKE '%TL%' AND statecode=0` için birim deseni ortalama fiyat (legacy fallback). Params: `(unit_pattern,)`.
- `DC_SALES_POTENTIAL` (legacy v1) — `tl_catalog × dc_capacity/rack/allocated` FULL/LEFT JOIN'leri ile katalog×kapasite. Params (sorgudaki `%s` sırası, yukarıdan aşağıya): `(site_name, site_name, datacenter_name, cluster_name, dc_code, dc_name, dc_name)` — yani `dc_capacity` ve `dc_rack_capacity` için `site_name`, `dc_allocated_vmware` için `datacenter_name`, `dc_allocated_nutanix` için `cluster_name`, SELECT çıktısı için `dc_code`, son iki LEFT JOIN (`va`/`na`) için `dc_name`. `dc_code` 5. parametredir, ilk değil.
- `WEBUI_ALIAS_ACCOUNTIDS_FOR_TENANTS` (webui-db) — `lower(trim(netbox_musteri_value)) = ANY(%s)` ile tenant değer listesinden accountid'leri döner. Params: `(tenant_values[],)`.

---

## Hesaplamalar / Formüller

### YTD (cari yıl) gerçekleşen satış

- **Kapsam:** `statecode IN (3, 4)` (3=Fulfilled, 4=Invoiced) — ADR-0010.
- **Yıl filtresi:** `EXTRACT(YEAR FROM COALESCE(fulfilldate, submitdate, modifiedon::date)) = EXTRACT(YEAR FROM CURRENT_DATE)`. Tarih, üç kolonun fallback zincirinden alınır.
- **Ciro:** `SUM(totalamount)`; **sipariş sayısı:** `COUNT(DISTINCT salesorderid)`; **para birimi:** `MIN(transactioncurrency_text)`.
- **Aktif (in-progress):** `statecode IN (0, 1)` → `active_order_count`, `active_order_value`.

### Unmapped / unmatched product count

`LIST_SERVICE_MAPPINGS_WEBUI` sorgusunda her ürün satırı bir `source` etiketi alır:

- `override` — `gui_crm_service_mapping_override`'da kayıt var.
- `yaml` — yalnızca `gui_crm_service_mapping_seed`'de var.
- `unmatched` — ne override ne seed var (ya da çözülen `page_key` NULL).

"Unmapped product count" = `source = 'unmatched'` satır sayısıdır (servis katmanında sayılır). Bu satırlar
operatöre "henüz eşleştirilmemiş ürünler" olarak gösterilir.

### Assignment (atama) mantığı

İki ayrı atama dünyası vardır:

1. **Müşteri → altyapı (VM/LPAR/host):** SQL'de **isim deseni (ILIKE pattern)** ile. Müşteri adı bir pattern'e
   (`'%<ad>%'`) çevrilir; `vmname / vm_name / lparname / workloaddisplayname / name` kolonlarında aranır. VMware ve
   Nutanix arası mükerrer VM'ler `NOT EXISTS / UNION` ile tekilleştirilir (`vmware_only + nutanix_only + in_both`).
   Compute tipi cluster ismiyle bölünür: Classic = `cluster ILIKE '%KM%'`, Hyperconv = `NOT ILIKE`, Pure Nutanix =
   `cluster_uuid ∈ (verilen cluster adları)`.

2. **Müşteri → CRM hesap (accountid):** İsim doğrudan CRM'e join'lenmez. `gui_crm_customer_alias` üzerinden
   (`canonical_customer_key` / `crm_account_name` / `netbox_musteri_value`) accountid listesi Python'da çözülür,
   ardından `so.customerid = ANY(%s)` ile satış sorgularına geçirilir. DC tarafında zincir:
   `DC_TENANT_VALUES` → `WEBUI_ALIAS_ACCOUNTIDS_FOR_TENANTS` → accountid[] → `DC_POTENTIAL_SUMMARY`.

3. **Ürün → GUI sayfası/kategori:** `override` (öncelik) → `seed` → `unmatched`. `gui_crm_service_pages` page_key
   registry'sine `LEFT JOIN` ile zenginleştirilir.

### ITSM çözüm-süresi metrikleri

- `resolution_hours` = `EXTRACT(EPOCH FROM (closed_and_done_date - created_date)) / 3600.0` (yalnız incident, kapalı).
- `open_age_days` = `EXTRACT(EPOCH FROM (NOW() - created_date)) / 86400.0` (açık kayıt).
- Özet istatistikleri: `AVG`, `PERCENTILE_CONT(0.5)` (median), `PERCENTILE_CONT(0.95)` (p95), `STDDEV_SAMP`.
- **Long-tail eşiği:** `resolution_hours > avg + COALESCE(stddev, 0)`.
- **SLA ihlali:** açık (`closed_and_done_date IS NULL`) + terminal-olmayan + `target_resolution_date < NOW()`.

### NetBackup dedup faktörü

- Pre-dedup (GiB) = `SUM(kilobytestransferred) / 1024^3`.
- Post-dedup (GiB) = `SUM(kilobytestransferred / NULLIF(dedupratio, 0)) / 1024^3`.
- Dedup faktör = `AVG(NULLIF(dedupratio, 0))` (varsayılan `1`), `'x'` ile birleştirilir.

### Birim dönüşümleri (SQL içi)

- Nutanix memory/disk: `/ 1024.0 / 1024.0 / 1024.0` (byte → GB/GiB).
- Power memory: customer-api `lpar_memory_logicalmem / 1.048576`; datacenter-api `/ 1024.0` (servisler farklı!).
- Nutanix util normalizasyonu: memory pct `memory_usage_* / 10000.0`, used disk `used_storage / 1073741824.0`.
- Zerto/IBM storage: `provisioned_storage_mb / 1024.0` (MB → GB).
- Nutanix cluster bellek kapasitesi (`DC_NUTANIX_CLUSTER_CAPACITY`): `total_memory_capacity / 1073741824.0` (byte → GB).

---

## Caching

Bu query dosyaları ham SQL tanımıdır; cache servis/Redis katmanındadır (bkz. README "Üç katmanlı cache"). Müşteri ve
CRM sorguları için belirgin desenler:

- **DC details / sellable** Redis anahtarları (`dc_details:{dc}:{start}:{end}`, `sellable:panels:...`) — bu dokümanın
  doğrudan kapsamı değil; CRM config tabloları o pipeline tarafından okunur (bkz. [05](05-sellable-potential.md)).
- **CRM/satış ve ITSM** sorgularında bu dosyalarda (`crm_sales.py`, `itsm.py`, `customer.py`) gömülü cache yoktur;
  cache varsa servis katmanında uygulanır.

> Not: Backup/DR warm-window cache deseni [06-backup-dr.md](06-backup-dr.md)'de; bu dosyadaki Veeam/Zerto/NetBackup
> sorguları müşteri-bağlamlı (faturalama paneli) varyantlardır.

---

## Özet

Bu doküman müşteri (tenant) ve CRM ile ilgili tüm sorguları kapsar (Sellable hesaplama pipeline'ı hariç):
müşteri listesi/detayı (`CUSTOMER_NAME_LIST`, Intel/Classic/Hyperconv/Pure Nutanix/Power varyantları), backup/DR/
storage faturalama sorguları, service mapping (seed + override + page registry), müşteri alias, ITSM
(incident + service request, çözüm-süresi & SLA metrikleri), CRM YTD gerçekleşen satış (`statecode IN (3,4)`,
ADR-0010) ve unmapped ürün sayımı. Atama iki dünyada yürür: altyapı tarafı **ILIKE isim deseni**, CRM tarafı
**alias → accountid → `customerid = ANY()`**. CRM konfigürasyon tabloları (`gui_crm_threshold_config`,
`gui_crm_price_override`, `gui_crm_calc_config`) burada **tanımlanır**; Sellable tarafında **tüketilir** →
[05-sellable-potential.md](05-sellable-potential.md). `customer-api` ve `datacenter-api` müşteri sorguları
büyük ölçüde aynıdır; başlıca farklar silinmiş-VM filtresi (`LEFT(name,1)='_'`) ve Power memory böleni
(`/1.048576` vs `/1024.0`).
```
