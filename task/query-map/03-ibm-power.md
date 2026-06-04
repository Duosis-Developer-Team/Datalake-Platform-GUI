# IBM Power (HMC) Sorguları ve Hesaplamaları

> Cross-reference: [README](README.md) · [05-sellable-potential.md](05-sellable-potential.md) (`virt_power` / `virt_power_hana` aileleri)

## Genel Bakış

IBM Power ortamı, HMC (Hardware Management Console) üzerinden toplanan metriklerle izlenir. Bu doküman datacenter görünümünü besleyen sorguları ve bunların hesaplama mantığını açıklar.

Üç ana mantık katmanı vardır:

1. **Individual (tekil DC) sorguları** — `services/datacenter-api/app/db/queries/ibm.py` içindeki `HOST_COUNT`, `VIOS_COUNT`, `LPAR_COUNT`, `MEMORY`, `CPU`. Bunlar tek bir DC için sunucu adı `LIKE` filtresi ile çalışır.
2. **Batch raw sorguları** — `BATCH_RAW_*`. Bunlar DC kodu ayıklamadan ham satırları çeker; DC ataması Python tarafında regex ile yapılır. Aktif yol `DCService._fetch_all_batch` içindeki **inline** işlemedir (`services/datacenter-api/app/services/dc_service.py`, yaklaşık satır 1340–1442; yerel `_extract_dc(server_name)` closure'ı + DC bazında SUM/AVG döngüleri). `IBMPowerAdapter.process_raw_batch` (adapter) bu yola **bağlı değildir** — bkz. aşağıdaki not.
3. **Legacy batch sorguları** — `BATCH_HOST_COUNT`, `BATCH_VIOS_COUNT`, `BATCH_LPAR_COUNT`, `BATCH_MEMORY`, `BATCH_CPU`. Bunlar SQL içinde `regexp_matches` ile DC ayıklar; artık `_fetch_all_batch` tarafından çağrılmaz, yalnızca registry/explorer için tutulur.

> **Önemli not (branch farkı):** Bu doküman `main` branch'ini anlatır; `main` hâlâ legacy tabloları kullanır: `public.ibm_server_general`, `public.ibm_vios_general`, `public.ibm_lpar_general`, `public.ibm_server_power`. `ibm_*_performance_metrics` tablolarına geçiş (`b169e0e`) yalnızca `feature/vcenter-nutanix-ibm-integration` branch'indedir.

> **Önemli not (overcommit):** IBM Power'da shared-memory overcommit yoktur. LPAR'lara atanmış (assigned) değer = ayrılmış kapasite (allocated cap). Bu yüzden VMware/Nutanix'teki gibi bir "overcommit" çarpanı uygulanmaz.

Kaynak dosyalar:

- `services/datacenter-api/app/db/queries/ibm.py` — tüm SQL tanımları
- `services/datacenter-api/app/services/dc_service.py` — IBM getter'ları, batch çağrı orkestrasyonu ve **aktif** batch DC ayıklama/agregasyon (inline `_fetch_all_batch`)
- `services/datacenter-api/app/adapters/ibm_power_adapter.py` — `IBMPowerAdapter.process_raw_batch` + `_extract_dc(server_name, dc_set_upper)`. **PARALEL / KULLANILMAYAN duplikat:** `dc_service.py` bu sınıfı import etmez veya örneklemez (grep ile doğrulandı, 0 referans). Regex ve SUM/AVG mantığı inline yol ile birebir aynıdır; sadece bu adapter sürümü datacenter görünüm yoluna bağlanmamıştır.
- `services/datacenter-api/app/adapters/base.py` — `PlatformAdapter` soyut sınıfı (adapter ile birlikte; aktif batch yolunda kullanılmaz)
- `services/customer-api/app/services/sellable_service.py` — sellable (CRM) tarafı, HMC sunucu adı filtresi (190f07c fix'i)

## Veri Kaynakları

Üç ana HMC tablosu kullanılır (artı enerji için `ibm_server_power`).

### `public.ibm_server_general` (sunucu / kasa düzeyi)

| Kolon | Açıklama |
|---|---|
| `server_details_servername` | Fiziksel Power sunucu adı (DC kodu bu adın içine gömülüdür) |
| `time` | Örnek (sample) zaman damgası |
| `server_memory_totalmem` | Toplam bellek (MB) |
| `server_memory_availablemem` | Kullanılabilir bellek (MB) |
| `server_memory_assignedmemtolpars` | LPAR'lara atanmış bellek (MB) |
| `server_processor_totalprocunits` | Toplam proc-unit |
| `server_processor_availableprocunits` | Kullanılabilir proc-unit |
| `server_processor_utilizedprocunits` | Kullanılan (utilized) proc-unit |
| `server_physicalprocessorpool_assignedprocunits` | Fiziksel işlemci havuzundan atanmış proc-unit |

### `public.ibm_vios_general` (VIOS düzeyi)

| Kolon | Açıklama |
|---|---|
| `vios_details_servername` | VIOS'un bağlı olduğu sunucu adı (DC kodu burada) |
| `viosname` | VIOS adı (distinct sayım anahtarı) |
| `time` | Örnek zaman damgası |

### `public.ibm_lpar_general` (LPAR düzeyi)

| Kolon | Açıklama |
|---|---|
| `lpar_details_servername` | LPAR'ın bağlı olduğu sunucu adı (DC kodu burada) |
| `lparname` | LPAR adı (distinct sayım anahtarı) |
| `time` | Örnek zaman damgası |

> Not: DC kodu her zaman `*_details_servername` (sunucu adı) kolonundan ayıklanır — `viosname` / `lparname` değil. Sayımlar (`COUNT(DISTINCT ...)`) ise `viosname` / `lparname` üzerinden yapılır.

## Sorgular

Aşağıdaki SQL'ler `services/datacenter-api/app/db/queries/ibm.py` dosyasından **birebir** (verbatim) alınmıştır.

### HOST_COUNT (tekil)

```sql
SELECT COUNT(DISTINCT server_details_servername)
FROM public.ibm_server_general
WHERE server_details_servername LIKE %s AND time BETWEEN %s AND %s
```

- **Ne yapar:** Verilen pencerede, sunucu adı pattern'ine uyan distinct fiziksel Power sunucu sayısını verir.
- **Parametreler:** `(wildcard, start_ts, end_ts)` — örn. `('%DC13%', start, end)`.
- **Dönen sütunlar:** tek değer (host sayısı).

### VIOS_COUNT (tekil)

```sql
SELECT COUNT(DISTINCT viosname) AS vios_count
FROM public.ibm_vios_general
WHERE vios_details_servername LIKE %s AND time BETWEEN %s AND %s
```

- **Ne yapar:** Distinct VIOS sayısını verir; filtre sunucu adı üzerinden, sayım `viosname` üzerinden.
- **Parametreler:** `(wildcard, start_ts, end_ts)`.
- **Dönen sütunlar:** `vios_count`.

### LPAR_COUNT (tekil)

```sql
SELECT COUNT(DISTINCT lparname) AS lpar_count
FROM public.ibm_lpar_general
WHERE lpar_details_servername LIKE %s AND time BETWEEN %s AND %s
```

- **Ne yapar:** Distinct LPAR sayısını verir; filtre sunucu adı, sayım `lparname` üzerinden.
- **Parametreler:** `(wildcard, start_ts, end_ts)`.
- **Dönen sütunlar:** `lpar_count`.

### MEMORY (tekil)

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

- **Ne yapar:** Her sunucu için pencere içindeki **en son** satırı seçer (`DISTINCT ON (server_details_servername) ... ORDER BY ..., time DESC`), sonra sunucular arasında **SUM** alır.
- **Parametreler:** `(wildcard, start_ts, end_ts)`.
- **Dönen sütunlar:** `total_memory`, `available_memory`, `assigned_memory` (MB).

### CPU (tekil)

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

- **Ne yapar:** Her sunucunun en son satırını alır; kapasite sütunlarını **SUM**, kullanım sütunlarını **AVG** ile birleştirir.
  - `total_proc`, `available_proc` → **SUM** (toplam kapasite)
  - `used_proc`, `assigned_proc` → **AVG** (sunucular arası ortalama)
- **Parametreler:** `(wildcard, start_ts, end_ts)`.
- **Dönen sütunlar:** `total_proc`, `available_proc`, `used_proc`, `assigned_proc` (proc-units).

### BATCH_RAW_HOST / VIOS / LPAR (ham satırlar)

```sql
-- BATCH_RAW_HOST
SELECT server_details_servername
FROM public.ibm_server_general
WHERE time BETWEEN %s AND %s
```

```sql
-- BATCH_RAW_VIOS
SELECT vios_details_servername, viosname
FROM public.ibm_vios_general
WHERE time BETWEEN %s AND %s
```

```sql
-- BATCH_RAW_LPAR
SELECT lpar_details_servername, lparname
FROM public.ibm_lpar_general
WHERE time BETWEEN %s AND %s
```

- **Ne yapar:** DC ayıklamadan, sadece zaman aralığı filtresiyle ham satırları çeker. DC ataması ve distinct sayım Python'da yapılır.
- **Parametreler:** `(start_ts, end_ts)`.
- **Dönen sütunlar:** HOST → `server_details_servername`; VIOS → `(vios_details_servername, viosname)`; LPAR → `(lpar_details_servername, lparname)`.

### BATCH_RAW_MEMORY (ham satırlar + time)

```sql
SELECT server_details_servername,
       server_memory_totalmem,
       server_memory_availablemem,
       server_memory_assignedmemtolpars,
       time
FROM public.ibm_server_general
WHERE time BETWEEN %s AND %s
```

- **Ne yapar:** Tüm bellek örneklerini `time` ile birlikte çeker. "Sunucu başına en son örnek" seçimi ve DC bazında SUM Python'da yapılır.
- **Parametreler:** `(start_ts, end_ts)`.
- **Dönen sütunlar:** `server_details_servername`, `server_memory_totalmem`, `server_memory_availablemem`, `server_memory_assignedmemtolpars`, `time`.

### BATCH_RAW_CPU (ham satırlar + time)

```sql
SELECT server_details_servername,
       server_processor_totalprocunits,
       server_processor_availableprocunits,
       server_processor_utilizedprocunits,
       server_physicalprocessorpool_assignedprocunits,
       time
FROM public.ibm_server_general
WHERE time BETWEEN %s AND %s
```

- **Ne yapar:** Tüm CPU örneklerini `time` ile birlikte çeker; latest-per-server seçimi, SUM (kapasite) ve AVG (kullanım) hesabı Python'da yapılır.
- **Parametreler:** `(start_ts, end_ts)`.
- **Dönen sütunlar:** `server_details_servername`, `server_processor_totalprocunits`, `server_processor_availableprocunits`, `server_processor_utilizedprocunits`, `server_physicalprocessorpool_assignedprocunits`, `time`.

### Legacy batch sorguları (artık çağrılmıyor)

`BATCH_HOST_COUNT`, `BATCH_VIOS_COUNT`, `BATCH_LPAR_COUNT`, `BATCH_MEMORY`, `BATCH_CPU` DC kodunu SQL içinde ayıklar. Örnek (`BATCH_HOST_COUNT`):

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

- **Parametreler:** `(start_ts, end_ts, dc_list)`.
- **Not:** SQL içindeki regex pattern (`'DC[0-9]+|AZ[0-9]+|ICT[0-9]+'`) Python tarafındaki pattern'den daha **dardır** (`UZ`/`DH` içermez). Aktif yol Python regex'idir; bu sorgular yalnızca registry/explorer için tutulur ve `_fetch_all_batch` tarafından kullanılmaz.

## Hesaplamalar / Formüller

### proc-units agregasyonu (SUM vs AVG)

- **Toplam / kullanılabilir proc-units → SUM:** `server_processor_totalprocunits` ve `server_processor_availableprocunits` sunucular arasında toplanır (toplam fiziksel kapasite).
- **Kullanılan / atanmış proc-units → AVG:** `server_processor_utilizedprocunits` ve `server_physicalprocessorpool_assignedprocunits` sunucular arasında ortalanır (anlık kullanım/atama oranı).

Python tarafındaki karşılığı (aktif yol: `DCService._fetch_all_batch` inline, `ibm_cpu_map` döngüsü; adapter'daki `process_raw_batch` ile birebir aynı mantık): her sunucunun en son örneği seçilir, `tpu`/`apu` toplanır, `used`/`asg` listelere eklenip ortalama alınır:

```python
nu = len(used_vals) or 1
na = len(asg_vals) or 1
ibm_cpu[dc] = (
    st,                      # SUM total proc-units
    sa,                      # SUM available proc-units
    sum(used_vals) / nu,     # AVG utilized proc-units
    sum(asg_vals) / na,      # AVG assigned proc-units
)
```

### LPAR'lara atanmış bellek (`assignedmemtolpars`)

`server_memory_assignedmemtolpars`, sunucunun LPAR'larına ayrılmış belleği temsil eder. IBM'de overcommit olmadığından bu değer fiilen ayrılmış kapasitedir. Tekil sorguda (`MEMORY`) ve Python batch işlemede en son örnek bazında **SUM** alınır:

```python
lt, la, las, _ts = max(samples, key=lambda v: v[3])
t_mb += lt    # total
a_mb += la    # available
as_mb += las  # assignedmemtolpars
```

### Sunucu başına en son örnek (latest sample per server)

İki uygulama vardır:

- **SQL (tekil):** `DISTINCT ON (server_details_servername) ... ORDER BY server_details_servername, time DESC` → her sunucu için pencerede en yeni satır.
- **Python (batch):** Örnekler `(dc, server_name)` altında gruplanır; `max(samples, key=lambda v: v[ts_index])` ile en yeni örnek seçilir, sonra DC bazında toplanır/ortalanır.

### Python tarafı DC ayıklama (regex)

**Aktif yol** `services/datacenter-api/app/services/dc_service.py` içinde, `_fetch_all_batch` gövdesinde tanımlı yerel `_extract_dc(server_name)` closure'ıdır (~satır 1341). Modül seviyesindeki `_DC_CODE_RE` üzerinden çalışır ve `dc_set_upper`'ı closure ile yakalar (tek argümanlı imza):

```python
# dc_service.py modül seviyesi
_DC_CODE_RE = re.compile(r'(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)', re.IGNORECASE)

# _fetch_all_batch içinde, dc_set_upper'ı kapatan yerel closure (~satır 1341)
def _extract_dc(server_name: str) -> str | None:
    if not server_name:
        return None
    m = _DC_CODE_RE.search(server_name.upper())
    if m and m.group(1) in dc_set_upper:
        return m.group(1)
    return None
```

Yani DC kodu sunucu adının içinden (`DCn`, `AZn`, `ICTn`, `UZn`, `DHn`) ayıklanır, büyük harfe çevrilir ve yalnızca istenen DC kümesinde (`dc_set_upper`) ise kabul edilir.

> **Kullanılmayan duplikat:** `services/datacenter-api/app/adapters/ibm_power_adapter.py` içinde, aynı regex ile çalışan iki argümanlı bir sürüm vardır — `_extract_dc(server_name, dc_set_upper)` — ve `IBMPowerAdapter.process_raw_batch` tarafından kullanılır. Mantık birebir aynıdır, ancak bu adapter `dc_service.py` tarafından import edilmez/örneklenmez; datacenter görünüm yolunda **çalışmayan paralel kod**tur. Aktif imza yukarıdaki tek argümanlı inline closure'dır.

### Neden IBM batch'te ham satır + Python ayıklama kullanır?

`ibm.py` içindeki yorumda belirtildiği gibi:

> *These fetch raw rows; DC code extraction is done in Python to minimise database CPU load and allow the queries to leverage simple time-range indexes instead of computing `regexp_matches` on every row.*

Kısaca:

- SQL'de her satırda `regexp_matches` çalıştırmak veritabanı CPU'sunu yorar ve indeks kullanımını engeller.
- Ham `BATCH_RAW_*` sorguları yalnızca basit `time BETWEEN` filtresi kullanır → zaman aralığı indeksinden yararlanır.
- DC ayıklama, distinct sayım, latest-per-server seçimi ve SUM/AVG agregasyonu Python tarafına alınır (aktif: `DCService._fetch_all_batch` inline; adapter'daki `process_raw_batch` aynı mantığın kullanılmayan kopyasıdır).
- Ek avantaj: Python pattern'i `UZ`/`DH` dahil daha geniştir ve legacy SQL pattern'inden farklılaşmadan tek noktadan güncellenebilir.

### HMC sunucu adı filtresi (190f07c fix'i)

Sellable/CRM tarafında (`services/customer-api/app/services/sellable_service.py`), `virt_power_cpu` / `virt_power_ram` panelleri eskiden `site_name` kolonuyla filtreleniyordu — ancak HMC tablolarında `site_name` kolonu **yoktur**. Fix (`190f07c`), DC kapsamını HMC sunucu adı kolonları üzerinden uygular.

`_sum_sql` içinde `ibm_server_general` için (verbatim):

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

`ibm_lpar_general` için (verbatim):

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

Dikkat edilecek noktalar:

- Filtre kolonu her iki tabloda da **`*_details_servername`** (sunucu adı), `site_name` değil.
- `ibm_server_general` için latest anahtarı `server_details_servername`; `ibm_lpar_general` için `lparname`.
- `_query_total_allocated` içinde tablo `ibm_server_general` / `ibm_lpar_general` ise `where_total` / `where_alloc` cümleleri **bypass** edilir ve parametre yalnızca `[self._dc_pattern(dc_code)]` olur:

```python
total_table_bare = self._bare_table_name(src.source_table)
if total_table_bare in ("ibm_server_general", "ibm_lpar_general"):
    params = [self._dc_pattern(dc_code)]
elif src.filter_clause:
    ...
```

Tamamlayıcı migration `015_fix_ibm_power_infra_filter.sql`, `virt_power_cpu` / `virt_power_ram` panellerinde geçersiz `site_name` filtresini temizler (`filter_clause = NULL`), çünkü DC kapsamı artık SellableService içinde HMC sunucu adı kolonlarıyla uygulanır.

## Birim Dönüşümleri

- **proc-units → Core:** CRM fiyatları Core bazlıdır; datalake proc-unit tutar. `012_power_crm_panels.sql` içinde dönüşüm: **1 PU = 8 Core** (`'procunit' → 'Core'`, `factor 8.0`, `operation multiply`). `virt_power_cpu` paneli proc-unit toplamını alır, CRM Core fiyatlamasında ×8 uygulanır.
- **Bellek (MB):** `server_memory_*` kolonları **MB** cinsindendir. Tekil ve batch sorgular MB toplar; GB'ye dönüşüm tüketici (panel/CRM) katmanında yapılır.
- **Storage (GB):** Power storage `virt_power_cpu`/`ram`'dan ayrı olarak `public.raw_ibm_storage_system` tablosundan beslenir (`total_mdisk_capacity` / `total_used_capacity`, varchar → GB parse, latest-per-`storage_ip`). Bu tablo HMC değil, IBM Storage kaynağıdır.

## Caching

- Datacenter görünümünde IBM metrikleri, `dc_service.py` içindeki batch yolundan tek seferde çekilir; ham `BATCH_RAW_*` sonuçları `_fetch_all_batch` içinde **inline** olarak (yerel `_extract_dc` + SUM/AVG döngüleri) işlenir. DC bazında dict olarak döner ve view oluşturulurken bu yapı yeniden kullanılır. (Adapter'ın `process_raw_batch` metodu bu yola dahil değildir.)
- Tekil DC yolunda IBM Storage IP→DC eşlemesi için `dc_service.py` içinde `self._ibm_storage_ip_dc_cache: dict[str, str | None]` bellek-içi cache vardır.
- CRM/sellable tarafında Tier-2 sonuç snapshot'ı `gui_panel_result_snapshot` tablosunda tutulur (bkz. migration `013`/`014`); panel sonuçları bu snapshot üzerinden servis edilebilir.
- HMC sorgu seviyesinde ayrı bir uygulama içi cache yoktur; latest-per-server seçimi her çağrıda yeniden hesaplanır.

## Özet

- IBM Power metrikleri üç HMC tablosundan gelir: `ibm_server_general` (host + bellek + CPU), `ibm_vios_general` (VIOS sayımı), `ibm_lpar_general` (LPAR sayımı); enerji ayrıca `ibm_server_power`'dan, storage `raw_ibm_storage_system`'den gelir.
- Sayımlar `COUNT(DISTINCT ...)`; bellek/CPU `DISTINCT ON (server)` ile latest-per-server seçip kapasiteyi SUM, kullanımı AVG ile birleştirir.
- Batch yolu performans için ham satır çeker (`BATCH_RAW_*`) ve DC ayıklamayı Python regex'ine (`DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+`) bırakır; bu, DB'de satır-başına `regexp_matches` maliyetinden kaçınır ve zaman indeksini kullanır.
- IBM'de shared-memory overcommit yoktur: assigned = allocated cap.
- Sellable tarafında 190f07c fix'i, olmayan `site_name` yerine `*_details_servername ILIKE` ile DC kapsamı uygular; migration `015` eski `site_name` filtresini temizler.
- `main` legacy tabloları (`ibm_*_general`) kullanır; `ibm_*_performance_metrics` geçişi feature branch'tedir.
