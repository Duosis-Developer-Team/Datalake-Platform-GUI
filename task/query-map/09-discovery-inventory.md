# Discovery & Envanter Sorguları

> Cross-reference: [README](README.md) — mimari ve ortak desenler.

Bu doküman, Loki/NetBox tabanlı **keşif (discovery)** ve **fiziksel envanter**
sorgularını belgeler. Kaynak dosyalar:

- `services/datacenter-api/app/db/queries/discovery_rack.py` — rack + rack-device sorguları
- `services/datacenter-api/app/db/queries/loki.py` — dinamik DC listesi + lokasyon/açıklama eşlemleri
- `services/datacenter-api/app/db/queries/registry.py` — Query Explorer için merkezi sorgu kataloğu
- `services/datacenter-api/app/db/queries/customer.py` — `PHYSICAL_INVENTORY_ALL_DEVICES` (NetBox cihaz listesi)
- `services/datacenter-api/app/services/dc_service.py` — DC listesi çözümleme + rack/floor/NetBox kullanım mantığı
- `src/pages/floor_map.py`, `src/pages/dc_detail.py` — floor map görselleştirme

---

## Genel Bakış

Bu kapsamdaki sorguların iki ana işlevi vardır:

1. **Dinamik DC listesi çözümleme** (`public.loki_locations`).
   Tüm uygulamanın üzerinde iterasyon yaptığı DC kümesini bu tablo belirler.
   `DatabaseService._load_dc_list()` başlangıçta (ve her `get_all_datacenters_summary()`
   yeniden inşasında) çağrılır; `self._dc_list`, `self._dc_site_map` ve
   `self._dc_description_map` bu sorgulardan beslenir. DB erişilemezse
   `_FALLBACK_DC_LIST` (`AZ11, DC11–DC17, ICT11`) kullanılır. `dc_list` property'si
   bu listeyi salt-okunur biçimde dışarı verir ve neredeyse tüm batch/per-DC akışları
   (`_fetch_all_batch`, physical inventory warm, brocade/IBM-storage DC çözümleme,
   S3 warm vb.) bu küme üzerinde döner.

2. **Fiziksel rack/cihaz keşfi → Floor Map**
   (`public.discovery_loki_rack`, `public.discovery_loki_location`, `loki_devices`).
   `get_dc_racks(dc_code)` bir DC'nin rack'lerini + özetini döner;
   `get_rack_devices(rack_name)` tek bir rack'in içindeki cihazları döner.
   Bu veriler `src/pages/floor_map.py` ile bina kat planı (halls → racks → devices)
   olarak çizilir; giriş noktası `src/pages/dc_detail.py:136` (`api.get_dc_racks(dc_id)`).

3. **NetBox fiziksel envanter** (`public.discovery_netbox_inventory_device`).
   `_get_physical_inventory_raw()` ile tüm aktif cihazlar tek sefer çekilir,
   `loki_locations` üzerinden DC'ye eşlenir ve Python tarafında role/manufacturer/
   location kırılımları üretilir (Overview drill-down ve Customer View).
   Ayrıca brocade switch ve IBM storage IP'lerinin DC'ye çözümlenmesinde
   fallback kaynağı olarak kullanılır.

### Hangi ekranlar

| Ekran / akış | Kaynak metot | Sorgu |
|---|---|---|
| Tüm uygulamanın DC iterasyonu | `_load_dc_list` | `loki.DC_LIST_WITH_SITE` (+fallback'ler) |
| DC kartı `site_name` / açıklama | `_load_dc_list`, `_ensure_dc_description_map` | `DC_LIST_WITH_SITE`, `DC_NAME_DESCRIPTION_MAP` |
| DC detay → Floor Map | `get_dc_racks` | `discovery_rack.RACKS_BY_DC`, `RACK_SUMMARY_BY_DC` |
| Rack tıklama → cihaz listesi | `get_rack_devices` | `discovery_rack.DEVICES_BY_RACK_NAME` |
| Physical Inventory (overview/DC/customer) | `_get_physical_inventory_raw` + `_get_location_dc_map` | `customer.PHYSICAL_INVENTORY_ALL_DEVICES`, `loki.LOCATION_DC_MAP` |
| Brocade/IBM-storage DC fallback | `_resolve_brocade_dc`, IBM storage çözümleyici | inline `discovery_netbox_inventory_device` SELECT |
| Query Explorer | `execute_registered_query` | `registry.QUERY_REGISTRY` |

---

## Veri Kaynakları (tablolar + kolonlar)

### `public.loki_locations`
Loki'den senkronlanan lokasyon hiyerarşisi. DC kök kayıtları `parent_id IS NULL`
olanlardır; alt lokasyonlar (hall vb.) `parent_name` ile DC'ye bağlanır.
Kullanılan kolonlar: `name`, `parent_id`, `parent_name`, `site_name`,
`description`, `status_value`.

### `public.discovery_loki_rack` (alias `r`)
Fiziksel rack envanteri. Kolonlar (RACKS_BY_DC'de seçilenler):
`id, name, display_name, status, status_description, u_height, kabin_enerji,
pdu_a_ip, pdu_b_ip, rack_type, serial, asset_tag, tenant_name, facility_id,
weight, max_weight, weight_unit, description, comments, first_observed,
last_observed, location_id, site_id`.

### `public.discovery_loki_location` (alias `l`)
Rack'in bağlı olduğu lokasyon. `RACKS_BY_DC` içinde `r.location_id = l.id::varchar`
ile JOIN edilir; `l.name AS hall_name` floor map'te hall etiketi olur.
Filtre `l.name` veya `l.parent_name` üzerinden yapılır.

### `loki_devices` (alias `d`)
Rack içindeki cihazlar. Kolonlar: `name, position, face_value, device_role_name,
device_type_name, status_value, status_label, manufacturer_name, description,
rack_name, rack_id, collection_time`.

### `public.discovery_netbox_inventory_device`
NetBox keşif cihaz envanteri. Kullanılan kolonlar: `id, name, device_type_name,
manufacturer_name, device_role_name, tenant_id, site_id, site_name, location_id,
location_name, status_value, primary_ip_address, collection_time`.

---

## Sorgular

### 1. `DC_LIST_WITH_SITE` — Dinamik DC listesi (site ile, aktif)

```sql
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name,
    site_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
    AND status_value = 'active'
ORDER BY 1
```

**Ne yapar:** Aktif lokasyonlardan benzersiz DC adlarını ve `site_name`'lerini döner.
Kök kayıtta (`parent_id IS NULL`) `name`, alt kayıtta `parent_name` DC adı olarak alınır.
Bu, `_load_dc_list()`'in birincil kaynağıdır.
**Parametreler:** yok.
**Dönen sütunlar:** `dc_name`, `site_name`.

### 2. `DC_LIST_WITH_SITE_NO_STATUS` — Dinamik DC listesi (site ile, status filtresiz)

```sql
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name,
    site_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
ORDER BY 1
```

**Ne yapar:** Aktif filtreli sorgu boş dönerse fallback olarak kullanılır
(`status_value` filtresi yoktur).
**Parametreler:** yok.
**Dönen sütunlar:** `dc_name`, `site_name`.

### 3. `DC_LIST` — Sadece DC adları (aktif)

```sql
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
    AND status_value = 'active'
ORDER BY 1
```

**Ne yapar:** `site_name` olmadan yalnızca DC adı listesi.
**Parametreler:** yok.
**Dönen sütunlar:** `dc_name`.

### 4. `DC_LIST_NO_STATUS` — Sadece DC adları (status filtresiz)

```sql
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
ORDER BY 1
```

**Ne yapar:** `DC_LIST`'in status filtresiz fallback varyantı.
**Parametreler:** yok.
**Dönen sütunlar:** `dc_name`.

### 5. `LOCATION_DC_MAP` — Lokasyon adı → DC adı eşlemi

```sql
SELECT
    name AS location_name,
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name
FROM public.loki_locations
WHERE CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
```

**Ne yapar:** Her lokasyon adını ait olduğu DC'ye eşler. `_get_location_dc_map()`
ile çekilir ve NetBox cihazlarının `location_name` alanını DC'ye çözmek için
bellekte (cache `loki:location_dc_map`) tutulur.
**Parametreler:** yok.
**Dönen sütunlar:** `location_name`, `dc_name`.

### 6. `DC_NAME_DESCRIPTION_MAP` — DC adı → tesis açıklaması (aktif)

```sql
SELECT
    name AS dc_name,
    MAX(NULLIF(TRIM(description), '')) AS description
FROM public.loki_locations
WHERE parent_id IS NULL
  AND status_value = 'active'
GROUP BY name
ORDER BY name
```

**Ne yapar:** DC kök kayıtlarının (NetBox/Loki) tesis açıklamasını döner
(örn. `DC13 → Equinix IL2 DC`). `_load_dc_list()` ve `_ensure_dc_description_map()`
ile `self._dc_description_map`'i doldurur; bu açıklama DC detay `meta.description`
alanına yansır.
**Parametreler:** yok.
**Dönen sütunlar:** `dc_name`, `description`.

### 7. `DC_NAME_DESCRIPTION_MAP_NO_STATUS` — DC açıklaması (status filtresiz)

```sql
SELECT
    name AS dc_name,
    MAX(NULLIF(TRIM(description), '')) AS description
FROM public.loki_locations
WHERE parent_id IS NULL
GROUP BY name
ORDER BY name
```

**Ne yapar:** Bir önceki sorgu boş dönerse fallback.
**Parametreler:** yok.
**Dönen sütunlar:** `dc_name`, `description`.

### 8. `RACKS_BY_DC` — Bir DC'nin rack'leri (floor map)

```sql
SELECT
    r.id,
    r.name,
    r.display_name,
    r.status,
    r.status_description,
    r.u_height,
    r.kabin_enerji,
    r.pdu_a_ip,
    r.pdu_b_ip,
    r.rack_type,
    r.serial,
    r.asset_tag,
    r.tenant_name,
    r.facility_id,
    r.weight,
    r.max_weight,
    r.weight_unit,
    r.description,
    r.comments,
    r.first_observed,
    r.last_observed,
    r.location_id,
    r.site_id,
    l.name AS hall_name
FROM public.discovery_loki_rack r
JOIN public.discovery_loki_location l
    ON r.location_id = l.id::varchar
WHERE (l.name = %s OR l.parent_name = %s)
ORDER BY l.name, r.name
```

**Ne yapar:** Verilen DC adına ait tüm rack'leri, bağlı oldukları lokasyon
(`hall_name`) ile birlikte döner. Eşleştirme rack'in lokasyonunun `name`'i ya da
`parent_name`'i DC adına eşitse yapılır. Sonuç hall → rack → device hiyerarşisi için
floor map'e girer.
**Parametreler:** `(dc_code, dc_code)` — aynı değer iki kez (`l.name = %s OR l.parent_name = %s`).
**Dönen sütunlar:** yukarıdaki 24 kolon; `get_dc_racks` bunları `columns` listesiyle
dict'e map'ler (`first_observed`/`last_observed` string'e çevrilir).

### 9. `RACK_SUMMARY_BY_DC` — DC rack özeti

```sql
SELECT
    COUNT(*) AS total_racks,
    COUNT(*) FILTER (WHERE r.status = 'active') AS active_racks,
    COALESCE(SUM(r.u_height), 0) AS total_u_height,
    COUNT(*) FILTER (WHERE r.kabin_enerji IS NOT NULL AND r.kabin_enerji != '') AS racks_with_energy,
    COUNT(*) FILTER (WHERE r.pdu_a_ip IS NOT NULL AND r.pdu_a_ip != '') AS racks_with_pdu
FROM public.discovery_loki_rack r
JOIN public.discovery_loki_location l
    ON r.location_id = l.id::varchar
WHERE (l.name = %s OR l.parent_name = %s)
```

**Ne yapar:** DC için rack özet sayıları üretir: toplam, aktif, toplam U yüksekliği,
kabin enerjisi tanımlı olanlar ve PDU-A IP'si olanlar.
**Parametreler:** `(dc_code, dc_code)`.
**Dönen sütunlar:** `total_racks, active_racks, total_u_height, racks_with_energy, racks_with_pdu`.

### 10. `DEVICES_BY_RACK_NAME` — Rack içindeki cihazlar

```sql
SELECT DISTINCT ON (d.name)
    d.name,
    d.position,
    d.face_value,
    d.device_role_name,
    d.device_type_name,
    d.status_value,
    d.status_label,
    d.manufacturer_name,
    d.description
FROM loki_devices d
WHERE d.rack_name = %s
  AND d.rack_id IS NOT NULL
ORDER BY d.name, d.collection_time DESC
```

**Ne yapar:** Belirli bir rack'teki cihazları döner; cihaz adı başına en son
snapshot (`DISTINCT ON (d.name)` + `collection_time DESC`) alınır. `position`
floor map'te U yerleşimini sürer.
**Parametreler:** `(rack_name,)`.
**Dönen sütunlar:** `name, position, face_value, device_role_name, device_type_name,
status_value, status_label, manufacturer_name, description`. `get_rack_devices`
bunları `name, position, face, role, device_type, status_value, status_label,
manufacturer, description` anahtarlarına map'ler (`position` float'a çevrilir).

### 11. `PHYSICAL_INVENTORY_ALL_DEVICES` — Tüm aktif NetBox cihazları

```sql
SELECT DISTINCT ON (name, site_id, location_id)
    id,
    name,
    device_type_name,
    manufacturer_name,
    device_role_name,
    tenant_id,
    site_id,
    site_name,
    location_id,
    location_name
FROM public.discovery_netbox_inventory_device
WHERE status_value = 'active'
ORDER BY name, site_id, location_id, collection_time DESC NULLS LAST
```

**Ne yapar:** Aktif fiziksel cihazların tamamını (cihaz+site+location anahtarı başına
en son snapshot) tek sorguda döner. JOIN/aggregation yoktur; DC eşlemesi ve role/
manufacturer/location kırılımları Python tarafında (`_get_location_dc_map` ile)
yapılır. Physical Inventory overview, per-DC ve Customer View (tenant_id=5 → Boyner)
görünümlerinin tek veri kaynağıdır.
**Parametreler:** yok.
**Dönen sütunlar:** `id, name, device_type_name, manufacturer_name, device_role_name,
tenant_id, site_id, site_name, location_id, location_name`.

### 12. NetBox DC fallback çözümleme (inline SQL — `_resolve_brocade_dc`)

```sql
SELECT
    site_name,
    location_name,
    "name",
    primary_ip_address
FROM public.discovery_netbox_inventory_device
WHERE
    status_value = 'active'
    AND (
    primary_ip_address = %s
 OR primary_ip_address ILIKE %s
 OR "name" ILIKE %s
 OR location_name ILIKE %s
 OR site_name ILIKE %s
    )
ORDER BY collection_time DESC NULLS LAST
LIMIT 20
```

**Ne yapar:** Bir brocade switch host (veya benzer biçimde IBM storage IP) için DC
kodu doğrudan regex ile çıkarılamadığında, NetBox cihaz envanterinde IP/ad eşleşmesi
arar; dönen satırların `site_name`/`location_name`/`name` alanlarından `_DC_CODE_RE`
ile DC kodu çıkarmaya çalışır (ilk eşleşen DC seçilir).
**Parametreler:** `(host_key, like, like, like, like)` — `host_key` ham değer,
`like = f"%{host_key}%"`.
**Dönen sütunlar:** `site_name, location_name, name, primary_ip_address`.
> Not: IBM storage tarafında (`dc_service.py:3424` civarı) aynı tabloyu kullanan
> benzer bir fallback SELECT daha vardır; ayrıntısı [04-ibm-storage-san.md](04-ibm-storage-san.md)
> kapsamındadır.

### 13. Query Registry — `QUERY_REGISTRY` (registry.py)

`registry.py` SQL üretmez; her dashboard sorgusunu **merkezi bir katalogda** kaydeder
ve Query Explorer'ın (`execute_registered_query`) dinamik çalıştırması için meta veri
sağlar. Her giriş şu alanları taşır:

- `sql` — ilgili provider modülünden SQL string'i
- `source` — bilgilendirici tablo adı
- `result_type` — `"value" | "row" | "rows"`
- `params_style` — `"wildcard" | "exact" | "array_wildcard" | "array_exact" | "wildcard_pair" | "exact_pair"`
- `provider` — `nutanix | vmware | ibm | energy | customer | backup`
- `batch_key` — (yalnız batch) satırı DC koduna geri eşleyen kolon adı

`_prepare_params(params_style, user_input)` kullanıcı girdisini parametre tuple/list'ine
çevirir: `wildcard → (f"%{input}%",)`, `array_wildcard → ([f"%{p}%", ...],)`,
`exact → (input,)`, `wildcard_pair → (p, p)` vb. `execute_registered_query` ise
`result_type`'a göre `value`/`row`/`rows` yapısını döner.
> **Önemli:** `QUERY_REGISTRY` bu kapsamdaki discovery/loki/netbox sorgularını
> **içermez** — yalnız nutanix/vmware/ibm/energy/customer/backup provider'larını
> kaydeder. Discovery sorguları doğrudan `dc_service` metotları üzerinden çağrılır.
> Registry'nin tam kullanım akışı için bkz. [11-query-api.md](11-query-api.md).

---

## Hesaplamalar / Formüller

### DC listesi çözümleme mantığı (`_load_dc_list`)

`dc_service.py` içindeki sıralama (lines 536–562):

1. `DC_LIST_WITH_SITE` çalıştırılır → `dc_names = [row[0] for row in rows if row[0]]`.
2. Boşsa `DC_LIST_WITH_SITE_NO_STATUS` ile tekrar denenir (status filtresi kalkar).
3. `self._dc_site_map = {row[0]: row[1] for row in rows if row[0] and row[1]}`
   (DC → site_name eşlemi).
4. `DC_NAME_DESCRIPTION_MAP` (boşsa `..._NO_STATUS`) ile
   `self._dc_description_map` doldurulur.
5. `OperationalError` (DB erişilemez) → `_FALLBACK_DC_LIST.copy()` döner.
6. `dc_names` doluysa o döner; boşsa yine `_FALLBACK_DC_LIST` döner.

`_FALLBACK_DC_LIST = ["AZ11", "DC11", "DC12", "DC13", "DC14", "DC15", "DC16", "DC17", "ICT11"]`.

Çözümlenen liste `self._dc_list`'e yazılır ve `get_all_datacenters_summary()` her
yeniden inşada `self._dc_list = self._load_dc_list()` ile günceller. Böylece
`loki_locations` **tüm uygulamanın DC kümesini** belirler: batch metrikler
(`_fetch_all_batch`), physical inventory warm, brocade/IBM-storage DC çözümleme,
S3 warm vb. hep `self.dc_list` üzerinde döner.

`DC_LOCATIONS` dict'i (örn. `DC13 → "Istanbul"`) yalnızca **görüntüleme amaçlı**
sabit eşlemdir; mantık dinamik listeden gelir. DB'den `meta.location` üretilmez,
`DC_LOCATIONS.get(dc_code, "Unknown Data Center")` kullanılır.

### DC adı çıkarma regex'i (`_DC_CODE_RE`)

```python
_DC_CODE_RE = re.compile(r'(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)', re.IGNORECASE)
```

Serbest metinden DC kodu çıkarır. `_extract_dc_from_text(value, dc_set)` eşleşeni
büyük harfe çevirir ve **yalnızca** `dc_set` (= mevcut `self.dc_list`) içindeyse döner;
bu, NetBox fallback ve backup DC atama akışlarında kullanılır.

### Rack ↔ hall ↔ floor eşleştirme

- **Rack → hall:** `RACKS_BY_DC` JOIN'i `r.location_id = l.id::varchar`; rack'in hall
  adı `l.name AS hall_name`. DC filtresi `l.name = dc OR l.parent_name = dc`
  (rack ya doğrudan DC lokasyonunda ya da DC altındaki bir hall'da olabilir).
- **Floor map yerleşimi** (`src/pages/floor_map.py`): tüm hall'lar tek bir bina kat
  sınırı içinde çizilir; her hall etiketli bir zon, rack'ler hall içinde grid'e
  yerleşir. Rack sıralaması `facility_id` (yoksa `name`) ile yapılır
  (`_sort_key`). Hover kartı `id, name, status, u_height, kabin_enerji (pwr),
  hall_name, rack_type, serial` alanlarını gösterir. Şekil değişikliğini saptamak
  için `_rack_fingerprint` `(id, name, status, u_height, hall_name, facility_id,
  last_observed)` alanlarını kullanır.
- **Rack → device:** `DEVICES_BY_RACK_NAME` `d.rack_name = rack_name` ile filtreler;
  cihazın `position` değeri U yerleşimini, `face_value` ön/arka yüzü verir.

### NetBox cihazını DC'ye çözme (`_resolve_device_location`)

```text
loc = device.location_name
if loc:
    return loc_map.get(loc) or loc      # loki_locations LOCATION_DC_MAP üzerinden
return device.site_name or "Unknown"
```

Per-DC eşleştirmede (`get_physical_inventory_dc`) ek olarak
`dc_key in resolved or dc_key in site` (her ikisi lower-case) kontrolü yapılır.
Customer View'da filtre sabit: `tenant_id == 5` (Boyner).

---

## Caching

| Veri | Cache key | TTL / mekanizma |
|---|---|---|
| DC listesi / site / description map | — (in-memory: `self._dc_list`, `_dc_site_map`, `_dc_description_map`) | `_load_dc_list` çağrısında yenilenir; `_ensure_dc_description_map` process başına bir kez lazy-load |
| DC rack listesi + özeti | `dc_racks:{dc_code}` | `cache.run_singleflight(..., ttl=21600)` (6 saat) |
| Rack cihazları | `rack_devices:{rack_name}` | `cache.run_singleflight(..., ttl=21600)` (6 saat) |
| NetBox ham cihaz listesi | `phys_inv:raw_devices` | `cache.set` (varsayılan TTL); `force=True` ile yenilenir |
| Lokasyon→DC eşlemi | `loki:location_dc_map` | `cache.set` (varsayılan TTL) |
| Türetilmiş physical inventory | `phys_inv:overview_by_role`, `phys_inv:customer_boyner`, `phys_inv:dc:{dc}`, `phys_inv:manufacturer:{role}`, `phys_inv:location:{role}:{mfr}` | `cache.set`; `warm_physical_inventory` ile prefix-temizleyip yeniden hesaplar |

**Warm-up:** `warm_cache()` başlangıçta her DC için `get_dc_racks(dc_code)` çağırır
(time-range bağımsız) ve `warm_physical_inventory()`'yi tetikler. Frontend tarafında
`src/services/global_view_prefetch.py` floor map figürlerini ve rack cihazlarını
ön-yükler (`api.get_dc_racks`, `api.get_rack_devices`). Frontend → backend HTTP
uçları: `/api/v1/datacenters/{dc}/racks` ve `/api/v1/datacenters/{dc}/racks/{rack}/devices`
(`src/services/api_client.py`).

---

## Özet

- **`loki_locations` tüm uygulamanın DC kümesini belirler.** `_load_dc_list()`
  `DC_LIST_WITH_SITE` (→ status filtresiz → `_FALLBACK_DC_LIST`) zinciriyle
  `self._dc_list`'i kurar; `site_name` ve `description` eşlemleri de buradan gelir.
  Tüm batch/per-DC iterasyonları bu liste üzerinde döner.
- **Floor Map** `discovery_loki_rack` + `discovery_loki_location` (RACKS_BY_DC,
  RACK_SUMMARY_BY_DC) ve `loki_devices` (DEVICES_BY_RACK_NAME) ile beslenir;
  rack'ler `location_id` üzerinden hall'lara, cihazlar `rack_name` üzerinden
  rack'lere bağlanır. 6 saatlik singleflight cache + startup warm.
- **NetBox envanteri** (`discovery_netbox_inventory_device`) tek `PHYSICAL_INVENTORY_ALL_DEVICES`
  sorgusuyla çekilip Python'da DC/role/manufacturer kırılımlarına dönüşür; ayrıca
  brocade/IBM-storage DC çözümlemede fallback kaynağıdır.
- **`registry.py`** discovery sorgularını içermez; Query Explorer için
  nutanix/vmware/ibm/energy/customer/backup sorgularının meta-kataloğudur.

### Belirsizlikler / Notlar

- Görev tanımı `discovery_rack.py` içinde `discovery_netbox_inventory_device`
  fonksiyonları olduğunu belirtiyordu; gerçekte dosyada yalnızca üç rack sorgusu
  (`RACKS_BY_DC`, `DEVICES_BY_RACK_NAME`, `RACK_SUMMARY_BY_DC`) var. NetBox
  sorguları `customer.py` (`PHYSICAL_INVENTORY_ALL_DEVICES`) ve `dc_service.py`
  içinde inline olarak bulunuyor — doğru kaynaklar bu doğrultuda belgelendi.
- `loki_devices` tablosu sema-prefix'siz (`public.` belirtmeden) sorgulanıyor;
  diğer discovery tabloları `public.` ile niteleniyor. Tutarsızlık kaynak kodda
  olduğu gibi bırakıldı.
</content>
</invoke>
