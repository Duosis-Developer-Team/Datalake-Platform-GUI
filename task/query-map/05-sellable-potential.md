# Sellable Potential (Satılabilir Kapasite) — Sorgular ve Hesaplamalar

> Çapraz referans: [README](README.md) · [01-vmware.md](01-vmware.md) · [02-nutanix.md](02-nutanix.md) · [03-ibm-power.md](03-ibm-power.md) · [04-ibm-storage-san.md](04-ibm-storage-san.md) · [10-customer-crm.md](10-customer-crm.md)

---

## Genel Bakış

**Sellable Potential**, C-seviye (yönetim) bir CRM ekonomi panosudur: "Şu anki
altyapıda satabileceğim boş kapasite ne kadar ve bu kaç TL'lik potansiyel
gelire denk gelir?" sorusunu cevaplar.

- **Ekran:** `src/pages/crm_sellable_potential.py` — route `/crm/sellable-potential`.
  - KPI şeridi: Total Potential TL, YTD Sales TL, Constrained Loss TL, Unmapped Products.
  - DC seçici (tekli; `*` = tüm DC'ler).
  - Aile (family) roll-up kartları: Total / Allocated / Sellable raw / Sellable
    constrained / Potential TL + kapasite kullanım gauge'ları.
  - Panel-seviyesi sıralanabilir tablo (`panel_key, label, unit, total, allocated,
    sellable_raw, sellable_constrained, unit_price_tl, potential_tl`, `ratio_bound` rozeti).
  - Seçili panel için trend grafiği (`gui_metric_snapshot` son 30 gün).
  - Excel export.
- **`customer_view`** (`src/pages/customer_view.py`) ve **`/datacenters`** listesi
  de aynı boru hattını kullanır: DC bazında "Potential Sales" TL değeri
  `src/utils/datacenters_virt_sellable.py` üzerinden hesaplanır.

**Aileler (family):**

| family | Anlam | Karşılık gelen altyapı dokümanı |
|---|---|---|
| `virt_classic` | VMware Classic (KM) | [01-vmware.md](01-vmware.md) |
| `virt_hyperconverged` | Nutanix | [02-nutanix.md](02-nutanix.md) |
| `virt_power` | IBM Power (PowerVM) | [03-ibm-power.md](03-ibm-power.md) |
| `virt_power_hana` | IBM Power HANA | [03-ibm-power.md](03-ibm-power.md) |

`src/utils/virt_sellable_aggregate.py` içindeki sabitler:
```python
VIRT_POWER_FAMILIES = ("virt_power", "virt_power_hana")
VIRT_SELLABLE_FAMILY_LABELS = ("virt_classic", "virt_hyperconverged", "virt_power", "virt_power_hana")
```

---

## Mimari ve Akış

İki servis çalışır:

- **customer-api** — `SellableService` (orkestrasyon + hesap). Dosya:
  `services/customer-api/app/services/sellable_service.py`.
- **crm-engine** — `/api/v1/crm/*` endpoint'lerini host eder (sellable, panels,
  ratios, conversions, thresholds) + APScheduler ile `snapshot_all` refresh
  scheduler'ı. Frontend `src/services/api_client.py` içinde `_client_crm`
  üzerinden çağırır.

İki veritabanı (ADR-0013 gereği uygulama katmanında join edilir):

- **webui-db** — panel registry, infra source binding, ratio, unit conversion,
  threshold, panel↔page link, price override, snapshot (`gui_*` tabloları).
- **datalake** — panel başına total/allocated lookup'ları (infra-source
  descriptor'undan dinamik kurulur) + CRM katalog fiyatı + YTD satış.

### Adım adım pipeline (panel başına — `compute_panel`)

```
1. InfraSource çöz        (panel_key, dc_code) → gui_panel_infra_source
                           (dc-spesifik satır '*' wildcard'tan önce gelir)
2. Threshold çöz          panel_key > resource_type > '*' önceliği
3. Unit price çöz         override > katalog TL > 0
4. Total / Allocated al   - cluster verildi + family /compute'a maplenirse:
                             datacenter-api /compute/{kind}?clusters=... (cap & used)
                           - manual_total varsa: doğrudan kullan
                           - raw_ibm_storage_system: varchar kapasiteleri parse et
                           - aksi halde: datalake'te SUM (VMware/Nutanix/IBM
                             için latest-snapshot subquery)
                           - vm_metrics / nutanix_vm_metrics ALLOCATED: datalake
                             yerine datacenter-api Redis payload'undan okunur
5. convert_unit           ham datalake birimi → panel.display_unit
                           (gui_unit_conversion: multiply|divide, ceil)
6. apply_threshold        sellable_raw = max(total*pct/100 - allocated, 0)
7. PanelResult döndür      (constrained başlangıçta = raw)

--- aile geçişi (compute_all_panels) ---
8. constrain_by_ratio     CPU:RAM:Storage darboğazı → sellable_constrained
                           (virt_power için storage decouple edilir)
9. compute_potential_tl   potential_tl = sellable_constrained * unit_price_tl
10. cache + snapshot       Tier-1 Redis (crm-engine DB2) + Tier-2 webui-db
```

### `compute_all_panels` akışı (orkestrasyon)

1. **Tier-1** Redis result cache lookup (`sellable:panels:{dc}:{family}:{clusters}`).
2. Miss → **Tier-2** webui-db kalıcı snapshot (`gui_panel_result_snapshot`); hit
   olursa Redis'i tekrar doldurur.
3. Panel tanımlarını çek (`list_panel_defs`); `family` verildiyse ÖNCE filtrele.
4. WebUI metadata'sını **3 toplu sorgu** ile yükle (N×3 round-trip yerine):
   `_bulk_load_infra_sources`, `_bulk_load_thresholds`, `_bulk_load_price_overrides`.
5. Redis DC payload'unu **bir kez** çek (`_load_dc_redis_payload`) — Redis tabanlı
   her `allocated` paneli aynı JSON'u yeniden kullanır.
6. Aile başına `/compute` yanıt cache'i (aynı ailenin cpu/ram/storage panelleri
   tek HTTP çağrısını paylaşır).
7. Her panel için `compute_panel` çağır.
8. Aile bazında `constrain_by_ratio` uygula; her panel için `potential_tl`'i
   `sellable_constrained` üzerinden yeniden hesapla.
9. Sonucu Tier-1 + Tier-2'ye yaz.

### `compute_summary` akışı

`compute_all_panels` sonucunu alır, aileye göre gruplar, her aile için
`FamilyAggregate` üretir: `total_potential_tl`, `constrained_loss_tl`
(= `max(raw_potential - constrained_potential, 0)`), kaynak türü başına
`total_sellable_constrained_units`. Ayrıca `_compute_ytd_sales_tl()` ve
`_count_unmapped_products()` çağrılır → `DashboardSummary`.

### `snapshot_all` (scheduler)

1. `_prewarm_dc_virt_snapshots()` — her DC × her virt family için
   `compute_all_panels(dc_code=dc, family=family)` çalıştırıp snapshot doldurur
   (`clusters=None`, yani dc-geneli datalake+Redis yolu).
2. `compute_summary("*")` — global pano (başarılı scope'lar Tier-1/Tier-2'yi yerinde günceller).
3. Her panel ölçüsünü (`measures_from_panel`) `TaggingService` cache'ine yazar ve
   `gui_metric_snapshot`'a snapshot'lar; üst-düzey 4 KPI metriğini de ekler.

---

## Veri Kaynakları

### WebUI DB tabloları (`gui_*`)

| Tablo | Rol | Anahtar kolonlar |
|---|---|---|
| `gui_panel_definition` | Panel registry | `panel_key, label, family, resource_kind, display_unit, sort_order, enabled` |
| `gui_panel_infra_source` | Panel → datalake kaynak eşlemesi | `panel_key, dc_code, source_table, total_column, total_unit, allocated_table, allocated_column, allocated_unit, manual_total, manual_allocated, filter_clause` |
| `gui_panel_resource_ratio` | Aile başına CPU:RAM:Storage oranı | `family, dc_code, cpu_per_unit, ram_gb_per_unit, storage_gb_per_unit` |
| `gui_unit_conversion` | Birim dönüşümleri | `from_unit, to_unit, factor, operation, ceil_result` |
| `gui_crm_threshold_config` | Satılabilir tavan % | `panel_key, resource_type, dc_code, sellable_limit_pct` |
| `gui_crm_price_override` | Operatör birim fiyatı (TL) | `productid, unit_price_tl, currency, resource_unit` |
| `gui_crm_service_pages` | panel_key ↔ page_key | `panel_key, page_key` |
| `gui_crm_service_mapping_seed` | page_key ↔ productid (tohum) | `page_key, productid` |
| `gui_crm_service_mapping_override` | productid override | `productid` |
| `gui_crm_calc_config` | Genel sayısal/string config | `config_key, config_value, value_type` |
| `gui_panel_result_snapshot` | **Tier-2** panel sonuç cache | `dc_code, family, clusters_csv, payload(jsonb), computed_at` |
| `gui_metric_snapshot` | Trend için metrik snapshot | `metric_key, scope_type, scope_id, value, unit, captured_at` |

> **Not (dokümandaki şema adları):** Görev şablonu `gui_panel_definitions`,
> `gui_panel_infra_source`, `gui_calc_thresholds`, `gui_resource_ratio` gibi
> adlar geçirmişti; gerçek kaynak kodda kullanılan tablo adları yukarıdaki
> sütundakilerdir (`gui_panel_definition` tekil, threshold için
> `gui_crm_threshold_config`, ratio için `gui_panel_resource_ratio`).

### Datalake DB tabloları

| Tablo | Kullanım | latest-snapshot mantığı |
|---|---|---|
| `datacenter_metrics` | VMware DC total (cap) | `DISTINCT ON (dc, datacenter) ORDER BY ... "timestamp" DESC` |
| `cluster_metrics` | VMware cluster total | `DISTINCT ON (cluster, datacenter) ... "timestamp" DESC` |
| `nutanix_cluster_metrics` | Nutanix cluster total | `DISTINCT ON (cluster_uuid) ... collection_time DESC` |
| `ibm_server_general` | IBM Power server total | `DISTINCT ON (server_details_servername) ... time DESC` |
| `ibm_lpar_general` | IBM Power LPAR allocated | `DISTINCT ON (lparname) ... time DESC` |
| `raw_ibm_storage_system` | IBM storage (varchar kapasite) | `DISTINCT ON (storage_ip) ... "timestamp" DESC` |
| `vm_metrics` | VMware allocated | datalake'te DEĞİL — Redis'ten okunur |
| `nutanix_vm_metrics` | Nutanix allocated | datalake'te DEĞİL — Redis'ten okunur |
| `discovery_crm_productpricelevels` | Katalog fiyatı | — |
| `discovery_crm_pricelevels` | Para birimi / kur | — |
| `discovery_crm_salesorders` | YTD gerçekleşen satış | — |
| `discovery_crm_products` | Unmapped ürün sayacı | — |

---

## Sorgular

Tüm SQL `services/customer-api/app/db/queries/sellable.py` ve `crm_config.py`
içindedir. Aşağıda kaynaktan **birebir** alınmıştır.

### Bulk infra source (DC başına en iyi eşleşme)

```sql
SELECT DISTINCT ON (panel_key)
    panel_key, dc_code, source_table, total_column, total_unit,
    allocated_table, allocated_column, allocated_unit,
    manual_total, manual_allocated,
    filter_clause, notes
FROM   gui_panel_infra_source
WHERE  dc_code = %s OR dc_code = '*'
ORDER  BY panel_key, (dc_code = '*') ASC;
```
**Ne yapar:** Her `panel_key` için, verilen `dc_code` ile eşleşen veya `'*'`
wildcard satırını döndürür. `ORDER BY ... (dc_code = '*') ASC` sayesinde
`False < True`, yani **dc-spesifik satır wildcard'tan önce** seçilir
(`DISTINCT ON` ilkini alır).
**Parametreler:** `%s` = `dc_code`.

### Bulk thresholds (DC başına tüm eşik satırları)

```sql
SELECT panel_key, resource_type, dc_code, sellable_limit_pct
FROM   gui_crm_threshold_config
WHERE  dc_code = %s OR dc_code = '*'
ORDER  BY (dc_code = '*') ASC;
```
**Ne yapar:** Bir DC için tüm eşik satırlarını çeker; `panel_key > resource_type`
önceliği ve dc-spesifik vs wildcard önceliği Python'da (`_bulk_load_thresholds`)
işlenir. Sonuç `{"_by_panel_key": {...}, "_by_resource_type": {...}}`.
**Parametreler:** `%s` = `dc_code`.

### Bulk price overrides (panel başına en iyi override)

```sql
SELECT DISTINCT ON (sp.panel_key)
    sp.panel_key,
    po.unit_price_tl
FROM   gui_crm_service_pages       sp
JOIN   gui_crm_service_mapping_seed sm  ON sm.page_key  = sp.page_key
LEFT   JOIN gui_crm_service_mapping_override ov
                                        ON ov.productid = sm.productid
JOIN   gui_crm_price_override       po
       ON po.productid = COALESCE(ov.productid, sm.productid)
WHERE  po.unit_price_tl IS NOT NULL
ORDER  BY sp.panel_key, po.updated_at DESC;
```
**Ne yapar:** Her panel için, panel→page→product zinciri üzerinden (override
varsa onu, yoksa seed productid'sini kullanarak) operatör birim fiyatını (TL)
döndürür. En yeni `updated_at` kazanır. Override'ı olmayan paneller katalog
fallback'e düşer.
**Parametreler:** yok.

### Tek panel threshold (precedence)

```sql
SELECT sellable_limit_pct
FROM   gui_crm_threshold_config
WHERE  (panel_key = %s OR resource_type = %s)
  AND  (dc_code   = %s OR dc_code = '*')
ORDER BY (panel_key = %s) DESC,
         (dc_code = '*') ASC
LIMIT 1;
```
**Ne yapar:** Bulk yol mevcut değilse panel başına eşik çözer; `panel_key`
eşleşmesi `resource_type` eşleşmesinin, dc-spesifik satır wildcard'ın önündedir.
**Parametreler:** `panel_key, resource_kind, dc_code, panel_key`.

### Price override (tek panel, katalog fallback öncesi)

```sql
SELECT po.unit_price_tl, po.currency, po.productid
FROM   gui_crm_price_override   po
JOIN   gui_crm_service_pages    sp  ON sp.panel_key = %s
JOIN   gui_crm_service_mapping_seed     sm  ON sm.page_key = sp.page_key
LEFT  JOIN gui_crm_service_mapping_override ov ON ov.productid = sm.productid
WHERE  po.productid = COALESCE(ov.productid, sm.productid)
ORDER BY (po.unit_price_tl IS NOT NULL) DESC, po.updated_at DESC
LIMIT 1;
```
**Ne yapar:** Panel için operatör override fiyatını döndürür.
**Parametreler:** `%s` = `panel_key`.

### Katalog TL fiyatı (datalake — fallback)

```sql
SELECT ppl.amount, pl.transactioncurrency_text
FROM   discovery_crm_productpricelevels ppl
JOIN   discovery_crm_pricelevels        pl  ON pl.pricelevelid = ppl.pricelevelid
WHERE  ppl.productid = %s
ORDER BY (pl.transactioncurrency_text = 'TL') DESC,
         ppl.amount DESC
LIMIT 1;
```
**Ne yapar:** Override yoksa, ürünün katalog fiyatını verir; TL para birimi
öncelikli, sonra en yüksek tutar. TL değilse `CurrencyService.to_tl` ile çevrilir.
**Parametreler:** `%s` = `productid`.

### Döviz kurları

```sql
SELECT transactioncurrency_text AS currency,
       MAX(exchangerate) FILTER (WHERE exchangerate IS NOT NULL AND exchangerate > 0) AS rate
FROM   discovery_crm_pricelevels
GROUP  BY transactioncurrency_text;
```
**Ne yapar:** TL hedef/temel kabul edilerek CRM price level'larından kur tablosu.
**Parametreler:** yok.

### YTD gerçekleşen satış (TL)

```sql
SELECT COALESCE(so.transactioncurrency_text, 'TL') AS currency,
       COALESCE(SUM(so.totalamount), 0)::double precision AS amount
FROM   discovery_crm_salesorders so
WHERE  so.statecode IN (3, 4)
  AND  EXTRACT(YEAR FROM COALESCE(so.fulfilldate, so.submitdate, so.modifiedon::date))
       = EXTRACT(YEAR FROM CURRENT_DATE)
GROUP  BY so.transactioncurrency_text;
```
**Ne yapar:** Bu yılki kapanmış (`statecode IN (3, 4)`) satış siparişlerinin
toplamını para birimi bazında verir; çağıran tarafta TL'ye çevrilip toplanır.
**Parametreler:** yok.

### Unmapped product sayacı

```sql
SELECT COUNT(*)::bigint
FROM   discovery_crm_products pr
LEFT JOIN gui_crm_service_mapping_seed     s ON s.productid = pr.productid
LEFT JOIN gui_crm_service_mapping_override o ON o.productid = pr.productid
WHERE  s.productid IS NULL AND o.productid IS NULL;
```
**Ne yapar:** Ne seed ne override eşlemesi olan ürün sayısını verir.
**Parametreler:** yok.

### Dinamik total/allocated SUM — `_sum_sql`

`_query_total_allocated` infra-source descriptor'una göre SQL'i çalışma anında
kurar. Kolon adı `^[a-zA-Z_][a-zA-Z0-9_]*$` regex'i ile (`_sql_ident`) doğrulanır.
`filter_clause` içindeki `:dc_pattern`, `%s` ile değiştirilip DC glob pattern'ine
(`_dc_pattern`: `*` → `%`, aksi halde `%{dc_code.lower()}%`) bağlanır.

**VMware `datacenter_metrics`:**
```sql
SELECT COALESCE(SUM(_infra_dm.{col}), 0)::double precision
FROM (
    SELECT DISTINCT ON (dc, datacenter)
        *
    FROM datacenter_metrics
    ORDER BY dc, datacenter, "timestamp" DESC
) AS _infra_dm {where_sql};
```

**VMware `cluster_metrics`:**
```sql
SELECT COALESCE(SUM(_infra_cm.{col}), 0)::double precision
FROM (
    SELECT DISTINCT ON (cluster, datacenter)
        *
    FROM cluster_metrics
    ORDER BY cluster, datacenter, "timestamp" DESC
) AS _infra_cm {where_sql};
```

**Nutanix `nutanix_cluster_metrics`:**
```sql
SELECT COALESCE(SUM(_infra_ncm.{col}), 0)::double precision
FROM (
    SELECT DISTINCT ON (cluster_uuid)
        *
    FROM nutanix_cluster_metrics
    ORDER BY cluster_uuid, collection_time DESC
) AS _infra_ncm {where_sql};
```

**IBM `ibm_server_general`** (filter_clause yerine `server_details_servername ILIKE %s`):
```sql
SELECT COALESCE(SUM(latest.{col}), 0)::double precision
FROM (
    SELECT DISTINCT ON (server_details_servername)
        {col}
    FROM public.ibm_server_general
    WHERE server_details_servername ILIKE %s
    ORDER BY server_details_servername, time DESC
) latest;
```

**IBM `ibm_lpar_general`** (DISTINCT `lparname`, filtre `lpar_details_servername ILIKE %s`):
```sql
SELECT COALESCE(SUM(latest.{col}), 0)::double precision
FROM (
    SELECT DISTINCT ON (lparname)
        {col}
    FROM public.ibm_lpar_general
    WHERE lpar_details_servername ILIKE %s
    ORDER BY lparname, time DESC
) latest;
```

**Diğer tablolar (generic):**
```sql
SELECT COALESCE(SUM({col}), 0)::double precision
FROM {physical_table}{where_sql};
```

**Ne yapar:** Her aile için "tekrarlı zaman-serisi snapshot'larını çift saymadan"
en güncel satırı baz alan total/allocated SUM'ı. VMware/Nutanix/IBM farkı tam
olarak bu `DISTINCT ON` anahtarında ve sıralama kolonunda (`timestamp` /
`collection_time` / `time`). `{col}` doğrulanmış kolon adı, `{where_sql}`
opsiyonel `WHERE` (yalnız generic ve VMware/Nutanix yolları), `%s` = DC pattern.

### IBM storage varchar kapasite — `_query_ibm_storage_string_totals`

```sql
WITH latest AS (
    SELECT DISTINCT ON (storage_ip)
        storage_ip,
        {tc} AS _tot,
        {ac} AS _used,
        "timestamp"
    FROM {tbl}
    {where_sql}
    ORDER BY storage_ip, "timestamp" DESC
)
SELECT _tot, _used FROM latest
```
**Ne yapar:** `raw_ibm_storage_system` için storage_ip başına en güncel satırı
alır; varchar kapasite stringleri `parse_storage_string_to_gb` ile GB'a çevrilip
toplanır (`total_gb`, `used_gb`). Ayrıntı: [04-ibm-storage-san.md](04-ibm-storage-san.md).
**Parametreler:** `filter_clause` varsa `%s` = DC pattern.

### Snapshot sorguları (Tier-2 + metrik)

```sql
-- gui_panel_result_snapshot okuma
SELECT payload, computed_at
FROM   gui_panel_result_snapshot
WHERE  dc_code = %s AND family = %s AND clusters_csv = %s;

-- yazma (upsert)
INSERT INTO gui_panel_result_snapshot
    (dc_code, family, clusters_csv, payload, computed_at)
VALUES (%s, %s, %s, %s::jsonb, NOW())
ON CONFLICT (dc_code, family, clusters_csv) DO UPDATE SET
    payload     = EXCLUDED.payload,
    computed_at = NOW();

-- metrik snapshot (trend için)
INSERT INTO gui_metric_snapshot (metric_key, scope_type, scope_id, value, unit, captured_at)
VALUES (%s, %s, %s, %s, %s, NOW())
ON CONFLICT (metric_key, scope_type, scope_id, captured_at) DO NOTHING;
```
**Ne yapar:** Panel sonuç payload'unu (PanelResult JSON listesi) kalıcılaştırır ve
trend grafiği için her ölçüyü zaman damgalı snapshot'lar.
**Parametreler:** sırasıyla yukarıdaki kolon değerleri.

### crm_config tabloları (operatör CRUD)

`services/customer-api/app/db/queries/crm_config.py` — Settings ekranından
yönetilen threshold, price override ve calc config tablolarının liste/upsert/delete
SQL'leri burada. Örnek upsert mantığı:
```sql
INSERT INTO gui_crm_threshold_config
    (panel_key, resource_type, dc_code, sellable_limit_pct, notes, updated_by, updated_at)
VALUES (%s, %s, %s, %s, %s, %s, NOW())
ON CONFLICT (resource_type, dc_code) DO UPDATE SET
    panel_key          = EXCLUDED.panel_key,
    sellable_limit_pct = EXCLUDED.sellable_limit_pct,
    ...
```
`gui_crm_price_override` ve `gui_crm_calc_config` benzer `ON CONFLICT`
upsert'lerine sahiptir (detay dosyada). Bu tablolar değişince
`_invalidate_sellable_caches()` ile cache düşürülür.

---

## Hesaplamalar / Formüller

Tüm saf fonksiyonlar `shared/sellable/computation.py` içindedir (DB ve framework
bağımsız; hızlı unit test edilebilir). Algoritma dört adımdır.

### 1) `convert_unit(value, conv)`

```python
def convert_unit(value, conv) -> float:
    if value is None:
        return 0.0
    v = float(value)
    if conv is None:
        return v
    if conv.factor == 0:
        return 0.0
    if conv.operation == "multiply":
        v = v * conv.factor
    else:
        v = v / conv.factor
    if conv.ceil_result:
        v = float(math.ceil(v))
    return v
```
- `value=None` → `0.0`; `conv=None` → identity (değişmez).
- `factor == 0` → `0.0` (sıfıra bölme koruması).
- `operation`: `multiply` ise çarp, aksi halde böl (varsayılan `divide`).
- `ceil_result=True` → işlem sonrası yukarı yuvarla.

### 2) `apply_threshold(total, allocated, pct)`

```python
def apply_threshold(total, allocated, pct) -> float:
    if total <= 0:
        return 0.0
    capped = total * (max(pct, 0.0) / 100.0)
    return max(capped - max(allocated, 0.0), 0.0)
```
**Formül:** `sellable_raw = max(total * pct/100 - allocated, 0)`.
- `total <= 0` → `0.0`.
- Negatif `pct`/`allocated` 0'a kelepçelenir.
- `pct` (`sellable_limit_pct`) eşik çözümünden gelir; varsayılan
  `DEFAULT_THRESHOLD_PCT = 80.0`.

### 3) `constrain_by_ratio(panels, ratio, *, decouple_resource_kinds=None)`

Bir ailenin CPU:RAM:Storage oranını (`gui_panel_resource_ratio`) panellere
uygular. **Yeni** PanelResult listesi döndürür; `sellable_constrained` ve
`ratio_bound` doldurulur. Algoritma (docstring'den birebir):

```
effective_cpu     = sellable_raw_cpu / ratio.cpu_per_unit
effective_ram     = sellable_raw_ram / ratio.ram_gb_per_unit
effective_storage = sellable_raw_storage / ratio.storage_gb_per_unit
n = min(present effective values)            # herhangi biri 0 ise 0
sellable_constrained_cpu     = n * ratio.cpu_per_unit
sellable_constrained_ram     = n * ratio.ram_gb_per_unit
sellable_constrained_storage = n * ratio.storage_gb_per_unit
ratio_bound = constrained < raw - 1e-6
```

Gerçek kod adım adım:
- Paneller `resource_kind`'a göre indekslenir (`_split_by_kind`; son gelen kazanır,
  aile başına kind başına tek panel beklenir).
- `effective_units` listesi: ilgili panel mevcut **ve** `..._per_unit > 0` ise
  `sellable_raw / per_unit` eklenir. `storage` `decouple` içindeyse listeye
  **eklenmez**.
- `n = min(effective_units) if effective_units else 0.0` — darboğaz (en kıt
  kaynak kaç adet CPU birimine izin veriyorsa).
- Her panel için:
  - `cpu` → `constrained = n * ratio.cpu_per_unit`
  - `ram` → `constrained = n * ratio.ram_gb_per_unit`
  - `storage` → `decouple`'da ise `sellable_raw=0, sellable_constrained=0,
    ratio_bound=False` ile çıkar (continue); değilse `n * ratio.storage_gb_per_unit`.
  - diğer (`other` — firewall, license, …) → orana bağlı değil:
    `sellable_constrained = sellable_raw`, `ratio_bound = False`.
  - `ratio_bound = constrained + 1e-6 < p.sellable_raw`.

**Storage compute coupling (2026-06, ADR-0019):** After CPU/RAM ratio and IBM
storage range, `apply_storage_ratio_cap` caps storage by effective compute
bottleneck. `virt_power` storage decouple removed. Pipeline:

```
host/cluster ratio (CPU/RAM) → _apply_storage_range (classic/power)
→ apply_storage_ratio_cap → annotate_panel_constraint_metadata → pricing
```

For `virt_classic` / `virt_hyperconverged` with host rows present (ADR-0020,
`SELLABLE_PAYLOAD_VERSION = 4`), storage participates in **per-host triple-min**
with **independent allocation vs max tracks** (ADR-0021):

```
per-host gates → triple-min per track:
  allocation: (cpu=effective, ram=physical, storage=alloc)
  max:        (cpu=max, ram=max, storage=max)
→ Σ host n_units per track → family KPI Alloc | Max
→ potential_tl_min = allocation TL sum, potential_tl_max = max TL sum
→ deduped storage_pools min/max band per track → pricing
```

CPU sellable quantity is always **vCPU** (1 GHz = 1 vCPU); no separate Phys GHz
display or GHz-based pricing on CPU panels.

Skip `_apply_storage_range` DC aggregate and `apply_storage_ratio_cap` when
`host_based_ok` is true.

`constraint_reason` / `bottleneck_kind` / `bottleneck_units` on panel JSON.

**Storage decouple (virt_power) — REMOVED 2026-06:** Previously:
```python
virt_power_storage_decouple = frozenset({"storage"})
decouple = virt_power_storage_decouple if fam == "virt_power" else None
```
Storage now participates in ratio min() like other virt families.

### 5) Host-level triple-min (`host_sellable.py`, ADR-0020)

`virt_classic` and `virt_hyperconverged` with host rows use per-host triple-min
before family SUM rollup. Ratio defaults from `gui_panel_resource_ratio` (e.g.
1 vCPU : 4 GB RAM : 50 GB Storage per sellable unit).

**Operator example** (gates passed, headroom after threshold):

| Resource | Headroom |
|----------|----------|
| CPU | 4 GHz |
| RAM | 56 GB |
| Storage | 800 GB |

```
n_cpu  = 4 / 1  = 4
n_ram  = 56 / 4 = 14
n_stor = 800 / 50 = 16
n_units = min(4, 14, 16) = 4
sellable: 4 GHz CPU, 16 GB RAM, 200 GB storage
waste tags: "40 GB RAM ratio-bound", "600 GB Storage ratio-bound"
```

KM shared LUN: min band uses `stor_exclusive_free_gb`; max band adds shared mount
free. Family `storage_pools` dedupes by `datastore_moid`.

### 4) `compute_potential_tl(sellable_constrained, unit_price_tl)`

```python
def compute_potential_tl(sellable_constrained, unit_price_tl) -> float:
    return max(sellable_constrained, 0.0) * max(unit_price_tl, 0.0)
```
**Formül:** `potential_tl = max(sellable_constrained, 0) * max(unit_price_tl, 0)`.
Negatif girdiler 0'a çökerir. Aile geçişinde, ratio uygulandıktan sonra her panel
için yeniden hesaplanır (`compute_all_panels` adım 8-9).

### Aile oranları (ResourceRatio varsayılanları)

`shared/sellable/models.py`:
```python
@dataclass(frozen=True)
class ResourceRatio:
    family: str
    dc_code: str = "*"
    cpu_per_unit: float = 1.0
    ram_gb_per_unit: float = 8.0
    storage_gb_per_unit: float = 100.0
```
Gerçek değerler `gui_panel_resource_ratio`'dan gelir (`(family, dc_code)`,
dc-spesifik > `'*'`). Ratio bulunamazsa `ResourceRatio(family=fam)` varsayılanı.

### Family aggregate (`compute_summary`)

```python
family_potential     = sum(p.potential_tl for p in group)
family_raw_potential = sum(compute_potential_tl(p.sellable_raw, p.unit_price_tl) for p in group)
agg.total_potential_tl  = family_potential
agg.constrained_loss_tl = max(family_raw_potential - family_potential, 0.0)
```
`constrained_loss_tl` = ratio darboğazı yüzünden kaybedilen potansiyel TL.

### Frontend toplama (`virt_sellable_aggregate.py`)

`aggregate_virt_sellable_panels` panel dict'lerini kind bazında toplar:
```python
by_kind = {
    "cpu":     {"constrained": 0.0, "tl": 0.0, "unit": "vCPU"},
    "ram":     {"constrained": 0.0, "tl": 0.0, "unit": "GB"},
    "storage": {"constrained": 0.0, "tl": 0.0, "unit": "GB"},
}
```
`total_potential_tl(panels)` = tüm panellerin `potential_tl` toplamı.

---

## Birim Dönüşümleri (`gui_unit_conversion`)

`SellableService` ham datalake değerini panelin `display_unit`'ine `convert_unit`
ile çevirir. Dönüşüm satırı `_lookup_conversion` ile çözülür:

1. `to_unit` boşsa `None` (dönüşüm yok).
2. `from_unit` boşsa `to_unit` ile eşitlenir.
3. Önce **tam eşleşme** `(from_unit, to_unit)`, bulunamazsa **case-insensitive**
   tarama.

`compute_panel` içinde (legacy datalake yolu):
- `total_from = src.total_unit or panel.display_unit`
- `alloc_from = src.allocated_unit or src.total_unit or panel.display_unit`
- Dönüşüm bulunamaz ve `from != display_unit` ise WARNING loglanır (total ham
  birimde kalır → sellable UI kapasitesine göre absürt büyük olabilir).

Cluster-aware (`/compute`) yolunda kaynak birim sabittir:
```python
_RESOURCE_KIND_TO_COMPUTE_FIELDS = {
    "cpu":     ("cpu_cap",  "cpu_used",  "GHz"),
    "ram":     ("mem_cap",  "mem_used",  "GB"),
    "storage": ("stor_cap", "stor_used", "TB"),
}
```
Bu kaynak birimden `panel.display_unit`'e yine `gui_unit_conversion` üzerinden
çevrilir.

`UnitConversion` modeli: `from_unit, to_unit, factor, operation('divide'|'multiply'),
ceil_result(bool)`.

---

## Caching

Üç katmanlı cache vardır.

### Tier-1 — Redis (crm-engine DB 2)

- Anahtar: `sellable:panels:{dc_code|'*'}:{family|'*'}:{clusters_csv}`
  (`_result_cache_key`; cluster listesi sıralı CSV).
- TTL: `SELLABLE_CACHE_TTL_SECONDS` (varsayılan **3600 sn**); `0` cache'i kapatır.
- `compute_all_panels` ilk adımda buraya bakar; `_result_cache_set` ile yazar.
- `invalidate_result_cache(dc_code)` → `scan_iter(match=...)` ile ilgili anahtarları
  siler (DC verilirse `sellable:panels:{dc}:*`, yoksa `sellable:panels:*`).

### Tier-2 — webui-db kalıcı snapshot (`gui_panel_result_snapshot`)

- `(dc_code, family, clusters_csv)` PK; `payload` jsonb (PanelResult listesi).
- Tier-1 miss → Tier-2 okunur (`_snapshot_db_get`); hit olursa Tier-1 tekrar
  doldurulur. `compute_all_panels` sonunda `_snapshot_db_set` ile yazılır.
- `_snapshot_db_invalidate(dc_code)` → `DELETE ... WHERE (%s IS NULL OR dc_code = %s)`.
- `snapshot_meta` / `GET_LATEST_SNAPSHOT_META` → en güncel `computed_at`
  (frontend "veri tazeliği" göstergesi).
- Restart sonrası soğuk-başlangıç sıfırlarını azaltır.

### Tier-3 — frontend in-process warm cache (`datacenters_virt_sellable.py`)

- `/datacenters` listesindeki DC başına virt TL değeri için süreç-içi sözlük
  (`_VIRT_TL_CACHE`), `tr_key` (preset|start|end) ile anahtarlanır.
- `start_virt_cache_warm` → arka plan thread'de tüm DC'leri `ThreadPoolExecutor`
  ile paralel ısıtır (worker'lar `DC_OVERVIEW_VIRT_WORKERS`=4,
  `DC_OVERVIEW_VIRT_FAMILY_WORKERS`=1 env'leri).
- `resolve_virt_sellable_for_dcs` cache tam değilse arka plan warm tetikler,
  `loading=True` ile kısmi/sıfır harita döndürür; tamamlanınca gerçek değerler.
- `refresh_virt_sellable_cache` poll callback'i için senkron yeniden hesap.
- `_virt_sellable_tl_for_dc(dc_id)` → `collect_virt_sellable_panels(dc_id, None,
  None)` (cluster=None, yani dc-geneli yol) → `total_potential_tl`.

### Allocated için datacenter-api Redis payload (ara katman)

`vm_metrics` / `nutanix_vm_metrics` panellerinde allocated, datalake yerine
datacenter-api Redis cache'inden okunur (full-table VM taramasından, bayat-VM
dahil etmekten ve Nutanix JOIN'deki `uuid = character varying` tip uyumsuzluğundan
kaçınmak için). Anahtarlar `_dc_redis_key` ile DC payload pencerelerine hizalanır:
- Global: `global_dashboard:{start}:{end}` (section `*_totals`).
- DC: `dc_details:{dc_code}:{start}:{end}` (section `classic` / `hyperconv`).
- Pencere `SELLABLE_REDIS_WINDOW_DAYS` (varsayılan **7 gün**); datacenter-api
  default time-range ile eşleşmeli, yoksa her lookup miss olur.

Eşleme tabloları:
```python
_VM_TABLE_DC_SECTION     = {"vm_metrics": "classic",        "nutanix_vm_metrics": "hyperconv"}
_VM_TABLE_GLOBAL_SECTION = {"vm_metrics": "classic_totals", "nutanix_vm_metrics": "hyperconv_totals"}
_VM_COLUMN_TO_REDIS_FIELD = {
    "number_of_cpus": "cpu_used", "total_memory_capacity_gb": "mem_used", "provisioned_space_gb": "stor_used",  # VMware
    "cpu_count": "cpu_used",      "memory_capacity": "mem_used",          "disk_capacity": "stor_used",          # Nutanix
}
```
Redis miss + HTTP fallback (`/api/v1/dashboard/overview` veya
`/api/v1/datacenters/{dc}`) de başarısızsa allocated `0` kabul edilir.

### Trend metrik snapshot

`snapshot_all` her panelin 6 ölçüsünü (`total, allocated, sellable_raw,
sellable_constrained, unit_price_tl, potential_tl`) `gui_metric_snapshot`'a yazar.
Metrik anahtarı `build_metric_key(family, resource_kind, measure)` →
`family_namespace.resource_kind.measure` (ör. `virtualization.hyperconverged.ram.total`).
Üst-düzey KPI'lar: `crm.sellable_potential.total_tl`,
`crm.sellable_potential.constrained_loss_tl`, `crm.sellable_potential.ytd_sales_tl`,
`crm.sellable_potential.unmapped_count`.

---

## Özet

- **Sellable Potential**, panel→infra source→unit conversion→threshold→ratio
  darboğazı→TL fiyat zinciriyle altyapıdaki boş kapasitenin TL karşılığını
  hesaplayan CRM panosudur. Saf matematik `shared/sellable/computation.py`'de,
  orkestrasyon `customer-api/SellableService`'de, dağıtım crm-engine'dedir.
- **Çekirdek formüller:** `sellable_raw = max(total*pct/100 - allocated, 0)`;
  ratio darboğazı `n = min(sellable_raw_kind / ratio.kind_per_unit)` ve
  `sellable_constrained_kind = n * ratio.kind_per_unit`;
  `potential_tl = max(sellable_constrained,0) * max(unit_price_tl,0)`.
- **Aile farkları:** total/allocated SUM'ı VMware (`datacenter_metrics`/
  `cluster_metrics`, `timestamp`), Nutanix (`nutanix_cluster_metrics`,
  `collection_time`), IBM (`ibm_server/lpar_general`, `time`) için ayrı
  latest-snapshot subquery'siyle; VM allocated'ı datacenter-api Redis'inden;
  `virt_power`'da storage decouple edilir. Üç katmanlı cache (Redis DB2 →
  webui-db snapshot → frontend warm) ile maliyetli yeniden hesaplama önlenir.

### Belirsizlikler / Notlar

1. **Tablo adı uyumu:** Görev şablonundaki `gui_panel_definitions`,
   `gui_calc_thresholds`, `gui_resource_ratio` adları kaynakta sırasıyla
   `gui_panel_definition`, `gui_crm_threshold_config`, `gui_panel_resource_ratio`
   olarak geçiyor; dokümanda gerçek adlar kullanıldı.
2. **Branch:** İçerik `main` (190f07c) dalından alınmıştır. `sellable_service.py`
   içindeki dinamik SQL, `main`'in eski tablo adlarını kullanır — doğrulandı:
   `datacenter_metrics`, `nutanix_cluster_metrics`, `ibm_server_general`.
   `*_performance_metrics` migration'ı `feature/vcenter-nutanix-ibm-integration`
   dalındadır; o dalda bu tablo adları değişir (bkz.
   [01-vmware.md](01-vmware.md)/[02-nutanix.md](02-nutanix.md) migration notları).
3. **`gui_unit_conversion` ve `gui_panel_resource_ratio` satır değerleri** veritabanı
   tohumuna (seed) bağlıdır; kaynak kodda yalnız varsayılanlar (`ram_gb_per_unit=8`,
   `storage_gb_per_unit=100`) sabittir. Gerçek üretim oranları DB'den okunur.
