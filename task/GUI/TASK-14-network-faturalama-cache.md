# TASK-14 — Network Faturalandırma: Veri Bazlı Hesap + Yarım Cache Temizliği

**Tip:** Hesaplama / Cache · **Efor:** M · **Öncelik:** Orta-Yüksek

## Hedef
Network tarafında müşteri hesaplamaları için (örn. 30 gün seçildiğinde) **zaman tabanlı değil,
sadece veriye yönelik** bir hesaplama algoritması kurulacak.
- Varsayılan süre: **30 gün**
- **7 günde bir "yarı (half) cache" temizlenecek**

## Mevcut durum

```python
# shared/network/backbone_billing.py  (15 satır - hepsi bu)
BPS_PER_MBIT = 1_000_000
def p95_bps_to_mbit(p95_total_bps): return float(p95_total_bps or 0) / BPS_PER_MBIT
def estimate_backbone_cost_tl(p95_total_bps, unit_price_tl_per_mbit):
    return round(p95_bps_to_mbit(p95_total_bps) * float(unit_price_tl_per_mbit or 0), 2)
```

Fiyat kaynağı — `services/datacenter-api/app/db/queries/crm_network_pricing.py`:
```python
NETWORK_DC_ACCESS_PRODUCT_ID   = "e2f585bb-c2e0-f011-8406-6045bd9c244d"   # = 000BLT-208
NETWORK_DC_ACCESS_PANEL_KEY    = "network_dc_access"
NETWORK_DC_ACCESS_RESOURCE_UNIT= "Mbit"
GET_PRICE_OVERRIDE_FOR_PANEL   # gui_crm_price_override önce
CATALOG_TL_PRICE_FOR_PRODUCT   # sonra discovery_crm_productpricelevels
```
Veri: `/datacenters/{dc}/network/95th-percentile` → `zabbix_network.py`, TimescaleDB `time_bucket`.

## "Zaman tabanlı değil, veriye yönelik" ne demek — yorum

Bugün: kullanıcı 30 gün seçer → o pencerede **takvim bazlı** 95p hesaplanır. Sorun:
veri boşlukları (collector durması, bakım) varsa 30 günün bir kısmı boş olsa da tam pencere üzerinden hesap yapılır.

**Hedef davranış:** hesaplama **mevcut veri noktaları** üzerinden yapılmalı:
- 95p, pencere içindeki **gerçek örnek** kümesi üzerinden hesaplanır (boş bucket'lar sıfır sayılmaz)
- Sonuçla birlikte **veri kapsama oranı** (`data_coverage_pct = dolu_bucket / beklenen_bucket`) döndürülür
- Kapsama eşiğin altındaysa (örn. < %80) UI uyarı gösterir — fatura sessizce düşük çıkmasın

> Bu yorumu paydaşla teyit edin; "veriye yönelik" ifadesi başka bir şey de kastediyor olabilir
> (örn. faturalamanın transfer hacmine göre yapılması).

## Yarım (half) cache temizliği

7 günde bir cache'in **yarısı** temizlenecek. Amaç: tüm cache'in aynı anda soğumasını engellemek
(thundering herd) ama veriyi de tazelemek. Uygulama:

```python
# Deterministik yarı seçimi - her turda diğer yarı temizlenir
def half_cache_keys(keys: list[str], epoch_week: int) -> list[str]:
    """hash(key) % 2 == epoch_week % 2 olanları döndür."""
    return [k for k in sorted(keys) if (hash_stable(k) % 2) == (epoch_week % 2)]
```
- `hash_stable`: `zlib.crc32(key.encode())` gibi süreçler arası tutarlı bir hash (`hash()` Python'da
  süreçler arası tutarsızdır — **kullanmayın**)
- Scheduler: haftalık job; `docs/CACHE_STRATEGY_COMPARISON.md` ilkesi gereği
  temizlenen anahtarların `{key}:last_good` gölgesi **korunur**

## Yapılacaklar

- [ ] Paydaş teyidi: "veriye yönelik hesap" tanımı
- [ ] `shared/network/backbone_billing.py`'yi genişlet:
      - `compute_p95_from_samples(samples)` — boş bucket'ları hariç tutar
      - `data_coverage(samples, expected_buckets)` → oran döner
      - `estimate_backbone_cost_tl(...)` imzası korunur (geriye dönük uyum)
- [ ] `/network/95th-percentile` cevabına `data_coverage_pct`, `sample_count`, `window_start/end` ekle
- [ ] Varsayılan aralık **30d** (frontend + backend default; `src/utils/time_range.py`)
- [ ] Yarım cache temizleyici: `services/datacenter-api/app/services/scheduler_service.py`'ye
      haftalık job; `dl:fecache:network:*` deseninde çalışır
- [ ] Konfigürasyon: `NETWORK_BILLING_DEFAULT_RANGE_DAYS=30`, `NETWORK_HALF_CACHE_INTERVAL_DAYS=7`,
      `NETWORK_MIN_COVERAGE_PCT=80`
- [ ] UI: kapsama oranı düşükse uyarı rozeti + hesaplanan Mbit ve TL yanında "N örnek / %M kapsama"
- [ ] Fiyat GUID'ini registry'ye taşı (TASK-10 ile ortak)

## Doğrulama SQL'leri

```sql
-- 1) Veri kapsama: 30 günde beklenen vs gerçek bucket sayısı (örnek: 1 saatlik bucket)
WITH b AS (
  SELECT time_bucket('1 hour', collection_timestamp) AS bucket, COUNT(*) AS ornek
  FROM   public.raw_zabbix_network_interface_metrics_v
  WHERE  collection_timestamp > now() - interval '30 days'
    AND  loki_id ~ '^[0-9]+$'
  GROUP  BY 1
)
SELECT COUNT(*) AS dolu_bucket, 720 AS beklenen_bucket,
       ROUND(100.0*COUNT(*)/720, 1) AS kapsama_pct,
       MIN(bucket) AS ilk, MAX(bucket) AS son
FROM b;

-- 2) Boşluk (gap) analizi - hangi günlerde veri yok
SELECT date_trunc('day', collection_timestamp) AS gun, COUNT(*) AS satir
FROM   public.raw_zabbix_network_interface_metrics_v
WHERE  collection_timestamp > now() - interval '30 days'
GROUP  BY 1 ORDER BY 1;

-- 3) 95p ham hesap — platformdaki gerçek desen (1 saatlik bucket, sonra percentile_cont)
--    Kaynak: services/datacenter-api/app/db/queries/zabbix_network.py
WITH hourly AS (
  SELECT time_bucket('1 hour', collection_timestamp) AS ts,
         AVG(COALESCE(bits_received,0))::double precision AS avg_rx_bps,
         AVG(COALESCE(bits_sent,0))::double precision     AS avg_tx_bps
  FROM   public.raw_zabbix_network_interface_metrics_v
  WHERE  collection_timestamp > now() - interval '30 days'
    AND  loki_id ~ '^[0-9]+$'
  GROUP  BY 1
)
SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_rx_bps)                AS p95_rx_bps,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_tx_bps)                AS p95_tx_bps,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY (avg_rx_bps+avg_tx_bps))   AS p95_total_bps,
       COUNT(*) AS dolu_bucket
FROM   hourly;
-- p95_total_bps / 1e6 = Mbit  (shared/network/backbone_billing.py :: p95_bps_to_mbit)

-- 4) Fiyat kaynağı (bulutwebui)
SELECT po.productid, po.unit_price_tl, po.currency, po.updated_at
FROM   gui_crm_price_override po
WHERE  po.productid = 'e2f585bb-c2e0-f011-8406-6045bd9c244d';
```

```bash
# API kapsama alanı dönüyor mu
curl -s "http://10.134.52.250:8000/api/v1/datacenters/DC13/network/95th-percentile?range=30d" \
  | python3 -m json.tool

# Yarım cache temizliği sonrası anahtar sayısı yaklaşık yarıya inmeli
docker exec bulutistan-redis redis-cli -n 2 --scan --pattern "dl:fecache:network:*" | wc -l
```

## Kabul kriterleri
- [ ] 95p, boş bucket'ları hariç tutan örnek kümesi üzerinden hesaplanıyor
- [ ] Cevapta `data_coverage_pct` + `sample_count` var; kapsama < eşik ise UI uyarıyor
- [ ] Varsayılan aralık 30 gün (URL parametresi verilmediğinde)
- [ ] Haftalık job cache anahtarlarının ~%50'sini siliyor, `last_good` gölgeleri duruyor
- [ ] Temizlik sonrası ilk isteklerde 500 yok, p95 < 2500 ms (soğuk SLO)
- [ ] API 95p değeri doğrulama SQL'i ile ±%2 uyumlu

## Cursor / Claude Code prompt

```
Bağlam: task/GUI/00-ortam-ve-dogrulama-rehberi.md, docs/CACHE_STRATEGY_COMPARISON.md,
task/query-map/08-zabbix-monitoring.md, shared/network/backbone_billing.py,
services/datacenter-api/app/db/queries/{zabbix_network.py,crm_network_pricing.py},
services/datacenter-api/app/services/scheduler_service.py, src/utils/time_range.py

Görev: Network faturalandırmasını veri-bazlı hesaba çevir ve 7 günlük yarım cache temizliği ekle.

1. shared/network/backbone_billing.py'yi genişlet (mevcut iki fonksiyonun imzası korunacak):
   - compute_p95_from_samples(samples): boş/eksik bucket'ları hariç tutarak 95p döner
   - data_coverage(sample_count, expected_buckets) -> yüzde
   Saf fonksiyonlar olsun, unit test edilebilir kalsın.
2. /datacenters/{dc}/network/95th-percentile cevabına data_coverage_pct, sample_count,
   window_start, window_end ekle. Varsayılan range 30d olsun.
3. Yarım cache temizleyici: scheduler_service.py'ye haftalık job.
   Anahtar seçimi zlib.crc32(key) % 2 == (hafta_no % 2) ile deterministik olsun.
   Python'un yerleşik hash()'ini KULLANMA (süreçler arası tutarsız).
   {key}:last_good gölgelerini SİLME.
4. Konfig: NETWORK_BILLING_DEFAULT_RANGE_DAYS=30, NETWORK_HALF_CACHE_INTERVAL_DAYS=7,
   NETWORK_MIN_COVERAGE_PCT=80 -> .env.example + docker-compose.yml.
5. UI: kapsama oranı eşiğin altındaysa uyarı rozeti; Mbit ve TL yanında örnek sayısı/kapsama göster.
6. crm_network_pricing.py'deki hard-code productid'yi registry lookup'a çevir (TASK-10 ile ortak).
7. tests/: p95 boş bucket senaryosu, kapsama hesabı, yarım cache seçiminin deterministikliği.

Kısıt: Mevcut estimate_backbone_cost_tl davranışı değişmemeli (geriye dönük uyum + test).
```

## İlgili
TASK-11 ile aynı endpoint ailesi — birlikte test edin.
