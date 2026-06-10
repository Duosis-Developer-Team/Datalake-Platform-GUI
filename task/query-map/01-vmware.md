# VMware Sorguları ve Hesaplamaları

> Kaynak dosyalar:
> - `services/datacenter-api/app/db/queries/vmware.py` (SQL'in tamamı)
> - `services/datacenter-api/app/adapters/vmware_adapter.py`
> - `services/datacenter-api/app/adapters/base.py`
> - `services/datacenter-api/app/services/dc_service.py`
> - `src/utils/format_units.py` (yalnızca ekranda gösterim formatı)
>
> İlgili belgeler: [README](README.md) · [02-nutanix.md](02-nutanix.md) · [05-sellable-potential.md](05-sellable-potential.md)

> **Uyarı (branch farkı):** Bu belge `main` branch'indeki kodu anlatır. `main`'de tablo isimleri **legacy**'dir: `public.datacenter_metrics`, `public.cluster_metrics`, `public.vm_metrics`. `feature/vcenter-nutanix-ibm-integration` branch'inde bu tablolar `vmware_*_performance_metrics` tablolarına (snake_case kolonlar, text timestamp cast) taşınmıştır. Aşağıdaki tüm SQL `main` üzerindeki gerçek metni birebir yansıtır.

---

## Genel Bakış

VMware entegrasyonu üç tür ekranı besler:

- **`dc_view`** — Tek bir veri merkezinin (DC) ayrıntı ekranı. `get_dc_details(dc_code, time_range)` çağrılır; Classic (KM) ve Hyperconverged (non-KM) compute bölümleri ayrı ayrı doldurulur. Cluster seçicisi açıldığında `*_FILTERED` sorguları devreye girer.
- **`datacenters`** (liste / özet) — Tüm DC'lerin özetini tek seferde getiren batch yol. `_fetch_all_batch` ile `BATCH_*` sorguları paralel çalışır.
- **`global_view`** — Toplam/genel görünüm; aynı batch verisini agregeleyerek besler.

VMware verisi üç ana mantıksal kümeden gelir:

1. **DC seviyesi** (`datacenter_metrics`) — Eski/legacy toplulaştırılmış metrikler. Hâlâ enerji ve genel "intel" özeti için kullanılır.
2. **Cluster seviyesi** (`cluster_metrics`) — Asıl ayrım burada yapılır: cluster adı `KM` içeriyorsa **Classic**, içermiyorsa **Hyperconverged** sayılır.
3. **VM seviyesi** (`vm_metrics`) — Thin-provisioned vs gerçek kullanılan storage ile VM'lere atanmış (allocated) CPU/RAM dökümü.

---

## Veri Kaynakları

### `public.datacenter_metrics` (DC seviyesi)

| Kolon | Açıklama |
|---|---|
| `dc`, `datacenter` | DISTINCT ON anahtarı (hypervisor/datacenter kimliği) |
| `total_cluster_count` | Cluster sayısı |
| `total_host_count` | Host sayısı |
| `total_vm_count` | VM sayısı |
| `total_memory_capacity_gb`, `total_memory_used_gb` | Bellek (GB) |
| `total_storage_capacity_gb`, `total_used_storage_gb` | Depolama (GB) |
| `total_cpu_ghz_capacity`, `total_cpu_ghz_used` | CPU (GHz) |
| `timestamp` | Snapshot zaman damgası (en güncel için ORDER BY ... DESC) |

Eşleşme: `datacenter ILIKE '%<DC_CODE>%'`.

### `public.cluster_metrics` (cluster seviyesi — Classic/Hyperconv ayrımı)

| Kolon | Açıklama |
|---|---|
| `datacenter`, `cluster` | Filtre + DISTINCT ON anahtarı |
| `vhost_count`, `vm_count` | Host / VM sayıları |
| `cpu_ghz_capacity`, `cpu_ghz_used` | CPU (GHz) |
| `memory_capacity_gb`, `memory_used_gb` | Bellek (GB) |
| `total_capacity_gb`, `total_freespace_gb` | Depolama (GB); kullanılan = capacity − freespace |
| `cpu_usage_avg_perc`, `memory_usage_avg_perc` | Kullanım yüzdeleri (AVG30 için) |
| `timestamp` | Snapshot zaman damgası |

Eşleşme: `datacenter ILIKE %s`; ayrım `cluster ILIKE '%KM%'` (Classic) vs `cluster NOT ILIKE '%KM%'` (Hyperconverged).

### `public.vm_metrics` (VM seviyesi allocation)

| Kolon | Açıklama |
|---|---|
| `vmname` | DISTINCT ON anahtarı |
| `provisioned_space_gb` | Thin-provisioned (atanan) disk (GB) |
| `used_space_gb` | Gerçek kullanılan disk (GB) |
| `total_cpu_capacity_mhz` | VM'e atanmış CPU (MHz) → `/1000` ile GHz |
| `total_memory_capacity_gb` | VM'e atanmış RAM (GB) |
| `datacenter`, `cluster`, `timestamp` | Filtre; son 24 saat penceresi |

---

## Sorgular

Parametre konvansiyonu (dosyanın başındaki yorumdan):

- **Individual** params: `(dc_code, start_ts, end_ts)` — `datacenter_metrics` sorguları DC kodunu çıplak alır (`'%%' || %s || '%%'` ile sarılır); `cluster_metrics` sorguları tam wildcard string'i (`'%DC13%'`) alır.
- **Batch** params: `(dc_list[], pattern_list[], start_ts, end_ts)` — `pattern_list = ['%' + dc + '%' ...]`, `dc_list` ile aynı sıra.

### COUNTS (DC seviyesi sayımlar)

```sql
WITH latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc, datacenter)
        dc, datacenter, total_cluster_count, total_host_count, total_vm_count
    FROM public.datacenter_metrics
    WHERE datacenter ILIKE ('%%' || %s || '%%') AND timestamp BETWEEN %s AND %s
    ORDER BY dc, datacenter, timestamp DESC
)
SELECT
    COALESCE(SUM(total_cluster_count), 0),
    COALESCE(SUM(total_host_count), 0),
    COALESCE(SUM(total_vm_count), 0)
FROM latest_per_hypervisor
```

**Ne yapar:** Her `(dc, datacenter)` için zaman aralığındaki en güncel satırı (`DISTINCT ON ... ORDER BY ... timestamp DESC`) seçer, sonra tüm hypervisor'lar üzerinden cluster/host/VM sayılarını toplar.
**Parametreler:** `(dc_code, start_ts, end_ts)`.
**Dönen sütunlar:** `(total_cluster_count, total_host_count, total_vm_count)`.

### MEMORY (DC seviyesi bellek)

```sql
WITH latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc, datacenter)
        dc,
        datacenter,
        total_memory_capacity_gb * 1024 * 1024 * 1024 AS mem_cap,
        total_memory_used_gb * 1024 * 1024 * 1024 AS mem_used
    FROM public.datacenter_metrics
    WHERE datacenter ILIKE ('%%' || %s || '%%') AND timestamp BETWEEN %s AND %s
    ORDER BY dc, datacenter, timestamp DESC
)
SELECT
    COALESCE(SUM(mem_cap), 0),
    COALESCE(SUM(mem_used), 0)
FROM latest_per_hypervisor
```

**Ne yapar:** En güncel snapshot başına bellek kapasitesi/kullanımını GB → byte'a çevirir (`* 1024 * 1024 * 1024`) ve toplar.
**Parametreler:** `(dc_code, start_ts, end_ts)`.
**Dönen sütunlar:** `(mem_cap, mem_used)` — byte cinsinden.

### STORAGE (DC seviyesi depolama)

```sql
WITH latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc, datacenter)
        dc,
        datacenter,
        total_storage_capacity_gb * (1024 * 1024) AS stor_cap,
        total_used_storage_gb * (1024 * 1024) AS stor_used
    FROM public.datacenter_metrics
    WHERE datacenter ILIKE ('%%' || %s || '%%') AND timestamp BETWEEN %s AND %s
    ORDER BY dc, datacenter, timestamp DESC
)
SELECT
    COALESCE(SUM(stor_cap), 0),
    COALESCE(SUM(stor_used), 0)
FROM latest_per_hypervisor
```

**Ne yapar:** En güncel snapshot başına depolama değerlerini `* (1024 * 1024)` ile ölçekler ve toplar. Not: Bu çarpan GB'ı MB'a değil, MB-tabanlı bir ölçeğe taşır; Python tarafında sonuç `/1024.0` ile TB'a çevrilir (bkz. Birim Dönüşümleri).
**Parametreler:** `(dc_code, start_ts, end_ts)`.
**Dönen sütunlar:** `(stor_cap, stor_used)`.

### CPU (DC seviyesi CPU)

```sql
WITH latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc, datacenter)
        dc,
        datacenter,
        total_cpu_ghz_capacity * 1000000000 AS cpu_cap,
        total_cpu_ghz_used * 1000000000 AS cpu_used
    FROM public.datacenter_metrics
    WHERE datacenter ILIKE ('%%' || %s || '%%') AND timestamp BETWEEN %s AND %s
    ORDER BY dc, datacenter, timestamp DESC
)
SELECT
    COALESCE(SUM(cpu_cap), 0),
    COALESCE(SUM(cpu_used), 0)
FROM latest_per_hypervisor
```

**Ne yapar:** GHz değerlerini `* 1000000000` ile Hz'e çevirir, en güncel snapshot başına toplar.
**Parametreler:** `(dc_code, start_ts, end_ts)`.
**Dönen sütunlar:** `(cpu_cap, cpu_used)` — Hz cinsinden. Python'da `/1_000_000_000` ile GHz'e geri çevrilir.

### BATCH_COUNTS / BATCH_MEMORY / BATCH_STORAGE / BATCH_CPU

Batch sorgular `unnest(... WITH ORDINALITY)` desenini kullanır: `dc_list` ve `pattern_list` iki paralel `text[]` olarak açılır, her satıra bir `dc_code`, `pattern` ve sıra numarası `ord` düşer. `INNER JOIN ... ON d.datacenter ILIKE u.pattern` ile her DC satırı doğru `dc_code`'a eşlenir; `DISTINCT ON` sıralamasına `ord` eklenerek deterministiklik sağlanır; sonuç `GROUP BY dc_code` ile DC başına döner.

```sql
WITH matched AS (
    SELECT d.dc, d.datacenter, d.total_cluster_count, d.total_host_count, d.total_vm_count,
        d.timestamp, u.dc_code, u.ord
    FROM public.datacenter_metrics d
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON d.datacenter ILIKE u.pattern
    WHERE d.timestamp BETWEEN %s AND %s
),
latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc, datacenter) dc_code, total_cluster_count, total_host_count, total_vm_count
    FROM matched
    ORDER BY dc, datacenter, ord, timestamp DESC
)
SELECT
    dc_code,
    COALESCE(SUM(total_cluster_count), 0) AS total_cluster_count,
    COALESCE(SUM(total_host_count), 0) AS total_host_count,
    COALESCE(SUM(total_vm_count), 0) AS total_vm_count
FROM latest_per_hypervisor
GROUP BY dc_code
```

```sql
-- BATCH_MEMORY
WITH matched AS (
    SELECT d.datacenter, d.timestamp, d.total_memory_capacity_gb, d.total_memory_used_gb, u.dc_code, u.ord
    FROM public.datacenter_metrics d
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON d.datacenter ILIKE u.pattern
    WHERE d.timestamp BETWEEN %s AND %s
),
latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc_code, datacenter)
        dc_code,
        total_memory_capacity_gb * 1024 * 1024 * 1024 AS mem_cap,
        total_memory_used_gb * 1024 * 1024 * 1024 AS mem_used
    FROM matched
    ORDER BY dc_code, datacenter, ord, timestamp DESC
)
SELECT dc_code,
    COALESCE(SUM(mem_cap), 0) AS mem_cap,
    COALESCE(SUM(mem_used), 0) AS mem_used
FROM latest_per_hypervisor
GROUP BY dc_code
```

```sql
-- BATCH_STORAGE
WITH matched AS (
    SELECT d.datacenter, d.timestamp, d.total_storage_capacity_gb, d.total_used_storage_gb, u.dc_code, u.ord
    FROM public.datacenter_metrics d
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON d.datacenter ILIKE u.pattern
    WHERE d.timestamp BETWEEN %s AND %s
),
latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc_code, datacenter)
        dc_code,
        total_storage_capacity_gb * (1024 * 1024) AS stor_cap,
        total_used_storage_gb * (1024 * 1024) AS stor_used
    FROM matched
    ORDER BY dc_code, datacenter, ord, timestamp DESC
)
SELECT dc_code,
    COALESCE(SUM(stor_cap), 0) AS stor_cap,
    COALESCE(SUM(stor_used), 0) AS stor_used
FROM latest_per_hypervisor
GROUP BY dc_code
```

```sql
-- BATCH_CPU
WITH matched AS (
    SELECT d.datacenter, d.timestamp, d.total_cpu_ghz_capacity, d.total_cpu_ghz_used, u.dc_code, u.ord
    FROM public.datacenter_metrics d
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON d.datacenter ILIKE u.pattern
    WHERE d.timestamp BETWEEN %s AND %s
),
latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc_code, datacenter)
        dc_code,
        total_cpu_ghz_capacity * 1000000000 AS cpu_cap,
        total_cpu_ghz_used * 1000000000 AS cpu_used
    FROM matched
    ORDER BY dc_code, datacenter, ord, timestamp DESC
)
SELECT dc_code,
    COALESCE(SUM(cpu_cap), 0) AS cpu_cap,
    COALESCE(SUM(cpu_used), 0) AS cpu_used
FROM latest_per_hypervisor
GROUP BY dc_code
```

**Ne yaparlar:** Individual karşılıklarıyla aynı mantık, fakat tüm DC'ler tek sorguda. Birim çarpanları aynı (memory `* 1024^3`, storage `* (1024*1024)`, cpu `* 1e9`).
**Parametreler:** `(dc_list[], pattern_list[], start_ts, end_ts)`.
**Dönen sütunlar:** `dc_code` + ilgili toplam sütunları.

### BATCH_PLATFORM_COUNT

```sql
WITH matched AS (
    SELECT d.dc, d.datacenter, d.timestamp, u.dc_code, u.ord
    FROM public.datacenter_metrics d
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON d.datacenter ILIKE u.pattern
    WHERE d.timestamp BETWEEN %s AND %s
),
latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc, datacenter) dc_code
    FROM matched
    ORDER BY dc, datacenter, ord, timestamp DESC
)
SELECT dc_code, COUNT(*) AS platform_count
FROM latest_per_hypervisor
GROUP BY dc_code
```

**Ne yapar:** Zaman aralığında DC başına farklı hypervisor (`datacenter`) sayısını verir (platform sayımı).
**Parametreler:** `(dc_list[], pattern_list[], start_ts, end_ts)`.
**Dönen sütunlar:** `(dc_code, platform_count)`.

> `VMwareAdapter.fetch_batch_queries` bu beş batch sorguyu sırasıyla `("v_cnt", "v_mem", "v_stor", "v_cpu", "v_platform")` anahtarlarıyla döndürür.

### CLASSIC_METRICS (Classic = cluster ILIKE '%KM%')

```sql
WITH latest_per_cluster AS (
    SELECT DISTINCT ON (cluster)
        vhost_count, vm_count,
        cpu_ghz_capacity, cpu_ghz_used,
        memory_capacity_gb, memory_used_gb,
        total_capacity_gb, total_freespace_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC
)
SELECT
    COALESCE(SUM(vhost_count), 0)                                   AS hosts,
    COALESCE(SUM(vm_count), 0)                                      AS vms,
    COALESCE(SUM(cpu_ghz_capacity), 0)                              AS cpu_cap_ghz,
    COALESCE(SUM(cpu_ghz_used), 0)                                  AS cpu_used_ghz,
    COALESCE(SUM(memory_capacity_gb), 0)                            AS mem_cap_gb,
    COALESCE(SUM(memory_used_gb), 0)                                AS mem_used_gb,
    COALESCE(SUM(total_capacity_gb), 0)                             AS stor_cap_gb,
    COALESCE(SUM(total_capacity_gb - total_freespace_gb), 0)        AS stor_used_gb
FROM latest_per_cluster
```

**Ne yapar:** Her `KM` cluster'ı için en güncel satırı seçer; host/VM/CPU/RAM/storage'ı toplar. Kullanılan storage = `total_capacity_gb - total_freespace_gb`.
**Parametreler:** `(dc_pattern, start_ts, end_ts)` — `dc_pattern` tam wildcard (`'%DC13%'`).
**Dönen sütunlar:** `(hosts, vms, cpu_cap_ghz, cpu_used_ghz, mem_cap_gb, mem_used_gb, stor_cap_gb, stor_used_gb)`. (Tümü GHz/GB; Python TB'a çevirir.)

### HYPERCONV_METRICS (Hyperconverged = cluster NOT ILIKE '%KM%')

CLASSIC_METRICS ile birebir aynı, tek fark `cluster NOT ILIKE '%%KM%%'` filtresi.

```sql
WITH latest_per_cluster AS (
    SELECT DISTINCT ON (cluster)
        vhost_count, vm_count,
        cpu_ghz_capacity, cpu_ghz_used,
        memory_capacity_gb, memory_used_gb,
        total_capacity_gb, total_freespace_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster NOT ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC
)
SELECT
    COALESCE(SUM(vhost_count), 0)                                   AS hosts,
    COALESCE(SUM(vm_count), 0)                                      AS vms,
    COALESCE(SUM(cpu_ghz_capacity), 0)                              AS cpu_cap_ghz,
    COALESCE(SUM(cpu_ghz_used), 0)                                  AS cpu_used_ghz,
    COALESCE(SUM(memory_capacity_gb), 0)                            AS mem_cap_gb,
    COALESCE(SUM(memory_used_gb), 0)                                AS mem_used_gb,
    COALESCE(SUM(total_capacity_gb), 0)                             AS stor_cap_gb,
    COALESCE(SUM(total_capacity_gb - total_freespace_gb), 0)        AS stor_used_gb
FROM latest_per_cluster
```

> **Önemli:** `_aggregate_dc` içinde Hyperconverged bölümünün `hosts` ve `stor_cap`/`stor_used` değerleri Nutanix'ten alınır (host = `nutanix_host_count`, storage = Nutanix TB). `HYPERCONV_METRICS`'in CPU/RAM/VM sütunları VMware tarafından kullanılır. Detay için bkz. [02-nutanix.md](02-nutanix.md).

### CLASSIC_AVG30 / HYPERCONV_AVG30 (30 günlük kullanım yüzdeleri)

```sql
-- CLASSIC_AVG30
SELECT
    COALESCE(AVG(cpu_usage_avg_perc), 0)    AS cpu_avg_pct,
    COALESCE(AVG(memory_usage_avg_perc), 0) AS mem_avg_pct,
    COALESCE(MAX(cpu_usage_avg_perc), 0)    AS cpu_max_pct,
    COALESCE(MAX(memory_usage_avg_perc), 0) AS mem_max_pct,
    COALESCE(MIN(cpu_usage_avg_perc), 0)    AS cpu_min_pct,
    COALESCE(MIN(memory_usage_avg_perc), 0) AS mem_min_pct
FROM public.cluster_metrics
WHERE datacenter ILIKE %s
  AND cluster ILIKE '%%KM%%'
  AND timestamp BETWEEN %s AND %s
```

HYPERCONV_AVG30 aynıdır, yalnızca `cluster NOT ILIKE '%%KM%%'`.

**Ne yapar:** Zaman aralığındaki tüm satırlar üzerinden CPU/RAM kullanım yüzdesinin AVG/MAX/MIN değerlerini verir. (Burada `DISTINCT ON`/latest-snapshot **yoktur**; tüm aralık üzerinde istatistiktir.)
**Parametreler:** `(dc_pattern, start_ts, end_ts)`.
**Dönen sütunlar:** `(cpu_avg_pct, mem_avg_pct, cpu_max_pct, mem_max_pct, cpu_min_pct, mem_min_pct)`.

### BATCH_CLASSIC_METRICS / BATCH_HYPERCONV_METRICS

```sql
-- BATCH_CLASSIC_METRICS (Hyperconv versiyonu: c.cluster NOT ILIKE '%%KM%%')
WITH matched AS (
    SELECT c.datacenter, c.cluster, c.timestamp,
           c.vhost_count, c.vm_count,
           c.cpu_ghz_capacity, c.cpu_ghz_used,
           c.memory_capacity_gb, c.memory_used_gb,
           c.total_capacity_gb, c.total_freespace_gb,
           u.dc_code, u.ord
    FROM public.cluster_metrics c
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON c.datacenter ILIKE u.pattern
    WHERE c.cluster ILIKE '%%KM%%'
      AND c.timestamp BETWEEN %s AND %s
),
latest_per_cluster AS (
    SELECT DISTINCT ON (datacenter, cluster) dc_code,
        vhost_count, vm_count,
        cpu_ghz_capacity, cpu_ghz_used,
        memory_capacity_gb, memory_used_gb,
        total_capacity_gb, total_freespace_gb
    FROM matched
    ORDER BY datacenter, cluster, ord, timestamp DESC
)
SELECT
    dc_code,
    COALESCE(SUM(vhost_count), 0)                            AS hosts,
    COALESCE(SUM(vm_count), 0)                               AS vms,
    COALESCE(SUM(cpu_ghz_capacity), 0)                       AS cpu_cap_ghz,
    COALESCE(SUM(cpu_ghz_used), 0)                           AS cpu_used_ghz,
    COALESCE(SUM(memory_capacity_gb), 0)                     AS mem_cap_gb,
    COALESCE(SUM(memory_used_gb), 0)                         AS mem_used_gb,
    COALESCE(SUM(total_capacity_gb), 0)                      AS stor_cap_gb,
    COALESCE(SUM(total_capacity_gb - total_freespace_gb), 0) AS stor_used_gb
FROM latest_per_cluster
GROUP BY dc_code
```

**Parametreler:** `(dc_list[], pattern_list[], start_ts, end_ts)`. **Dönen:** `dc_code` + Classic/Hyperconv metrik sütunları.

### BATCH_CLASSIC_AVG30 / BATCH_HYPERCONV_AVG30

```sql
-- BATCH_CLASSIC_AVG30 (Hyperconv versiyonu: c.cluster NOT ILIKE '%%KM%%')
WITH matched AS (
    SELECT c.datacenter, c.timestamp,
           c.cpu_usage_avg_perc, c.memory_usage_avg_perc,
           u.dc_code
    FROM public.cluster_metrics c
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON c.datacenter ILIKE u.pattern
    WHERE c.cluster ILIKE '%%KM%%'
      AND c.timestamp BETWEEN %s AND %s
)
SELECT
    dc_code,
    COALESCE(AVG(cpu_usage_avg_perc), 0)    AS cpu_avg_pct,
    COALESCE(AVG(memory_usage_avg_perc), 0) AS mem_avg_pct,
    COALESCE(MAX(cpu_usage_avg_perc), 0)    AS cpu_max_pct,
    COALESCE(MAX(memory_usage_avg_perc), 0) AS mem_max_pct,
    COALESCE(MIN(cpu_usage_avg_perc), 0)    AS cpu_min_pct,
    COALESCE(MIN(memory_usage_avg_perc), 0) AS mem_min_pct
FROM matched
GROUP BY dc_code
```

### CLASSIC_CLUSTER_LIST / HYPERCONV_CLUSTER_LIST (cluster seçicisi)

```sql
-- CLASSIC_CLUSTER_LIST (Hyperconv versiyonu: cluster NOT ILIKE '%%KM%%')
SELECT DISTINCT cluster
FROM public.cluster_metrics
WHERE datacenter ILIKE %s
  AND cluster ILIKE '%%KM%%'
  AND timestamp BETWEEN %s AND %s
ORDER BY cluster
```

**Ne yapar:** DC view'daki cluster seçici için DC + zaman aralığındaki farklı cluster adlarını döner.
**Parametreler:** `(dc_pattern, start_ts, end_ts)`.

> Not: `get_hyperconv_cluster_list` aslında `HYPERCONV_CLUSTER_LIST` yerine Nutanix `nq.CLUSTER_LIST` sorgusunu kullanır (hyperconverged cluster'lar Nutanix tarafında). `HYPERCONV_CLUSTER_LIST` tanımlı olsa da bu yolda çağrılmaz.

### CLASSIC_METRICS_FILTERED / HYPERCONV_METRICS_FILTERED

CLASSIC/HYPERCONV_METRICS ile aynı toplulaştırma; fakat `KM`/`NOT KM` ILIKE filtresi yerine seçilen cluster listesiyle eşleşir: `cluster = ANY(%s::text[])`.

```sql
-- CLASSIC_METRICS_FILTERED (HYPERCONV_METRICS_FILTERED metni de aynıdır)
WITH latest_per_cluster AS (
    SELECT DISTINCT ON (cluster)
        vhost_count, vm_count,
        cpu_ghz_capacity, cpu_ghz_used,
        memory_capacity_gb, memory_used_gb,
        total_capacity_gb, total_freespace_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster = ANY(%s::text[])
      AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC
)
SELECT
    COALESCE(SUM(vhost_count), 0)                                   AS hosts,
    COALESCE(SUM(vm_count), 0)                                      AS vms,
    COALESCE(SUM(cpu_ghz_capacity), 0)                              AS cpu_cap_ghz,
    COALESCE(SUM(cpu_ghz_used), 0)                                  AS cpu_used_ghz,
    COALESCE(SUM(memory_capacity_gb), 0)                            AS mem_cap_gb,
    COALESCE(SUM(memory_used_gb), 0)                                AS mem_used_gb,
    COALESCE(SUM(total_capacity_gb), 0)                             AS stor_cap_gb,
    COALESCE(SUM(total_capacity_gb - total_freespace_gb), 0)        AS stor_used_gb
FROM latest_per_cluster
```

**Parametreler:** `(dc_pattern, cluster_array, start_ts, end_ts)` — `cluster_array` boş olmamalıdır.

### CLASSIC_AVG30_FILTERED / HYPERCONV_AVG30_FILTERED

```sql
-- CLASSIC_AVG30_FILTERED (HYPERCONV_AVG30_FILTERED de aynıdır)
SELECT
    COALESCE(AVG(cpu_usage_avg_perc), 0)    AS cpu_avg_pct,
    COALESCE(AVG(memory_usage_avg_perc), 0) AS mem_avg_pct,
    COALESCE(MAX(cpu_usage_avg_perc), 0)    AS cpu_max_pct,
    COALESCE(MAX(memory_usage_avg_perc), 0) AS mem_max_pct,
    COALESCE(MIN(cpu_usage_avg_perc), 0)    AS cpu_min_pct,
    COALESCE(MIN(memory_usage_avg_perc), 0) AS mem_min_pct
FROM public.cluster_metrics
WHERE datacenter ILIKE %s
  AND cluster = ANY(%s::text[])
  AND timestamp BETWEEN %s AND %s
```

> `get_classic_metrics_filtered` / `get_hyperconv_metrics_filtered`: `selected_clusters` boş/`None` ise filtreli sorgu çalışmaz; bunun yerine `get_dc_details`'ten ilgili `classic`/`hyperconv` bölümü döner. Hyperconverged filtreli yolda CPU/RAM/storage Nutanix'in `*_FILTERED` sorgularından gelir; yalnızca `HYPERCONV_AVG30_FILTERED` VMware'den okunur.

### CLASSIC_STORAGE_VM / HYPERCONV_VMWARE_STORAGE_VM (VM seviyesi allocation)

```sql
-- CLASSIC_STORAGE_VM (HYPERCONV_VMWARE_STORAGE_VM: cluster NOT ILIKE '%%KM%%')
WITH latest AS (
    SELECT DISTINCT ON (vmname)
        vmname, provisioned_space_gb, used_space_gb,
        total_cpu_capacity_mhz, total_memory_capacity_gb
    FROM public.vm_metrics
    WHERE datacenter ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND timestamp >= NOW() - INTERVAL '24 hours'
    ORDER BY vmname, timestamp DESC
)
SELECT
    COALESCE(SUM(provisioned_space_gb), 0)              AS provisioned_gb,
    COALESCE(SUM(used_space_gb), 0)                     AS used_gb,
    COALESCE(SUM(total_cpu_capacity_mhz / 1000.0), 0)   AS cpu_alloc_ghz,
    COALESCE(SUM(total_memory_capacity_gb), 0)          AS mem_alloc_gb
FROM latest
```

**Ne yapar:** Her VM (`vmname`) için son 24 saatteki en güncel satırı seçer; thin-provisioned disk, gerçek kullanılan disk, atanmış CPU (MHz → `/1000` ile GHz) ve atanmış RAM (GB) değerlerini toplar.
**Parametreler:** `(dc_pattern,)` — yalnızca DC wildcard; zaman penceresi sorgunun içinde sabit (`NOW() - INTERVAL '24 hours'`).
**Dönen sütunlar:** `(provisioned_gb, used_gb, cpu_alloc_ghz, mem_alloc_gb)`.

> `get_hyperconv_storage_vm` bu VMware sonucunu Nutanix `NUTANIX_VM_STORAGE` sonucuyla **toplar** (her dört alan da Nutanix + VMware): provisioned, used, cpu_alloc_ghz, mem_alloc_gb. Nutanix tarafında 1 vCPU ≈ 1 GHz iş kuralı geçerlidir (bkz. [02-nutanix.md](02-nutanix.md)).

---

## Hesaplamalar / Formüller

Tüm normalize işlemleri `dc_service.py` içindeki `_aggregate_dc` (ve filtreli yollardaki muadilleri) tarafından yapılır.

### Latest-snapshot deseni

`DISTINCT ON (anahtar) ... ORDER BY anahtar, timestamp DESC` PostgreSQL deseni, her gruptan (DC/hypervisor veya cluster) yalnızca en güncel satırı seçer. Ardından dış `SELECT SUM(...)` ile o anlık değerler toplanır. Batch'te sıralamaya `ord` eklenir (unnest sırası deterministik kalsın diye). AVG30 sorguları bu desenin **istisnasıdır**: orada tüm aralık üzerinden AVG/MAX/MIN alınır.

### Classic vs Hyperconverged ayrımı

- **Classic (KM):** `cluster ILIKE '%KM%'` — geleneksel/klasik Intel compute.
- **Hyperconverged (non-KM):** `cluster NOT ILIKE '%KM%'`.

`_aggregate_dc`'de:
- **Classic bölümü** tamamen `cluster_metrics`'ten gelir (host/VM/CPU/RAM/storage).
- **Hyperconverged bölümü** karışıktır: `hosts = nutanix_host_count`, `stor_cap/stor_used = Nutanix TB`; `vms/cpu_cap/cpu_used/mem_cap/mem_used` ise VMware `HYPERCONV_METRICS` satırından gelir.

### Utilization yüzdesi

**2026-06 güncellemesi:** `cpu_usage_*_perc` / `memory_usage_*_perc` kolonları kullanılmaz. `CLASSIC_AVG30` / `HYPERCONV_AVG30` (ve batch/filtered karşılıkları) zaman aralığında **used/capacity** oranının AVG/MAX/MIN değerlerini döner:

```sql
100.0 * cpu_ghz_used / cpu_ghz_capacity
100.0 * memory_used_gb / memory_capacity_gb
```

`cluster_metrics.*_used` alanları **utilization** (anlık kullanım) anlamına gelir; allocation değildir.

AVG30 sıfır ama kapasite > 0 ise anlık snapshot yedek hesabı:

```python
if cl_cpu_pct == 0.0 and cl_cpu_cap > 0:
    cl_cpu_pct = round(100.0 * cl_cpu_used / cl_cpu_cap, 1)
```

### VM-level allocation (vm_metrics + NetBox)

`get_classic_storage_vm` / `get_hyperconv_storage_vm` artık `CLASSIC_VM_ALLOCATION_ROWS` / `HYPERCONV_VMWARE_VM_ALLOCATION_ROWS` ile VM snapshot'larını çeker; CPU allocation Python'da hesaplanır:

```
cpu_alloc_ghz_sales = SUM(number_of_cpus)          # 1 vCPU = 1 GHz (billing / sellable)
cpu_alloc_ghz_vm    = SUM(number_of_cpus × host_ghz_per_core)  # infrastructure real
```

`host_ghz_per_core` → `discovery_netbox_inventory_device.custom_fields['CPU']` regex (`@ 2.50GHz`); eşleşme `vm_metrics.vmhost = netbox.name`. Eksik host'ta `gui_crm_calc_config.vmware.default_host_cpu_ghz` (UI default, seed **2.0**).

RAM allocation: `SUM(total_memory_capacity_gb)`. Storage: `SUM(provisioned_space_gb)`.

Redis / sellable **allocated (sales)** alanları: `cpu_alloc_ghz_sales`, `mem_alloc_gb_vm`, `stor_provisioned_gb`.  
`cpu_alloc_ghz_vm` yanıtta kalır (DC view real subtitle, ops); sellable hesabına karışmaz.

Overallocation bayrakları (DC seviyesi): `cpu_overallocated_sales`, `cpu_overallocated_real`.

**DC View Capacity Planning (Classic/Hyperconv, 2026-06):** Tek satır/kaynak tablo — Total, Allocation (real VM), Sales allocation (CPU only), Max utilization, allocation bar. Allocation gauge merkezinde `%100+` değerler (`allow_over_100`); sales overalloc → gauge badge `Overallocated for Sales` (üst alert kaldırıldı).

---

## Birim Dönüşümleri

| Yer | SQL içi çarpan | Anlam | Python tarafı sonradan |
|---|---|---|---|
| MEMORY / BATCH_MEMORY | `* 1024 * 1024 * 1024` | GB → byte | `_aggregate_dc` VMware mem'i doğrudan GB alır (`dc_service.py:992-993` → `v_mem_cap_gb = float(vmware_mem[0] or 0)`, bölme yok) ⚠️ **Olası tutarsızlık / bug:** SQL bellek değerini `* 1024^3` ile byte'a çevirip döndürürken Python tarafı aynı değeri bölmeden GB kabul ediyor — birim uyuşmazlığı (Nutanix mem'in aksine `1024^3` ile geri çevrilmiyor). Doğrulanmalı. |
| STORAGE / BATCH_STORAGE | `* (1024 * 1024)` | GB → MB-tabanlı ölçek | `v_stor_*_tb = stor / 1024.0` (TB) |
| CPU / BATCH_CPU | `* 1000000000` (`1e9`) | GHz → Hz | `v_cpu_*_ghz = cpu / 1_000_000_000` (GHz) |
| CLASSIC/HYPERCONV_METRICS storage | — (GB) | `total_capacity_gb` zaten GB | `cl_stor_* = gb / 1024.0` (TB) |
| CLASSIC_STORAGE_VM CPU | `total_cpu_capacity_mhz / 1000.0` | MHz → GHz | — |
| Nutanix bellek (`_aggregate_dc`) | — | bytes | `/ 1024**3` (GB) |
| Nutanix CPU (`_aggregate_dc`) | — | Hz | `/ 1_000_000_000` (GHz) |
| Nutanix storage (`_aggregate_dc`) | — | bytes | `/ 1024**4` (TB) |

Ekranda gösterim `src/utils/format_units.py` üzerinden yapılır: `smart_memory`/`smart_storage` (GB girdi → ≥1024 ise TB, <1 ise MB), `smart_cpu` (GHz girdi → <1 ise MHz), `pct_str`/`pct_float` (yüzde, 100 ile sınırlı).

---

## Caching

`dc_service.py` modül seviyesinde `cache_service` (TTL ~20 dk, singleflight destekli) kullanır. VMware ile ilgili cache anahtarları:

| Fonksiyon | Cache anahtarı |
|---|---|
| `get_dc_details` | `dc_details:{dc_code}:{tr.start}:{tr.end}` (`cache.run_singleflight` ile) |
| `get_classic_cluster_list` | `classic_clusters:{dc_code}:{tr.start}:{tr.end}` |
| `get_hyperconv_cluster_list` | `hyperconv_clusters:{dc_code}:{tr.start}:{tr.end}` |

`get_dc_details`'te `time_range.anchor_latest` set ise zaman aralığı `_smart_1h_tr` ile en güncel 1 saatlik pencereye sabitlenir. DB erişilemezse `_EMPTY_DC(dc_code)` (sıfırlanmış sözlük) döner. Batch yolu (`_fetch_all_batch`) Nutanix/VMware/IBM/Energy gruplarını ayrı bağlantılarda paralel çalıştırır.

---

## Özet

- VMware verisi üç katmandan gelir: `datacenter_metrics` (DC seviyesi sayım/bellek/storage/CPU), `cluster_metrics` (Classic-KM vs Hyperconv-nonKM ayrımı + AVG30 utilization), `vm_metrics` (VM seviyesi provisioned/used disk + atanmış CPU/RAM).
- Tüm anlık metrikler `DISTINCT ON ... ORDER BY ... timestamp DESC` ile en güncel snapshot'a indirgenip `SUM`'lanır; batch sorgular `unnest(... WITH ORDINALITY)` ile tek geçişte tüm DC'leri eşler.
- Birim dönüşümleri: bellek `* 1024^3` (byte), CPU `* 1e9` (Hz), storage `* (1024*1024)` (sonra Python `/1024` ile TB), VM CPU `MHz/1000` (GHz).
- Sonuç `dc_details:{dc}:{start}:{end}` anahtarıyla TTL-cache'lenir; Classic/Hyperconv bölümleri `dc_view`, `datacenters` ve `global_view` ekranlarını besler.
