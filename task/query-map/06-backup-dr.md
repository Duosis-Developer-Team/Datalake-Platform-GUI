# Backup & DR Sorguları ve Hesaplamaları (NetBackup, Veeam, Zerto, S3 iCOS)

> Bu dosya, yedekleme ve felaket kurtarma (DR) verilerinin nereden geldiğini,
> hangi SQL ile çekildiğini ve service katmanında nasıl işlendiğini belgeler.
> Ortak desenler ("latest snapshot", DC eşleştirme, cache katmanları) için bkz.
> [README](README.md).

İçerdiği ürünler:
- **NetBackup** — disk havuzları + job istatistikleri (`raw_netbackup_*`).
- **Veeam** — repository state'leri + session (job) istatistikleri (`raw_veeam_*`).
- **Zerto** — site metrikleri + VPG (Virtual Protection Group) job/DR istatistikleri (`raw_zerto_*`).
- **S3 iCOS** (IBM Cloud Object Storage) — pool ve vault kapasite metrikleri (`raw_s3icos_*`).

Kaynak dosyalar:
- `services/datacenter-api/app/db/queries/backup.py` — NetBackup/Veeam/Zerto SQL'leri.
- `services/datacenter-api/app/db/queries/customer.py` — customer_view backup özetleri.
- `services/datacenter-api/app/db/queries/s3.py` — S3 iCOS pool/vault SQL'leri.
- `services/datacenter-api/app/services/dc_service.py` — job istatistik hesabı + warm-window cache.
- `services/datacenter-api/app/utils/time_range.py` — warm-window zaman aralıkları.

---

## Genel Bakış

İki farklı ekran ailesi bu verileri kullanır:

### 1. `customer_view` (müşteri perspektifi)
Bir müşterinin backup/DR durumunun özeti. `dc_service.py` içindeki
müşteri-backup bloğu (≈ satır 2256–2479) şu kartları üretir:
- **Veeam:** tanımlı session sayısı, session tipi dağılımı, platform dağılımı.
- **NetBackup:** pre-dedup / post-dedup boyut (GiB) ve deduplication faktörü (billing için).
- **Zerto:** korunan toplam VM sayısı (`vmscount`) ve VPG başına provisioned storage (GiB).

Filtreleme `name`/`vault_name` üzerinden `ILIKE '%<müşteri>%'` ile yapılır.

### 2. `dc_view` (datacenter perspektifi)
Bir DC'nin backup/DR altyapısı. İki tür çıktı:
- **Kapasite/durum snapshot'ları:** NetBackup disk pool'ları, Zerto site'ları, Veeam
  repository state'leri (`get_dc_netbackup_pools`, `get_dc_zerto_sites`, `get_dc_veeam_repos`).
- **Job istatistikleri (Phase 1, bar chart):** Veeam/Zerto/NetBackup için zaman serisinde
  başarı/başarısızlık dağılımı (`get_dc_veeam_jobs`, `get_dc_zerto_jobs`,
  `get_dc_netbackup_jobs`). Bu üçü **warm-window per-backup cache** kullanır (aşağıda).

> **DC attribution:** backup tabloları doğrudan DC kolonu içermez. DC, host adı /
> media server adı / site adı gibi serbest-metin alanlarından `_extract_dc_from_text`
> ile regex `(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)` kullanılarak çıkarılır; çıkan kod yalnızca
> `dc_list` içinde varsa kabul edilir. Veeam'de jobs tablosunda DC etiketi yoktur, bu yüzden
> `source_ip → DC` haritası ayrı bir seed sorgusuyla kurulur (bkz. `VEEAM_IP_TO_DC_SEED`).

---

## Veri Kaynakları

### NetBackup
| Tablo | Kullanım | Önemli kolonlar |
|---|---|---|
| `public.raw_netbackup_disk_pools_metrics` | DC disk havuzu kapasitesi | `collection_timestamp`, `netbackup_host`, `name`, `stype`, `storagecategory`, `diskvolumes_name`, `diskvolumes_state`, `usablesizebytes`, `availablespacebytes`, `usedcapacitybytes` |
| `public.raw_netbackup_jobs_metrics` | Job sayıları/boyut/dedup/başarı | `starttime`, `collection_timestamp`, `destinationmediaservername`, `status` (int exit code), `jobtype`, `policytype`, `kilobytestransferred`, `dedupratio`, `workloaddisplayname`, `percentcomplete` |

### Veeam
| Tablo | Kullanım | Önemli kolonlar |
|---|---|---|
| `public.raw_veeam_sessions` | Session (job) istatistikleri | `creation_time`, `source_ip`, `result_result` (Success/Failed/Warning/'' ), `session_type`, `name`, `platform_name` |
| `public.raw_veeam_repositories_states` | Repository state + IP→DC seed | `collection_time`, `id`, `name`, `host_name` (DC kodu taşır), `type`, `capacity_gb`, `free_gb`, `used_space_gb`, `is_online`, `source_ip` |

### Zerto
| Tablo | Kullanım | Önemli kolonlar |
|---|---|---|
| `public.raw_zerto_site_metrics` | DC site metrikleri | `collection_timestamp`, `zerto_host`, `name`, `site_type`, `is_connected`, `incoming_throughput_mb`, `outgoing_bandwidth_mb`, `provisioned_storage_mb`, `used_storage_mb` |
| `public.raw_zerto_vpg_metrics` | VPG (DR) job istatistikleri + müşteri özeti | `collection_timestamp`, `source_site` (DC etiketi taşır), `status` (int enum), `name`, `vmscount`, `provisioned_storage_mb`, `id` |

### S3 iCOS (IBM Cloud Object Storage)
| Tablo | Kullanım | Önemli kolonlar |
|---|---|---|
| `public.raw_s3icos_pool_metrics` | DC perspektifi (pool kapasite) | `pool_name`, `collection_timestamp`, `total_capacity_bytes`, `used_capacity_bytes` |
| `public.raw_s3icos_vault_metrics` | Müşteri perspektifi (vault kullanım) | `vault_id`, `vault_name`, `collection_timestamp`, `estimate_usable_used_logical_size_bytes` |
| `public.raw_s3icos_vault_inventory` | Vault kotası | `vault_id`, `collection_timestamp`, `hard_quota_bytes` |

> Raporlama kuralı (s3.py docstring): **DC perspektifi** pool'ları `pool_name ILIKE '%DC13%'`
> ile, **müşteri perspektifi** vault'ları `vault_name ILIKE '%Boyner%'` ile filtreler.

---

## Sorgular

### NetBackup — disk pool snapshot (`NETBACKUP_DISK_POOLS_LATEST`)

```sql
SELECT DISTINCT ON (id)
    collection_timestamp,
    netbackup_host,
    name,
    stype,
    storagecategory,
    diskvolumes_name,
    diskvolumes_state,
    usablesizebytes,
    availablespacebytes,
    usedcapacitybytes
FROM public.raw_netbackup_disk_pools_metrics
WHERE collection_timestamp BETWEEN %s AND %s
ORDER BY id, collection_timestamp DESC
```

**Ne yapar:** Zaman aralığında her pool `id`'si için en güncel satırı (`DISTINCT ON (id)`
+ `ORDER BY id, collection_timestamp DESC`) döndürür. DC filtresi SQL'de yoktur; uygulama
katmanında `netbackup_host` adından DC çıkarılarak yapılır (`_fetch_dc_netbackup_pools`).
**Parametreler:** `(start_ts, end_ts)`.
**Dönen sütunlar:** yukarıdaki 10 kolon (timestamp, host, pool adı/tipi, disk volume durumu,
usable/available/used byte).

### Zerto — site snapshot (`ZERTO_SITES_LATEST`)

```sql
SELECT DISTINCT ON (id)
    collection_timestamp,
    zerto_host,
    name,
    site_type,
    is_connected,
    incoming_throughput_mb,
    outgoing_bandwidth_mb,
    provisioned_storage_mb,
    used_storage_mb
FROM public.raw_zerto_site_metrics
WHERE collection_timestamp BETWEEN %s AND %s
ORDER BY id, collection_timestamp DESC
```

**Ne yapar:** Her Zerto site `id`'si için en güncel satır. DC, `zerto_host`/`name`'den
çıkarılır (`_fetch_dc_zerto_sites`).
**Parametreler:** `(start_ts, end_ts)`.
**Dönen sütunlar:** timestamp, host, site adı/tipi, bağlantı durumu, gelen/giden throughput
(MB), provisioned/used storage (MB).

### Veeam — repository state snapshot (`VEEAM_REPOSITORIES_LATEST`)

```sql
SELECT DISTINCT ON (id)
    collection_time,
    id,
    name,
    host_name,
    type,
    capacity_gb,
    free_gb,
    used_space_gb,
    is_online
FROM public.raw_veeam_repositories_states
WHERE collection_time BETWEEN %s AND %s
ORDER BY id, collection_time DESC
```

**Ne yapar:** Her repository `id`'si için en güncel state. DC, `host_name`'den çıkarılır.
**Parametreler:** `(start_ts, end_ts)`.
**Dönen sütunlar:** collection_time, id, repo adı, host adı, tip, kapasite/boş/kullanılan GB,
online durumu.

---

### Job istatistik sorguları (Phase 1, bar chart agregasyonu)

> Tasarım notu (backup.py): SQL `(date_trunc(granularity, ts), source_ip/dc_label, status,
> type)` bazında **önceden aggregate** eder; sonuç kümesi küçüktür (~10 IP × N periyot ×
> 5 status × 5 tip). DC filtreleme uygulama katmanında yapılır. `granularity` service
> katmanında `{'day','week','month'}` ile sınırlandırılıp `%s` ile geçirilir (psycopg2 escape).

#### Veeam session job istatistikleri (`VEEAM_SESSION_JOB_STATS`)

```sql
SELECT
    date_trunc(%s, creation_time) AS period,
    source_ip,
    COALESCE(NULLIF(result_result, ''), 'None') AS result,
    COALESCE(NULLIF(session_type, ''), 'Unknown') AS session_type,
    COUNT(*) AS cnt
FROM public.raw_veeam_sessions
WHERE creation_time BETWEEN %s AND %s
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4
```

**Ne yapar:** Periyot × source_ip × sonuç × session tipi bazında çalıştırma sayar. Boş
`result_result` → `'None'`, boş `session_type` → `'Unknown'`.
**Parametreler:** `(granularity, start_ts, end_ts)`.
**Dönen sütunlar:** `period`, `source_ip`, `result`, `session_type`, `cnt`.

#### Veeam IP → DC seed (`VEEAM_IP_TO_DC_SEED`)

```sql
SELECT DISTINCT source_ip, host_name
FROM public.raw_veeam_repositories_states
WHERE collection_time BETWEEN %s AND %s
  AND host_name IS NOT NULL
```

**Ne yapar:** `(source_ip, host_name)` çiftleri çeker; `host_name` DC kodunu içerir
(ör. `'Dc13-VeemConsule.blt.vc'`). Veeam jobs tablosunda yalnızca IP olduğundan, bu seed ile
`source_ip → DC` haritası kurulur.
**Parametreler:** `(start_ts, end_ts)`.
**Dönen sütunlar:** `source_ip`, `host_name`.

#### Zerto VPG job istatistikleri (`ZERTO_VPG_JOB_STATS`)

```sql
SELECT
    date_trunc(%s, collection_timestamp) AS period,
    source_site,
    status,
    COUNT(*) AS cnt
FROM public.raw_zerto_vpg_metrics
WHERE collection_timestamp BETWEEN %s AND %s
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
```

**Ne yapar:** Periyot × source_site × status (integer enum) bazında VPG kaydı sayar.
`source_site` zaten DC-taşıyan etiketler içerir (ör. `'DC14-Site02-V10'`, `'TurksatDC_ZVM'`),
bu yüzden ayrı seed sorgusu gerekmez.
**Parametreler:** `(granularity, start_ts, end_ts)`.
**Dönen sütunlar:** `period`, `source_site`, `status`, `cnt`.

> `status` Zerto enum'udur: `1 = MeetingSLA`, diğerleri problemli/ara durum (normalize için
> aşağıdaki Hesaplamalar bölümüne bakın).

#### NetBackup job istatistikleri (`NETBACKUP_JOB_STATS`)

```sql
SELECT
    date_trunc(%s, starttime) AS period,
    destinationmediaservername AS dc_label,
    status,
    COALESCE(NULLIF(jobtype, ''), 'Unknown') AS jobtype,
    COALESCE(NULLIF(policytype, ''), 'Unknown') AS policytype,
    COUNT(*) AS cnt
FROM public.raw_netbackup_jobs_metrics
WHERE starttime BETWEEN %s AND %s
  AND destinationmediaservername IS NOT NULL
GROUP BY 1, 2, 3, 4, 5
ORDER BY 1, 2, 3, 4, 5
```

**Ne yapar:** Periyot × media server × status × jobtype × policytype bazında job sayar.
`destinationmediaservername` (ör. `'nbmediadc14.blt.vc'`) DC kodunu taşıdığı için ayrı seed
gerekmez.
**Parametreler:** `(granularity, start_ts, end_ts)`.
**Dönen sütunlar:** `period`, `dc_label`, `status`, `jobtype`, `policytype`, `cnt`.

> `status` NetBackup exit code'udur: `0 = success`, `1 = warning (partial)`, diğeri `failed`.

---

### customer_view backup özet sorguları (`customer.py`)

#### Veeam tanımlı session sayısı (`CUSTOMER_VEEAM_DEFINED_SESSIONS`)

```sql
SELECT
    COUNT(DISTINCT name) AS "Defined Sessions"
FROM public.raw_veeam_sessions
WHERE name ILIKE %s
```
**Ne yapar:** Müşterinin tanımlı (distinct `name`) Veeam session sayısı.
**Parametreler:** `(name_pattern,)`. **Dönen sütun:** `Defined Sessions`.

#### Veeam session tipi dağılımı (`CUSTOMER_VEEAM_SESSION_TYPES`)

```sql
SELECT
    session_type AS "Session Type",
    COUNT(DISTINCT name) AS "Defined Session Count"
FROM public.raw_veeam_sessions
WHERE name ILIKE %s
GROUP BY session_type
ORDER BY "Defined Session Count" DESC
```
**Parametreler:** `(name_pattern,)`. **Dönen sütunlar:** `Session Type`, `Defined Session Count`.

#### Veeam platform dağılımı (`CUSTOMER_VEEAM_SESSION_PLATFORMS`)

```sql
SELECT
    platform_name AS "Platform",
    COUNT(DISTINCT name) AS "Defined Session Count"
FROM public.raw_veeam_sessions
WHERE name ILIKE %s
GROUP BY platform_name
ORDER BY "Defined Session Count" DESC
```
**Parametreler:** `(name_pattern,)`. **Dönen sütunlar:** `Platform`, `Defined Session Count`.

#### Zerto korunan toplam VM (`CUSTOMER_ZERTO_PROTECTED_VMS`)

```sql
WITH ranked_records AS (
    SELECT
        vmscount,
        ROW_NUMBER() OVER(PARTITION BY id ORDER BY collection_timestamp DESC) AS rn
    FROM public.raw_zerto_vpg_metrics
    WHERE collection_timestamp BETWEEN %s AND %s
      AND name LIKE %s
)
SELECT
    COALESCE(SUM(vmscount), 0) AS "Protected Total VMs"
FROM ranked_records
WHERE rn = 1
```
**Ne yapar:** Her VPG `id` için en güncel kayıt (`rn = 1`) seçilip `vmscount` toplanır —
"önce latest snapshot, sonra SUM" deseni.
**Parametreler:** `(start_ts, end_ts, name_like_pattern)`. **Dönen sütun:** `Protected Total VMs`.

#### NetBackup boyut + dedup özeti (`CUSTOMER_NETBACKUP_BACKUP_SUMMARY`)

```sql
WITH filtered AS (
    SELECT
        kilobytestransferred,
        dedupratio
    FROM public.raw_netbackup_jobs_metrics
    WHERE workloaddisplayname ILIKE %s
      AND jobtype = 'BACKUP'
      AND percentcomplete = 100
      AND collection_timestamp BETWEEN %s AND %s
)
SELECT
    COALESCE(CAST(SUM(kilobytestransferred) / 1024.0 / 1024.0 / 1024.0 AS NUMERIC(20, 2)), 0) AS "Pre Dedup Size (GiB)",
    COALESCE(
        CAST(SUM(kilobytestransferred / NULLIF(dedupratio, 0)) / 1024.0 / 1024.0 / 1024.0 AS NUMERIC(20, 2)),
        0
    ) AS "Post Dedup Size (GiB)",
    COALESCE(CAST(AVG(NULLIF(dedupratio, 0)) AS NUMERIC(20, 2)), 1) || 'x' AS "Deduplication Factor"
FROM filtered
```
**Ne yapar:** Tamamlanmış (`percentcomplete = 100`) BACKUP job'larında transfer edilen KB'yi
GiB'e çevirir; pre-dedup ve `dedupratio`'ya bölünmüş post-dedup boyutu, ve ortalama dedup
faktörünü (`...x` formatında) hesaplar. Billing için kullanılır.
**Parametreler:** `(workload_pattern, start_ts, end_ts)`.
**Dönen sütunlar:** `Pre Dedup Size (GiB)`, `Post Dedup Size (GiB)`, `Deduplication Factor`.

#### Zerto VPG provisioned storage (`CUSTOMER_ZERTO_PROVISIONED_STORAGE`)

```sql
WITH latest AS (
    SELECT DISTINCT ON (name)
        name,
        provisioned_storage_mb
    FROM public.raw_zerto_vpg_metrics
    WHERE name ILIKE %s
      AND collection_timestamp >= NOW() - INTERVAL '30 days'
    ORDER BY name, provisioned_storage_mb DESC
)
SELECT
    name,
    COALESCE(provisioned_storage_mb / 1024.0, 0) AS "Provisioned Storage (GiB)"
FROM latest
ORDER BY name
```
**Ne yapar:** Son 30 günde her VPG (`name`) için en yüksek `provisioned_storage_mb` değerini
alıp GiB'e çevirir (MB / 1024).
**Parametreler:** `(name_like_pattern,)`. **Dönen sütunlar:** `name`, `Provisioned Storage (GiB)`.

---

### S3 iCOS sorguları (`s3.py`)

#### Pool listesi (`POOL_LIST`)

```sql
SELECT DISTINCT pool_name
FROM public.raw_s3icos_pool_metrics
WHERE pool_name ILIKE %s
  AND collection_timestamp BETWEEN %s AND %s
ORDER BY pool_name
```
**Ne yapar:** Bir DC'ye ait distinct pool adlarını listeler.
**Parametreler:** `(pool_name_pattern, start_ts, end_ts)`. **Dönen sütun:** `pool_name`.

#### Pool en güncel kapasite (`POOL_LATEST`)

```sql
WITH per_timestamp AS (
    SELECT
        pool_name,
        collection_timestamp,
        SUM(total_capacity_bytes) AS total_usable,
        SUM(used_capacity_bytes)  AS total_used
    FROM public.raw_s3icos_pool_metrics
    WHERE pool_name = ANY(%s)
      AND collection_timestamp BETWEEN %s AND %s
    GROUP BY pool_name, collection_timestamp
),
ranked AS (
    SELECT
        per_timestamp.*,
        ROW_NUMBER() OVER (PARTITION BY pool_name ORDER BY collection_timestamp DESC) AS rn
    FROM per_timestamp
)
SELECT pool_name, total_usable, total_used, collection_timestamp
FROM ranked
WHERE rn = 1
```
**Ne yapar:** Her pool için önce timestamp bazında usable/used byte toplar, sonra en güncel
timestamp'i (`rn = 1`) seçer.
**Parametreler:** `(pool_names[], start_ts, end_ts)`.
**Dönen sütunlar:** `pool_name`, `total_usable`, `total_used`, `collection_timestamp`.

#### Pool ilk/son (büyüme) (`POOL_FIRST_LAST`)

```sql
WITH per_timestamp AS (
    SELECT
        pool_name,
        collection_timestamp,
        SUM(total_capacity_bytes) AS total_usable,
        SUM(used_capacity_bytes)  AS total_used
    FROM public.raw_s3icos_pool_metrics
    WHERE pool_name = ANY(%s)
      AND collection_timestamp BETWEEN %s AND %s
    GROUP BY pool_name, collection_timestamp
),
ranked AS (
    SELECT
        per_timestamp.*,
        ROW_NUMBER() OVER (PARTITION BY pool_name ORDER BY collection_timestamp ASC)  AS rn_first,
        ROW_NUMBER() OVER (PARTITION BY pool_name ORDER BY collection_timestamp DESC) AS rn_last
    FROM per_timestamp
)
SELECT
    pool_name,
    MAX(CASE WHEN rn_first = 1 THEN total_used  END) AS first_used,
    MAX(CASE WHEN rn_last  = 1 THEN total_used  END) AS last_used,
    MAX(CASE WHEN rn_first = 1 THEN collection_timestamp END) AS first_ts,
    MAX(CASE WHEN rn_last  = 1 THEN collection_timestamp END) AS last_ts
FROM ranked
GROUP BY pool_name
```
**Ne yapar:** Aralığın ilk (`rn_first = 1`) ve son (`rn_last = 1`) kullanım değerini ve
timestamp'lerini çıkarır — büyüme (delta) hesabı için.
**Parametreler:** `(pool_names[], start_ts, end_ts)`.
**Dönen sütunlar:** `pool_name`, `first_used`, `last_used`, `first_ts`, `last_ts`.

#### Vault listesi (`VAULT_LIST`)

```sql
SELECT DISTINCT vault_name
FROM public.raw_s3icos_vault_metrics
WHERE vault_name ILIKE %s
  AND collection_timestamp BETWEEN %s AND %s
ORDER BY vault_name
```
**Parametreler:** `(vault_name_pattern, start_ts, end_ts)`. **Dönen sütun:** `vault_name`.

#### Vault en güncel kullanım + kota (`VAULT_LATEST`)

```sql
WITH latest_metrics AS (
    SELECT
        vault_id,
        vault_name,
        collection_timestamp,
        estimate_usable_used_logical_size_bytes AS used_logical_bytes
    FROM public.raw_s3icos_vault_metrics
    WHERE vault_name = ANY(%s)
      AND collection_timestamp BETWEEN %s AND %s
),
ranked AS (
    SELECT
        latest_metrics.*,
        ROW_NUMBER() OVER (PARTITION BY vault_id ORDER BY collection_timestamp DESC) AS rn
    FROM latest_metrics
),
latest_snapshot AS (
    SELECT *
    FROM ranked
    WHERE rn = 1
)
SELECT
    ls.vault_id,
    ls.vault_name,
    vi.hard_quota_bytes,
    ls.used_logical_bytes,
    ls.collection_timestamp
FROM latest_snapshot ls
LEFT JOIN LATERAL (
    SELECT hard_quota_bytes
    FROM public.raw_s3icos_vault_inventory
    WHERE vault_id = ls.vault_id
      AND collection_timestamp <= ls.collection_timestamp
    ORDER BY collection_timestamp DESC
    LIMIT 1
) AS vi ON TRUE
```
**Ne yapar:** Her `vault_id` için en güncel kullanım (`estimate_usable_used_logical_size_bytes`)
satırını seçer; `LATERAL` join ile o ana en yakın (`<= ls.collection_timestamp`) kota
(`hard_quota_bytes`) değerini `raw_s3icos_vault_inventory`'den getirir.
**Parametreler:** `(vault_names[], start_ts, end_ts)`.
**Dönen sütunlar:** `vault_id`, `vault_name`, `hard_quota_bytes`, `used_logical_bytes`,
`collection_timestamp`.

#### Vault ilk/son (büyüme) + kota (`VAULT_FIRST_LAST`)

```sql
WITH per_timestamp AS (
    SELECT
        vault_id,
        vault_name,
        collection_timestamp,
        SUM(estimate_usable_used_logical_size_bytes) AS used_logical_bytes
    FROM public.raw_s3icos_vault_metrics
    WHERE vault_name = ANY(%s)
      AND collection_timestamp BETWEEN %s AND %s
    GROUP BY vault_id, vault_name, collection_timestamp
),
ranked AS (
    SELECT
        per_timestamp.*,
        ROW_NUMBER() OVER (PARTITION BY vault_id ORDER BY collection_timestamp ASC)  AS rn_first,
        ROW_NUMBER() OVER (PARTITION BY vault_id ORDER BY collection_timestamp DESC) AS rn_last
    FROM per_timestamp
),
first_last AS (
    SELECT
        vault_id,
        vault_name,
        MAX(CASE WHEN rn_first = 1 THEN used_logical_bytes END) AS first_used,
        MAX(CASE WHEN rn_last  = 1 THEN used_logical_bytes END) AS last_used,
        MAX(CASE WHEN rn_first = 1 THEN collection_timestamp END) AS first_ts,
        MAX(CASE WHEN rn_last  = 1 THEN collection_timestamp END) AS last_ts
    FROM ranked
    GROUP BY vault_id, vault_name
)
SELECT
    fl.vault_id,
    fl.vault_name,
    fl.first_used,
    fl.last_used,
    fl.first_ts,
    fl.last_ts,
    vi.hard_quota_bytes
FROM first_last fl
LEFT JOIN LATERAL (
    SELECT hard_quota_bytes
    FROM public.raw_s3icos_vault_inventory
    WHERE vault_id = fl.vault_id
    ORDER BY collection_timestamp DESC
    LIMIT 1
) AS vi ON TRUE
```
**Ne yapar:** Vault başına aralığın ilk/son kullanım değerlerini ve `LATERAL` ile en güncel
kotayı getirir (büyüme + kota karşılaştırması). `VAULT_LATEST`'tan farkı: kota `LATERAL`
filtresinde timestamp sınırı yok, doğrudan en güncel kota alınır.
**Parametreler:** `(vault_names[], start_ts, end_ts)`.
**Dönen sütunlar:** `vault_id`, `vault_name`, `first_used`, `last_used`, `first_ts`,
`last_ts`, `hard_quota_bytes`.

---

## Hesaplamalar / Formüller

### Job status normalize (her ürün için ayrı)

Her ürünün ham status'u service katmanında ortak bir sözlüğe normalize edilir
(`dc_service.py`):

**Veeam** (`_normalize_veeam_result`, ham string):
- `'success'` → `success`
- `'failed'` → `failed`
- `'warning'` → `warning`
- `'none'` (boş sonuç) → `running`
- diğeri / boş → `other`

**Zerto** (`_normalize_zerto_status`, integer VPG enum — docstring: "1=MeetingSLA (success),
2/3=problematic, 0/5=in-progress, 4=removing"):
- `1` → `success`
- `2`, `3` → `failed`
- `0`, `5` → `running`
- `4` → `warning`
- diğeri / parse hatası → `other`

**NetBackup** (`_normalize_netbackup_status`, integer exit code):
- `0` → `success`
- `1` → `warning` (partial)
- diğeri → `failed`
- parse hatası → `other`

### Series collapse (DC bazında toplama)

`_compute_all_dc_<vendor>_jobs` tek SQL pass'iyle tüm DC'lerin satırlarını çeker ve
`per_dc_collapsed[dc][(period, status, type)] += cnt` şeklinde toplar:
- **Veeam:** `source_ip → DC` haritası `VEEAM_IP_TO_DC_SEED`'den (`_build_ip_to_dc_map`).
  Anahtar `(period, status, session_type or "Unknown")`.
- **Zerto:** DC, `source_site`'tan `_extract_dc_from_text` ile. Anahtar
  `(period, status, f"status_{status_int}")`.
- **NetBackup:** DC, `dc_label` (= `destinationmediaservername`)'dan `_extract_dc_from_text`
  ile. (jobtype/policytype anahtar bileşeni olarak kullanılır.)

`period`, eğer `date()` metodu varsa `period.date().isoformat()` ile gün-bazlı string'e
çevrilir.

### Totals / başarı oranı (`_finalize_job_stats`)

Collapse edilmiş `series` (her eleman `{"period","status","job_type","policy_type","count"}`)
üzerinden:

```
total   = Σ count
success = Σ count where status == "success"
failed  = Σ count where status == "failed"
warning = Σ count where status == "warning"
other   = max(total - success - failed - warning, 0)
success_rate  = (success / total * 100)  if total else 0.0     → round(.., 2)
period_count  = distinct period sayısı (boş olmayan)
avg_per_period = (total / period_count)  if period_count else 0.0  → round(.., 2)
```

Çıktı payload'u: `{vendor, granularity, range:{start,end}, series, totals:{total, success,
failed, warning, other, success_rate, avg_per_period, period_count}, as_of}`.
Veri yoksa `_empty_job_stats` aynı şekli sıfır değerlerle döndürür.

### warm-window cache mantığı (neden normal time range yerine warm window?)

**Sorun:** Backup-jobs bar chart'ları sidebar'da 1M/2M/3M/6M preset'leriyle gösterilir. Bu
geniş aralıklarda `date_trunc + GROUP BY` ağır olduğundan, kullanıcı isteği anında hesaplamak
yavaştır. Ayrıca global `cache_ttl_seconds` (1200s/20dk) warm pass interval'ından kısa olduğu
için backup-jobs key'leri TTL geçince cache-miss yaşıyordu.

**Çözüm — warm-window pre-compute:** Scheduler periyodik olarak sabit pencereler için tüm
istatistikleri önceden hesaplayıp cache'e yazar. Pencereler `backup_jobs_warm_windows()`
(`app/utils/time_range.py`) ile tanımlıdır ve **bilerek** global `cache_time_ranges()`'e
EKLENMEZ (diğer endpoint'ler etkilenmesin):

```python
def backup_jobs_warm_windows():
    end = _today_utc()
    return [
        {"start": (end - timedelta(days=30)).isoformat(),  "end": end.isoformat(), "preset": "1m"},
        {"start": (end - timedelta(days=60)).isoformat(),  "end": end.isoformat(), "preset": "2m"},
        {"start": (end - timedelta(days=90)).isoformat(),  "end": end.isoformat(), "preset": "3m"},
        {"start": (end - timedelta(days=180)).isoformat(), "end": end.isoformat(), "preset": "6m"},
    ]

BACKUP_JOBS_WARM_GRANULARITIES = ("day", "week", "month")
```

`_warm_backup_jobs_cache` matrisi: **4 pencere × 3 granularity × 3 vendor = 36 task**. Her
task `_compute_all_dc_<vendor>_jobs` çağırır ve **tek SQL pass'iyle TÜM DC'lere** cache yazar
(eski sürümdeki "her DC için ayrı SQL" hatası giderildi — 504 task → 36 task, 14× azalma).
6 worker'lı `ThreadPoolExecutor` ile koşar.

**Cache TTL override:** `_BACKUP_JOBS_CACHE_TTL_SECONDS = 2100` (35 dk = 30 dk warm interval
+ 5 dk emniyet marjı). Bu, key'ler expire OLMADAN her warm pass tarafından overwrite
edilmesini garanti eder. Yalnızca backup-jobs key'lerine uygulanır.

**Stale-while-revalidate okuma** (`get_dc_<vendor>_jobs`):
- Cache fresh → direkt dön.
- Cache stale → stale snapshot'ı direkt dön + fresh key'i 35dk TTL ile yeniden yaz +
  `_trigger_async_jobs_compute` ile arka planda yeniden hesap tetikle.
- Hiçbiri yoksa → `cache.run_singleflight` (ttl=60) altında senkronize hesap; singleflight,
  eş zamanlı miss'lerde tek SQL run garantiler.

Cache anahtar formatı: `dc_<vendor>_jobs:{dc_code}:{tr_start}:{tr_end}:{gran}`.
Singleflight anahtarı: `_sf:<vendor>_jobs:{tr_start}:{tr_end}:{gran}` (DC içermez — tüm
DC'ler tek pass'te hesaplandığı için).

---

## Birim Dönüşümleri

| Kaynak | Dönüşüm | Yer |
|---|---|---|
| NetBackup `kilobytestransferred` (KB) → GiB | `KB / 1024 / 1024 / 1024` | `CUSTOMER_NETBACKUP_BACKUP_SUMMARY` (SQL) |
| NetBackup post-dedup | `Σ (KB / NULLIF(dedupratio, 0)) / 1024 / 1024 / 1024` | aynı sorgu |
| NetBackup dedup faktörü | `AVG(NULLIF(dedupratio, 0))` → `...||'x'` (yoksa `1x`) | aynı sorgu |
| Zerto `provisioned_storage_mb` (MB) → GiB | `MB / 1024` | `CUSTOMER_ZERTO_PROVISIONED_STORAGE` (SQL) |
| S3 iCOS pool/vault | byte cinsinden tutulur (`*_bytes`); GB/TB'ye çevrim service/format katmanında | s3.py |

> NetBackup disk pool ve Zerto site snapshot'ları byte/MB'yi **ham** döndürür; gösterim
> ölçeklemesi (`smart_storage` vb.) frontend `format_units` katmanındadır (bkz. README §4).

### Zaman aralığı sınırları (`time_range_to_bounds`)

UI time range dict'i SQL bound'larına (UTC) çevrilir:
- Sadece tarih (`YYYY-MM-DD`): start `00:00:00`, end `23:59:59` UTC.
- ISO datetime (custom / `1h` preset): string'lerden tam bound.

**İki ayrı `time_range.py` kopyası var — preset setleri FARKLI:**

- **Backend** (`services/datacenter-api/app/utils/time_range.py`): `preset_to_range`
  **yalnızca** `1h, 1d, 7d, 30d` preset'lerini işler; tanınmayan her preset (örn. aylık
  pencereler) `else` dalına düşüp **son 7 gün** döner. `1m/2m/3m/6m` anahtarları bu dosyada
  `preset_to_range` içinde YOKTUR.
- **Frontend** (`src/utils/time_range.py`): `preset_to_range` ek olarak `1m, 2m, 3m, 6m`
  preset'lerini de işler (sırasıyla son 30 / 60 / 90 / 180 gün). `1m/2m/3m/6m` eşlemeleri
  yalnızca bu dosyada tanımlıdır.
- **Backup-jobs aylık pencereler:** datacenter-api tarafındaki 30 / 60 / 90 / 180 günlük
  (`1m/2m/3m/6m` etiketli) aralıklar `preset_to_range`'den DEĞİL, aynı dosyadaki
  `backup_jobs_warm_windows()` fonksiyonundan gelir (yukarıdaki warm-window bölümüne bakın).

---

## Caching

| Katman | Anahtar | TTL | Not |
|---|---|---|---|
| **Snapshot cache** (NetBackup pool / Zerto site / Veeam repo) | `dc_netbackup:{dc}:{start}:{end}`, `dc_zerto:{dc}:{start}:{end}`, `dc_veeam:{dc}:{start}:{end}` | global `cache_ttl_seconds` | `get_dc_*` + `refresh_backup_cache` warm eder |
| **Job-stats cache** (warm-window per-backup) | `dc_<vendor>_jobs:{dc}:{tr_start}:{tr_end}:{gran}` | `2100s` (35 dk override) | `set_with_stale` + stale-while-revalidate |
| **Singleflight** | `_sf:<vendor>_jobs:{tr_start}:{tr_end}:{gran}` | `60s` | Eş zamanlı miss'lerde tek SQL pass |

- Backend cache Redis tabanlıdır (datacenter-api Redis DB 0); memory→Redis backfill default
  TTL kullandığından job-stats okumalarında fresh key 35 dk TTL ile yeniden yazılır.
- `refresh_backup_cache` (scheduler) standart raporlama pencereleri için snapshot'ları
  (NetBackup/Zerto/Veeam) yeniler, ardından `_warm_backup_jobs_cache` ile job-stats matrisini
  ısıtır.
- Genel üç katmanlı cache mimarisi için bkz. [README §6](README.md).

---

## Özet

Backup/DR dom'inde dört ürün vardır: **NetBackup** (disk pool snapshot + job boyut/dedup/exit
code), **Veeam** (repository state + session sonuç istatistikleri), **Zerto** (site metrikleri
+ VPG status enum'lu DR job istatistikleri) ve **S3 iCOS** (pool/vault byte kapasiteleri).
Snapshot sorguları README'deki "her varlık için en güncel kayıt, sonra topla" desenini
(`DISTINCT ON` / `ROW_NUMBER`) kullanır. Job istatistikleri SQL'de `date_trunc + GROUP BY` ile
önceden aggregate edilir, DC ataması uygulama katmanında host/site/media-server adından regex
ile (Veeam'de ayrıca `source_ip → DC` seed ile) yapılır; status her ürün için
`success/failed/warning/running/other`'a normalize edilir ve `_finalize_job_stats`
total/success_rate/avg_per_period hesaplar. `dc_view` bar chart'ları, geniş 1M/2M/3M/6M
pencerelerinin maliyetini gizlemek için **warm-window per-backup cache** kullanır: scheduler 4
pencere × 3 granularity × 3 vendor = 36 task'i tek SQL pass / tüm-DC ile önceden hesaplar,
35 dk TTL ve stale-while-revalidate + singleflight ile servis eder.
