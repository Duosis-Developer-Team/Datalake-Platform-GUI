# FAZ 2 — Redis Cache, Provider Adapters, Dinamik Time Filters

> **Hedef:** FAZ 1'deki monolitik `DatabaseService`'i (1135 satır, 25+ metot) üç yeni mimari
> katmanla evrimleştirmek: dağıtık Redis cache, platform-bağımsız adapter pattern ve merkezi
> time filter dependency.
>
> **Öncül:** FAZ 1 tamamlandı (%92 coverage, 0 yorum satırı). Bu plan üzerine inşa eder.
>
> **Executer Referansları:**
> - Anayasa: `task/microservis_remake/mcrsrvc_skills.md`
> - Öğretiler: `task/microservis_remake/mcrsrvc_lessons.md`
> - Test Standartları: `task/microservis_remake/mcrsrvc_tests.md`

---

> [!CAUTION]
> ## EXECUTER İÇİN MUTLAK YASAKLAR
>
> 1. **Yazılacak veya değiştirilecek HİÇBİR DOSYADA TEK BİR YORUM SATIRI (`#`) DAHİ OLMAYACAK.**
>    Docstring YASAK. Fonksiyon/sınıf/değişken isimleri kendini açıklayacak.
>    Tek istisna: `TODO:` ve `FIXME:` etiketleri.
>
> 2. **`mcrsrvc_lessons.md`'DEKİ ÖĞRETİLER İHLAL EDİLMEYECEK.** Özellikle:
>    - `_DC_CODE_RE` regex pattern'i BİREBİR korunacak (ÖGRT-001)
>    - ThreadPoolExecutor 4-worker paralel batch mantığı bozulmayacak (ÖGRT-002)
>    - IBM `set()` deduplikasyonu ve ortalama hesaplama yapısı korunacak (ÖGRT-003)
>    - Birim dönüşüm formülleri değiştirilmeyecek (ÖGRT-004)
>    - Cache TTL (1200s) > Scheduler aralığı (900s) ilişkisi korunacak (ÖGRT-005)
>
> 3. **HER ADIM DOĞRULANMADAN BİR SONRAKİNE GEÇİLMEYECEK.** Kanıt: test çıktısı, curl yanıtı
>    veya log.
>
> 4. **FRONTEND DOSYALARINA DOKUNULMAYACAK.** `app.py`, `src/pages/`, `src/components/`,
>    `assets/` dizinleri bu fazda READ-ONLY.

---

## MİMARİ GENEL BAKIŞ

### Mevcut Durum (FAZ 1 Çıktısı)

```
backend/app/
├── main.py                    ← FastAPI + lifespan (DB pool init/teardown)
├── config.py                  ← Pydantic BaseSettings (yalnızca DB params)
├── routers/
│   ├── datacenters.py         ← GET /summary, GET /{dc_code} (start/end Query params)
│   ├── dashboard.py           ← GET /overview (start/end Query params)
│   ├── customers.py           ← GET /customers, GET /{name}/resources
│   └── queries.py             ← GET /{query_key} (params Query string)
├── services/
│   ├── db_service.py          ← 1135 satır MONOLITH (tüm iş mantığı burada)
│   ├── cache_service.py       ← In-memory TTLCache (thread-safe, 1200s TTL)
│   ├── scheduler_service.py   ← APScheduler (15dk refresh + Boyner warm-up)
│   └── query_overrides.py     ← JSON file-based SQL override sistemi
├── models/schemas.py          ← 146 satır Pydantic response modelleri
├── db/queries/
│   ├── nutanix.py             ← 164s: 5 tekil + 6 batch SQL (cluster_metrics)
│   ├── vmware.py              ← 146s: 4 tekil + 5 batch SQL (datacenter_metrics)
│   ├── ibm.py                 ← 150s: 5 tekil + 5 batch + 5 batch_raw SQL (server_general)
│   ├── energy.py              ← 102s: 4 tekil + 4 batch SQL (server_power + vmhost_metrics)
│   ├── customer.py            ← 535s: 25 SQL (VM dedup, Veeam, Zerto, NetBackup, Storage)
│   ├── loki.py                ← 19s:  2 SQL (DC list + DC list no status)
│   └── registry.py            ← 295s: 28 kayıtlı QUERY_REGISTRY entry
└── utils/time_range.py        ← 70s: preset_to_range, time_range_to_bounds
```

### Hedef Durum (FAZ 2 Çıktısı)

```
backend/app/
├── main.py                         [GÜNCELLE] Redis lifespan + health check güncelle
├── config.py                       [GÜNCELLE] Redis + Cache TTL ayarları
├── core/                           [YENİ DİZİN]
│   ├── __init__.py
│   ├── redis_client.py             [YENİ] Async Redis bağlantı yönetimi
│   ├── cache_backend.py            [YENİ] Dual-layer cache (Redis L1 + Memory L2)
│   └── time_filter.py              [YENİ] FastAPI Depends() time filter
├── adapters/                       [YENİ DİZİN]
│   ├── __init__.py
│   ├── base.py                     [YENİ] Abstract PlatformAdapter interface
│   ├── nutanix_adapter.py          [YENİ] Nutanix sorgu + dönüşüm
│   ├── vmware_adapter.py           [YENİ] VMware sorgu + dönüşüm
│   ├── ibm_power_adapter.py        [YENİ] IBM regex + dedup + ortalama
│   ├── energy_adapter.py           [YENİ] Enerji metrikleri (W→kW, kWh)
│   └── customer_adapter.py         [YENİ] 16-sorgu müşteri pipeline
├── services/
│   ├── db_service.py               [GÜNCELLE] Adapter delegasyonu, ~400 satıra düşecek
│   ├── cache_service.py            [GÜNCELLE] cache_backend.py'ye proxy
│   ├── scheduler_service.py        [GÜNCELLE] Redis health check ekleme
│   └── query_overrides.py          [DEĞİŞMEZ]
├── models/schemas.py               [DEĞİŞMEZ]
├── db/queries/                     [DEĞİŞMEZ — tüm SQL modülleri olduğu gibi kalır]
├── utils/time_range.py             [DEĞİŞMEZ]
└── tests/
    ├── test_redis_client.py        [YENİ]
    ├── test_cache_backend.py       [YENİ]
    ├── test_time_filter.py         [YENİ]
    ├── test_nutanix_adapter.py     [YENİ]
    ├── test_vmware_adapter.py      [YENİ]
    ├── test_ibm_adapter.py         [YENİ]
    ├── test_energy_adapter.py      [YENİ]
    ├── test_customer_adapter.py    [YENİ]
    └── test_regression_parity.py   [YENİ]
```

### Veri Akış Diyagramı

```
HTTP İstek (+ preset/start/end)
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ TimeFilter Dependency (core/time_filter.py)                 │
│ - ?preset=7d → {start: "2026-03-05", end: "2026-03-11"}    │
│ - ?start=X&end=Y → custom range                            │
│ - Parametre yok → default_time_range() (son 7 gün)         │
└───────────────────────────┬─────────────────────────────────┘
                            │ TimeFilter objesi
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Router (datacenters/dashboard/customers)                     │
│ - db.get_all_datacenters_summary(tf.to_dict())              │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ cache_service.get(cache_key)                                │
│         │                                                   │
│    ┌────▼────┐     ┌──────────┐                             │
│    │ Redis   │────▶│ HIT?     │──── Evet → JSON döndür      │
│    │ (L1)    │     │ (cache_  │                              │
│    └─────────┘     │ backend) │                              │
│                    └────┬─────┘                              │
│                    Hayır│                                    │
│                    ┌────▼────┐                               │
│                    │ Memory  │──── HIT? → döndür             │
│                    │ (L2)    │                               │
│                    └────┬────┘                               │
│                    Hayır│                                    │
└─────────────────────────┼───────────────────────────────────┘
                          │ MISS
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ DatabaseService._fetch_all_batch()                          │
│                                                             │
│  ThreadPoolExecutor(max_workers=4)                          │
│  ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌──────────┐     │
│  │Thread-1  │ │Thread-2  │ │Thread-3    │ │Thread-4  │     │
│  │Nutanix   │ │VMware    │ │IBMPower    │ │Energy    │     │
│  │Adapter   │ │Adapter   │ │Adapter     │ │Adapter   │     │
│  │6 sorgu   │ │5 sorgu   │ │5 batch_raw │ │4 sorgu   │     │
│  └────┬─────┘ └────┬─────┘ └─────┬──────┘ └────┬─────┘     │
│       │            │             │              │           │
│       ▼            ▼             ▼              ▼           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ _aggregate_dc() — birim dönüşüm + yapı birleştirme  │   │
│  │ (Dokunulmayacak — FAZ 1'den bire bir)                │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────┘
                            │ Sonuç
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ cache_service.set(cache_key, result)                        │
│ → Redis (L1) + Memory (L2) → her ikisine de yazar          │
└─────────────────────────────────────────────────────────────┘
```

---

## ADIM 1: Redis Cache Katmanı

### 1.1 — config.py Güncelleme

- [ ] `Settings` sınıfına şu alanları ekle:

  | Alan | Ortam Değişkeni | Varsayılan | Açıklama |
  |------|-----------------|------------|----------|
  | `redis_host` | `REDIS_HOST` | `"localhost"` | Redis sunucu adresi |
  | `redis_port` | `REDIS_PORT` | `6379` | Redis port |
  | `redis_db` | `REDIS_DB` | `0` | Redis veritabanı numarası |
  | `redis_password` | `REDIS_PASSWORD` | `""` | Redis şifresi |
  | `redis_socket_timeout` | `REDIS_SOCKET_TIMEOUT` | `5` | Bağlantı timeout (saniye) |
  | `cache_ttl_seconds` | `CACHE_TTL_SECONDS` | `1200` | Cache TTL (ÖGRT-005: scheduler interval'den büyük olmalı) |
  | `cache_max_memory_items` | `CACHE_MAX_MEMORY_ITEMS` | `200` | In-memory L2 cache max eleman |

### 1.2 — core/redis_client.py Oluştur

**Amaç:** Redis bağlantı havuzunu singleton olarak yönetmek.

- [ ] Dosyayı oluştur, aşağıdaki public API'yi implement et:

  | Fonksiyon | Dönüş Tipi | Davranış |
  |-----------|------------|----------|
  | `init_redis_pool()` | `redis.Redis \| None` | `redis-py` sync client oluşturur. Bağlantı başarısızsa `None` döner, exception fırlatMAZ. |
  | `get_redis_client()` | `redis.Redis \| None` | Mevcut client'ı döner. Singleton pattern. |
  | `close_redis_pool()` | `None` | Client'ı kapatır. `main.py` lifespan teardown'da çağrılır. |
  | `redis_is_healthy()` | `bool` | `client.ping()` çağırır. Exception → `False`. |

- [ ] **Bağlantı parametreleri:** `config.settings`'ten al (1.1'deki alanlar).

- [ ] **Hata toleransı kuralı:** Redis erişilemezse ASLA exception fırlatma. `None` dön veya `False` dön. API'nin çalışması Redis'e bağımlı OLMAMALI.

> [!IMPORTANT]
> **Sync vs Async Karar:** Mevcut `db_service.py` tamamen senkron çalışıyor (`psycopg2` sync driver,
> `ThreadPoolExecutor` ile parallelism). Redis client da **sync** (`redis.Redis`, `redis.asyncio`
> DEĞİL) olacak. Bu tutarlılığı koru. Async geçiş FAZ 3'e bırakılacak.

### 1.3 — core/cache_backend.py Oluştur

**Amaç:** Redis (L1) + in-memory TTLCache (L2) dual-layer cache.

- [ ] Dosyayı oluştur, aşağıdaki public API'yi implement et:

  | Fonksiyon | İmza | Davranış |
  |-----------|------|----------|
  | `cache_get` | `(key: str) -> Any \| None` | L1 (Redis) kontrol → HIT ise JSON deserialize et ve dön. MISS ise L2 (memory) kontrol → HIT ise dön ve Redis'e de yaz (backfill). Her iki MISS → `None` dön. |
  | `cache_set` | `(key: str, value: Any, ttl: int \| None = None) -> None` | Redis'e JSON serialize ederek yaz (TTL ile). Aynı anda memory cache'e de yaz. Redis erişilemezse yalnızca memory'e yaz. |
  | `cache_delete` | `(key: str) -> None` | Her iki katmandan sil. |
  | `cache_flush_pattern` | `(pattern: str) -> None` | Redis'te `SCAN` ile pattern'e uyan key'leri sil. Memory cache'i tamamen temizle (pattern filtresi yok). |
  | `cache_stats` | `() -> dict` | `{"redis_available": bool, "redis_keys": int, "memory_size": int, "memory_max": int, "ttl": int}` |

- [ ] **JSON Serialization:**
  - `json.dumps` ile serialize, `json.loads` ile deserialize
  - Custom encoder gerekli: `datetime` → ISO format string, `Decimal` → `float`
  - `TypeError` yakalanıp loglansın, serialize edilemeyen veri yalnızca memory'de kalsın

- [ ] **Fallback davranışı detaylı akış:**
  ```
  cache_get("all_dc_summary:2026-03-05:2026-03-11"):
      1. redis_client = get_redis_client()
      2. if redis_client:
             raw = redis_client.get(key)
             if raw: return json.loads(raw)        ← L1 HIT
      3. value = _memory_cache.get(key)
      4. if value is not None:
             if redis_client:
                 redis_client.setex(key, ttl, json.dumps(value))  ← backfill
             return value                           ← L2 HIT
      5. return None                                ← FULL MISS
  ```

- [ ] **L2 in-memory cache:** Mevcut `cache_service.py`'deki `cachetools.TTLCache` yapısını kullan.
  Bu cache **worker process** bazında çalışır. Uvicorn `--workers 4` ile çalıştığında her worker
  kendi memory cache'ine sahiptir, ama Redis tüm worker'lar arasında paylaşılır.

### 1.4 — cache_service.py Güncelleme

**Amaç:** Mevcut public API'yi (`get`, `set`, `delete`, `clear`, `stats`) KORUYARAK arka planı
`cache_backend.py`'ye yönlendirmek.

- [ ] Mevcut dosyanın iç implementasyonunu değiştir:
  ```
  ÖNCEKI:                          SONRAKI:
  get(key) → _cache.get(key)       get(key) → cache_backend.cache_get(key)
  set(key, val) → _cache[key]=val  set(key, val) → cache_backend.cache_set(key, val)
  delete(key) → _cache.pop(key)    delete(key) → cache_backend.cache_delete(key)
  clear() → _cache.clear()         clear() → cache_backend.cache_flush_pattern("*")
  stats() → {size, max, ttl}       stats() → cache_backend.cache_stats()
  ```

- [ ] **Geriye uyumluluk testi:** `db_service.py`'deki şu çağrılar DEĞİŞMEDEN çalışmalı:
  - `cache.get(cache_key)` → satır 364, 639, 771, 789, 802
  - `cache.set(cache_key, result)` → satır 397, 674, 709, 750, 760, 783, 1091
  - Mevcut `cached` decorator da çalışmalı (satır 37-52)

- [ ] `_lock` ve thread-level senkronizasyon kaldırılsın — artık Redis handle eder.
  Memory cache erişimi de `cache_backend` içinde lock altında.

### 1.5 — main.py Güncelleme

- [ ] `lifespan` context manager güncelle:
  ```
  STARTUP:
      1. DatabaseService() → DB pool init
      2. init_redis_pool() → Redis bağlantı (başarısızsa log + devam)
      3. start_scheduler(db) → APScheduler başlat
  
  SHUTDOWN:
      1. scheduler.shutdown()
      2. close_redis_pool()
      3. db._pool.closeall()
  ```

- [ ] `/health` endpoint güncelle:
  ```python
  @app.get("/health")
  def health():
      db: DatabaseService = app.state.db
      return {
          "status": "ok",
          "db_pool": "ok" if db._pool else "unavailable",
          "redis": "ok" if redis_is_healthy() else "unavailable",
      }
  ```

### 1.6 — requirements.txt Güncelleme

- [ ] Ekle: `redis[hiredis]>=5.0.0`
- [ ] Ekle (test): `fakeredis>=2.21.0`

### 1.7 — Docker & K8s Güncelleme

- [ ] Proje kökü `docker-compose.yml`'a Redis servisini ekle:
  ```yaml
  redis:
    image: redis:7-alpine
    container_name: bulutistan-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
  ```
- [ ] `backend` servisine `REDIS_HOST: redis` environment ve `depends_on: [redis, db]` ekle
- [ ] `volumes:` bloğuna `redis_data:` ekle
- [ ] `k8s/redis/deployment.yaml` oluştur (1 replica, 256Mi memory limit)
- [ ] `k8s/redis/service.yaml` oluştur (ClusterIP, port 6379)
- [ ] `k8s/backend/configmap.yaml`'a `REDIS_HOST`, `REDIS_PORT` ekle

### ADIM 1 — Doğrulama

- [ ] `docker compose up redis -d && redis-cli -h localhost ping` → `PONG`
- [ ] `cd backend && pytest tests/test_redis_client.py tests/test_cache_backend.py -v` → PASSED
- [ ] **Fallback testi:** Redis container durdur → `curl http://localhost:8000/api/v1/datacenters/summary` → hâlâ 200 döner (memory fallback)
- [ ] **Dual-layer testi:** İlk istek → Redis MISS + DB sorgusu. `redis-cli GET "all_dc_summary:..."` → veri var. İkinci istek → Redis HIT (DB çağrılmaz).
- [ ] `curl http://localhost:8000/health` → `{"status": "ok", "db_pool": "ok", "redis": "ok"}`
- [ ] Mevcut testlerin TÜMÜ hâlâ geçiyor: `pytest tests/ -v` → 0 FAILED

---

## ADIM 2: Merkezi Time Filter Dependency

### 2.1 — core/time_filter.py Oluştur

**Amaç:** 3 router'daki tekrarlayan `start/end` Query param parsing'ini tek noktaya indirgemek
ve yeni `preset` parametresi desteği eklemek.

- [ ] FastAPI injectable class oluştur:

  ```python
  from fastapi import Query
  from app.utils.time_range import default_time_range, preset_to_range

  class TimeFilter:
      def __init__(
          self,
          start: str | None = Query(None, description="Başlangıç tarihi (YYYY-MM-DD)"),
          end: str | None = Query(None, description="Bitiş tarihi (YYYY-MM-DD)"),
          preset: str | None = Query(None, description="Preset: 1d, 7d, 30d"),
      ):
          if start and end:
              self.time_range = {"start": start, "end": end, "preset": "custom"}
          elif preset:
              self.time_range = preset_to_range(preset)
          else:
              self.time_range = default_time_range()

      def to_dict(self) -> dict:
          return self.time_range
  ```

**Neden bu yapı?**
Mevcut 3 router'da (`datacenters.py:21`, `dashboard.py:21`, `customers.py:27`) aynı mantık
tekrarlanıyor:
```python
time_range = {"start": start, "end": end} if (start and end) else None
```
Bu durum, yeni bir `preset` parametresi eklendiğinde 3 dosyayı birden değiştirmeyi gerektiriyor.
`TimeFilter` class'ı bu mantığı TEK noktaya taşıyor.

### 2.2 — Router'ları Güncelle

- [ ] `datacenters.py` refactor:
  ```
  ÖNCEKİ (satır 15-22):
  @router.get("/datacenters/summary")
  def list_datacenters(
      start: Optional[str] = Query(None),
      end: Optional[str] = Query(None),
      db: DatabaseService = Depends(get_db),
  ):
      time_range = {"start": start, "end": end} if (start and end) else None
      return db.get_all_datacenters_summary(time_range)

  SONRAKI:
  @router.get("/datacenters/summary")
  def list_datacenters(
      tf: TimeFilter = Depends(),
      db: DatabaseService = Depends(get_db),
  ):
      return db.get_all_datacenters_summary(tf.to_dict())
  ```
- [ ] `datacenters.py` `datacenter_detail` fonksiyonunu aynı pattern ile güncelle
- [ ] `dashboard.py` `dashboard_overview` fonksiyonunu aynı pattern ile güncelle
- [ ] `customers.py` `customer_resources` fonksiyonunu aynı pattern ile güncelle

### 2.3 — Preset Endpoint Davranışları

| Parametre Kombinasyonu | Sonuç |
|------------------------|-------|
| `?preset=7d` | Son 7 gün (`preset_to_range("7d")`) |
| `?preset=30d` | Son 30 gün (`preset_to_range("30d")`) |
| `?preset=1d` | Bugün (`preset_to_range("1d")`) |
| `?start=2026-03-01&end=2026-03-10` | Custom range. Preset varsa yoksayılır. |
| Hiçbir parametre | `default_time_range()` → Son 7 gün |
| `?preset=invalid_value` | `preset_to_range` fallback → Son 7 gün |

### ADIM 2 — Doğrulama

- [ ] `curl "http://localhost:8000/api/v1/datacenters/summary?preset=7d"` → JSON array
- [ ] `curl "http://localhost:8000/api/v1/datacenters/summary?preset=30d"` → JSON array
- [ ] `curl "http://localhost:8000/api/v1/datacenters/summary?start=2026-03-01&end=2026-03-10"` → JSON
- [ ] `curl "http://localhost:8000/api/v1/datacenters/summary"` → varsayılan 7d ile JSON array
- [ ] Swagger UI'da (`/docs`) tüm endpoint'lerde `preset` parametresi görünüyor
- [ ] `cd backend && pytest tests/test_time_filter.py -v` → PASSED
- [ ] Mevcut `test_endpoints.py` testleri hâlâ geçiyor (geriye uyumluluk)

---

## ADIM 3: Provider Adapter Pattern

### 3.0 — Mimari Karar: Ne Taşınacak, Ne Kalacak

`db_service.py`'nin mevcut yapısında şu sorun var: 25+ getter metot (`get_nutanix_host_count`,
`get_vmware_counts`, `get_ibm_energy` vb.) doğrudan belirli SQL sorgularını çağırıyor.
Bu metotlar platform-spesifik, ama `DatabaseService` sınıfı platform-agnostik olmalı.

**Taşınacaklar (adapter'lara):**
- Platform-spesifik getter'lar (satır 215-267: 14 metot)
- IBM `_extract_dc` ve `set()` deduplikasyon mantığı (satır 463-523)
- Customer 16-sorgu pipeline'ı (satır 816-1092)

**Kalacaklar (db_service.py'de):**
- `_init_pool`, `_get_connection` → bağlantı yönetimi
- `_run_value`, `_run_row`, `_run_rows` → genel DB utility
- `_aggregate_dc` → platform-agnostik veri birleştirme
- `_fetch_all_batch` → ThreadPoolExecutor orkestrasyon (adapter'ları çağıracak)
- `_rebuild_summary` → cache + summary oluşturma
- `get_dc_details`, `get_all_datacenters_summary`, `get_global_*` → public API
- `warm_cache`, `warm_additional_ranges`, `refresh_all_data` → scheduler entegrasyonu

### 3.1 — adapters/base.py — Soyut Interface

- [ ] Dosyayı oluştur:

  ```python
  from abc import ABC, abstractmethod
  from typing import Any, Callable
  from contextlib import contextmanager

  class PlatformAdapter(ABC):
      def __init__(self, get_connection: Callable, run_value, run_row, run_rows):
          self._get_connection = get_connection
          self._run_value = run_value
          self._run_row = run_row
          self._run_rows = run_rows

      @abstractmethod
      def fetch_single_dc(
          self, cursor, dc_param: str, start_ts, end_ts
      ) -> dict[str, Any]:
          ...

      @abstractmethod
      def fetch_batch_queries(
          self, dc_list: list[str], pattern_list: list[str], start_ts, end_ts
      ) -> list[tuple[str, str, tuple]]:
          ...
  ```

**Neden `run_value/run_row/run_rows` inject ediliyor?**
Bu 3 static metot `db_service.py`'de tanımlı ve exception handling + ROLLBACK mantığı içeriyor
(satır 105-144). Her adapter aynı hata yönetimini kullanmalı. Kopyalamak yerine inject et.

### 3.2 — adapters/nutanix_adapter.py

- [ ] `NutanixAdapter(PlatformAdapter)` oluştur
- [ ] `fetch_single_dc` implementasyonu — şu metotları kapsar:

  | db_service Metodu (kaldırılacak) | Kullandığı SQL | adapter'daki karşılığı |
  |----------------------------------|----------------|------------------------|
  | `get_nutanix_host_count` (s.215) | `nq.HOST_COUNT` | `result["host_count"]` |
  | `get_nutanix_vm_count` (s.218) | `nq.VM_COUNT` | `result["vm_count"]` |
  | `get_nutanix_memory` (s.221) | `nq.MEMORY` | `result["memory"]` → (cap, used) tuple |
  | `get_nutanix_storage` (s.224) | `nq.STORAGE` | `result["storage"]` → (cap, used) tuple |
  | `get_nutanix_cpu` (s.227) | `nq.CPU` | `result["cpu"]` → (cap, used) tuple |

- [ ] `fetch_batch_queries` dönüşü — batch modda query listesi:
  ```python
  return [
      ("n_host",     nq.BATCH_HOST_COUNT,     (dc_list, pattern_list, start_ts, end_ts)),
      ("n_vm",       nq.BATCH_VM_COUNT,       (dc_list, pattern_list, start_ts, end_ts)),
      ("n_mem",      nq.BATCH_MEMORY,         (dc_list, pattern_list, start_ts, end_ts)),
      ("n_stor",     nq.BATCH_STORAGE,        (dc_list, pattern_list, start_ts, end_ts)),
      ("n_cpu",      nq.BATCH_CPU,            (dc_list, pattern_list, start_ts, end_ts)),
      ("n_platform", nq.BATCH_PLATFORM_COUNT, (dc_list, pattern_list, start_ts, end_ts)),
  ]
  ```

> [!WARNING]
> Nutanix birim dönüşümleri:
> - **Memory:** `_aggregate_dc` satır 301-302'de yapılıyor → `× 1024` (TiB → GB)
> - **Storage:** SQL'de zaten `/ 2` yapılıyor (`nutanix.py` satır 31-32). Adapter ek dönüşüm YAPMAZ.
> - **CPU:** SQL'de `* total_cpu_capacity / 1000000` yapılıyor (satır 40). Ham durum.
>
> Adapter bu dönüşümlere DOKUNMAZ. `_aggregate_dc` olduğu gibi kalır.

### 3.3 — adapters/vmware_adapter.py

- [ ] `VMwareAdapter(PlatformAdapter)` oluştur
- [ ] `fetch_single_dc` — şu metotları kapsar:

  | db_service Metodu | Kullandığı SQL |
  |-------------------|----------------|
  | `get_vmware_counts` (s.230) | `vq.COUNTS` |
  | `get_vmware_memory` (s.233) | `vq.MEMORY` |
  | `get_vmware_storage` (s.236) | `vq.STORAGE` |
  | `get_vmware_cpu` (s.239) | `vq.CPU` |

- [ ] `fetch_batch_queries` → `vq.BATCH_*` sorgularını listele (5 adet)

> [!WARNING]
> VMware SQL'leri birim dönüşümünü SQL içinde zaten yapıyor:
> - `vmware.py` s.18: `AVG(total_memory_capacity_gb) * 1024 * 1024 * 1024` → Bytes'a çeviriyor
> - `vmware.py` s.34: `AVG(total_cpu_ghz_capacity) * 1000000000` → Hz'e çeviriyor
> - `_aggregate_dc` satır 303-304: `÷ 1024³` (Bytes → GB'ye geri çeviriyor)
>
> Bu "GB → Bytes → GB" round-trip kasıtlı: Nutanix TiB, VMware Bytes döndürüyor,
> `_aggregate_dc` hepsini aynı birimde alıp standart dönüşüm yapıyor.
> Bu mantığa DOKUNMA.

### 3.4 — adapters/ibm_power_adapter.py

- [ ] `IBMPowerAdapter(PlatformAdapter)` oluştur

- [ ] `fetch_single_dc` — şu metotları kapsar:

  | db_service Metodu | Kullandığı SQL |
  |-------------------|----------------|
  | `get_ibm_host_count` (s.242) | `iq.HOST_COUNT` |
  | `get_ibm_vios_count` (s.257) | `iq.VIOS_COUNT` |
  | `get_ibm_lpar_count` (s.260) | `iq.LPAR_COUNT` |
  | `get_ibm_memory` (s.263) | `iq.MEMORY` |
  | `get_ibm_cpu` (s.266) | `iq.CPU` |

- [ ] `fetch_batch_queries` → `iq.BATCH_RAW_*` sorgularını listele (5 adet)

- [ ] **KRİTİK: IBM batch post-processing mantığı** (satır 463-523)
  Bu mantık adapter'a taşınacak:
  - `_extract_dc` fonksiyonu (satır 463-469) — `_DC_CODE_RE` kullanan regex çıkarma
  - Host dedup: `set().add(server_name)` → `len(set)` (satır 471-476)
  - VIOS dedup: `set().add(vios_name)` → `len(set)` (satır 478-483)
  - LPAR dedup: `set().add(lpar_name)` → `len(set)` (satır 485-490)
  - Memory ortalama: `sum(values) / len(values)` (satır 492-505)
  - CPU ortalama: 3-tuple ortalama (satır 507-523)

- [ ] `_DC_CODE_RE` ve `_extract_dc` bu adapter'da tanımlanacak:
  ```python
  _DC_CODE_RE = re.compile(r'(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)', re.IGNORECASE)
  ```
  `db_service.py`'den kaldırılacak (ama modül-seviyesinde export ediliyorsa import yolu korunacak).

- [ ] Adapter'a `process_raw_batch(raw_data, dc_set_upper)` metodu ekle — yukarıdaki tüm
  post-processing'i kapsayan tek metot.

### 3.5 — adapters/energy_adapter.py

- [ ] `EnergyAdapter` oluştur (PlatformAdapter'dan miras ALMAZ — farklı dönüş yapısı)
- [ ] Kendi interface'i:
  ```python
  class EnergyAdapter:
      def __init__(self, get_connection, run_value):
          ...

      def fetch_single_dc(self, cursor, dc_code_exact, dc_code_like, start_ts, end_ts) -> dict:
          ...

      def fetch_batch_queries(self, dc_list, pattern_list, start_ts, end_ts) -> list[tuple]:
          ...
  ```

- [ ] `fetch_single_dc` kapsar:

  | db_service Metodu | SQL | Parametre farkı |
  |-------------------|-----|-----------------|
  | `get_ibm_energy` (s.245) | `eq.IBM` | `dc_code_like` (%DC11%) |
  | `get_vcenter_energy` (s.248) | `eq.VCENTER` | `dc_code_exact` (DC11) |
  | `get_ibm_kwh` (s.251) | `eq.IBM_KWH` | `dc_code_like` |
  | `get_vcenter_kwh` (s.254) | `eq.VCENTER_KWH` | `dc_code_exact` |

> [!IMPORTANT]
> IBM enerji sorguları `LIKE %DC11%` kullanırken, vCenter sorguları `ILIKE %DC11%` kullanıyor.
> Bu fark IBM'de `server_name`, vCenter'da `datacenter` alanının farklı formatta olmasından
> kaynaklanıyor. Adapter bu ayrımı `dc_code_exact` ve `dc_code_like` parametreleriyle korumalı.

### 3.6 — adapters/customer_adapter.py

- [ ] `CustomerAdapter` oluştur (PlatformAdapter'dan miras ALMAZ)
- [ ] `get_customer_resources` iç mantığını (satır 806-1092, 16 sıralı DB sorgusu) bu adapter'a taşı

- [ ] **Sorgu sırası ve LIKE pattern'leri** (ÖGRT-007'ye uygun):

  | Pattern Değişkeni | Format | Kaynak satır |
  |-------------------|--------|-------------|
  | `vm_pattern` | `"{name}-%"` | s.807 |
  | `lpar_pattern` | `"{name}%"` | s.808 |
  | `veeam_pattern` | `"{name}%"` | s.809 |
  | `storage_like_pattern` | `"%{name}%"` | s.810 |
  | `netbackup_workload_pattern` | `"%{name}%"` | s.811 |
  | `zerto_name_like` | `"{name}%-%"` | s.812 |

- [ ] Adapter'ın `fetch` metodu `db_service.get_customer_resources` ile BİREBİR aynı dönüş
  yapısını üretmeli: `{"totals": {...}, "assets": {...}}`.

- [ ] Exception handling korunsun: `OperationalError` ve `PoolError` yakalanıp fallback dict döner
  (satır 969-1023).

### 3.7 — db_service.py Refactor

- [ ] `__init__` içinde adapter instance'larını oluştur:
  ```python
  def __init__(self):
      ...
      self._init_pool()
      self._nutanix = NutanixAdapter(self._get_connection, self._run_value, self._run_row, self._run_rows)
      self._vmware = VMwareAdapter(self._get_connection, self._run_value, self._run_row, self._run_rows)
      self._ibm = IBMPowerAdapter(self._get_connection, self._run_value, self._run_row, self._run_rows)
      self._energy = EnergyAdapter(self._get_connection, self._run_value)
      self._customer = CustomerAdapter(self._get_connection, self._run_value, self._run_row, self._run_rows)
  ```

- [ ] **Silinecek metotlar** (adapter'lara taşındı):
  - `get_nutanix_host_count`, `get_nutanix_vm_count`, `get_nutanix_memory`,
    `get_nutanix_storage`, `get_nutanix_cpu` (satır 215-228)
  - `get_vmware_counts`, `get_vmware_memory`, `get_vmware_storage`, `get_vmware_cpu` (satır 230-240)
  - `get_ibm_host_count`, `get_ibm_vios_count`, `get_ibm_lpar_count`,
    `get_ibm_memory`, `get_ibm_cpu` (satır 242-267)
  - `get_ibm_energy`, `get_vcenter_energy`, `get_ibm_kwh`, `get_vcenter_kwh` (satır 245-255)

- [ ] `get_dc_details` güncelle — adapter'ları çağır:
  ```python
  def get_dc_details(self, dc_code: str, time_range: dict | None = None) -> dict:
      ...
      try:
          with self._get_connection() as conn:
              with conn.cursor() as cur:
                  dc_wc = f"%{dc_code}%"
                  nutanix_data = self._nutanix.fetch_single_dc(cur, dc_code, start_ts, end_ts)
                  vmware_data = self._vmware.fetch_single_dc(cur, dc_code, start_ts, end_ts)
                  ibm_data = self._ibm.fetch_single_dc(cur, dc_wc, start_ts, end_ts)
                  energy_data = self._energy.fetch_single_dc(cur, dc_code, dc_wc, start_ts, end_ts)
                  result = self._aggregate_dc(
                      dc_code,
                      nutanix_host_count=nutanix_data["host_count"],
                      nutanix_vms=nutanix_data["vm_count"],
                      ...
                  )
  ```

- [ ] `_fetch_all_batch` güncelle — adapter batch query listelerini kullan:
  ```python
  def _fetch_all_batch(self, dc_list, start_ts, end_ts):
      pattern_list = [f"%{dc}%" for dc in dc_list]
      nutanix_queries = self._nutanix.fetch_batch_queries(dc_list, pattern_list, start_ts, end_ts)
      vmware_queries = self._vmware.fetch_batch_queries(dc_list, pattern_list, start_ts, end_ts)
      ibm_queries = self._ibm.fetch_batch_queries(dc_list, pattern_list, start_ts, end_ts)
      energy_queries = self._energy.fetch_batch_queries(dc_list, pattern_list, start_ts, end_ts)

      with ThreadPoolExecutor(max_workers=4) as pool:
          fut_n = pool.submit(_run_group, nutanix_queries)
          fut_v = pool.submit(_run_group, vmware_queries)
          fut_i = pool.submit(_run_group, ibm_queries)
          fut_e = pool.submit(_run_group, energy_queries)
          ...
  ```

- [ ] `get_customer_resources` güncelle → `self._customer.fetch(...)` çağır

- [ ] **_aggregate_dc DEĞİŞMEZ.** İmzası, dönüşüm mantığı ve dönüş yapısı birebir korunur.

- [ ] IBM post-processing (satır 463-523) → `self._ibm.process_raw_batch(ibm_raw, dc_set_upper)`

### ADIM 3 — Doğrulama

- [ ] `cd backend && pytest tests/ -v --tb=short` → TÜMÜ PASSED, SIFIR FAILED
- [ ] `cd backend && pytest tests/ --cov=app --cov-report=term-missing` → coverage ≥ %85
- [ ] **Regresyon testi — JSON yapı karşılaştırma:**
  - FAZ 1 sonuçlarını `expected_*.json` olarak kaydet
  - FAZ 2 sonuçlarını al ve `deepdiff` ile karşılaştır → SIFIR fark
  - `curl http://localhost:8000/api/v1/datacenters/summary` → aynı yapı
  - `curl http://localhost:8000/api/v1/datacenters/DC11` → aynı yapı
  - `curl http://localhost:8000/api/v1/customers/Boyner/resources` → aynı yapı
- [ ] `grep "_DC_CODE_RE" backend/app/adapters/ibm_power_adapter.py` → pattern mevcut
- [ ] `grep -rn "^#" backend/app/adapters/ --include="*.py" | grep -v "TODO\|FIXME"` → SIFIR
- [ ] `grep -rn "^#" backend/app/core/ --include="*.py" | grep -v "TODO\|FIXME"` → SIFIR
- [ ] `db_service.py` satır sayısı < 500 (monolitik yapı parçalandı)

---

## ADIM 4: Test Süiti

### 4.1 — test_redis_client.py

- [ ] `fakeredis` ile Redis mock
- [ ] `init_redis_pool` başarılı bağlantı → `redis_is_healthy() == True`
- [ ] Bağlantı hatası → `init_redis_pool()` None döner, exception fırlatmaz
- [ ] `close_redis_pool` sonrası `redis_is_healthy() == False`

### 4.2 — test_cache_backend.py

- [ ] cache_set → cache_get round-trip (Redis L1)
- [ ] Redis kapalı → cache_set yalnızca memory'ye yazar → cache_get memory'den döner (L2 fallback)
- [ ] cache_delete → her iki katmandan silinmiş
- [ ] cache_flush_pattern → Redis `SCAN` + memory clear
- [ ] JSON serialization: `datetime` ve `float` değerlerin doğru serialize/deserialize edilmesi
- [ ] L2 backfill: memory'de var, Redis'te yok → cache_get memory'den döner ve Redis'e yazar
- [ ] TTL expiry: TTL süresi dolunca cache_get None döner

### 4.3 — test_time_filter.py

- [ ] `preset=7d` → son 7 güne eşit tarih aralığı
- [ ] `preset=30d` → son 30 güne eşit tarih aralığı
- [ ] `preset=1d` → bugün
- [ ] `start=X&end=Y` → custom range (preset yoksayılır)
- [ ] Hiçbir parametre → default 7d
- [ ] Geçersiz preset → fallback 7d
- [ ] `to_dict()` her zaman `{"start": str, "end": str, "preset": str}` döner

### 4.4 — test_nutanix_adapter.py

- [ ] Mock cursor ile `fetch_single_dc` → doğru dict yapısı
- [ ] `fetch_batch_queries` → 6 tuple listesi döner
- [ ] Tüm sorgu label'ları doğru: `n_host`, `n_vm`, `n_mem`, `n_stor`, `n_cpu`, `n_platform`

### 4.5 — test_vmware_adapter.py

- [ ] Mock cursor ile `fetch_single_dc` → doğru dict yapısı
- [ ] `fetch_batch_queries` → 5 tuple listesi döner

### 4.6 — test_ibm_adapter.py

- [ ] `_DC_CODE_RE` pattern test: `mcrsrvc_tests.md` Bölüm 2.1'deki 10 case
- [ ] `_extract_dc` fonksiyonu: `"DC11-server-name"` → `"DC11"`
- [ ] Host dedup: aynı server name 3 kez → `ibm_h["DC11"] == 1`
- [ ] Memory ortalama: 2 kayıt → `(sum/2, sum/2)` tuple
- [ ] CPU ortalama: 3 kayıt → 3-tuple ortalama
- [ ] `process_raw_batch` uçtan uca testi

### 4.7 — test_energy_adapter.py

- [ ] `fetch_single_dc` → `dc_code_exact` ve `dc_code_like` ayrımı doğru parametrelenmiş
- [ ] `fetch_batch_queries` → 4 tuple listesi döner

### 4.8 — test_customer_adapter.py

- [ ] 16-sorgu mock pipeline → doğru `totals` ve `assets` yapısı
- [ ] LIKE pattern'leri: `vm_pattern="Boyner-%"`, `lpar_pattern="Boyner%"`,
  `zerto_name_like="Boyner%-%" `
- [ ] Boş müşteri adı → wildcard `"%"` pattern'leri
- [ ] `OperationalError` → fallback dict

### 4.9 — test_regression_parity.py

- [ ] FAZ 1 ve FAZ 2 sonuçlarının aynı JSON yapısı ürettiğini doğrula
- [ ] Mock DB ile: `DatabaseService.get_dc_details("DC11")` → FAZ 1 beklenen çıktı
- [ ] Mock DB ile: `DatabaseService.get_all_datacenters_summary()` → aynı yapı

### ADIM 4 — Doğrulama

- [ ] `cd backend && pytest tests/ -v --tb=short` → TÜMÜ PASSED
- [ ] `cd backend && pytest tests/ --cov=app --cov-report=term-missing` → coverage ≥ %85
- [ ] `grep -rn "^#" backend/tests/ --include="*.py" | grep -v "TODO\|FIXME"` → SIFIR
- [ ] `docker compose --profile microservice up -d` → backend + redis + db başarılı
- [ ] `docker logs bulutistan-backend-api | grep -i error` → SIFIR hata

---

## FAZ 2 TAMAMLANMA KRİTERLERİ

| # | Kriter | Kanıt Tipi |
|---|--------|------------|
| 1 | Redis cache çalışıyor (get/set/delete) | `redis-cli` çıktısı + pytest |
| 2 | Redis kapalıyken API hâlâ 200 dönüyor (L2 fallback) | Redis stop → curl → 200 |
| 3 | L1 HIT → DB sorgusu çağrılmıyor | Log'da "Batch fetch" satırı YOK |
| 4 | 5 adapter implement ve test edilmiş | `pytest --cov` raporu |
| 5 | `_DC_CODE_RE` adapter'da birebir korunmuş | `grep` çıktısı |
| 6 | IBM `set()` dedup ve ortalama mantığı adapter'da çalışıyor | Unit test |
| 7 | ThreadPoolExecutor 4-worker paralel batch korunmuş | Log: "parallel" kelimesi mevcut |
| 8 | `_aggregate_dc` DEĞİŞMEMİŞ | `git diff` → 0 değişiklik |
| 9 | TimeFilter dependency 3 router'da aktif | curl + Swagger UI |
| 10 | Preset desteği çalışıyor (`?preset=7d/30d/1d`) | curl çıktıları |
| 11 | Tüm endpoint'ler FAZ 1 ile aynı JSON döner | Regresyon test raporu |
| 12 | Coverage ≥ %85 | `pytest --cov` raporu |
| 13 | SIFIR yorum satırı (tüm yeni dosyalarda) | `grep` çıktısı |
| 14 | `db_service.py` < 500 satır | `wc -l` çıktısı |
| 15 | Docker Compose (backend + redis + db) çalışıyor | `docker compose up` + health |
