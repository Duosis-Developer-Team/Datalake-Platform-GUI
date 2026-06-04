# IBM Storage & Brocade SAN Sorguları ve Hesaplamaları

## Genel Bakış

Bu doküman, "Datalake Platform GUI" projesindeki **IBM Storage sistemleri** (IBM
SVC / Storwize / FlashSystem ailesi) ve **Brocade SAN switch'leri** ile ilgili
SQL sorgularını ve bunların üstüne kurulu kapasite/durum hesaplamalarını
açıklar.

İki temel kaynak dosya sorgu tanımlarını barındırır:

- `services/datacenter-api/app/db/queries/ibm_storage.py` — IBM Storage
  kapasite ve performans sorguları.
- `services/datacenter-api/app/db/queries/brocade.py` — Brocade SAN port
  kullanımı, sağlık (health) uyarıları ve trafik trendi sorguları.

Kapasite matematiğini besleyen snapshot verisi `dc_service.py`,
`get_storage_capacity(...)` içindeki **inline** sorgudan (yaklaşık satır 3665)
gelir — `ibm_storage.py` içindeki benzer görünümlü `STORAGE_SYSTEM_CAPACITY_LATEST`
sabiti **ölü koddur ve çağrılmaz** (bkz. Sorgu #1). Kapasite matematiğinin
kendisi (physical vs efficient, hyperswap divisor, utilization %)
`src/utils/ibm_storage_capacity.py` içinde; varchar kapasite stringlerinin
(`'110.00 TB'` gibi) GB'ye çevrilmesi ise `src/utils/format_units.py`
içindeki `parse_storage_string` ile yapılır.

DC (data center) eşlemesi SQL içinde değil, Python tarafında yapılır:

- IBM Storage için: `raw_ibm_storage_system` satırlarındaki `name` / `location`
  metin alanları üzerinden regex ile DC kodu çıkarılır; bulunamazsa IP üzerinden
  NetBox keşif tablosuna fallback yapılır.
- Brocade için: `switch_host` alanı regex ile çözümlenir; çözülemezse yine
  NetBox keşif verisine fallback yapılır. `raw_brocade_san_fcport_1` tablosunda
  `switch_host` bulunmadığı için bottleneck eşlemesi Python tarafında
  `portname` üzerinden yapılır.

Servis katmanı: `services/datacenter-api/app/services/dc_service.py`
(`DatabaseService`).

İlgili dokümanlar: [README](README.md), [07-energy.md](07-energy.md).

---

## Veri Kaynakları

### IBM Storage tabloları

| Tablo | Kullanım |
| --- | --- |
| `public.raw_ibm_storage_system` | Storage sistemi kapasite snapshot'ı (en güncel `timestamp` baz alınır). Kapasiteler **varchar string** (örn. `'110.00 TB'`). Alanlar: `storage_ip`, `name`, `topology`, `physical_capacity`, `physical_free_capacity`, `layer`, `total_mdisk_capacity`, `total_used_capacity`, `total_free_space`, `location`, `timestamp`. |
| `public.raw_ibm_storage_vdisk` | Virtual disk (vdisk) düzeyinde veri. Kapsamda belirtilmiş olmakla birlikte, bu doküman kapsamındaki sorgularda doğrudan kullanılmamaktadır (kaynak `ibm_storage.py` içinde sorgusu yoktur). |
| `public.raw_ibm_storage_system_stats` | Performans zaman serisi. Alanlar: `storage_ip`, `vdisk_io` (IOPS), `vdisk_mb` (throughput MB), `vdisk_ms` (latency ms), `timestamp`. |

### Brocade SAN tabloları

| Tablo | Kullanım |
| --- | --- |
| `public.raw_brocade_port_status` | Port durumu / lisans snapshot'ı (en güncel `collection_timestamp`). Alanlar: `switch_host`, `pod_license_status`, `operational_status`, `is_enabled_state`, `collection_timestamp`. |
| `public.raw_brocade_port_statistics` | Port istatistikleri ve delta sayaçları. Alanlar: `switch_host`, `name`, `crc_errors_delta`, `link_failures_delta`, `loss_of_sync_delta`, `loss_of_signal_delta`, `in_rate`, `out_rate`, `collection_timestamp`. |
| `public.raw_brocade_san_fcport_1` | FC port bottleneck verisi. **`switch_host` içermez**; DC eşlemesi Python'da `portname` üzerinden yapılır. Alanlar: `portname`, `swfcportnotxcredits`, `swfcporttoomanyrdys`, `timestamp`. |

---

## Sorgular

### 1. IBM Storage — Kapasite (DC-scoped, servis içi inline sorgu) — **gerçek kapasite kaynağı**

Yer: `dc_service.py`, `get_storage_capacity(...)` (yaklaşık satır 3665). Bu
sorgu `ibm_storage.py` dosyasında **değil**, servis içinde inline tanımlıdır ve
section 9'daki kapasite matematiğini (`aggregate_ibm_storage_capacities` /
`compute_system_capacities_gb`) **gerçekte besleyen** sorgudur.

> **Ölü sabit (dead constant) uyarısı:** `ibm_storage.py` içinde
> `STORAGE_SYSTEM_CAPACITY_LATEST` (satır 18) adlı, neredeyse aynı görünümlü bir
> sabit tanımlıdır; ancak bu sabit **hiçbir yerden çağrılmaz** — grep ile tüm
> `services/` ve `src/` ağacında yalnızca kendi tanım satırında geçer. Yani
> **kullanılmayan ölü koddur**, yalnızca referans için tutulmaktadır. Live
> kapasite akışı aşağıdaki inline sorguyla yürür. (Aradaki iki fark: inline
> sorgu `WHERE storage_ip = ANY(%s)` filtresi taşımaz — tüm IP'leri çeker, DC
> filtresini Python'da yapar — ve dönüş setine ek olarak `s.location` sütununu
> da içerir.)

```sql
WITH latest AS (
    SELECT storage_ip, MAX("timestamp") AS max_ts
    FROM public.raw_ibm_storage_system
    GROUP BY storage_ip
)
SELECT
    s.storage_ip,
    s.name,
    s.location,
    s.topology,
    s.physical_capacity,
    s.physical_free_capacity,
    s.layer,
    s.total_mdisk_capacity,
    s.total_used_capacity,
    s.total_free_space,
    s."timestamp"
FROM public.raw_ibm_storage_system s
JOIN latest l
  ON s.storage_ip = l.storage_ip
 AND s."timestamp" = l.max_ts;
```

**Ne yapar:** Tüm `storage_ip`'ler için her IP'nin **en güncel**
(`MAX("timestamp")`) kapasite snapshot satırını çeker. DC filtresi parametreyle
değil, dönen her satır için `_resolve_ibm_storage_dc(storage_ip, name, location)`
Python çağrısıyla yapılır; yalnızca hedef DC'ye çözülen sistemler `systems`
listesine eklenir. Bu liste `{"systems": [...], "system_count": N}` olarak döner
ve GUI'de section 9'daki `topology` / `physical_capacity` /
`total_mdisk_capacity` → `compute_system_capacities_gb` matematiğini besler.

**Parametreler:** Yok (inline sorguya parametre geçilmez; DC eşlemesi Python
tarafında). Metot imzası `get_storage_capacity(dc_code, time_range=None)`.

**Dönen sütunlar:** `storage_ip`, `name`, `location`, `topology`,
`physical_capacity`, `physical_free_capacity`, `layer`, `total_mdisk_capacity`,
`total_used_capacity`, `total_free_space`, `timestamp`. (Kapasite alanları
varchar string'tir; GB'ye `parse_storage_string` ile çevrilir.)

Servis çağrısı: `get_storage_capacity(...)` (yaklaşık satır 3644, inline SQL
~3665).

---

### 2. IBM Storage — Performans (günlük ortalama zaman serisi)

Sabit: `STORAGE_SYSTEM_STATS_DAILY_AVG`
(`services/datacenter-api/app/db/queries/ibm_storage.py`)

```sql
SELECT
    DATE_TRUNC('day', "timestamp") AS ts,
    AVG(COALESCE(vdisk_io, 0))::double precision AS avg_iops,
    AVG(COALESCE(vdisk_mb, 0))::double precision AS avg_throughput_mb,
    AVG(COALESCE(vdisk_ms, 0))::double precision AS avg_latency_ms
FROM public.raw_ibm_storage_system_stats
WHERE
    storage_ip = ANY(%s)
  AND "timestamp" BETWEEN %s AND %s
GROUP BY 1
ORDER BY 1;
```

**Ne yapar:** Verilen `storage_ip` listesi ve zaman aralığı için günlük
(`DATE_TRUNC('day', ...)`) ortalama IOPS, throughput (MB) ve latency (ms)
değerlerini döner. Sparkline / trend grafikleri için kullanılır.

**Parametreler:**
- `%s` → `storage_ips: list[str]`
- `%s` → `start_ts` (timestamp)
- `%s` → `end_ts` (timestamp)

**Dönen sütunlar:** `ts` (gün), `avg_iops`, `avg_throughput_mb`,
`avg_latency_ms`. `COALESCE(..., 0)` ile NULL değerler 0 sayılır.

Servis katmanındaki çağrı: `dc_service.py` içinde
`isq.STORAGE_SYSTEM_STATS_DAILY_AVG` (yaklaşık satır 3786).

> **Not — performans öncesi storage_ip çözümleme (inline sorgu):**
> `get_storage_performance(...)` (yaklaşık satır 3736) yukarıdaki günlük-ortalama
> sorgusunu çağırmadan **önce**, hedef DC'ye ait `storage_ip` kümesini bulmak
> için ayrı bir inline sorgu çalıştırır (yaklaşık satır 3756):
>
> ```sql
> WITH latest AS (
>     SELECT storage_ip, MAX("timestamp") AS max_ts
>     FROM public.raw_ibm_storage_system
>     GROUP BY storage_ip
> )
> SELECT
>     s.storage_ip,
>     s.name,
>     s.location
> FROM public.raw_ibm_storage_system s
> JOIN latest l
>   ON s.storage_ip = l.storage_ip
>  AND s."timestamp" = l.max_ts;
> ```
>
> Bu sorgu (parametresiz) her IP'nin en güncel `name`/`location` değerlerini
> çeker; her satır `_resolve_ibm_storage_dc(...)` ile DC'ye çözülür ve yalnızca
> hedef DC'ye uyan `storage_ip`'ler toplanır. Bu IP listesi daha sonra
> `STORAGE_SYSTEM_STATS_DAILY_AVG`'a `ANY(%s)` parametresi olarak verilir.

---

### 3. IBM Storage — DC bazlı tek satır kapasite (servis içi inline sorgu)

Yer: `dc_service.py`, `_get_ibm_storage_single(...)` (yaklaşık satır 1148). Bu
sorgu `ibm_storage.py` dosyasında değil, servis içinde inline tanımlıdır.

```sql
WITH latest AS (
    SELECT storage_ip, MAX("timestamp") AS max_ts
    FROM public.raw_ibm_storage_system
    GROUP BY storage_ip
)
SELECT
    s.total_mdisk_capacity,
    s.total_used_capacity
FROM public.raw_ibm_storage_system s
JOIN latest l ON s.storage_ip = l.storage_ip AND s."timestamp" = l.max_ts
WHERE UPPER(s.name) LIKE UPPER(%s) OR UPPER(s.location) LIKE UPPER(%s)
```

**Ne yapar:** `name` veya `location` alanı verilen pattern'e (`%DC_CODE%`)
uyan storage sistemlerinin en güncel snapshot'ından `total_mdisk_capacity` ve
`total_used_capacity` değerlerini çeker ve TB cinsine toplar.

**Parametreler:**
- `%s` (iki kez) → `pattern: str`, ör. `f"%{dc_code}%"`.

**Dönen sütunlar:** `total_mdisk_capacity`, `total_used_capacity` (varchar
string). Bu metodun döndürdüğü değer `(cap_tb, used_tb)` tuple'ıdır;
çevrim için yerel `parse_capacity` fonksiyonu kullanılır (aşağıda
"Birim Dönüşümleri" bölümünde anlatılıyor).

---

### 4. IBM Storage — Batch DC çıkarımı için ham snapshot (servis içi inline sorgu)

Yer: `dc_service.py` içinde batch fetch bloğu, `"ibm_storage_raw"` anahtarı
(yaklaşık satır 1304). Bu da inline tanımlıdır.

```sql
WITH latest AS (
    SELECT storage_ip, MAX("timestamp") AS max_ts
    FROM public.raw_ibm_storage_system
    GROUP BY storage_ip
)
SELECT
    s.name,
    s.location,
    s.total_mdisk_capacity,
    s.total_used_capacity
FROM public.raw_ibm_storage_system s
JOIN latest l ON s.storage_ip = l.storage_ip AND s."timestamp" = l.max_ts
```

**Ne yapar:** Tüm storage sistemlerinin en güncel snapshot'ını çeker; DC kodu
Python tarafında `name`/`location` üzerinden regex ile çıkarılıp toplama
yapılır (parametre yok).

**Parametreler:** Yok (boş tuple `()`).

**Dönen sütunlar:** `name`, `location`, `total_mdisk_capacity`,
`total_used_capacity`.

---

### 5. Brocade — Port kullanımı (gauge'lar)

Sabit: `PORT_USAGE_LATEST`
(`services/datacenter-api/app/db/queries/brocade.py`)

```sql
WITH latest AS (
    SELECT
        switch_host,
        MAX(collection_timestamp) AS max_ts
    FROM public.raw_brocade_port_status
    WHERE switch_host = ANY(%s)
    GROUP BY switch_host
)
SELECT
    COUNT(*)::bigint AS total_ports,
    COUNT(*) FILTER (WHERE pod_license_status = true) AS licensed_ports,
    COUNT(*) FILTER (WHERE operational_status = 2 AND is_enabled_state = true) AS active_ports,
    COUNT(*) FILTER (WHERE COALESCE(is_enabled_state, false) = true) AS enabled_ports,
    COUNT(*) FILTER (
        WHERE COALESCE(is_enabled_state, false) = true
          AND operational_status != 2
    ) AS no_link_ports,
    COUNT(*) FILTER (WHERE COALESCE(is_enabled_state, false) = false) AS disabled_ports
FROM public.raw_brocade_port_status ps
JOIN latest l
  ON ps.switch_host = l.switch_host
 AND ps.collection_timestamp = l.max_ts;
```

**Ne yapar:** Verilen switch listesindeki her switch'in en güncel
(`MAX(collection_timestamp)`) port durumu satırlarını alıp, toplam / lisanslı /
aktif / etkin / link'siz / devre dışı port sayılarını agregeler.

**Parametreler:**
- `%s` → `switch_hosts: list[str]`.

**Dönen sütunlar:**
- `total_ports` — toplam port sayısı.
- `licensed_ports` — `pod_license_status = true` olanlar (Ports-on-Demand
  lisanslı).
- `active_ports` — `operational_status = 2` **ve** `is_enabled_state = true`
  (operasyonel olarak online sayılan portlar).
- `enabled_ports` — `is_enabled_state = true` olanlar.
- `no_link_ports` — etkin (`is_enabled_state = true`) ama
  `operational_status != 2` (link yok).
- `disabled_ports` — `is_enabled_state = false` olanlar.

Servis çağrısı: `get_san_port_usage(...)` (yaklaşık satır 3495, `brq.PORT_USAGE_LATEST`).

---

### 6. Brocade — SAN sağlık uyarıları (delta tabanlı)

Sabit: `HEALTH_ALERTS_LATEST`
(`services/datacenter-api/app/db/queries/brocade.py`)

```sql
WITH latest AS (
    SELECT
        switch_host,
        MAX(collection_timestamp) AS max_ts
    FROM public.raw_brocade_port_statistics
    WHERE switch_host = ANY(%s)
    GROUP BY switch_host
)
SELECT
    ps.switch_host,
    ps.name AS port_name,
    COALESCE(ps.crc_errors_delta, 0) AS crc_errors_delta,
    COALESCE(ps.link_failures_delta, 0) AS link_failures_delta,
    COALESCE(ps.loss_of_sync_delta, 0) AS loss_of_sync_delta,
    COALESCE(ps.loss_of_signal_delta, 0) AS loss_of_signal_delta
FROM public.raw_brocade_port_statistics ps
JOIN latest l
  ON ps.switch_host = l.switch_host
 AND ps.collection_timestamp = l.max_ts
WHERE
    COALESCE(ps.crc_errors_delta, 0) > 0
 OR COALESCE(ps.link_failures_delta, 0) > 0
 OR COALESCE(ps.loss_of_sync_delta, 0) > 0
 OR COALESCE(ps.loss_of_signal_delta, 0) > 0
ORDER BY
    (COALESCE(ps.crc_errors_delta, 0)
   + COALESCE(ps.link_failures_delta, 0)
   + COALESCE(ps.loss_of_sync_delta, 0)
   + COALESCE(ps.loss_of_signal_delta, 0)) DESC;
```

**Ne yapar:** Her switch'in en güncel istatistik satırlarından, herhangi bir
delta sayacı 0'dan büyük olan portları döner; toplam delta'ya göre azalan
sıralar (en sorunlu port en üstte).

**Parametreler:**
- `%s` → `switch_hosts: list[str]`.

**Dönen sütunlar:** `switch_host`, `port_name`, `crc_errors_delta`,
`link_failures_delta`, `loss_of_sync_delta`, `loss_of_signal_delta`. NULL
delta'lar `COALESCE` ile 0 kabul edilir.

Servis çağrısı: `brq.HEALTH_ALERTS_LATEST` (yaklaşık satır 3574).

---

### 7. Brocade — Trafik trendi (saatlik)

Sabit: `TRAFFIC_TREND_HOURLY`
(`services/datacenter-api/app/db/queries/brocade.py`)

```sql
SELECT
    DATE_TRUNC('hour', collection_timestamp) AS ts,
    SUM(COALESCE(in_rate, 0))::bigint AS total_in_rate,
    SUM(COALESCE(out_rate, 0))::bigint AS total_out_rate
FROM public.raw_brocade_port_statistics
WHERE
    switch_host = ANY(%s)
  AND collection_timestamp BETWEEN %s AND %s
GROUP BY 1
ORDER BY 1;
```

**Ne yapar:** Verilen switch listesi ve zaman aralığı için saatlik
(`DATE_TRUNC('hour', ...)`) toplam in/out rate değerlerini döner.

**Parametreler:**
- `%s` → `switch_hosts: list[str]`
- `%s` → `start_ts` (timestamp)
- `%s` → `end_ts` (timestamp)

**Dönen sütunlar:** `ts` (saat), `total_in_rate`, `total_out_rate`.

Servis çağrısı: `brq.TRAFFIC_TREND_HOURLY` (yaklaşık satır 3626).

---

### 8. Brocade — Zaman aralığındaki switch keşfi

Sabit: `SWITCH_HOSTS_IN_RANGE`
(`services/datacenter-api/app/db/queries/brocade.py`)

```sql
SELECT DISTINCT switch_host
FROM public.raw_brocade_port_status
WHERE collection_timestamp BETWEEN %s AND %s
ORDER BY 1;
```

**Ne yapar:** Belirtilen zaman aralığında port durumu raporlamış benzersiz
`switch_host` değerlerini döner. Sonuçlar Python'da `_resolve_brocade_dc`
ile DC'ye göre filtrelenir.

**Parametreler:**
- `%s` → `start_ts` (timestamp)
- `%s` → `end_ts` (timestamp)

**Dönen sütunlar:** `switch_host`.

Servis çağrısı: `get_san_switches(...)` (yaklaşık satır 3475,
`brq.SWITCH_HOSTS_IN_RANGE`).

---

### 9. Brocade — SAN bottleneck (FC port)

Sabit: `SAN_FCPORT_LATEST`
(`services/datacenter-api/app/db/queries/brocade.py`)

```sql
SELECT
    portname,
    COALESCE(swfcportnotxcredits, 0) AS swfcportnotxcredits,
    COALESCE(swfcporttoomanyrdys, 0) AS swfcporttoomanyrdys,
    "timestamp" AS ts
FROM public.raw_brocade_san_fcport_1
WHERE "timestamp" = (SELECT MAX("timestamp") FROM public.raw_brocade_san_fcport_1)
  AND (
        COALESCE(swfcportnotxcredits, 0) > 0
     OR COALESCE(swfcporttoomanyrdys, 0) > 0
  )
ORDER BY
    swfcportnotxcredits DESC,
    swfcporttoomanyrdys DESC
LIMIT %s;
```

**Ne yapar:** `raw_brocade_san_fcport_1` tablosundaki en güncel timestamp'e ait,
"no Tx credits" veya "too many RDYs" sayacı 0'dan büyük olan portları döner.
Tablo `switch_host` içermediği için DC filtresi Python'da `portname` üzerinden
yapılır.

**Parametreler:**
- `%s` → `limit: int` (servis tarafında `200` ile çağrılır, satır 4561 civarı).

**Dönen sütunlar:** `portname`, `swfcportnotxcredits`,
`swfcporttoomanyrdys`, `ts`.

---

## Hesaplamalar / Formüller

Kaynak: `src/utils/ibm_storage_capacity.py`. GUI tarafında (`src/pages/dc_view.py`)
`aggregate_ibm_storage_capacities` ve `compute_system_capacities_gb`
fonksiyonları `parse_storage_string` callback'i ile çağrılır.

### 9.1 Hyperswap topology divisor

```python
def topology_divisor(topology: str | None) -> float:
    """Return 2 for hyperswap topology, otherwise 1."""
    return 2.0 if (topology or "").strip().lower() == "hyperswap" else 1.0
```

- `topology` alanı (case-insensitive, trim'lenmiş) `"hyperswap"` ise divisor =
  **2.0**, aksi halde **1.0**.
- Mantık: Hyperswap topolojisinde veri iki taraf arasında ayna (mirror)
  tutulduğundan, fiziksel kapasite sayımında 2'ye bölünür (sellable/etkin
  kapasite çift sayılmasın diye).

### 9.2 Sistem başına kapasite (GB) — `compute_system_capacities_gb`

`div = topology_divisor(system["topology"])` ve `parse_gb = parse_storage_string`
olmak üzere:

**Physical (divisor uygulanır):**

```
phys_total = parse_gb(physical_capacity)      / div
phys_free  = parse_gb(physical_free_capacity) / div
phys_used  = max(0.0, phys_total - phys_free)
```

**Efficient (divisor uygulanmaz; mdisk totallerinden physical raw düşülür):**

```
phys_cap_raw  = parse_gb(physical_capacity)        # bölünmemiş ham değer
phys_free_raw = parse_gb(physical_free_capacity)   # bölünmemiş ham değer
mdisk_total   = parse_gb(total_mdisk_capacity)
mdisk_free    = parse_gb(total_free_space)

eff_total = max(0.0, mdisk_total - phys_cap_raw)
eff_free  = max(0.0, mdisk_free  - phys_free_raw)
eff_used  = max(0.0, eff_total   - eff_free)
```

Dönen sözlük: `phys_total_gb`, `phys_free_gb`, `phys_used_gb`, `eff_total_gb`,
`eff_free_gb`, `eff_used_gb` (hepsi GB).

> Not: Physical değerler hyperswap'ta `div`'e bölünürken, efficient değerler
> **bölünmemiş** ham (`*_raw`) physical değerleri üzerinden hesaplanır. Bu
> kasıtlı bir tasarımdır — efficient kapasite mdisk havuzu ile fiziksel
> tahsis farkını gösterdiğinden divisor uygulanmaz.

### 9.3 Sistemler arası agregasyon — `aggregate_ibm_storage_capacities`

Her sistem için `compute_system_capacities_gb` çağrılır ve şu dört değer
toplanır:

```
phys_total_gb += caps["phys_total_gb"]
phys_free_gb  += caps["phys_free_gb"]
eff_total_gb  += caps["eff_total_gb"]
eff_free_gb   += caps["eff_free_gb"]
```

Toplamlardan türetilenler:

```
phys_used_gb = max(0.0, phys_total_gb - phys_free_gb)
eff_used_gb  = max(0.0, eff_total_gb  - eff_free_gb)

utilization_pct = (phys_used_gb / phys_total_gb * 100.0) if phys_total_gb > 0 else 0.0
```

Dönen sözlük: `phys_total_gb`, `phys_used_gb`, `phys_free_gb`, `eff_total_gb`,
`eff_used_gb`, `eff_free_gb`, `utilization_pct`.

> Önemli ayrıntı: `phys_used` / `eff_used`, sistem düzeyinde de toplam düzeyinde
> de **total − free** formülüyle yeniden hesaplanır (sistem başına `used`
> değerleri ayrıca toplanmaz). `utilization_pct` yalnızca **physical** kapasite
> üzerinden hesaplanır.

### 9.4 GUI tarafındaki sade toplam (dc_view.py)

`src/pages/dc_view.py` (yaklaşık satır 785) ayrıca divisor uygulamayan basit
bir toplam da hesaplar (storage özet kartı için):

```python
total_gb = sum(parse_storage_string(s.get("total_mdisk_capacity")) for s in storage_systems)
used_gb  = sum(parse_storage_string(s.get("total_used_capacity"))  for s in storage_systems)
free_gb  = sum(parse_storage_string(s.get("total_free_space"))     for s in storage_systems)
```

---

## Birim Dönüşümleri

### varchar string → GB: `parse_storage_string`

Kaynak: `src/utils/format_units.py` (yaklaşık satır 94). `'110.00 TB'` gibi
stringleri **GB cinsinden float**'a çevirir.

```python
def parse_storage_string(value: str | None) -> float:
    import re
    if value is None:
        return 0.0
    s = str(value)
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(PB|TB|GB|MB)\b", s, flags=re.IGNORECASE)
    if not m:
        return 0.0
    num = float(m.group(1))
    unit = m.group(2).upper()
    factors_to_gb = {
        "PB": 1024 * 1024,
        "TB": 1024,
        "GB": 1,
        "MB": 1 / 1024,
    }
    return num * factors_to_gb.get(unit, 0.0)
```

- Regex `(-?\d+(?:\.\d+)?)\s*(PB|TB|GB|MB)\b` ile sayı + birim yakalanır
  (case-insensitive).
- Eşleşme yoksa veya `value is None` ise **0.0** döner.
- Tüm tier'lar **1024 tabanlıdır** (PB = 1024², TB = 1024, GB = 1, MB = 1/1024).
- `'110.00 TB'` → `110.00 * 1024 = 112640.0` GB.

### GB → en uygun birim: `smart_storage`

Görüntüleme için GB değerini human-readable string'e çevirir
(`format_units.py`, satır 17):

```python
def smart_storage(gb: float) -> str:
    if gb is None:
        return "0.00 GB"
    gb = float(gb)
    if gb >= 1024:
        return f"{gb / 1024:.2f} TB"
    if gb >= 1:
        return f"{gb:.2f} GB"
    return f"{gb * 1024:.2f} MB"
```

- `>= 1024 GB` → TB, `>= 1 GB` → GB, aksi halde MB. Tabanı 1024.

### Servis içi alternatif parser (TB cinsinden): `parse_capacity` / `_parse_capacity`

`dc_service.py` (satır 1164) içindeki yerel fonksiyon, `parse_storage_string`'den
**farklı** olarak değeri **TB** cinsinden döner ve birim tespitini substring
kontrolü ile yapar:

```python
def parse_capacity(val: str) -> float:
    if not val:
        return 0.0
    val = str(val).upper().strip()
    try:
        num = float(''.join(c for c in val if c.isdigit() or c == '.'))
        if 'GB' in val:
            return num / 1024.0
        if 'MB' in val:
            return num / (1024.0**2)
        if 'PB' in val:
            return num * 1024.0
        return num   # TB veya birimsiz → olduğu gibi (TB kabul edilir)
    except Exception:
        return 0.0
```

> Dikkat: Bu fonksiyon sayıyı ham karakter ayıklama (`isdigit() or '.'`) ile
> alır; birim belirsiz/eksikse değeri TB kabul eder. `parse_storage_string`
> ise regex tabanlıdır ve GB döner. İki parser ayrı amaçlara hizmet eder
> (servis-içi DC toplamı TB, GUI kapasite matematiği GB).
>
> **Kopyalanmış parser uyarısı:** Bu TB-parser'ı `dc_service.py` içinde **iki kez**
> birebir aynı gövdeyle kopyalanmıştır:
> - `parse_capacity` — `_get_ibm_storage_single(...)` içinde (satır **1164**),
>   tek-DC kapasite toplamı için.
> - `_parse_capacity` — `_fetch_all_batch(...)` içinde (satır **1444**),
>   batch `ibm_storage_raw` satırlarını DC bazında TB'ye toplamak için.
>
> İki kopya da aynı substring-tabanlı (GB→`/1024`, MB→`/1024²`, PB→`*1024`,
> birimsiz→TB) mantığı kullanır; biri değişirse diğeri de elle güncellenmelidir.

---

## Caching

Sorgu sonuçları `services/datacenter-api/app/services/cache_service.py` (ve
altındaki `app/core/cache_backend.py`) üzerinden TTL-cache ile saklanır.

- Backend: in-memory `cachetools.TTLCache` (`maxsize=cache_max_memory_items`,
  `ttl=cache_ttl_seconds`); Redis varsa onun üzerinden `setex` ile.
- Varsayılan TTL: `cache_ttl_seconds = 1200` saniye (**20 dakika**),
  `cache_max_memory_items = 200` (`services/datacenter-api/app/config.py`).
- `dc_service.py` başlığındaki nota göre: modül düzeyinde 20 dakikalık TTL cache,
  bozuk `lru_cache` davranışını düzeltmek için kullanılır; `warm_cache()`
  açılışta veriyi önceden yükler, `refresh_all_data()` scheduler tarafından
  her ~15 dakikada bir cache'i tazeler.
- IBM/Brocade ilgili cache anahtarları (DC ve zaman aralığı bazlı):
  - `dc_details:{dc_code}:{start}:{end}` — DC tam metrik seti
    (IBM storage tek-satır kapasitesi dahil). `run_singleflight` ile aynı anahtar
    için eşzamanlı tek sorgu garantilenir.
  - `dc_san_switches:{dc}:{start}:{end}` — DC'ye çözülmüş switch listesi.
  - `dc_san_port_usage:{dc}:{start}:{end}` — port kullanım gauge'ları.
- DC çözümleme cache'leri (in-process dict): `_brocade_switch_dc_cache`
  (`switch_host` → DC) ve `_ibm_storage_ip_dc_cache` (`storage_ip` → DC).
- `set_with_stale` / `get_with_stale`: fresh TTL + 24 saatlik (`86400 s`)
  stale fallback katmanı sunar (kaynak veritabanı yanıt vermediğinde eski
  veriyle hizmet vermek için).

---

## Özet

- **IBM Storage:** Live kapasite akışı `dc_service.py`,
  `get_storage_capacity(...)` içindeki **inline** sorguyla (yaklaşık satır 3665)
  yürür; bu sorgu `raw_ibm_storage_system`'ten storage_ip başına en güncel
  snapshot'ı çekip section 9 kapasite matematiğini besler. `ibm_storage.py`
  içindeki `STORAGE_SYSTEM_CAPACITY_LATEST` sabiti ise **ölü koddur** — hiçbir
  yerden çağrılmaz, yalnızca referans için tutulur. Performans verisi
  `STORAGE_SYSTEM_STATS_DAILY_AVG` (`ibm_storage.py`) ile
  `raw_ibm_storage_system_stats`'ten (günlük IOPS/throughput/latency) gelir;
  `get_storage_performance(...)` bundan önce DC'ye ait `storage_ip` kümesini
  çözmek için ayrı bir inline sorgu (yaklaşık satır 3756) çalıştırır. Ayrıca
  `dc_service.py` içinde DC-bazlı iki inline sorgu daha (`_get_ibm_storage_single`
  ve batch `ibm_storage_raw`) vardır. Kapasiteler varchar string olarak tutulur;
  `parse_storage_string` (GB, 1024-tabanlı, regex) veya servis-içi
  `parse_capacity` / `_parse_capacity` (TB; satır 1164 ve 1444'te iki kopya) ile
  çevrilir.
- **Brocade SAN:** `PORT_USAGE_LATEST` (port gauge'ları), `HEALTH_ALERTS_LATEST`
  (delta tabanlı sağlık uyarıları), `TRAFFIC_TREND_HOURLY` (saatlik in/out),
  `SWITCH_HOSTS_IN_RANGE` (switch keşfi) ve `SAN_FCPORT_LATEST` (FC bottleneck)
  sorguları `raw_brocade_port_status`, `raw_brocade_port_statistics` ve
  `raw_brocade_san_fcport_1` tablolarını kullanır. DC eşlemesi Python'da yapılır.
- **Kapasite matematiği** (`ibm_storage_capacity.py`): hyperswap için divisor=2;
  physical değerler divisor'a bölünür, efficient değerler bölünmemiş physical
  raw'dan mdisk totalleri üzerinden türetilir; `utilization_pct` yalnızca
  physical üzerinden `phys_used / phys_total * 100`.
- **Caching:** 20 dk (1200 s) varsayılan TTL; `warm_cache` / `refresh_all_data`
  (~15 dk) ile sıcak tutulur; `run_singleflight` ve 24 saatlik stale fallback.

İlgili: [README](README.md), [07-energy.md](07-energy.md).
