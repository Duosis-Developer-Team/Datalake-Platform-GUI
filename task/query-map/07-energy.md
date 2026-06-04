# Enerji Tüketimi Sorguları ve Hesaplamaları

İlgili dosyalar:
- `services/datacenter-api/app/db/queries/energy.py` (SQL tanımları)
- `services/datacenter-api/app/adapters/energy_adapter.py` (kaynak bazlı sorgu eşlemesi)
- `services/datacenter-api/app/adapters/base.py` (adapter sözleşmesi)
- `services/datacenter-api/app/services/dc_service.py` (kW / kWh toplama ve aggregation)

Çapraz referans: [README](README.md), [04-ibm-storage-san.md](04-ibm-storage-san.md), [06-backup-dr.md](06-backup-dr.md).

> Not: `energy.py` dosyası yalnızca güç/enerji sorgularını içerir. Zerto VPG (replikasyon) sorguları bu dokümanın kapsamı dışındadır ve [06-backup-dr.md](06-backup-dr.md) içinde belgelenir.

---

## Genel Bakış

Enerji tüketimi iki büyüklük olarak ölçülür:

- **kW (anlık güç)**: Rapor aralığındaki tüm örnek (sample) ölçümlerinin ortalama gücü. UI'de güç tüketimi göstergesi olarak gösterilir.
- **kWh (zaman üzerinden enerji)**: Faturalama için rapor aralığında tüketilen toplam enerji.

Hangi ekranlarda kullanılır:
- **dc_view (tekil DC detayı)**: Her veri merkezi için IBM ve vCenter güç/enerji değerleri ayrı ayrı ve toplam olarak döndürülür (`energy` bloğu: `total_kw`, `ibm_kw`, `vcenter_kw`, `total_kwh`, `ibm_kwh`, `vcenter_kwh`).
- **global_view (genel bakış / ana sayfa)**: Tüm DC'lerin toplam `total_energy_kw` değeri ve `energy_breakdown` (`ibm_kw`, `vcenter_kw`) hesaplanır.

Veri kaynağı yalnızca **IBM** ve **vCenter (VMware)** sistemleridir. `dc_service.py` içindeki yorumda belirtildiği gibi Loki/rack verileri enerji hesabında kullanılmaz (`# Energy → kW (IBM + vCenter only; Loki/racks not used)`).

---

## Veri Kaynakları

`energy.py` başındaki yorum:
> `# Sources: vmhost_metrics (vCenter), ibm_server_power (IBM HMC).`

| Kaynak | Tablo | Güç kolonu | DC eşleme kolonu | Zaman kolonu |
|--------|-------|-----------|------------------|--------------|
| vCenter (VMware) | `public.vmhost_metrics` | `power_usage` (watt) | `datacenter` (ILIKE `%dc%`) | `timestamp` |
| IBM (HMC) | `public.ibm_server_power` | `power_watts` (watt) | `server_name` (ILIKE pattern / regex) | `timestamp` |

Batch (toplu) vCenter DC eşlemesi için ek olarak `public.datacenter_metrics` tablosu (`datacenter` kolonu) ILIKE pattern listesiyle eşleştirilerek `dc_code` çıkarımı yapılır.

**DC eşleme yöntemleri kaynaklara göre farklıdır:**
- vCenter: `datacenter` alanı, DC kodunu içeren ILIKE deseni ile eşlenir (`'%' || dc_code || '%'`).
- IBM tekil: `server_name` ILIKE wildcard deseni ile eşlenir.
- IBM batch: `server_name` üzerinden regex (`DC[0-9]+|AZ[0-9]+|ICT[0-9]+`) ile `dc_code` çıkarılır.

Örnekleme sıklığı (yorumdan): veri tipik olarak **15 dakikada bir** toplanır (günde 96 örnek). Bu nedenle kWh hesabında 15 dakikalık aralık (0.25 saat) çarpanı kullanılır.

---

## Sorgular

### 1. VCENTER — vCenter anlık güç (AVG watt)

```sql
SELECT COALESCE(AVG(vm.power_usage), 0)
FROM public.vmhost_metrics vm
WHERE vm.datacenter ILIKE ('%%' || %s || '%%')
AND vm."timestamp" BETWEEN %s AND %s
```

**Ne yapar:** Belirtilen DC için `vmhost_metrics.power_usage` değerlerinin aralık içindeki ortalamasını (watt) döndürür.

**Parametreler:** `(dc_code, start_ts, end_ts)` — `dc_code` ILIKE deseninin içine gömülür.

**Dönen sütunlar:** Tek değer — ortalama güç (watt).

---

### 2. IBM — IBM anlık güç (AVG watt)

```sql
SELECT COALESCE(AVG(power_watts), 0)
FROM public.ibm_server_power
WHERE server_name ILIKE %s AND "timestamp" BETWEEN %s AND %s
```

**Ne yapar:** Aralık içindeki sunucu başına ortalama gücü (`power_watts`, watt) döndürür.

**Parametreler:** `(wildcard, start_ts, end_ts)` — `wildcard` örn. `%dc01%` deseni.

**Dönen sütunlar:** Tek değer — ortalama güç (watt).

---

### 3. VCENTER_KWH — vCenter faturalama enerjisi (kWh)

```sql
SELECT COALESCE(SUM(total_watts) * (15.0 / 60.0) / 1000.0, 0)
FROM (
    SELECT vm."timestamp", SUM(vm.power_usage) AS total_watts
    FROM public.vmhost_metrics vm
    WHERE vm.datacenter ILIKE ('%%' || %s || '%%') AND vm."timestamp" BETWEEN %s AND %s
    GROUP BY vm."timestamp"
) sub
```

**Ne yapar:** Her timestamp için tüm host'ların gücünü toplar (`total_watts`), ardından bu değerleri 15 dakikalık aralık (0.25 saat) ile çarparak ve 1000'e bölerek toplam kWh hesaplar.

**Parametreler:** `(dc_code, start_ts, end_ts)`.

**Dönen sütunlar:** Tek değer — toplam enerji (kWh).

---

### 4. IBM_KWH — IBM faturalama enerjisi (kWh)

```sql
SELECT COALESCE(SUM(total_watts) * (15.0 / 60.0) / 1000.0, 0)
FROM (
    SELECT "timestamp", SUM(power_watts) AS total_watts
    FROM public.ibm_server_power
    WHERE server_name ILIKE %s AND "timestamp" BETWEEN %s AND %s
    GROUP BY "timestamp"
) sub
```

**Ne yapar:** Her timestamp için tüm sunucuların `power_watts` toplamını alır, 15 dakikalık aralık çarpanı ile kWh'a çevirir.

**Parametreler:** `(wildcard, start_ts, end_ts)`.

**Dönen sütunlar:** Tek değer — toplam enerji (kWh).

---

### 5. BATCH_VCENTER — vCenter toplu anlık güç (DC bazında AVG watt)

```sql
WITH dc_map AS (
    SELECT DISTINCT ON (d.datacenter) d.datacenter, u.dc_code
    FROM public.datacenter_metrics d
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON d.datacenter ILIKE u.pattern
    ORDER BY d.datacenter, u.ord
)
SELECT dm.dc_code, AVG(vm.power_usage) AS avg_power_watts
FROM public.vmhost_metrics vm
JOIN dc_map dm ON vm.datacenter = dm.datacenter
WHERE vm."timestamp" BETWEEN %s AND %s
GROUP BY dm.dc_code
```

**Ne yapar:** `datacenter_metrics.datacenter` alanını verilen pattern listesiyle ILIKE eşleştirerek her datacenter'a bir `dc_code` atar (ilk eşleşen patterne göre, `ORDER BY ... u.ord`). Sonra `vmhost_metrics` güç değerlerini DC bazında ortalar.

**Parametreler:** `(dc_list, pattern_list, start_ts, end_ts)`.

**Dönen sütunlar:** `(dc_code, avg_power_watts)`.

---

### 6. BATCH_IBM — IBM toplu anlık güç (DC bazında AVG watt)

```sql
WITH extracted AS (
    SELECT
        (regexp_matches(UPPER(server_name), 'DC[0-9]+|AZ[0-9]+|ICT[0-9]+'))[1] AS dc_code,
        power_watts
    FROM public.ibm_server_power
    WHERE "timestamp" BETWEEN %s AND %s
)
SELECT dc_code, AVG(power_watts) AS avg_power_watts
FROM extracted
WHERE dc_code = ANY(%s)
GROUP BY dc_code
```

**Ne yapar:** `server_name` üzerinden regex ile `dc_code` çıkarır (`DC#`, `AZ#`, `ICT#` desenleri), verilen DC listesine filtreler ve DC bazında ortalama gücü döndürür.

**Parametreler:** `(start_ts, end_ts, dc_list)`.

**Dönen sütunlar:** `(dc_code, avg_power_watts)`.

---

### 7. BATCH_VCENTER_KWH — vCenter toplu kWh (DC bazında)

```sql
WITH dc_map AS (
    SELECT DISTINCT ON (d.datacenter) d.datacenter, u.dc_code
    FROM public.datacenter_metrics d
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON d.datacenter ILIKE u.pattern
    ORDER BY d.datacenter, u.ord
),
per_ts AS (
    SELECT dm.dc_code, vm."timestamp", SUM(vm.power_usage) AS total_watts
    FROM public.vmhost_metrics vm
    JOIN dc_map dm ON vm.datacenter = dm.datacenter
    WHERE vm."timestamp" BETWEEN %s AND %s
    GROUP BY dm.dc_code, vm."timestamp"
)
SELECT dc_code, SUM(total_watts) * (15.0 / 60.0) / 1000.0 AS total_kwh
FROM per_ts
GROUP BY dc_code
```

**Ne yapar:** DC eşlemesini yapar, her (dc_code, timestamp) için güç toplamını alır, ardından DC bazında 15 dakikalık aralık çarpanıyla kWh'a çevirir.

**Parametreler:** `(dc_list, pattern_list, start_ts, end_ts)`.

**Dönen sütunlar:** `(dc_code, total_kwh)`.

---

### 8. BATCH_IBM_KWH — IBM toplu kWh (DC bazında)

```sql
WITH extracted AS (
    SELECT
        (regexp_matches(UPPER(server_name), 'DC[0-9]+|AZ[0-9]+|ICT[0-9]+'))[1] AS dc_code,
        "timestamp",
        power_watts
    FROM public.ibm_server_power
    WHERE "timestamp" BETWEEN %s AND %s
),
per_ts AS (
    SELECT dc_code, "timestamp", SUM(power_watts) AS total_watts
    FROM extracted
    WHERE dc_code = ANY(%s)
    GROUP BY dc_code, "timestamp"
)
SELECT dc_code, SUM(total_watts) * (15.0 / 60.0) / 1000.0 AS total_kwh
FROM per_ts
GROUP BY dc_code
```

**Ne yapar:** `server_name`'den regex ile `dc_code` çıkarır, DC listesine filtreler, her (dc_code, timestamp) için güç toplar ve DC bazında kWh hesaplar.

**Parametreler:** `(start_ts, end_ts, dc_list)`.

**Dönen sütunlar:** `(dc_code, total_kwh)`.

---

## Hesaplamalar / Formüller

### Adapter eşlemesi (kaynak bazında)

`energy_adapter.py` — tekil DC için dört değer döndürür:

```python
def fetch_single_dc(self, cursor, dc_code_exact, dc_code_like, start_ts, end_ts) -> dict:
    return {
        "ibm_w":       self._run_value(cursor, eq.IBM,         (dc_code_like, start_ts, end_ts)),
        "vcenter_w":   self._run_value(cursor, eq.VCENTER,     (dc_code_exact, start_ts, end_ts)),
        "ibm_kwh":     self._run_value(cursor, eq.IBM_KWH,     (dc_code_like, start_ts, end_ts)),
        "vcenter_kwh": self._run_value(cursor, eq.VCENTER_KWH, (dc_code_exact, start_ts, end_ts)),
    }
```

Dikkat: IBM sorgularına `dc_code_like` (wildcard), vCenter sorgularına `dc_code_exact` parametresi gider (VCENTER SQL'i deseni kendi içinde `'%' || ... || '%'` ile sarar).

Batch yolu (`fetch_batch_queries`) dört adlandırılmış sorgu üretir: `e_ibm`, `e_vcenter`, `e_ibm_kwh`, `e_vctr_kwh` — aynı adlandırma `dc_service.py` içindeki `energy_queries` listesinde de kullanılır.

### kW toplama (anlık güç)

`dc_service.py` (tekil DC, satır ~1008-1011):

```python
# Energy → kW (IBM + vCenter only; Loki/racks not used)
total_energy_kw = (float(ibm_w or 0) + float(vcenter_w or 0)) / 1000.0
# Total energy for billing (kWh in report period)
total_energy_kwh = float(ibm_kwh or 0) + float(vcenter_kwh or 0)
```

`energy` çıktı bloğu (satır ~1127-1133):

```python
"energy": {
    "total_kw": round(total_energy_kw, 2),
    "ibm_kw": round(float(ibm_w or 0) / 1000.0, 2),
    "vcenter_kw": round(float(vcenter_w or 0) / 1000.0, 2),
    "total_kwh": round(total_energy_kwh, 2),
    "ibm_kwh": round(float(ibm_kwh or 0), 2),
    "vcenter_kwh": round(float(vcenter_kwh or 0), 2),
},
```

Özet formüller:
- `ibm_kw = ibm_w / 1000`
- `vcenter_kw = vcenter_w / 1000`
- `total_kw = (ibm_w + vcenter_w) / 1000`
- `total_kwh = ibm_kwh + vcenter_kwh` (SQL'den gelen kWh değerleri zaten kWh biriminde olduğu için ek dönüşüm yok)

### Batch satır eşleme (DC bazında map)

`dc_service.py` (satır ~1531-1539):

```python
ibm_e_rows = e["e_ibm"]
vcenter_rows = e["e_vcenter"]
ibm_kwh_rows = e["e_ibm_kwh"]
vcenter_kwh_rows = e["e_vctr_kwh"]

ibm_e   = {row[0]: float(row[1] or 0) for row in ibm_e_rows if row and len(row) >= 2 and row[0]}
vctr_e  = {row[0]: float(row[1] or 0) for row in vcenter_rows if row and len(row) >= 2 and row[0]}
ibm_kwh_m   = {row[0]: float(row[1] or 0) for row in ibm_kwh_rows if row and len(row) >= 2 and row[0]}
vctr_kwh_m  = {row[0]: float(row[1] or 0) for row in vcenter_kwh_rows if row and len(row) >= 2 and row[0]}
```

Her DC için (`ibm_w=ibm_e.get(dc, 0.0)`, `vcenter_w=vctr_e.get(dc, 0.0)`, `ibm_kwh=ibm_kwh_m.get(dc, 0.0)`, `vcenter_kwh=vctr_kwh_m.get(dc, 0.0)`) değerleri aynı tekil DC çıktı bloğuna beslenir.

### Global toplama (global_view)

DC bazında `ibm_kw` ve `vcenter_kw` değerleri toplanır (satır ~1882-1886):

```python
ei = ev = 0.0
for d in all_dc_data.values():
    e = d.get("energy", {})
    ei += float(e.get("ibm_kw", 0) or 0)
    ev += float(e.get("vcenter_kw", 0) or 0)
```

`global_dashboard` cache'inde (satır ~1950):

```python
"energy_breakdown": {"ibm_kw": round(ei, 2), "vcenter_kw": round(ev, 2)},
```

`get_global_overview` toplam kW'ı DC özetlerinden toplar (satır ~1983):

```python
"total_energy_kw": round(sum(s["stats"]["total_energy_kw"] for s in summaries), 2),
```

DC özet `stats` bloğunda her DC için (satır ~1810-1812): `total_energy_kw`, `ibm_kw`, `vcenter_kw` taşınır.

---

## Birim Dönüşümleri

| Dönüşüm | Yer | Çarpan |
|---------|-----|--------|
| W → kW | `dc_service.py` (`ibm_w/1000`, `vcenter_w/1000`) | `/ 1000` |
| W (anlık) → kWh (15 dk aralık) | SQL (`*_KWH` sorguları) | `* (15.0 / 60.0) / 1000.0` |

kWh formülünün mantığı (`energy.py` yorumundan):
- Veri ~15 dakikada bir toplanır (günde 96 örnek).
- Her timestamp'te tüm cihazların toplam gücü (`total_watts`) hesaplanır.
- Her örnek 15 dakika = `15/60 = 0.25` saat boyunca geçerli kabul edilir.
- `watt * saat / 1000 = kWh`.

Anlık güç (kW) hesabında AVG kullanıldığı için ekstra aralık ölçeklemesi yoktur (`energy.py` yorumu: *"No extra scaling by interval count is needed."*). UI'de rapor periyodu bir veya daha fazla gün ise bu değer "günlük ortalama" olarak gösterilir.

---

## Caching

Enerji sorguları için doğrudan ayrı bir cache katmanı yoktur; değerler daha büyük dashboard cache'lerinin parçası olarak saklanır:

- `get_all_datacenters_summary` içinde batch enerji sorguları bir thread pool ile çalıştırılır (`fut_energy = pool.submit(_run_group, energy_queries)`).
- Sonuçlar `global_dashboard:{start}:{end}` anahtarıyla cache'e yazılır (`energy_breakdown` dahil).
- `get_global_overview`, `global_overview:{start}:{end}` anahtarıyla cache kullanır; cache miss durumunda `get_all_datacenters_summary` üzerinden türetilir.
- Tekil DC enerji değerleri (`energy` bloğu) DC detay cache'inin parçasıdır.

Time range `anchor_latest` ise `_smart_1h_tr(tr)` ile normalize edilir ve cache anahtarı buna göre belirlenir.

---

## Özet

- Enerji yalnızca iki kaynaktan hesaplanır: **vCenter** (`vmhost_metrics.power_usage`) ve **IBM** (`ibm_server_power.power_watts`). Loki/rack verisi kullanılmaz.
- **kW** = aralık içindeki `AVG(power)` watt değerinin `/1000`'i; **kWh** = her timestamp'in toplam wattının `* (15/60) / 1000` ile çarpılıp toplanması (15 dakikalık örnekleme varsayımı).
- Tekil sorgular DC'yi vCenter'da ILIKE (`%dc%`), IBM tekilde wildcard, IBM batch'te regex (`DC#|AZ#|ICT#`) ile eşler; batch vCenter eşlemesi `datacenter_metrics` üzerinden pattern listesiyle yapılır.
- `dc_service.py` per-DC `total_kw`/`total_kwh` üretir ve global_view için `ibm_kw`/`vcenter_kw` breakdown'ını toplar; sonuçlar dashboard cache anahtarlarında saklanır.

**Belirsizlikler / Notlar:**
- kWh sorgularındaki çarpan SQL'de `15.0/60.0` olarak sabittir; gerçek örnekleme aralığı 15 dk'dan farklıysa kWh değeri orantılı olarak yanlış olur. Bu, kodda belgelenmiş bir varsayımdır (örnekleme sıklığı veriden teyit edilmez).
- `EnergyAdapter` `PlatformAdapter` (base.py) soyut sınıfından türemiyor; bağımsız bir sınıf olarak tanımlı. Yine de `dc_service.py` enerji sorgularını çoğunlukla doğrudan kendi metotlarıyla (`get_ibm_energy` vb.) ve inline `energy_queries` listesiyle çalıştırıyor — `energy_adapter.py`'nin çağrıldığı yere bu kapsamda rastlanmadı (sorgu metinleri özdeş).
