# Nutanix Sorguları ve Hesaplamaları

> İlgili dokümanlar: [README](README.md) · [01-vmware.md](01-vmware.md)

## Genel Bakış

Bu doküman, Datalake Platform GUI'nin **Nutanix (hyperconverged)** entegrasyonuna ait
veri sorgularını ve bunların üzerindeki hesaplama mantığını açıklar. Nutanix, KM
(Klasik Mimari) dışındaki **non-KM hyperconverged** platformu temsil eder: compute,
storage ve memory aynı node'lar üzerinde birleşiktir (depolama ayrı bir SAN/array
değildir).

Kaynak kod yerleşimi:

- SQL tanımları: `services/datacenter-api/app/db/queries/nutanix.py`
- Adapter: `services/datacenter-api/app/adapters/nutanix_adapter.py`
- Adapter temel sınıfı: `services/datacenter-api/app/adapters/base.py`
- İş mantığı / birim dönüşümleri: `services/datacenter-api/app/services/dc_service.py`

**VMware ile karşılaştırma (bkz. [01-vmware.md](01-vmware.md)):**

| Konu | VMware | Nutanix |
|------|--------|---------|
| Mimari | Klasik (KM) + Hyperconverged (vCenter yönetimli) | Hyperconverged (non-KM), compute+storage birleşik |
| DC eşleştirme | `cluster_name LIKE '%DC%'` benzeri | `cluster_name LIKE '%DC%'` (aynı desen) |
| CPU birimi (ham) | Hz | Hz (capacity) + usage % (`cpu_usage_avg`) |
| Storage varsayımı | doğrudan | **dedup/compression için `/ 2`** |
| Snapshot | `DISTINCT ON` ile son kayıt | `DISTINCT ON (cluster_name)` ile son kayıt |

> **Not (branch farkı):** `main` üzerinde kaynak tablo **`nutanix_cluster_metrics`**'tir
> (legacy). `*_performance_metrics` tablolarına geçiş (örn.
> `nutanix_*_performance_metrics`, snake_case kolonlar) `feature/vcenter-nutanix-ibm-integration`
> feature branch'inde yapılmaktadır. Bu doküman `main` durumunu (legacy tablo adları)
> baz alır.

---

## Veri Kaynakları (tablo + kolonlar)

### `public.nutanix_cluster_metrics`

Cluster düzeyindeki periyodik metrikler. Tüm ana sorgular bu tabloyu kullanır.

| Kolon | Açıklama / kullanım |
|-------|---------------------|
| `cluster_name` | DC eşleştirme anahtarı (`LIKE '%<dc>%'`) ve `DISTINCT ON` grup anahtarı |
| `cluster_uuid` | VM tablosuna join anahtarı (`NUTANIX_VM_STORAGE`) |
| `cluster_name` | DC eşleştirme (`LIKE '%dc_code%'`) — tüm Nutanix sorgularında |
| `collection_time` | Zaman filtresi (`BETWEEN`) ve `DISTINCT ON` sıralaması |
| `num_nodes` | Host (node) sayısı |
| `total_vms` | VM sayısı |
| `total_memory_capacity` | Toplam memory kapasitesi (int8, **byte**) |
| `memory_usage_avg` | Memory kullanım ortalaması (binde — bkz. formül) |
| `total_cpu_capacity` | Toplam CPU kapasitesi (**Hz**) |
| `cpu_usage_avg` | CPU kullanım ortalaması (% benzeri ham değer — bkz. formül) |
| `storage_capacity` | Toplam storage kapasitesi (int8, **byte**) |
| `storage_usage` | Kullanılan storage (int8, **byte**) |

### `public.nutanix_vm_metrics`

VM düzeyinde storage/CPU/memory dağılımı. Yalnızca `NUTANIX_VM_STORAGE` sorgusunda
kullanılır.

| Kolon | Açıklama |
|-------|----------|
| `vm_name` | `DISTINCT ON` anahtarı |
| `cluster_uuid` | `nutanix_cluster_metrics.cluster_uuid` ile join |
| `collection_time` | Son 24 saat filtresi ve sıralama |
| `disk_capacity` | Provisioned disk (byte) |
| `used_storage` | Gerçekte kullanılan storage (byte) |
| `cpu_count` | vCPU sayısı |
| `memory_capacity` | Tahsisli memory (byte) |

---

## Sorgular

Tüm bireysel ve filtreli sorgularda DC eşleştirmesi `cluster_name LIKE ('%%' || %s || '%%')`
(yani `'%<dc_code>%'`) ile yapılır. Her sorgu, zaman aralığı içinde **cluster başına en
güncel snapshot'ı** `DISTINCT ON (cluster_name) ... ORDER BY cluster_name, collection_time DESC`
ile seçer, ardından cluster'lar üzerinde toplar.

Parametre sözleşmesi:

- **Bireysel sorgular:** `(dc_code, start_ts, end_ts)`
- **Batch sorgular:** `(dc_list, pattern_list, start_ts, end_ts)` —
  `pattern_list[i] = '%' || dc_list[i] || '%'`, aynı sıra. Her cluster, `dc_list`
  sırasına göre **ilk eşleşen DC'ye** atanır (`ORDER BY ... ord ...`).
- **Filtreli sorgular:** `(dc_code, cluster_array, start_ts, end_ts)`, `cluster_array`
  boş olmamalı.

---

### HOST_COUNT (bireysel)

```sql
SELECT COALESCE(SUM(num_nodes), 0)
FROM (
    SELECT DISTINCT ON (cluster_name) cluster_name, num_nodes
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
```

**Ne yapar:** DC'ye ait her cluster'ın son snapshot'ındaki `num_nodes` değerlerini
toplayarak toplam host (node) sayısını döner.
**Parametreler:** `dc_code, start_ts, end_ts`
**Dönen sütunlar:** tek skaler — toplam node sayısı.

---

### VM_COUNT (bireysel)

```sql
SELECT COALESCE(SUM(total_vms), 0)
FROM (
    SELECT DISTINCT ON (cluster_name) cluster_name, total_vms
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
```

**Ne yapar:** Cluster başına son snapshot'taki `total_vms` toplamı.
**Parametreler:** `dc_code, start_ts, end_ts`
**Dönen sütunlar:** tek skaler — toplam VM sayısı.

---

### MEMORY (bireysel)

```sql
SELECT
    COALESCE(SUM(total_memory_capacity), 0) AS total_memory_capacity,
    COALESCE(SUM(used_memory), 0) AS used_memory
FROM (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        total_memory_capacity,
        ((memory_usage_avg / 1000.0) * total_memory_capacity) / 1000.0 AS used_memory
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
```

**Ne yapar:** Cluster başına son snapshot'tan toplam memory kapasitesini ve
`memory_usage_avg`'dan türetilen kullanılan memory'yi toplar. Kullanılan memory formülü
için bkz. [Hesaplamalar / Formüller](#hesaplamalar--formüller).
**Parametreler:** `dc_code, start_ts, end_ts`
**Dönen sütunlar:** `total_memory_capacity`, `used_memory`.

---

### STORAGE (bireysel)

```sql
SELECT
    COALESCE(SUM(storage_capacity) / 2, 0) AS storage_capacity,
    COALESCE(SUM(storage_usage) / 2, 0) AS storage_usage
FROM (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        storage_capacity,
        storage_usage
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
```

**Ne yapar:** Cluster başına son snapshot'taki ham `storage_capacity` ve `storage_usage`
toplamını alır, ardından **ikiye böler** (dedup/compression varsayımı — bkz. formüller).
**Parametreler:** `dc_code, start_ts, end_ts`
**Dönen sütunlar:** `storage_capacity` (÷2), `storage_usage` (÷2).

---

### CPU (bireysel)

```sql
SELECT
    COALESCE(SUM(total_cpu_capacity), 0) AS total_cpu_capacity,
    COALESCE(SUM(cpu_used), 0) AS cpu_used
FROM (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        total_cpu_capacity,
        (cpu_usage_avg * total_cpu_capacity) / 1000000.0 AS cpu_used
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
```

**Ne yapar:** Toplam CPU kapasitesini (Hz) ve `cpu_usage_avg` yüzdesinden türetilen
kullanılan CPU'yu toplar. `cpu_used` formülü için bkz. [Hesaplamalar / Formüller](#hesaplamalar--formüller).
**Parametreler:** `dc_code, start_ts, end_ts`
**Dönen sütunlar:** `total_cpu_capacity`, `cpu_used`.

---

### BATCH_HOST_COUNT (batch)

```sql
WITH matched AS (
    SELECT n.cluster_name, n.num_nodes, n.collection_time, u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (cluster_name) dc_code, num_nodes
    FROM matched
    ORDER BY cluster_name, ord, collection_time DESC
)
SELECT dc_code, SUM(num_nodes) AS num_nodes
FROM latest
GROUP BY dc_code
```

**Ne yapar:** `unnest(dc_list, pattern_list) WITH ORDINALITY` ile çok sayıda DC'yi tek
sorguda eşler; her cluster'ı `ord` sırasına göre ilk eşleşen DC'ye atar; cluster başına
son snapshot'ı seçip DC bazında node sayısını toplar.
**Parametreler:** `dc_list, pattern_list, start_ts, end_ts`
**Dönen sütunlar:** `dc_code`, `num_nodes`.

---

### BATCH_VM_COUNT (batch)

```sql
WITH matched AS (
    SELECT n.cluster_name, n.total_vms, n.collection_time, u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (cluster_name) dc_code, total_vms
    FROM matched
    ORDER BY cluster_name, ord, collection_time DESC
)
SELECT dc_code, SUM(total_vms) AS total_vms
FROM latest
GROUP BY dc_code
```

**Ne yapar:** DC bazında, cluster başına son snapshot'taki `total_vms` toplamı.
**Parametreler:** `dc_list, pattern_list, start_ts, end_ts`
**Dönen sütunlar:** `dc_code`, `total_vms`.

---

### BATCH_MEMORY (batch)

```sql
WITH matched AS (
    SELECT n.cluster_name, n.collection_time, n.total_memory_capacity,
        ((n.memory_usage_avg / 1000.0) * n.total_memory_capacity) / 1000.0 AS used_memory,
        u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (cluster_name) dc_code, total_memory_capacity, used_memory
    FROM matched
    ORDER BY cluster_name, ord, collection_time DESC
)
SELECT dc_code,
    COALESCE(SUM(total_memory_capacity), 0) AS total_memory_capacity,
    COALESCE(SUM(used_memory), 0) AS used_memory
FROM latest
GROUP BY dc_code
```

**Ne yapar:** DC bazında toplam memory kapasitesi ve türetilen kullanılan memory.
**Parametreler:** `dc_list, pattern_list, start_ts, end_ts`
**Dönen sütunlar:** `dc_code`, `total_memory_capacity`, `used_memory`.

---

### BATCH_STORAGE (batch)

```sql
WITH matched AS (
    SELECT n.cluster_name, n.collection_time, n.storage_capacity, n.storage_usage, u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (cluster_name) dc_code, storage_capacity, storage_usage
    FROM matched
    ORDER BY cluster_name, ord, collection_time DESC
)
SELECT dc_code,
    COALESCE(SUM(storage_capacity) / 2, 0) AS storage_cap,
    COALESCE(SUM(storage_usage) / 2, 0) AS storage_used
FROM latest
GROUP BY dc_code
```

**Ne yapar:** DC bazında storage kapasitesi/kullanımı toplamı, **÷2** uygulanmış
(dedup/compression varsayımı).
**Parametreler:** `dc_list, pattern_list, start_ts, end_ts`
**Dönen sütunlar:** `dc_code`, `storage_cap` (÷2), `storage_used` (÷2).

---

### BATCH_CPU (batch)

```sql
WITH matched AS (
    SELECT n.cluster_name, n.collection_time, n.total_cpu_capacity, n.cpu_usage_avg, u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (cluster_name) dc_code,
        total_cpu_capacity,
        (cpu_usage_avg * total_cpu_capacity) / 1000000.0 AS cpu_used
    FROM matched
    ORDER BY cluster_name, ord, collection_time DESC
)
SELECT dc_code,
    COALESCE(SUM(total_cpu_capacity), 0) AS total_cpu_capacity,
    COALESCE(SUM(cpu_used), 0) AS cpu_used
FROM latest
GROUP BY dc_code
```

**Ne yapar:** DC bazında toplam CPU kapasitesi (Hz) ve türetilen kullanılan CPU.
**Parametreler:** `dc_list, pattern_list, start_ts, end_ts`
**Dönen sütunlar:** `dc_code`, `total_cpu_capacity`, `cpu_used`.

---

### BATCH_PLATFORM_COUNT (batch)

```sql
WITH matched AS (
    SELECT n.cluster_name, n.collection_time, u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (cluster_name) dc_code
    FROM matched
    ORDER BY cluster_name, ord, collection_time DESC
)
SELECT dc_code, COUNT(*) AS platform_count
FROM latest
GROUP BY dc_code
```

**Ne yapar:** Zaman aralığında DC başına **distinct cluster** sayısını döner (platform
sayacı).
**Parametreler:** `dc_list, pattern_list, start_ts, end_ts`
**Dönen sütunlar:** `dc_code`, `platform_count`.

---

### CLUSTER_LIST (cluster seçici)

```sql
SELECT DISTINCT cluster_name
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
ORDER BY cluster_name
```

**Ne yapar:** DC view'da cluster seçici için, zaman aralığındaki distinct Nutanix
(hyperconverged) cluster adlarını sıralı döner.
**Parametreler:** `dc_code, start_ts, end_ts`
**Dönen sütunlar:** `cluster_name`.

---

### HOST_COUNT_FILTERED / VM_COUNT_FILTERED / MEMORY_FILTERED / STORAGE_FILTERED / CPU_FILTERED

Bunlar bireysel sorguların birebir aynısıdır; tek fark, ek bir
`AND cluster_name = ANY(%s::text[])` koşulu ile yalnızca seçili cluster'lara
filtrelenmeleridir. Örnek (CPU_FILTERED):

```sql
SELECT
    COALESCE(SUM(total_cpu_capacity), 0) AS total_cpu_capacity,
    COALESCE(SUM(cpu_used), 0) AS cpu_used
FROM (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        total_cpu_capacity,
        (cpu_usage_avg * total_cpu_capacity) / 1000000.0 AS cpu_used
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND cluster_name = ANY(%s::text[])
      AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
```

**Ne yapar:** Seçili cluster alt kümesi için aynı metrik/formülü uygular.
**Parametreler:** `dc_code, cluster_array, start_ts, end_ts`
**Dönen sütunlar:** ilgili bireysel sorgu ile aynı.

Diğer `*_FILTERED` sorgular (HOST_COUNT_FILTERED, VM_COUNT_FILTERED, MEMORY_FILTERED,
STORAGE_FILTERED) aynı kalıba uyar; MEMORY_FILTERED kullanılan memory formülünü ve
STORAGE_FILTERED `/ 2` varsayımını korur.

---

### NUTANIX_VM_STORAGE (VM düzeyi storage/CPU/RAM dağılımı)

```sql
WITH dc_clusters AS (
    SELECT DISTINCT cluster_uuid::text AS cluster_uuid
    FROM public.nutanix_cluster_metrics
    WHERE datacenter_name ILIKE %s
      AND collection_time >= NOW() - INTERVAL '24 hours'
),
latest AS (
    SELECT DISTINCT ON (vm_name)
        vm_name, disk_capacity, used_storage, cpu_count, memory_capacity
    FROM public.nutanix_vm_metrics
    WHERE cluster_uuid::text IN (SELECT cluster_uuid FROM dc_clusters)
      AND collection_time >= NOW() - INTERVAL '24 hours'
    ORDER BY vm_name, collection_time DESC
)
SELECT
    COALESCE(SUM(disk_capacity / 1073741824.0), 0)     AS provisioned_gb,
    COALESCE(SUM(used_storage  / 1073741824.0), 0)     AS used_gb,
    COALESCE(SUM(cpu_count), 0)::bigint                AS vcpu_count,
    COALESCE(SUM(memory_capacity / 1073741824.0), 0)   AS mem_alloc_gb
FROM latest
```

**Ne yapar:** Önce `cluster_name LIKE '%' || dc_code || '%'` ile DC'ye ait cluster_uuid'leri
(son 24 saat) bulur; ardından bu cluster'lardaki VM'lerin son snapshot'larını
(`DISTINCT ON (vm_name)`) alıp provisioned disk, kullanılan storage, vCPU ve tahsisli
memory toplamlarını döner. Byte → GB için **1073741824.0 (1024³)** ile bölünür.
**Parametreler:** `(dc_code,)` — örn. `'AZ11'` (wildcard değil; diğer Nutanix sorgularıyla aynı).
**Filtered:** `(dc_code, cluster_array)` — `NUTANIX_VM_STORAGE_FILTERED`, cluster selector ile uyumlu.
**Dönen sütunlar:** `provisioned_gb`, `used_gb`, `vcpu_count`, `mem_alloc_gb`.

> **2026-06 düzeltme:** Eski `datacenter_name ILIKE` eşleştirmesi AZ11 gibi DC'lerde
> (`PRISM-AZ11-SSD`, `datacenter_name='PRISM'`) allocation'ı 0 gösteriyordu; artık
> `cluster_name LIKE '%dc_code%'` kullanılır.

> `dc_service.get_hyperconv_storage_vm()` VMware allocation ile Nutanix VM satırlarını
> (`NUTANIX_VM_ALLOCATION_ROWS`) Python'da birleştirir. Nutanix CPU:
> `cpu_alloc_ghz_vm = SUM(cpu_count × host_ghz_per_core)` — `host_name` → NetBox GHz
> (VMware ile aynı `aggregate_vm_allocation`). `cpu_alloc_ghz_sales = SUM(cpu_count)`
> yalnızca CRM/sellable içindir; DC View göstermez.

---

## Hesaplamalar / Formüller

### CPU kullanım % → kullanılan (cpu_used)

SQL içinde (bireysel `CPU`, `BATCH_CPU`, `CPU_FILTERED`):

```
cpu_used = (cpu_usage_avg * total_cpu_capacity) / 1000000.0
```

Burada `cpu_usage_avg` ham bir kullanım göstergesi, `total_cpu_capacity` ise Hz
cinsindendir. `1_000_000` böleni hem yüzde-ölçek normalizasyonunu hem de Hz → GHz
dönüşümünün bir kısmını birleşik şekilde uygular; sonuç **GHz cinsinden kullanılan CPU**
olur (`total_cpu_capacity` Hz iken `cpu_usage_avg` çarpanıyla ölçeklenir).

**Önemli birim notu — batch/single yolu:** `dc_service.get_dc_details()` içinde Nutanix
CPU değerleri ham olarak alınır ve **ek dönüşüm uygulanmaz**:

```python
# CPU → GHz
n_cpu_cap_ghz  = float(nutanix_cpu[0] or 0)
n_cpu_used_ghz = float(nutanix_cpu[1] or 0)
v_cpu_cap_ghz  = float(vmware_cpu[0] or 0) / 1_000_000_000
```

VMware tarafı Hz → GHz için `1_000_000_000`'a bölünürken, Nutanix sorgudan gelen değer
zaten GHz mertebesinde kabul edilir (capacity için `total_cpu_capacity` doğrudan, used
için `/ 1000000.0` formülü ile ölçeklenmiş). Buna karşılık **filtreli yol**
(`get_hyperconv_metrics_filtered`) `total_cpu_capacity`'yi Hz olarak kabul edip ayrıca
GHz'e böler:

```python
# nutanix_cluster_metrics.total_cpu_capacity is in Hz; convert to GHz (match VMware)
_hz_per_ghz = 1_000_000_000
cpu_cap_ghz = float(n_cpu[0] or 0) / _hz_per_ghz
cpu_used_ghz = float(n_cpu[1] or 0) / _hz_per_ghz
```

> Ambiguite: Aynı `CPU`/`CPU_FILTERED` sorgu çıktısı, batch/single yolda doğrudan GHz,
> filtreli yolda ise Hz→GHz bölünerek kullanılıyor. İki yol birbirinden farklı birim
> varsayımına sahip (aşağıdaki "Ambiguiteler" bölümüne bakınız).

### Memory kullanım % → kullanılan (used_memory)

SQL içinde (bireysel `MEMORY`, `BATCH_MEMORY`, `MEMORY_FILTERED`):

```
used_memory = ((memory_usage_avg / 1000.0) * total_memory_capacity) / 1000.0
```

`memory_usage_avg` binde (per-mille benzeri) ölçekte tutulur; `/ 1000.0` ile orana
çevrilir, `total_memory_capacity` (byte) ile çarpılır ve tekrar `/ 1000.0` ile
ölçeklenerek kullanılan memory elde edilir.

### Storage / 2 (dedup/compression varsayımı)

Bireysel `STORAGE`, `BATCH_STORAGE` ve `STORAGE_FILTERED` sorgularında hem kapasite hem
kullanım **ikiye bölünür**:

```sql
COALESCE(SUM(storage_capacity) / 2, 0) AS storage_capacity,
COALESCE(SUM(storage_usage)    / 2, 0) AS storage_usage
```

Bu, Nutanix'in dedup/compression nedeniyle ham raporladığı storage'ın yaklaşık yarısının
fiili kullanılabilir/etkin kapasiteye karşılık geldiği iş varsayımını yansıtır.

### Cluster scale / birim normalizasyonu (Python tarafı)

`dc_service.get_hyperconv_metrics_filtered()` ham byte/Hz değerlerini şu sabitlerle
normalize eder:

```python
# memory: byte → GB
_bytes_per_gb = 1024**3
mem_cap_gb  = float(n_mem[0] or 0) / _bytes_per_gb
mem_used_gb = float(n_mem[1] or 0) / _bytes_per_gb
# cpu: Hz → GHz
_hz_per_ghz = 1_000_000_000
cpu_cap_ghz  = float(n_cpu[0] or 0) / _hz_per_ghz
cpu_used_ghz = float(n_cpu[1] or 0) / _hz_per_ghz
# storage: byte → TB
_bytes_per_tb = 1024**4
stor_cap_tb  = float(n_stor[0] or 0) / _bytes_per_tb
stor_used_tb = float(n_stor[1] or 0) / _bytes_per_tb
```

Kullanım yüzdeleri kapasiteye göre türetilir:

```python
hc_cpu_pct_cap = round(100.0 * hc_cpu_used / hc_cpu_cap, 1) if hc_cpu_cap else 0.0
hc_mem_pct_cap = round(100.0 * hc_mem_used / hc_mem_cap, 1) if hc_mem_cap else 0.0
```

`get_dc_details()` (batch/single) yolundaki normalizasyon farklıdır:

```python
# memory → GB (Nutanix değeri burada ×1024 ile ölçeklenir)
n_mem_cap_gb  = float(nutanix_mem[0] or 0) * 1024
n_mem_used_gb = float(nutanix_mem[1] or 0) * 1024
# storage → TB
_bytes_per_tb = 1024**4
n_stor_cap_tb  = float(nutanix_storage[0] or 0) / _bytes_per_tb
n_stor_used_tb = float(nutanix_storage[1] or 0) / _bytes_per_tb
```

> Bu, son commit'lerde Nutanix cluster scale formüllerinin normalize edildiği
> (byte→GB/TB, Hz→GHz) noktadır. İki kod yolu (batch vs filtreli) arasında memory ve CPU
> ölçek varsayımları farklılık gösterir (bkz. Ambiguiteler).

### Host birleştirme ve VM çift sayım önleme

`get_dc_details()` içinde:

- Hyperconverged host sayısı doğrudan Nutanix node sayısından alınır
  (`hc_hosts = int(nutanix_host_count or 0)`), böylece Classic/Hyperconverged host'ları
  çift sayılmaz.
- VM çift sayımını önlemek için VMware tarafında yalnızca Classic (KM) cluster VM'leri
  gösterilir; Nutanix donanımındaki hyperconverged VM'ler zaten `nutanix.vms` içinde
  temsil edilir.

---

## Birim Dönüşümleri

| Kaynak (ham) | Hedef | Dönüşüm | Nerede |
|--------------|-------|---------|--------|
| `total_cpu_capacity` (Hz) | GHz | `/ 1_000_000_000` | `get_hyperconv_metrics_filtered`, VMware CPU |
| `cpu_usage_avg` + capacity | GHz (used) | `(cpu_usage_avg * total_cpu_capacity) / 1000000.0` | SQL `CPU`/`BATCH_CPU` |
| `total_memory_capacity` (byte) | GB | `/ 1024³` | `get_hyperconv_metrics_filtered` |
| Nutanix memory (batch) | GB | `* 1024` | `get_dc_details` |
| `memory_usage_avg` | oran/used | `((x / 1000.0) * cap) / 1000.0` | SQL `MEMORY`/`BATCH_MEMORY` |
| `storage_capacity`/`storage_usage` (byte) | TB | `/ 1024⁴` | `get_*_metrics_filtered`, `get_dc_details` |
| storage (cluster) | etkin | `/ 2` (dedup/compress) | SQL `STORAGE`/`BATCH_STORAGE` |
| VM `disk_capacity`/`used_storage`/`memory_capacity` (byte) | GB | `/ 1073741824.0` (1024³) | SQL `NUTANIX_VM_STORAGE` |
| `cpu_count` (vCPU) | GHz (physical) | `vCPU × host_ghz_per_core` via `host_name` + NetBox | `NUTANIX_VM_ALLOCATION_ROWS` → `aggregate_vm_allocation` |

---

## Caching

Sorgu sonuçları `app.services.cache_service` üzerinden TTL'li olarak önbelleğe alınır
(`app/core/cache_backend.py` → memory `TTLCache` + opsiyonel Redis).

- **Varsayılan TTL:** `settings.cache_ttl_seconds = 1200` saniye (20 dakika)
  (`app/config.py`).
- **DC detay önbelleği:** `cache_key = f"dc_details:{dc_code}:{start}:{end}"`
  (`get_dc_details`). Sonuç tüm Nutanix + VMware + IBM + Energy metriklerini içerir.
- **Cluster listesi önbelleği:** `cache_key = f"hyperconv_clusters:{dc_code}:{start}:{end}"`
  (`get_hyperconv_cluster_list`, `CLUSTER_LIST` sorgusu).
- **Stale-while-revalidate:** `set_with_stale` / `get_with_stale` ile fresh key'in yanı
  sıra daha uzun TTL'li (`stale:` prefix, varsayılan 86400 sn = 24 saat) snapshot tutulur;
  fresh expire olduğunda stale anlık yanıt verilir, arka planda revalidate edilir.
- **Singleflight:** `cache_run_singleflight` ile aynı key'e eşzamanlı cache miss'lerde
  factory yalnızca bir kez çalışır.
- **Cache warm-up:** `warm_cache()` başlangıçta tüm veriyi yükler; scheduler
  `refresh_all_data()`'ı periyodik (≈15 dk) çağırarak cache'i taze tutar.

---

## Özet

- Tüm Nutanix metrikleri `public.nutanix_cluster_metrics`'ten (VM dağılımı için
  `public.nutanix_vm_metrics`) gelir; DC eşleştirme `cluster_name LIKE '%<dc>%'` ile,
  güncel değer ise `DISTINCT ON (cluster_name) ... ORDER BY ... collection_time DESC`
  ile (cluster başına en son snapshot) elde edilir.
- Batch sorgular `unnest(...) WITH ORDINALITY` ile çok-DC eşleştirmesi yapar; her cluster
  `ord` sırasına göre ilk eşleşen DC'ye atanır.
- Kritik formüller: CPU used `= (cpu_usage_avg * total_cpu_capacity) / 1000000.0`;
  memory used `= ((memory_usage_avg / 1000.0) * total_memory_capacity) / 1000.0`;
  storage kapasite/kullanım **÷2** (dedup/compression varsayımı).
- Python tarafı ham değerleri normalize eder (byte→GB `/1024³`, byte→TB `/1024⁴`,
  Hz→GHz `/10⁹`); VM CPU `cpu_alloc_ghz_vm = SUM(cpu_count × host_ghz)` (NetBox/fallback).
- Nutanix, [01-vmware.md](01-vmware.md)'deki KM Klasik mimariden farklı olarak non-KM
  hyperconverged platformudur; host'lar Nutanix node sayısından alınır ve VMware VM
  sayımıyla çift sayım önlenir.
- `main` üzerinde tablo `nutanix_cluster_metrics` (legacy); `*_performance_metrics`
  migrasyonu feature branch'tedir.
