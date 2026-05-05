# Executor brief: Global View prefetch + Dash cache optimizasyonu

Bu belge, kullanıcı testleri sonrası kod tabanı taramasıyla üretilmiştir. Workspace içinde `.cursor/debug-13edb8.log` bulunamadı; Executor çalışırken NDJSON / container loglarını ekte toplamalıdır.

---

## 1. Mimari özet (değiştirmeden önce oku)

| Katman | Dosya / servis | Rol |
|--------|----------------|-----|
| UI | `src/pages/global_view.py`, `app.py` | Globe pin, `building-reveal-timer`, `advance_to_floor_map`, rack `clickData` |
| Prefetch | `src/services/global_view_prefetch.py` | Phase 1: summary + `get_dc_details` + `get_dc_racks` + `build_floor_map_figure`. Phase 2: tüm DC’ler için `get_rack_devices`. |
| Pin tıklama | `app.py` → `handle_globe_pin_click` | Her tıkta `warm_dc_priority(dc_id)` (daemon thread + thread pool). |
| Periyodik | `app.py` → `refresh_global_view_prefetch` | `dcc.Interval` 900_000 ms → `trigger_background(tr)`. |
| HTTP istemcisi | `src/services/api_client.py` | `_api_cache_get_with_stale`: RAM hit → `_clone`; miss → HTTP. Thread-local `httpx.Client`. |
| Dash RAM cache | `src/services/cache_service.py` | LRU `OrderedDict`, `MAX_SIZE=2048`. |
| Floor map figür | `src/pages/floor_map.py` | `_FIG_CACHE` (LRU+TTL), `build_floor_map_figure`. |
| API | `services/datacenter-api` | `dc_service.get_*` + `app/core/cache_backend.py` (Redis + TTLCache memory, singleflight). |

**Önemli:** Global View veri yolu **`datacenter-api`** üzerinden; `customer-api` floor map / rack payload’ını beslemez.

---

## 2. Kod tabanında tespit edilen boşluklar (öncelik sırası)

### 2.1 `is_warm(tr)` hiç kullanılmıyor

- Tanım: `src/services/global_view_prefetch.py` içinde `is_warm`, `last_warm_stats`.
- **Grep sonucu:** projede `is_warm` çağrısı yok (sadece docstring / tanım).
- **Sonuç:** UI veya callback’ler “Phase 1 bitti mi?” bilgisine göre davranamıyor; kullanıcı prefetch bitmeden pin’e basınca her şey “yavaş” hissedilir.

**Yönerge:**  
- `is_warm(tr)` ve isteğe bağlı `last_warm_stats(tr)` değerlerini `dcc.Store` veya mevcut bir store’a yazan hafif bir callback veya `build_global_view` içinde clientside olmayan tek seferlik server verisi ile expose et.  
- `advance_to_floor_map` veya globe → building geçişinde: `is_warm` false ise ya (a) kısa bekleme + yeniden dene ya (b) loading metni ya (c) sadece `get_dc_racks` + figure’ı önceliklendir (Phase 1’in zaten doldurduğu cache’e güven). Davranışı ürünle netleştir; ölçülebilir kabul kriteri tanımla (ör. cold pin → floor map < X s, warm → < Y s).

### 2.2 Phase 2 (tüm rack `get_rack_devices`) ile kullanıcı tıklaması yarışıyor

- Phase 2, Phase 1 bitince daemon thread’de `_DEVICE_WORKERS` (12) ile **tüm** `(dc_id, rack)` çiftlerini dolduruyor.
- Aynı anda kullanıcı floor map’te tıklıyor → aynı `api_client` + `datacenter-api` kaynakları.
- `warm_dc_priority` da aynı DC için tekrar `get_rack_devices` çağırabilir (cache hit ile ucuz olmalı; yine de thread + Redis/DB yükü var).

**Yönerge:**  
- Phase 2 için **üst sınır** (ör. ilk N rack veya sadece “aktif” DC’ler) veya **düşük öncelikli** kuyruk (batch arası `time.sleep(0)` yerine küçük yield).  
- Kullanıcı `current-view-mode == floor_map` iken Phase 2’yi **duraklat** / worker sayısını düşür (state `dcc.Store` veya thread-safe flag).  
- Metrik: `last_warm_stats` içine `phase2_paused`, `pairs_skipped` ekle.

### 2.3 Phase 1d floor map figürleri **sıralı** üretiliyor

```python
for dc_id, racks in racks_by_dc.items():
    build_floor_map_figure(racks, dc_id=dc_id)
```

**Yönerge:** Sınırlı paralellik (ör. 4 worker) ile figür üret; sıra bağımsız. Hata ve log formatını koru.

### 2.4 Periyodik prefetch ile `warm` TTL aynı pencere

- `GLOBAL_VIEW_PREFETCH_INTERVAL_SECONDS = 900` hem interval hem “skip TTL” ile uyumlu; ancak `tr` anahtarı (`_tr_key`) değişmedikçe 15 dk içinde **tekrar warm atlanıyor**.
- Kullanıcı preset değiştirirse `tr` değişmeli; edge case: store’da aynı dict referansı → anahtar stabil mi kontrol et.

**Yönerge:** `trigger_background` çağrılmadan önce `tr`’nin serialize edildiği yolu logla; gerekirse “force refresh” bayrağı (admin) ekle.

### 2.5 `handle_globe_pin_click` ikinci tıkta erken dönüş

- `dc_id == last_dc_id` iken `mode` `"building"` dönüyor; `warm_dc_priority` yine çağrılıyor (iyi).
- Panel `no_update`: bilinçli; regression testi: çift tıklamada floor map süresi.

---

## 3. `api_client` / `cache_service` (Dash süreci)

- `_api_cache_get_with_stale`: başarılı yolda RAM okunuyor; tüm endpoint’ler için “stale sadece hata anında” değil, **normal hit** davranışı var. Ürün gereksinimi: bazı uçlar için TTL / invalidation gerekebilir — dokümante et.
- `get_rack_devices` için NDJSON loglar (`rack_devices_memory_*`) hâlâ var; doğrulama bittikten sonra kaldırılmalı veya `DEBUG` env ile sarılmalı.
- `cache_service`: LRU + 2048; rack_device anahtarlarını **ayrı namespace / ayrı cap** ile izole etmek (ileri seviye) eviction’ı azaltır.

**Yönerge:** Executor, prod öncesi log gürültüsünü kaldırsın veya `os.environ.get("GV_DEBUG_CACHE")` ile sar.

---

## 4. `datacenter-api` cache_backend

- Bellek isabetinde Redis’e yazım: **`SET EX NX`** (tekrarlayan `setex` kaldırıldı).
- `customer-api` aynı mantıkla hizalandı.

**Yönerge:** Redis sürümü / `redis-py` imzası uyumluluğunu CI’da doğrula. Regresyon: memory hit + Redis down senaryosu.

---

## 5. Ölçüm ve kabul kriterleri (zorunlu)

Executor şunları **sayı olarak** raporlamalı:

1. Soğuk başlangıç: Global View açılışından itibaren Phase 1 `critical_ms`, `dc_count`, `rack_count`, `figure_count` (`global_view_prefetch` logları).
2. Phase 2: `device_request_count`, `device_ms` (ve mümkünse toplam HTTP sayısı).
3. Pin → floor map: `advance_to_floor_map` tetiklenmesinden önce/sonra süre (gerekirse `app.py`’ye geçici timer log).
4. Rack panel: `show_rack_detail_get_rack_devices_ms` (app.py NDJSON) + `api_client` `rack_devices_memory_hit` oranı.
5. `datacenter-api`: ilgili endpoint için ortanca latency (Prometheus / log).

**Kabul örneği (takımca güncellenir):**  
- Warm path: rack tıklamasında `api_ms` p95 < 500 ms (backend sıcakken).  
- Phase 2 aktifken kullanıcı tıklaması: p95 regresyonu < %X (baseline’a göre).

---

## 6. Test planı

- `pytest` mevcut: `tests/test_api_client_itsm.py`, `test_floor_map.py`, `services/datacenter-api/tests/test_dc_service.py` (rack singleflight).
- Eklenmeli: `global_view_prefetch` için mock `api_client` ile Phase 1 sırası / `is_warm` store entegrasyonu (integration light).

---

## 7. Teslim checklist

- [ ] `is_warm` / istatistik UI veya callback ile tüketiliyor.  
- [ ] Phase 2 throttling veya floor_map sırasında pause politikası kod + log.  
- [ ] Phase 1d figürler sınırlı paralel.  
- [ ] Debug NDJSON temizliği veya env sarımı.  
- [ ] Ölçüm tablosu + karar: “prefetch işe yarıyor” kanıtı.  

---

## 8. Referans dosyalar (kısa liste)

- `src/services/global_view_prefetch.py`  
- `src/pages/global_view.py` (prefetch trigger, interval)  
- `app.py` (`handle_globe_pin_click`, `advance_to_floor_map`, `show_rack_detail`, `refresh_global_view_prefetch`)  
- `src/services/api_client.py`, `src/services/cache_service.py`  
- `services/datacenter-api/app/core/cache_backend.py`, `app/services/dc_service.py`  

---

*Bu brief, Cursor oturumunda yapılan statik kod incelemesiyle üretilmiştir; kullanıcı logları workspace’e yazılmadıysa Executor kendi koşularından örnek NDJSON satırları eklemelidir.*
