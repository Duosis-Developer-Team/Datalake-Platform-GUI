# query-api Wrapper Katmanı ve Frontend Çağrı Akışı

> Cross-ref: [README](README.md) · [01-vmware.md](01-vmware.md) · [02-nutanix.md](02-nutanix.md) · [03-ibm-power.md](03-ibm-power.md)

## Genel Bakış (query-api neden var; datacenter-api ile ilişki/fark)

`query-api`, frontend için **hafif, registry tabanlı bir sorgu wrapper** servisidir
(`services/query-api/`). Tek bir okuma endpoint'i yayınlar:

```
GET /api/v1/queries/{query_key}?params=<kullanıcı girdisi>
```

Mimari olarak `datacenter-api` / `customer-api`'den **temelde farklıdır**:

| | datacenter-api / customer-api | query-api |
|---|---|---|
| Sorgu seçimi | Sabit, domain'e özel endpoint'ler (`/datacenters/{id}`, `/customers/{id}/resources` ...) | Tek generic endpoint; SQL `query_key` ile registry'den seçilir |
| Orkestrasyon | `*_service.py` + `adapters/*` katmanı; birden çok sorguyu birleştirir, hesaplar | **Yok.** Tek SQL'i çalıştırır, ham satır/değer döner |
| Hesaplama | TL fiyat, TB dönüşümü, util %, aile/ratio constrain | **Hiçbiri.** Sadece SQL'in döndürdüğü kolonlar |
| Tüketici | Streamlit sayfaları (dashboard, dc_view, customer ...) | Sadece **Query Explorer** admin sayfası (`src/pages/query_explorer.py`) |

`query-api` registry'sindeki SQL'ler `datacenter-api` ve `customer-api`'deki SQL'lerin
**kopyalanmış bir alt kümesidir** (curated subset). Bir kısmı **birebir aynı**, bir
kısmı ise **basitleştirilmiş** versiyonlardır (aşağıda her sorguda işaretlendi).
`ibm.py` dosyasının başında bunu açıkça belirten bir not vardır:

```python
# Synced with datacenter-api app/db/queries/ibm.py — IBM Power HMC queries.
```

Yani query-api **birincil veri yolu değildir**; üretim dashboard'ları metriklerini
`datacenter-api`/`customer-api`'den (hesaplanmış, adapter'dan geçmiş hâliyle) alır.
query-api, registry'deki anahtarları seçip ham SQL'i tek tek çalıştırmaya yarayan bir
keşif/debug aracını besler.

### Çalışma mekaniği

- **DB bağlantısı:** `QueryService` kendi `ThreadedConnectionPool`'unu (psycopg2, min=1
  max=4) açar; `query_svc` kullanıcısıyla Datalake PostgreSQL'e (`bulutlake`) bağlanır
  (`services/query-api/app/services/query_service.py`).
- **Registry + override:** Çağrı geldiğinde `query_overrides.get_merged_entry(key)`
  çalışır. Önce diskteki `data/query_overrides.json` okunur, `QUERY_REGISTRY` ile
  birleştirilir. Override varsa registry'deki `sql`/`result_type`/`params_style`
  alanlarını ezebilir; registry'de hiç olmayan tamamen yeni anahtarlar da tanımlanabilir
  (`services/query-api/app/services/query_overrides.py`).
- **Parametre hazırlama** (`QueryService._prepare_params`): `params_style` alanına göre
  kullanıcı girdisi `%s` parametrelerine dönüştürülür:
  - `wildcard` → `("%girdi%",)`
  - `wildcard_pair` → `("%girdi%", "%girdi%")`
  - `exact` → `("girdi",)`
  - `array_wildcard` → virgülle bölünür, her parça `%p%` → `([...],)`
  - `array_exact` → virgülle bölünür, sarmalanmaz → `([...],)`
- **Sonuç tipi** (`result_type`): `value` (tek hücre), `row` (tek satır + kolon adları),
  `rows` (çok satır + kolon adları). Yanıt `QueryResult` pydantic modeline serialize
  edilir (`app/models/schemas.py`).
- **Auth:** `verify_api_user` opsiyoneldir; `API_AUTH_REQUIRED=true` ise JWT (`HS256`,
  `Bearer`) doğrulanır, aksi hâlde geçilir (`app/core/api_auth.py`).

## Veri Kaynakları (hangi tablolar — datacenter-api ile aynı mı?)

Evet, **aynı Datalake `public.*` tablolarını** kullanır (ayrı bir veritabanı veya görünüm
yoktur):

| Provider | Tablo(lar) |
|---|---|
| vmware | `public.datacenter_metrics`, `public.vmhost_metrics` (customer/energy) |
| nutanix | `public.nutanix_cluster_metrics`, `public.nutanix_vm_metrics` (customer) |
| ibm | `public.ibm_server_general`, `public.ibm_vios_general`, `public.ibm_lpar_general`, `public.ibm_server_power` (energy) |
| energy | `public.vmhost_metrics`, `public.ibm_server_power`, `public.datacenter_metrics` (batch eşleme için) |
| customer | yukarıdakiler + `public.vm_metrics`, `public.raw_veeam_sessions`, `public.raw_zerto_vpg_metrics`, `public.raw_ibm_storage_vdisk`, `public.raw_netbackup_jobs_metrics` |

> Not: query-api `main` dalındaki eski tablo adlarını kullanır (`datacenter_metrics`,
> `nutanix_cluster_metrics`, `ibm_*_general`). `*_performance_metrics` migration'ı
> `feature/...` dalındadır; bu wrapper henüz onları yansıtmaz.

## Sorgular

Aşağıda her query dosyasındaki sorgular **gerçek SQL ile** verilmiştir. Registry'de
kayıtlı (`QUERY_REGISTRY`) olanlar Query Explorer'dan çalıştırılabilir; `customer.py`
içindeki çoğu sorgu dosyada **tanımlı ama registry'ye bağlı değildir** (aşağıda
belirtilir).

> SQL'lerdeki `%%` PostgreSQL `%` literal kaçışıdır (psycopg2 `%s` parametre stiliyle
> birlikte kullanıldığında). `%s` ise bağlanacak parametredir.

---

### vmware.py

Tüm vmware sorguları registry'de kayıtlıdır ve `datacenter_metrics` üzerinden çalışır.
**Önemli:** vmware sorgularından yalnızca `vmware_counts` (COUNTS) datacenter-api ile
**birebir aynıdır**; `vmware_memory` / `vmware_storage` / `vmware_cpu` ise
**basitleştirilmiştir** (datacenter-api'deki latest-snapshot dedup yerine düz `AVG`) —
yani tıpkı nutanix bireysel sorguları gibi (aşağıda her birinde işaretlendi).

#### `vmware_counts` (COUNTS)

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

**Ne yapar:** DC adı içinde substring eşleşen `datacenter_metrics` satırlarından her
`(dc, datacenter)` için en güncel snapshot'ı alır; cluster/host/VM sayılarını toplar.
**datacenter-api karşılığı:** `vmware.COUNTS` ile **birebir aynı** (byte-identik).

#### `vmware_memory` (MEMORY) — BASİTLEŞTİRİLMİŞ

```sql
SELECT
    AVG(total_memory_capacity_gb) * 1024 * 1024 * 1024,
    AVG(total_memory_used_gb) * 1024 * 1024 * 1024
FROM public.datacenter_metrics
WHERE datacenter ILIKE ('%%' || %s || '%%') AND timestamp BETWEEN %s AND %s
```

**Ne yapar:** Aralıktaki tüm satırların GB cinsinden bellek kapasitesi/kullanımının düz
ortalamasını alıp byte'a çevirir.
**datacenter-api karşılığıyla fark (ÖNEMLİ):** datacenter-api `vmware.MEMORY` ise
"latest snapshot" desenini kullanır — `WITH latest_per_hypervisor AS (SELECT DISTINCT ON
(dc, datacenter) ... ORDER BY dc, datacenter, timestamp DESC) SELECT COALESCE(SUM(...), 0)`
ile her `(dc, datacenter)` için en güncel satırı seçip sonra `SUM` alır. query-api versiyonu
bu dedup'ı yapmaz, **doğrudan `AVG`** alır — yani nutanix bireysel sorgularıyla aynı sınıf
basitleştirme. Sonuçlar birebir tutmayabilir. STORAGE ve CPU bireysel sorguları için de aynı
durum geçerlidir (aşağıda düz `AVG`).

#### `vmware_storage` (STORAGE) — BASİTLEŞTİRİLMİŞ

```sql
SELECT
    AVG(total_storage_capacity_gb) * (1024 * 1024),
    AVG(total_used_storage_gb) * (1024 * 1024)
FROM public.datacenter_metrics
WHERE datacenter ILIKE ('%%' || %s || '%%') AND timestamp BETWEEN %s AND %s
```

**Ne yapar:** Storage kapasite/kullanımı düz ortalaması; `*(1024*1024)` ile ölçeklenir
(GB→KB değil, kaynak ölçeği için; bkz. [01-vmware.md](01-vmware.md)). datacenter-api
`vmware.STORAGE` ise latest-snapshot dedup (`DISTINCT ON (dc, datacenter)` → `SUM`) yapar;
bu versiyon yapmaz (düz `AVG`).

#### `vmware_cpu` (CPU) — BASİTLEŞTİRİLMİŞ

```sql
SELECT
    AVG(total_cpu_ghz_capacity) * 1000000000,
    AVG(total_cpu_ghz_used) * 1000000000
FROM public.datacenter_metrics
WHERE datacenter ILIKE ('%%' || %s || '%%') AND timestamp BETWEEN %s AND %s
```

**Ne yapar:** GHz cinsinden CPU kapasite/kullanım düz ortalaması, Hz'e çevrilir.
datacenter-api `vmware.CPU` ise latest-snapshot dedup (`DISTINCT ON (dc, datacenter)` →
`SUM`) yapar; bu versiyon yapmaz (düz `AVG`).

#### `vmware_batch_counts` / `vmware_batch_memory` / `vmware_batch_storage` / `vmware_batch_cpu`

Bunlar `unnest(%s::text[], %s::text[]) WITH ORDINALITY` deseniyle (bkz. README §2)
tüm DC'leri tek sorguda toplar. Örnek (`BATCH_COUNTS`):

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

**Ne yapar:** Her DC için latest snapshot toplamı, tek roundtrip'te `dc_code` bazında.
`BATCH_MEMORY`/`BATCH_STORAGE`/`BATCH_CPU` ise `one_dc_per_row` (her `(datacenter,
timestamp)` için tek satır) CTE'siyle çift sayımı engelleyip `AVG` alır. **datacenter-api
karşılığı:** aynı batch desenleri; `datacenter-api/.../vmware.py` ile büyük ölçüde örtüşür.

> **Tanımlı ama registry'de YOK:** `vmware.py` ayrıca `BATCH_PLATFORM_COUNT` (zaman
> aralığındaki DC başına distinct hypervisor/`datacenter` sayısı; `latest_per_hypervisor`
> → `COUNT(*)`) tanımlar, ancak `QUERY_REGISTRY`'ye bağlı değildir — Query Explorer'dan
> çağrılamaz.

---

### nutanix.py

Tüm sorgular `nutanix_cluster_metrics` üzerinde. Registry'de kayıtlı 8 anahtar:
`nutanix_host_count`, `nutanix_memory`, `nutanix_storage`, `nutanix_cpu` ve
`nutanix_batch_host_count` / `nutanix_batch_memory` / `nutanix_batch_storage` /
`nutanix_batch_cpu`. (`VM_COUNT`, `BATCH_VM_COUNT`, `BATCH_PLATFORM_COUNT` dosyada tanımlı
ama registry'ye bağlı **değildir** — bkz. aşağıdaki not.)

#### `nutanix_host_count` (HOST_COUNT)

```sql
SELECT COALESCE(SUM(num_nodes), 0)
FROM (
    SELECT DISTINCT ON (cluster_name) cluster_name, num_nodes
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
```

**Ne yapar:** Her cluster için en güncel `num_nodes`'u alıp toplar (host = node sayısı).

#### `nutanix_memory` (MEMORY) — BASİTLEŞTİRİLMİŞ

```sql
SELECT
    AVG(total_memory_capacity),
    AVG(((memory_usage_avg / 1000) * total_memory_capacity) / 1000)
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
```

**Ne yapar:** Aralıktaki tüm satırların bellek kapasitesi ve hesaplanan kullanılan
belleğinin düz ortalaması.
**datacenter-api karşılığıyla fark (ÖNEMLİ):** datacenter-api `nutanix.MEMORY` ise
"latest snapshot" desenini kullanır — önce `DISTINCT ON (cluster_name) ... ORDER BY
cluster_name, collection_time DESC` ile her cluster'ın en güncel satırını seçip sonra
`SUM` alır. query-api versiyonu bu dedup'ı yapmaz, **doğrudan `AVG`** alır. Yani aynı
mantığın **basitleştirilmiş/yaklaşık** bir hâlidir; sonuçlar birebir tutmayabilir. CPU ve
STORAGE bireysel sorguları için de aynı durum geçerlidir (aşağıda düz `AVG`).

#### `nutanix_storage` (STORAGE)

```sql
SELECT
    AVG(storage_capacity / 2),
    AVG(storage_usage / 2)
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
```

**Ne yapar:** Storage kapasite/kullanımını `/2` (replication factor düzeltmesi; bkz.
[02-nutanix.md](02-nutanix.md)) ile ölçekleyip ortalar. Yine düz `AVG` (latest-dedup yok).

#### `nutanix_cpu` (CPU)

```sql
SELECT
    AVG(total_cpu_capacity),
    AVG((cpu_usage_avg * total_cpu_capacity) / 1000000)
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
```

**Ne yapar:** CPU kapasite ortalaması ve `cpu_usage_avg` yüzdesinden kullanılan CPU
türevi. Düz `AVG`.

#### `nutanix_batch_host_count` / `nutanix_batch_memory` / `nutanix_batch_storage` / `nutanix_batch_cpu`

Batch versiyonlar `unnest WITH ORDINALITY` + `array_exact` parametre stiliyle (`LIKE
u.pattern`; bu dosyada batch'ler için pattern listesi `%...%` ile *önceden* sarılı
geldiği varsayılır) çalışır. Memory/storage/cpu batch'leri `one_dc_per_row`
(`DISTINCT ON (cluster_name, collection_time)`) ile dedup yapıp **sonra** `AVG` alır —
yani batch versiyonlar bireysel versiyonlardan **daha doğru** (latest-dedup içerir).
host/vm batch'leri ise `latest` (`DISTINCT ON (cluster_name) ... collection_time DESC`)
ile en güncel satırı alıp `SUM`'lar.

> **Tanımlı ama registry'de YOK:** `nutanix.py` ayrıca üç sabit daha tanımlar; hiçbiri
> `QUERY_REGISTRY`'ye bağlı değildir, dolayısıyla Query Explorer'dan çağrılamaz:
> - `VM_COUNT` — her cluster için latest `total_vms` (`DISTINCT ON (cluster_name) ...
>   collection_time DESC`) → `SUM`.
> - `BATCH_VM_COUNT` — yukarıdakinin `unnest WITH ORDINALITY` batch hâli, `dc_code` bazında
>   `SUM(total_vms)`.
> - `BATCH_PLATFORM_COUNT` — DC başına distinct cluster sayısı; `latest` (`DISTINCT ON
>   (cluster_name)`) → `COUNT(*)`.

---

### ibm.py

`# Synced with datacenter-api` notlu dosya. Registry'de kayıtlı olanlar:
`ibm_host_count`, `ibm_vios_count`, `ibm_lpar_count`, `ibm_memory`, `ibm_cpu` ve
`ibm_batch_host_count` / `ibm_batch_vios_count` / `ibm_batch_lpar_count` /
`ibm_batch_memory` / `ibm_batch_cpu`. (`BATCH_RAW_*` sorguları dosyada tanımlı ama
registry'ye bağlı **değildir**.)

#### `ibm_host_count` / `ibm_vios_count` / `ibm_lpar_count`

```sql
SELECT COUNT(DISTINCT server_details_servername)
FROM public.ibm_server_general
WHERE server_details_servername LIKE %s AND time BETWEEN %s AND %s
```
```sql
SELECT COUNT(DISTINCT viosname) AS vios_count
FROM public.ibm_vios_general
WHERE vios_details_servername LIKE %s AND time BETWEEN %s AND %s
```
```sql
SELECT COUNT(DISTINCT lparname) AS lpar_count
FROM public.ibm_lpar_general
WHERE lpar_details_servername LIKE %s AND time BETWEEN %s AND %s
```

**Ne yapar:** Sunucu/VIOS/LPAR adına göre distinct sayım. **datacenter-api karşılığı:**
senkron tutulan aynı sorgular.

#### `ibm_memory` (MEMORY)

```sql
WITH latest_per_server AS (
    SELECT DISTINCT ON (server_details_servername)
        server_details_servername,
        server_memory_totalmem,
        server_memory_availablemem,
        server_memory_assignedmemtolpars
    FROM public.ibm_server_general
    WHERE server_details_servername LIKE %s AND time BETWEEN %s AND %s
    ORDER BY server_details_servername, time DESC
)
SELECT
    COALESCE(SUM(server_memory_totalmem), 0) AS total_memory,
    COALESCE(SUM(server_memory_availablemem), 0) AS available_memory,
    COALESCE(SUM(server_memory_assignedmemtolpars), 0) AS assigned_memory
FROM latest_per_server
```

**Ne yapar:** Her sunucu için en güncel bellek satırını alıp toplam/erişilebilir/LPAR'a
atanmış belleği toplar. (Burada latest-dedup **vardır** — nutanix bireysel sorgularının
aksine.)

#### `ibm_cpu` (CPU)

```sql
WITH latest_per_server AS (
    SELECT DISTINCT ON (server_details_servername)
        server_details_servername,
        server_processor_totalprocunits,
        server_processor_availableprocunits,
        server_processor_utilizedprocunits,
        server_physicalprocessorpool_assignedprocunits
    FROM public.ibm_server_general
    WHERE server_details_servername LIKE %s AND time BETWEEN %s AND %s
    ORDER BY server_details_servername, time DESC
)
SELECT
    COALESCE(SUM(server_processor_totalprocunits), 0) AS total_proc,
    COALESCE(SUM(server_processor_availableprocunits), 0) AS available_proc,
    COALESCE(AVG(server_processor_utilizedprocunits), 0) AS used_proc,
    COALESCE(AVG(server_physicalprocessorpool_assignedprocunits), 0) AS assigned_proc
FROM latest_per_server
```

**Ne yapar:** Proc-units için latest snapshot; toplam/erişilebilir SUM, kullanılan/atanmış
ise AVG.

#### `ibm_batch_*` — regex ile DC çıkarımı

IBM'in batch sorguları diğer provider'lardan farklıdır: DC kodu sunucu adından regex ile
çıkarılır (bkz. [03-ibm-power.md](03-ibm-power.md)) ve `params_style: array_wildcard`
parametresi `WHERE dc_code = ANY(%s)` ile filtrelenir. Örnek (`BATCH_HOST_COUNT`):

```sql
WITH extracted AS (
    SELECT
        (regexp_matches(UPPER(server_details_servername), 'DC[0-9]+|AZ[0-9]+|ICT[0-9]+'))[1] AS dc_code,
        server_details_servername
    FROM public.ibm_server_general
    WHERE time BETWEEN %s AND %s
)
SELECT dc_code, COUNT(DISTINCT server_details_servername) AS host_count
FROM extracted
WHERE dc_code = ANY(%s)
GROUP BY dc_code
```

`BATCH_MEMORY` / `BATCH_CPU` benzer şekilde `extracted → latest (DISTINCT ON (dc_code,
server_details_servername) ... time DESC) → GROUP BY dc_code` zinciriyle çalışır.

---

### energy.py

Registry'de: `energy_ibm` (IBM), `energy_vcenter` ve `energy_racks` (ikisi de VCENTER),
`energy_batch_ibm` (BATCH_IBM), `energy_batch_vcenter` (BATCH_VCENTER). `*_KWH` sorguları
dosyada tanımlı ama registry'ye bağlı **değildir**.

#### `energy_vcenter` / `energy_racks` (VCENTER)

```sql
SELECT COALESCE(AVG(vm.power_usage), 0)
FROM public.vmhost_metrics vm
WHERE vm.datacenter ILIKE ('%%' || %s || '%%')
AND vm."timestamp" BETWEEN %s AND %s
```

**Ne yapar:** DC'deki vmhost güç tüketiminin (Watt) ortalaması. `energy_vcenter` ve
`energy_racks` **aynı SQL'i** kullanır (registry'de iki ayrı anahtar, tek sorgu).
`params_style: exact` — wildcard sarmalanmaz (SQL içinde `%%...%%` zaten ekler).

#### `energy_ibm` (IBM)

```sql
SELECT COALESCE(AVG(power_watts), 0)
FROM public.ibm_server_power
WHERE server_name ILIKE %s AND "timestamp" BETWEEN %s AND %s
```

**Ne yapar:** IBM sunucularının ortalama güç tüketimi (Watt).

#### `VCENTER_KWH` / `IBM_KWH` (registry'de YOK)

```sql
SELECT COALESCE(SUM(total_watts) * (15.0 / 60.0) / 1000.0, 0)
FROM (
    SELECT vm."timestamp", SUM(vm.power_usage) AS total_watts
    FROM public.vmhost_metrics vm
    WHERE vm.datacenter ILIKE ('%%' || %s || '%%') AND vm."timestamp" BETWEEN %s AND %s
    GROUP BY vm."timestamp"
) sub
```

**Ne yapar:** kWh hesabı — her timestamp'te toplam Watt, 15 dk örnekleme aralığı
(`15/60` saat) ile kWh'a çevrilir. Bkz. [07-energy.md]. (IBM_KWH benzeri, `ibm_server_power`
üzerinde.)

#### `energy_batch_vcenter` (BATCH_VCENTER) / `energy_batch_ibm` (BATCH_IBM)

VCENTER batch'i `datacenter_metrics` üzerinden bir `dc_map` (DC pattern → dc_code) kurup
`vmhost_metrics` ile join eder; IBM batch'i regex ile dc_code çıkarır. İkisi de
`AVG(power_watts)` döner. `BATCH_VCENTER_KWH`/`BATCH_IBM_KWH` (registry'de yok) bunların
kWh karşılıklarıdır.

---

### customer.py

Bu dosya **datacenter-api ve customer-api'deki müşteri/DC sorgularının kopyasıdır**
(aynı `CUSTOMER_VM_DEDUP`, `CUSTOMER_INTEL_*`, `NUTANIX_TOTALS`, `VMWARE_TOTALS`, IBM/VEEAM/
ZERTO/NETBACKUP/STORAGE sorguları hem `customer-api/app/db/queries/customer.py` hem
`datacenter-api/app/db/queries/customer.py` içinde de mevcut).

**Önemli:** `customer.py` içindeki sorguların **çoğu registry'ye bağlı değildir.**
`QUERY_REGISTRY`'de bağlı olan yalnızca şunlardır:
`customer_nutanix_totals` (NUTANIX_TOTALS), `customer_nutanix_by_dc` (NUTANIX_BY_DC),
`customer_vmware_totals` (VMWARE_TOTALS), `customer_vmware_by_dc` (VMWARE_BY_DC),
`customer_ibm_lpar_totals` (IBM_LPAR_TOTALS), `customer_ibm_vios_totals` (IBM_VIOS_TOTALS,
`wildcard_pair`), `customer_ibm_host_totals` (IBM_HOST_TOTALS), `customer_vcenter_host_totals`
(VCENTER_HOST_TOTALS).

`CUSTOMER_VM_DEDUP`, `CUSTOMER_INTEL_*`, `CUSTOMER_POWER_*`, `CUSTOMER_VEEAM_*`,
`CUSTOMER_ZERTO_*`, `CUSTOMER_NETBACKUP_*`, `CUSTOMER_STORAGE_*`, `VCENTER_BY_HOST`,
`IBM_*_BY_SERVER` gibi sorgular dosyada **tanımlı ama Query Explorer'dan çağrılamaz**
(registry'de anahtarları yok) — bunlar customer-api'nin adapter katmanında kullanılır,
query-api'ye sadece kopya olarak taşınmıştır.

Registry'ye bağlı olanlardan örnekler:

#### `customer_nutanix_totals` (NUTANIX_TOTALS)

```sql
WITH latest AS (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        datacenter_name,
        num_nodes,
        total_vms
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name ILIKE %s AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
)
SELECT COALESCE(SUM(num_nodes), 0) AS total_hosts, COALESCE(SUM(total_vms), 0) AS total_vms
FROM latest
```

**Ne yapar:** Müşteri pattern'ine uyan cluster'ların latest snapshot'ından toplam host/VM.

#### `customer_vmware_totals` (VMWARE_TOTALS)

```sql
WITH latest AS (
    SELECT DISTINCT ON (datacenter)
        datacenter,
        total_cluster_count,
        total_host_count,
        total_vm_count
    FROM public.datacenter_metrics
    WHERE datacenter ILIKE %s AND timestamp BETWEEN %s AND %s
    ORDER BY datacenter, timestamp DESC
)
SELECT
    COALESCE(SUM(total_cluster_count), 0) AS total_clusters,
    COALESCE(SUM(total_host_count), 0) AS total_hosts,
    COALESCE(SUM(total_vm_count), 0) AS total_vms
FROM latest
```

#### `customer_ibm_vios_totals` (IBM_VIOS_TOTALS, `wildcard_pair`)

```sql
SELECT COUNT(DISTINCT viosname) AS vios_count
FROM public.ibm_vios_general
WHERE (viosname ILIKE %s OR vios_details_servername ILIKE %s) AND time BETWEEN %s AND %s
```

**Ne yapar:** İki ayrı kolonda aynı pattern aranır — bu yüzden `params_style:
wildcard_pair` (girdi iki kez sarmalanıp bağlanır).

Diğer registry'ye bağlı customer sorguları (`IBM_LPAR_TOTALS`, `IBM_HOST_TOTALS`,
`VCENTER_HOST_TOTALS`) basit `COUNT(DISTINCT ...) ... ILIKE %s ... BETWEEN %s AND %s`
sayımlarıdır.

---

### registry.py

`QUERY_REGISTRY: dict[str, dict]` — her anahtar için `sql`, `source` (tablo adı,
dokümantasyon amaçlı), `result_type` (`value`/`row`/`rows`), `params_style`
(`wildcard`/`wildcard_pair`/`exact`/`array_wildcard`/`array_exact`), `provider` ve batch
sorgularda `batch_key`. Bu metadata SQL'i seçmek, parametreleri hazırlamak ve sonucu
şekillendirmek için kullanılır. Toplam kayıtlı anahtar: nutanix (8), vmware (8), ibm (10),
energy (5), customer (8).

---

## Frontend → Backend Çağrı Akışı

### `src/services/api_client.py` — servis yönlendirme

api_client, **dört ayrı backend base URL'ine** sahiptir ve her birine **thread-local bir
httpx.Client** açar (background prefetch thread pool'ları için thread başına ayrı client;
httpx.Client thread-safe paylaşılamaz):

```python
DATACENTER_API_URL = os.getenv("DATACENTER_API_URL", _API_BASE)
CUSTOMER_API_URL   = os.getenv("CUSTOMER_API_URL", _API_BASE)
QUERY_API_URL      = os.getenv("QUERY_API_URL", _API_BASE)
CRM_ENGINE_URL     = os.getenv("CRM_ENGINE_URL", CUSTOMER_API_URL)
```

Hepsi `API_BASE_URL`'e (varsayılan `http://localhost:8000`) düşer — yani tek binary'lik
(gateway) dağıtımda hepsi aynı host'a gider; mikroservis dağıtımında ayrı host'lara.
İstemci seçimi `_get_client_dc()` / `_get_client_cust()` / `_get_client_query()` /
`_client_crm` ile yapılır. **Yönlendirme kararı endpoint fonksiyonunda sabittir** (runtime
dispatch yoktur); hangi veri hangi servisten geliyor:

| Veri / fonksiyon | Servis (client) | Endpoint |
|---|---|---|
| `get_global_dashboard`, `get_all_datacenters_summary`, `get_dc_details` | datacenter-api (`_get_client_dc`) | `/api/v1/dashboard/overview`, `/api/v1/datacenters/...` |
| SLA, S3 pools, backup (veeam/zerto/netbackup), zabbix, SAN, physical-inventory, cluster lists, classic/hyperconv compute, sales-potential | datacenter-api | `/api/v1/datacenters/{dc}/...` |
| `get_customer_list`, `get_customer_resources`, ITSM, S3 vaults, CRM sales (summary/items/efficiency/catalog), service-mapping, aliases | customer-api (`_get_client_cust`) | `/api/v1/customers/...`, `/api/v1/crm/...` |
| `execute_registered_query` | **query-api** (`_get_client_query`) | `/api/v1/queries/{key}?params=...` |
| Sellable snapshot-meta, refresh | crm-engine (`_client_crm`) | `/api/v1/crm/sellable-potential/...` |

`execute_registered_query`, query-api'ye giden **tek** çağrıdır:

```python
def execute_registered_query(key: str, params: str) -> dict:
    enc_key = quote(key, safe="")
    ck = f"api:query:{enc_key}:{json.dumps(params or '', ensure_ascii=False)}"
    def fetch() -> dict:
        data = _get_json(_get_client_query(), f"/api/v1/queries/{enc_key}", params={"params": params or ""})
        return data if isinstance(data, dict) else _clone(_EMPTY_QUERY)
    return _api_cache_get_with_stale(ck, fetch, _EMPTY_QUERY)
```

Tek tüketicisi `src/pages/query_explorer.py` (admin sorgu keşif sayfası):

```python
result = api.execute_registered_query(query_key, params_input or "")
```

Ortak yardımcılar: `_build_time_params(tr)` preset/start-end → query string; `_auth_headers()`
Flask request context'inden JWT üretip `Authorization: Bearer` ekler; `_get_json`
`raise_for_status` + `.json()`.

### `src/utils/api_parallel.py` — paralel fetch

```python
def parallel_execute(tasks: dict[str, Callable[[], T]]) -> dict[str, T]:
    max_workers = min(8, len(tasks))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_key = {pool.submit(fn): key for key, fn in tasks.items()}
        for fut in as_completed(future_to_key):
            results[future_to_key[fut]] = fut.result()
    return results
```

Bağımsız api_client çağrılarını **anahtar→callable** sözlüğü olarak alıp thread havuzunda
(en çok 8 worker) paralel çalıştırır; ilk istisnayı sıralı kod gibi yukarı fırlatır. Her
thread, api_client'ın thread-local httpx client'larını kullandığından çakışma olmaz.

Kullanımı (ör. `src/pages/dc_view.py`): DC detay sayfası açılışında birbirinden bağımsız
çağrılar tek seferde fan-out edilir —

```python
batch1 = parallel_execute({
    "data": lambda: api.get_dc_details(dc_id, tr),
    "sla_by_dc": lambda: api.get_sla_by_dc(tr),
    "s3_data": lambda: api.get_dc_s3_pools(dc_id, tr),
    "classic_clusters": lambda: api.get_classic_cluster_list(dc_id, tr),
    "hyperconv_clusters": lambda: api.get_hyperconv_cluster_list(dc_id, tr),
})
```

ardından bir `batch2` (phys_inv, san_switches, net_filters, aura_dc). Bu, sayfa render
süresini ardışık HTTP yerine en yavaş çağrıya indirir. **Not:** Bu paralel desen
datacenter-api / customer-api çağrılarında kullanılır; `execute_registered_query`
(query-api) bu fan-out içinde değildir — query-api yalnızca admin Query Explorer'dan
tek tek tetiklenir.

## Hesaplamalar / Formüller

**query-api'de hesaplama yoktur — ham sorgu wrapper'ıdır.** `QueryService` yalnızca SQL'i
çalıştırır ve `result_type`'a göre tek değer / tek satır / çok satırı kolon adlarıyla
döndürür. TL fiyatlama, TB/GB dönüşümü, util %, aile/ratio constrain gibi türev mantık
tamamen `datacenter-api`/`customer-api`/`crm-engine` servis ve adapter katmanlarındadır
(bkz. README §"Sellable" ve domain dosyaları). Tek istisna, SQL **içine gömülü** sabit
çarpanlardır (ör. `*1024*1024*1024`, `/2`, `*(15.0/60.0)/1000.0`) — bunlar hesap değil,
sorgunun parçasıdır ve ilgili domain dosyalarında zaten açıklanmıştır.

## Caching

- **query-api servisinde sunucu tarafı cache yoktur.** Her istek DB pool'undan canlı
  çalışır (datacenter-api'deki Redis/snapshot katmanı query-api'de bulunmaz).
- **Frontend tarafında** `execute_registered_query` diğer tüm api_client çağrıları gibi
  `_api_cache_get_with_stale` ile sarılıdır: cache anahtarı `api:query:{key}:{params}`.
  Cache'te varsa kopya döner; yoksa fetch edip saklar; HTTP/transport hatasında son iyi
  payload'a düşer, o da yoksa `_EMPTY_QUERY = {"error": "API unreachable"}` döner. Cache
  backend'i `src/services/cache_service.py`.
- **Override "cache" benzeri kalıcılık:** `query_overrides.json` diskte tutulur ve her
  `get_merged_entry` çağrısında okunur — bu bir cache değil, registry'yi runtime'da
  ezmeye yarayan kalıcı override deposudur.

## Özet

`query-api`, frontend'in admin **Query Explorer** sayfası için tek generic endpoint
(`GET /api/v1/queries/{key}`) sunan, registry tabanlı **ham sorgu wrapper**'ıdır;
hesaplama/orkestrasyon yapmaz, sonucu kolon adlarıyla döndürür. SQL'leri
`datacenter-api`/`customer-api`'deki sorguların **curated bir alt kümesinin
kopyasıdır**: bir kısmı **birebir aynı** (vmware `COUNTS`, energy ve ibm bireysel
sorguları — ibm dosyası açıkça "Synced with datacenter-api" notlu), bir kısmı ise
**basitleştirilmiştir** — hem **nutanix** hem **vmware** bireysel `MEMORY`/`STORAGE`/`CPU`
sorguları datacenter-api'deki latest-snapshot dedup (`DISTINCT ON ... ORDER BY ...
DESC` → `SUM`) yerine düz `AVG` kullanır; `customer.py`'nin çoğu sorgusu kopyalanmış olsa
da registry'ye bağlı değildir, dolayısıyla Query Explorer'dan çağrılamaz. Ayrıca
`vmware.BATCH_PLATFORM_COUNT` ile `nutanix.VM_COUNT` / `BATCH_VM_COUNT` /
`BATCH_PLATFORM_COUNT` dosyalarda tanımlı ama registry'ye bağlı olmadığından çağrılamaz. Frontend yönlendirmesi `api_client.py`'de sabit fonksiyon bazlı
(dört ayrı base URL + thread-local httpx client); `api_parallel.parallel_execute` ise
bağımsız datacenter/customer çağrılarını ≤8 worker'lı thread havuzunda fan-out eder
(query-api bu fan-out'ta yer almaz).
