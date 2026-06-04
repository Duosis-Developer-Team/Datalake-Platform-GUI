# Datalake WebUI — Query & Calculation Map

Bu klasör, Datalake Platform GUI'nin **tüm veri sorgularını** ve **hesaplama
mantıklarını** belgeler. Amaç: hangi ekrandaki hangi sayının nereden, hangi SQL ile
geldiğini ve hangi formülle hesaplandığını tek bir referansta toplamak.

> **Branch notu:** Bu dokümantasyon `main` (190f07c) dalının mevcut hâlini yansıtır.
> `*_performance_metrics` tablo isimlendirmesine geçiş (VMware/Nutanix/IBM)
> `feature/vcenter-nutanix-ibm-integration` dalındadır; `main` hâlâ eski tablo
> adlarını (`datacenter_metrics`, `cluster_metrics`, `nutanix_cluster_metrics`,
> `ibm_server_general` ...) kullanır. İlgili dosyalarda migration notu düşülmüştür.

---

## İçindekiler

| # | Dosya | Kapsam |
|---|---|---|
| — | [README.md](README.md) | Mimari + ortak desenler (bu dosya) |
| 01 | [01-vmware.md](01-vmware.md) | VMware: `datacenter_metrics`, `cluster_metrics`, `vm_metrics`; Classic (KM) vs Hyperconverged |
| 02 | [02-nutanix.md](02-nutanix.md) | Nutanix: `nutanix_cluster_metrics`, `nutanix_vm_metrics`; CPU% dönüşümü, storage /2 |
| 03 | [03-ibm-power.md](03-ibm-power.md) | IBM Power (HMC): `ibm_server/vios/lpar_general`; proc-units, regex DC extraction |
| 04 | [04-ibm-storage-san.md](04-ibm-storage-san.md) | IBM Storage + Brocade SAN; physical/efficient capacity, hyperswap divisor |
| 05 | [05-sellable-potential.md](05-sellable-potential.md) | Sellable Potential (CRM): panel → infra source → threshold → ratio → TL fiyat |
| 06 | [06-backup-dr.md](06-backup-dr.md) | NetBackup, Veeam, Zerto, S3 iCOS; warm-window cache |
| 07 | [07-energy.md](07-energy.md) | Enerji tüketimi: kW/kWh, IBM/VMware kaynak bazında |
| 08 | [08-zabbix-monitoring.md](08-zabbix-monitoring.md) | Zabbix: `zabbix_network_*`, `zabbix_storage_*` |
| 09 | [09-discovery-inventory.md](09-discovery-inventory.md) | Discovery/envanter: Loki rack, Netbox, `loki_locations`, registry |
| 10 | [10-customer-crm.md](10-customer-crm.md) | Müşteri atamaları, service mapping, ITSM, CRM satış/konfig |
| 11 | [11-query-api.md](11-query-api.md) | query-api wrapper katmanı + frontend → backend çağrı akışı |

---

## Mimari Genel Bakış

Platform **mikroservis** mimarisindedir. Frontend Streamlit (`src/`), backend FastAPI
servisleridir:

| Servis | Sorumluluk | Sorgu klasörü |
|---|---|---|
| **datacenter-api** | Altyapı metrikleri (VMware, Nutanix, IBM Power, storage, energy, backup, zabbix, discovery) | `services/datacenter-api/app/db/queries/` |
| **customer-api** | CRM/satış, Sellable Potential, müşteri yönetimi, ITSM | `services/customer-api/app/db/queries/` |
| **query-api** | Frontend için hafif sorgu wrapper'ı | `services/query-api/app/db/queries/` |
| **crm-engine** | CRM konfigürasyonu + Sellable Potential refresh scheduler | `services/crm-engine/app/` |
| **admin-api** | Kullanıcı/LDAP/audit/yetki (veri-ağırlıklı değil — ayrı dosya yok) | — |
| **Frontend** | Streamlit sayfaları + util'ler | `src/pages/`, `src/utils/` |

**Veri akışı:** Streamlit sayfası → `src/services/api_client.py` (HTTP) → backend servisi
→ `app/services/*_service.py` (orkestrasyon + hesap) → `app/adapters/*` (şema köprüsü) →
`app/db/queries/*.py` (SQL) → Datalake PostgreSQL.

İki ayrı veritabanı vardır:
- **Datalake DB** — ham telemetri (VMware/Nutanix/IBM/Zabbix/backup tabloları, `public.*`).
- **WebUI DB** — uygulamaya özel tablolar (CRM panel tanımları, threshold, ratio,
  snapshot, `gui_*` tabloları).

---

## Ortak Desenler (her dosyada tekrar eder)

### 1. "Latest snapshot" deseni

Telemetri tabloları zaman serisidir (her toplama bir satır ekler). Anlık kapasite/kullanım
için **her varlığın zaman aralığındaki en güncel satırı** alınır, sonra toplanır:

```sql
WITH latest_per_cluster AS (
    SELECT DISTINCT ON (cluster)
        cpu_ghz_capacity, cpu_ghz_used, ...
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC      -- her cluster için en yeni
)
SELECT SUM(cpu_ghz_capacity), SUM(cpu_ghz_used) FROM latest_per_cluster
```

`DISTINCT ON (key) ... ORDER BY key, timestamp DESC` = "her `key` için en güncel kayıt".
Önce en güncel snapshot seçilir, **sonra** SUM alınır — aksi hâlde aynı varlık birden çok
kez sayılırdı.

### 2. Batch sorgu deseni (`unnest WITH ORDINALITY`)

Tüm DC'leri tek seferde çekmek için (N+1 yerine ~tek roundtrip), DC kodu + ILIKE pattern
listesi sorguya `unnest` ile enjekte edilir:

```sql
INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
    ON d.datacenter ILIKE u.pattern
... GROUP BY dc_code
```

- **Individual** sorgu params: `(dc_code, start_ts, end_ts)`
- **Batch** sorgu params: `(dc_list[], pattern_list[], start_ts, end_ts)` —
  `pattern_list = ['%'+dc+'%' for dc in dc_list]`.

### 3. DC eşleştirme

DC, isim içinde **substring** olarak aranır: `datacenter ILIKE '%<DC_CODE>%'`. IBM tarafında
ise sunucu adından regex ile DC çıkarılır: `(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)`.

### 4. Birim dönüşümleri

İki ayrı dönüşüm dünyası vardır:

**a) SQL içi sabit çarpanlar** (telemetri → temel birim): VMware sorgularında GB→byte
(`*1024*1024*1024`), GHz→Hz (`*1000000000`) gibi çarpanlar SQL'e gömülüdür. Storage'ta
yer yer `*(1024*1024)` kullanımı vardır (ilgili dosyada belirtilir).

**b) Sellable `gui_unit_conversion`** (DB-tablosu tabanlı): Sellable pipeline'ında ham
datalake değeri, panelin `display_unit`'ine `convert_unit(value, conv)` ile çevrilir —
`multiply`/`divide` + opsiyonel `ceil`. Bkz. [05-sellable-potential.md](05-sellable-potential.md).

**c) Görüntüleme formatı** (`src/utils/format_units.py`): `smart_storage`, `smart_cpu`,
`smart_memory` gibi fonksiyonlar GB/TB, GHz/MHz arası **sadece gösterim** için ölçek seçer
(hesaba girmez).

### 5. Utilization vs Allocation (önemli ayrım)

- **Utilization (kullanım):** Kaynağın gerçekte ne kadar **kullanıldığı** (ör. `cpu_ghz_used`,
  `cpu_usage_avg_perc`). "Anlık yük."
- **Allocation (tahsis):** VM'lere/LPAR'lara **atanmış/söz verilmiş** miktar (ör.
  `vm_metrics.total_cpu_capacity_mhz`, `assignedmemtolpars`). Overcommit nedeniyle allocation
  > kapasite olabilir.
- **Utilization %** = `min(used / capacity * 100, 100)` (capacity 0 ise 0).

### 6. Üç katmanlı cache

| Tier | Yer | Anahtar | Amaç |
|---|---|---|---|
| 1 | Redis (crm-engine DB 2 / datacenter-api DB 0) | `sellable:panels:{dc}:{family}:{clusters}`, `dc_details:{dc}:{start}:{end}` | Sıcak okuma |
| 2 | WebUI DB (`gui_panel_result_snapshot`) | (dc_code, family, clusters_csv) | Redis restart sonrası kalıcı snapshot |
| 3 | Frontend bellek (Streamlit) | per-DC virt family TL | Sayfa açılışında ön-ısıtma |

---

## Sellable Potential — temel formül (özet)

Detaylar [05-sellable-potential.md](05-sellable-potential.md)'de. Çekirdek (saf fonksiyonlar
`shared/sellable/computation.py`):

```
1. convert_unit:  display_value = ham_değer (multiply|divide) factor  [opsiyonel ceil]
2. apply_threshold:  sellable_raw = max(total * pct/100 - allocated, 0)
3. constrain_by_ratio (CPU:RAM:Storage aile oranı ile darboğaz):
     effective_cpu     = sellable_raw_cpu     / ratio.cpu_per_unit
     effective_ram     = sellable_raw_ram     / ratio.ram_gb_per_unit
     effective_storage = sellable_raw_storage / ratio.storage_gb_per_unit
     n = min(mevcut effective değerler)          # darboğaz birim sayısı
     sellable_constrained_<kind> = n * ratio.<kind>_per_unit
4. compute_potential_tl:  potential_tl = sellable_constrained * unit_price_tl
```

Aileler: `virt_classic` (VMware KM), `virt_hyperconverged` (Nutanix),
`virt_power` / `virt_power_hana` (IBM Power).

---

## Her dosyanın yapısı (şablon)

1. **Genel Bakış** — bu domain neyi kapsar, hangi ekranlarda kullanılır.
2. **Veri Kaynakları** — tablolar ve önemli kolonlar.
3. **Sorgular** — gerçek SQL + ne yaptığı + parametreler.
4. **Hesaplamalar / Formüller** — service/adapter katmanındaki mantık.
5. **Birim Dönüşümleri** — varsa.
6. **Caching** — varsa.
7. **Özet** — kısa Türkçe kapanış.

---

## Özet

Bu klasör, WebUI'daki her sayının arkasındaki SQL ve hesaplama mantığını domain bazında
(VMware, Nutanix, IBM Power, IBM Storage/SAN, Sellable, Backup/DR, Energy, Zabbix,
Discovery, Customer/CRM, query-api) belgeler. Tüm telemetri sorguları "her varlığın en
güncel snapshot'ını al, sonra topla" desenini; tüm DC-toplu sorgular `unnest WITH
ORDINALITY` batch desenini kullanır. Sellable Potential hesabı `threshold → ratio constrain
→ TL fiyat` zinciriyle ilerler. Dokümantasyon `main` dalının mevcut (eski tablo adlı)
hâlini yansıtır.
