# Datalake-Platform-GUI — Proje Kapanış Dokümantasyonu

> **Tarih:** 2026-02-26
> **Durum:** PRODUCTION-READY ✅
> **Branch:** `mikro_service_dev`
> **Toplam Tamamlanan Phase:** 4 / 4

---

## İçindekiler

1. [Projenin Amacı ve Başlangıç Noktası](#1-projenin-amacı-ve-başlangıç-noktası)
2. [Mimari Karar: Monolitsiz Mikroservis](#2-mimari-karar-monolitsiz-mikroservis)
3. [Phase 1 — Altyapı ve Veri Katmanı](#3-phase-1--altyapı-ve-veri-katmanı)
4. [Phase 2 — İş Mantığı ve Sorgu Motoru](#4-phase-2--iş-mantığı-ve-sorgu-motoru)
5. [Phase 3 — Kullanıcı Arayüzü ve Dashboard](#5-phase-3--kullanıcı-arayüzü-ve-dashboard)
6. [Phase 4 — Üretime Hazırlık ve Güvenlik](#6-phase-4--üretime-hazırlık-ve-güvenlik)
7. [Karşılaşılan Kritik Sorunlar ve Çözümler](#7-karşılaşılan-kritik-sorunlar-ve-çözümler)
8. [Proje Dosya Haritası](#8-proje-dosya-haritası)
9. [Deployment ve Çalıştırma Rehberi](#9-deployment-ve-çalıştırma-rehberi)
10. [Teknik Metrikler ve Sonuçlar](#10-teknik-metrikler-ve-sonuçlar)

---

## 1. Projenin Amacı ve Başlangıç Noktası

Bu proje, **Bulutistan Datalake platformundaki** VMware, Nutanix ve IBM Power sanallaştırma altyapılarının anlık durumunu izleyen bir **Executive Dashboard** geliştirmek için başlatıldı.

### Başlangıç Noktası: Monolitik Yapı

Proje, `docs/legacy/` altında belgelenmiş eski bir Python monolitinden türetildi:

- **db_logic.md**: Ham PostgreSQL sorguları, `psycopg2` ile senkron çalışan veri erişim mantığı
- **query_logic.md**: VMware, Nutanix ve IBM için vendor-spesifik sorgu mantıkları
- **ui_components.md**: Eski Dash bileşen yapısı

Eski yapının temel sorunları:
- Senkron DB bağlantıları → yüksek gecikme
- Vendor logikleri tek dosyada iç içe → bakımı imkânsız
- Önbellekleme yok → her istek DB'ye gidiyor (~74s cold start)
- GUI, veri ve iş mantığı aynı süreçte → yatay ölçekleme yok

### Hedef: Modern Mikroservis Mimarisi

```
Internet
   │
   ▼
[gui-service:8050]  ◄─ Kullanıcı tarayıcısı
   │
   ▼ HTTP (internal-net)
[query-service:8002]  ◄─ İş mantığı + Redis cache
   │
   ├──► [db-service:8001]  ◄─ Sadece veri erişimi
   │           │
   │           ▼ asyncpg
   │     [PostgreSQL 16.4]  10.134.16.6:5000
   │
   └──► [Redis:6379]  ◄─ 15 dakikalık TTL cache
```

Tek dışa açık port: **8050 (gui-service)**. Diğer tüm servisler yalnızca `internal-net` (Docker bridge) üzerinden erişilebilir.

---

## 2. Mimari Karar: Monolitsiz Mikroservis

### Ağ Tasarımı

**İki ağ katmanı** kullanıldı:

| Ağ | Adı | Açıklama |
|----|-----|----------|
| `internal-net` | `datalake_internal` | db-service, query-service, Redis, gui-service |
| `external-net` | `datalake_external` | Sadece gui-service → kullanıcı trafiği |

Bu sayede `db-service` ve `query-service` doğrudan internet'ten erişilemez; yalnızca Docker bridge üzerinden konuşabilirler.

### Güvenlik Katmanları (Defense-in-Depth)

1. **Ağ izolasyonu**: `expose:` (host'a açık değil), yalnızca `internal-net`
2. **API Key authentication**: `X-Internal-Key` header — tüm data endpoint'lerinde
3. **IP restriction middleware**: `TrustedNetworkMiddleware` — CIDR tabanlı subnet filtresi (Phase 4'te eklendi)

### Veri Akışı

```
Kullanıcı → gui-service
         → api_client.py (requests, 120s timeout, X-Internal-Key)
         → query-service /datacenters/summary
              → Redis.get("dc_summary_all")
                   HIT  → model_validate_json → döndür (~sub-ms)
                   MISS → db-service /datacenters/summary (httpx, 90s timeout)
                            → asyncpg pool → PostgreSQL
                            → Pydantic validation
                            → VMware/Nutanix/IBM Provider pipeline
                            → Redis.set(key, json, ex=900)
                            → döndür
```

---

## 3. Phase 1 — Altyapı ve Veri Katmanı

**Tamamlanma:** 2026-02-23 / 2026-02-24
**Amaç:** Docker orkestrasyonunu kur ve veritabanı erişimini API'ye dönüştür.

### Task 1.1 — Docker Orchestration

`docker-compose.yml` sıfırdan yazıldı:
- **4 servis**: db-service, redis, query-service, gui-service
- **2 ağ**: internal-net + external-net (bridge)
- **Healthcheck zinciri**: `depends_on: service_healthy` — her servis bir öncekinin sağlığına bağlı
- **`.env`**: DB credentials, INTERNAL_API_KEY (asla commit edilmez)
- **`.dockerignore`**: `.venv`, `__pycache__`, `*.pyc`, `.git`, `.env`

**Kritik keşfedilen sorun:** `.env` dosyası Windows'ta CRLF satır sonuyla kaydedilmişti; `\r` karakteri şifreye eklenince `asyncpg` bağlanamıyordu. `file .env` ile tespit edildi, LF'ye dönüştürüldü.

### Task 1.2 — DB-Service (DAL Katmanı)

**Teknoloji:** FastAPI + asyncpg (Python 3.11)

Oluşturulan endpoint'ler:

| Endpoint | Açıklama | Ort. Yanıt |
|----------|----------|------------|
| `GET /health` | Servis canlılık kontrolü | < 10ms |
| `GET /db-status` | Pool durumu + DB ping | < 100ms |
| `GET /datacenters/summary` | 14 DC özet verisi | 39s (warm) |
| `GET /datacenters/{dc_code}` | Tek DC detayı | 18s |
| `GET /overview` | Küresel platform özeti | 41s |

**Sorgu dosyaları** (`src/queries/`):
- `vmware.py`: VMware vCenter sorguları — `vmware_vm_metrics`, `vmware_host_metrics`
- `nutanix.py`: Nutanix cluster sorguları — `nutanix_cluster_metrics`
- `ibm.py`: IBM Power server sorguları — `ibm_server_inventory`
- `energy.py`: Enerji tüketim sorguları — DISTINCT ON + 4-saatlik filtre
- `loki.py`: Rack ve topoloji sorguları

**Performans iyileştirmesi (Task 1.4):**
TimescaleDB time filtresi `AND timestamp >= NOW() - INTERVAL '4 hours'` eklenerek yanıt süresi 97s → 40s'ye (%59 iyileşme) düştü.

### Task 1.3 — Shared Schemas (Pydantic Kontratlar)

`shared/schemas/` altında servisler arası veri sözleşmeleri:

- **`infrastructure.py`**: `DCMeta` (isim, lokasyon), `PowerInfo`, `ClusterInfo`
- **`metrics.py`**: `IntelMetrics` (cpu/ram/storage %), `EnergyMetrics` (kW), `DCStats`
- **`responses.py`**: `DCSummary`, `DCDetail`, `GlobalOverview`, `TrendSeries`, `OverviewTrends`

**Kural:** Servisler arası her veri transferi bu modellerden geçmek zorunda. Tip güvenliği `response_model=` ile FastAPI tarafından da zorlanır.

**Keşfedilen sorunlar bu aşamada:**
- `curl` paketi `python:3.11-slim`'de yok → healthcheck kırıldı → Dockerfile'a eklendi
- DB_USER `datalakeui` değil `bulutlake` olmalıydı

---

## 4. Phase 2 — İş Mantığı ve Sorgu Motoru

**Tamamlanma:** 2026-02-24
**Amaç:** Vendor-spesifik iş mantığını merkezileştir, Redis önbelleklemesini kur.

### Task 2.1 — Query-Service İskeleti

**Teknoloji:** FastAPI + httpx (async HTTP client)

**DI (Dependency Injection) zinciri:**
```python
verify_internal_key  ←  X-Internal-Key header kontrolü
    └── get_db_client  ←  app.state.db_client (httpx.AsyncClient)
    └── get_redis      ←  app.state.redis (aioredis)
         └── _get_service(QueryService)  ←  iş mantığı servisi
              └── endpoint handler
```

**Lifespan pattern:** `asyncio.contextmanager` ile uygulama başında `httpx.AsyncClient` ve Redis bağlantısı oluşturulur, kapanışta temizlenir.

**Timeout disiplini:** httpx default 5s → 90s'ye çıkarıldı (db-service soğuk başlangıç 74s alabilir).

### Task 2.2 — Provider Adapter Katmanı

Her vendor için ayrı provider sınıfı:

**`providers/base.py`:** `BaseProvider` ABC + status hesaplama yardımcıları
- CPU > 80% → `"Degraded"` | RAM > 85% → `"Degraded"` | Storage > 80% → `"Degraded"`
- Aksi hâlde → `"Healthy"`

**`providers/vmware.py`:** `VMwareProvider`
- db-service'ten VMware metric verisi alır
- `cpu_used/cpu_cap`, `ram_used/ram_cap`, `storage_used/storage_cap` hesaplar

**`providers/nutanix.py`:** `NutanixProvider`
- Nutanix cluster metriklerini işler
- `storage_capacity` bytes cinsinden → `/ (1024 ** 4)` ile TB'a çevrilir (bu bug Task 2.4'te keşfedildi)
- Sanity check: > 10000 TB/cluster → WARNING log

**`providers/ibm.py`:** `IBMProvider`
- IBM Power server enerji verisi
- DISTINCT ON + 4-saatlik filtre (öncesinde tüm geçmiş toplanıyordu → astronomik değerler)

**Provider pipeline:**
```python
QueryService._providers = [VMwareProvider, NutanixProvider, IBMProvider]
for provider in providers:
    enriched_data = provider.enrich(raw_data)
```

### Task 2.3 — Redis Cache-Aside

**Strateji:** Cache-aside (lazy caching)

```
Cache keys:
  dc_summary_all      → GET /datacenters/summary  (TTL: 900s)
  dc_detail:{code}    → GET /datacenters/{code}   (TTL: 900s)
  global_overview     → GET /overview             (TTL: 900s)
```

**Performans kanıtı:**

| Endpoint | 1. İstek (MISS) | 2. İstek (HIT) |
|----------|----------------|----------------|
| `/datacenters/summary` | ~41s | < 1ms |
| `/overview` | ~39s | < 1ms |

**Kritik konfigürasyon:**
`decode_responses=True` — Redis'ten `bytes` değil `str` döner; `model_validate_json()` uyumlu.

**Silent fail prensibi:** Redis çökmesi servisi durduramaz. GET/SET hatası → `warn` log + db-service'e düşme.

### Task 2.4 — Veri Akışı Doğrulaması

**Keşfedilen ve düzeltilen kritik hatalar:**

1. **Nutanix storage birimi:** `storage_capacity` `bytes` cinsindeydi, TB değil. `_aggregate_dc`'de `/ (1024 ** 4)` eklendi. DC11: 258,634,388,900,380 TB → **3,957 TB** (%99.9998 düşüş)

2. **IBM enerji astronomik değerleri:** `ibm_server_power` tablosunda zaman filtresi yoktu → tüm geçmiş toplanıyordu. DISTINCT ON + `AND timestamp >= NOW() - INTERVAL '4 hours'` eklendi. Sonuç: DC11 enerji **18.64 kW** (makul)

3. **asyncpg Decimal + Python float hatası:** `float(row[0] or 0)` explicit cast ile giderildi

4. **NutanixProvider sanity eşiği:** 1,000 TB → **10,000 TB** (birim fix sonrası gerçek değerler kalibre edildi)

5. **Cache invalidation:** db-service rebuild sonrası Redis'teki eski hatalı değerler `FLUSHALL` ile temizlendi

---

## 5. Phase 3 — Kullanıcı Arayüzü ve Dashboard

**Tamamlanma:** 2026-02-25
**Amaç:** Modern, reaktif Dash dashboard — Bulutistan kurumsal görsel standardı.

### Task 3.1 — AppShell Layout (Light Mode)

**Teknoloji:** Dash v4.0 + Dash Mantine Components v2.6.0

**Tema:** `forceColorScheme="light"`, `primaryColor="indigo"` (pastel mavi/mor tonları)

**Layout yapısı:**
```
dmc.MantineProvider
  └── dmc.AppShell
        ├── AppShellHeader: DashIconify logo + "Datalake Platform" başlık
        ├── AppShellNavbar: Floating sidebar (glassmorphism cam panel)
        │     ├── NavLink: Overview  → /overview
        │     ├── NavLink: Data Centers → /datacenters
        │     └── NavLink: Customs  → /customs (disabled)
        └── AppShellMain: dash.page_container (dinamik sayfa içeriği)
```

**Bulutistan Kurumsal Görsel Standardı:**

- **Mesh Gradient Body:** 4 katman radial-gradient (`background-attachment: fixed`) — pastel indigo/violet
- **Glassmorphism:** `background: rgba(255,255,255,0.82)` + `backdrop-filter: blur(18px)` + `border: 1px solid rgba(...)`
- **Floating Sidebar:** `AppShellNavbar` şeffaf → iç `dmc.Box.sidebar-float` cam panel (border-radius: 20px)
- **Active NavLink:** `.mantine-NavLink-root[data-active]::before` — 4px neon şerit (`linear-gradient indigo→violet + box-shadow glow`)
- **Hover micro-interactions:** `translateY(-4px) + box-shadow glow` kart efektleri

### Task 3.2 — Sayfa Hiyerarşisi ve Routing

**Dash `use_pages=True`** — `pages/` klasörü otomatik taranır.

**Sayfalar:**

**`/datacenters`** — `pages/datacenters.py`
- `_stat_boxes()`: 4 ThemeIcon Paper (Cluster/Host/VM/Sağlık sayıları)
- `_card(dc)`: Her DC için kart — sağ köşede `dmc.RingProgress` (avg CPU+RAM+Storage %)
- RingProgress renk eşiği: `teal < 60%` | `yellow < 80%` | `red ≥ 80%`
- `api_client.get_summary()` → 14 DC kartı

**`/datacenters/{dc_code}`** — `pages/dc_detail.py`
- Hero Section: Breadcrumb + DC başlığı + status badge
- `dmc.Tabs`: Intel Virtualization | Power Virtualization | Backup
- `api_client.get_dc_detail(dc_code)` → detay verisi

**`/overview`** — `pages/overview.py`
- Executive Command Center (Phase 3.5'te detaylandırıldı)

### Task 3.3 — Plotly Chart Entegrasyonu

**Intel Sekmesi:**
- 3 × `go.Pie(hole=0.62)` donut chart: CPU / RAM / Storage
- Merkez annotation: `fig.update_layout(annotations=[dict(text="<b>X%</b>")])`
- Renkler: Indigo `#4c6ef5` / Violet `#845ef7` / Sky `#74c0fc`
- Boş dilim: `#e9ecef`

**Power Sekmesi:**
- `dmc.Text(id="power-kpi-kw")`: KPI enerji değeri
- `go.Bar()`: IBM Hosts / IBM VMs inventory chart

**`chart-paper` CSS sınıfı:**
```css
.chart-paper {
    background: rgba(255, 255, 255, 0.78) !important;
    backdrop-filter: blur(14px) !important;
    border-radius: 16px;
    border: 1px solid rgba(99, 102, 241, 0.15);
}
```

**Tüm grafiklerde:** `paper_bgcolor="rgba(0,0,0,0)"` + `plot_bgcolor="rgba(0,0,0,0)"` — glassmorphism uyumu için

**`dcc.Store` + Callback pattern:**
```python
dcc.Store(id="dc-detail-store", data=detail_raw)  # layout'ta API verisi browser'a yazılır
# callback'te:
@callback(..., State("dc-detail-store", "data"))   # tekrar API çağrısı yok
```

**Oransal simülasyon (cluster filtresi):**
- `usage_weight = N / sum(1..k)` — yüksek indeks = daha fazla yük
- `cap_weight = 1/k` — eşit kapasite dağılımı
- Garanti: tüm ağırlıkların toplamı her zaman 1.0

### Task 3.4 — "Zombisiz" Auto-Refresh

**Mimari:**
```
layout() çağrısı → pre-render (anında görüntü)
    + dcc.Interval(interval=900_000)
    + dmc.Box(id="...-content", children=initial_content)
    @callback(prevent_initial_call=True)  ← ilk açılışta tetiklenmez
```

→ Kullanıcı sayfayı anında görür. 15 dakika sonra `n_intervals=1` → callback → taze veri → silent güncelleme.

**Unified Callback pattern (dc_detail.py):**

Eski 2 ayrı callback (Intel filtre + Power filtre) → 1 unified callback:
```python
@callback(
    Output(...) × 6,
    Input("dc-detail-interval", "n_intervals"),
    Input("intel-cluster-filter", "value"),
    Input("power-source-filter", "value"),
    State("dc-code-store", "data"),
    State("dc-detail-store", "data"),
    prevent_initial_call=True
)
def _refresh_and_render(n, cluster_filter, source_filter, dc_code, detail_data):
    if ctx.triggered_id == "dc-detail-interval":
        detail_data = get_dc_detail(dc_code)  # taze veri
    # aksi hâlde mevcut store verisi korunur
    ...
```

**Sessiz başarısızlık:** API hatası → `except: pass` → mevcut veri korunur → kullanıcı boş ekran görmez.

**`dc-code-store` pattern:** URL parametresini callback'e taşımanın standart Dash yolu:
```python
dcc.Store(id="dc-code-store", data=dc_code)  # layout'ta URL param → store
# callback'te State("dc-code-store", "data")
```

### Task 3.5 — Executive Overview (`/overview`)

**Tasarım: Executive Command Center**

**Sparklines (3 adet Area Chart):**
```python
go.Scatter(
    fill="tozeroy",      # sıfıra kadar dolu alan
    mode="lines",
    line=dict(shape="spline", width=2),
    fillcolor="rgba(r,g,b,0.12)"
)
# xaxis/yaxis: visible=False, margin=0
```
- CPU Trendi | RAM Trendi | Toplam Enerji (Phase 4.1'de gerçek veriye geçildi)

**Vendor Donut:**
```python
go.Pie(
    values=[60, 25, 15],
    labels=["VMware", "Nutanix", "IBM Power"],
    hole=0.62
)
# Merkez: "Vendor Mix" annotation
```

**Sistem Olay Günlüğü:**
```python
dmc.Timeline(active=4, bulletSize=22, color="indigo")
# 5 TimelineItem — DashIconify bullet icons
# CPU Alarmı, Yedekleme OK, Cluster Eklendi, Cache Miss, Cluster Sağlık
```

**CANLI Badge:** `dmc.Badge("CANLI", color="teal", variant="dot")` — sayfa başlığı yanında

---

## 6. Phase 4 — Üretime Hazırlık ve Güvenlik

**Tamamlanma:** 2026-02-25 / 2026-02-26
**Amaç:** Gözlemlenebilirlik, test kapsamı, imaj optimizasyonu ve güvenlik katmanları.

### Task 4.1 — Redis Sliding Window Zaman Serisi

**Amaç:** Overview sayfasındaki mock sparkline verilerini gerçek zaman serisi ile değiştir.

**`tasks/sampler.py`** — Query-service lifespan'ına bağlı background task:
```python
asyncio.create_task(run_sampler(app))  # 1 worker (çift yazma riski nedeniyle)
```

**Çalışma prensibi:**
1. Servis başladığında anında 1 örnek yazar (warm-up)
2. Her 5 dakikada bir: CPU%, RAM%, Enerji kW → Redis LPUSH
3. `LTRIM key 0 29` → maksimum 30 nokta (~2.5 saatlik pencere)
4. Pipeline atomik yazma

**Redis key yapısı:**
```
trend:cpu_pct    → [{"ts": "ISO-8601", "v": 23.54}, ...]
trend:ram_pct    → [{"ts": "ISO-8601", "v": 28.26}, ...]
trend:energy_kw  → [{"ts": "ISO-8601", "v": 2473479.16}, ...]
```

**`GET /overview/trends` endpoint'i:**
```json
{
  "cpu_pct":   {"labels": [...], "values": [...]},
  "ram_pct":   {"labels": [...], "values": [...]},
  "energy_kw": {"labels": [...], "values": [...]}
}
```

**Neden 1 worker?** `asyncio.create_task` process-level'dir. 2 uvicorn worker → 2 sampler → 2 LPUSH/5dk → trend:cpu_pct listesi çift hızda büyür → bozuk veri.

**GUI güncellemesi:** `dcc.Interval(300_000)` + `prevent_initial_call=False` — sayfa açıldığında ve her 5 dakikada veri çekilir.

### Task 4.2 — Merkezi Loglama Sistemi

**`shared/utils/logger.py`:**
```python
def setup_logger(service_name: str, level: str = None) -> logging.Logger:
    ...
```

**Kurumsal format:**
```
[2026-02-25 12:29:58] [INFO    ] [query-service] - Logger başlatıldı
[2026-02-25 12:29:58] [INFO    ] [query-service] - httpx client ready
```

**Özellikler:**
- **İdempotent handler:** Dash hot-reload'da çift handler oluşmaz
- **LOG_LEVEL env override:** `LOG_LEVEL=DEBUG` ile granüler kontrol
- **Python hiyerarşi korunur:** `getLogger(__name__)` child logger'lar `propagate=True` ile parent'a iletir → format otomatik miras alınır

**api_client.py hata yakalama:**
```python
except requests.exceptions.Timeout:
    logger.error("GET %s zaman aşımına uğradı (%ds)", endpoint, _TIMEOUT)
    raise  # log-and-rethrow: callback no_update ile sessiz kalır
except requests.exceptions.HTTPError as exc:
    logger.error("GET %s HTTP hatası: %s", endpoint, exc)
    raise
except requests.exceptions.RequestException as exc:
    logger.error("GET %s erişim hatası: %s", endpoint, exc)
    raise
```

### Task 4.3 — Unit Test Paketi (35/35 PASS)

**Test mimarisi karar:** FastAPI `dependency_overrides` ile tam DI izolasyonu.

**Sonuçlar:**

| Paket | Dosya | Sonuç |
|-------|-------|-------|
| `shared` | `shared/tests/test_logger.py` | 11/11 ✅ |
| `query-service` | `services/query-service/tests/test_endpoints.py` | 14/14 ✅ |
| `gui-service` | `services/gui-service/tests/test_api_client.py` | 10/10 ✅ |
| **TOPLAM** | | **35/35 ✅** |

**DI izolasyon mimarisi (`conftest.py`):**
```python
app.dependency_overrides = {
    get_db_client:       lambda: mock_db_client,  # gerçek httpx.Response ile
    get_redis:           lambda: mock_redis,       # AsyncMock
    verify_internal_key: lambda: None,             # bypass
}
```

**Kritik httpx mock fix:**
```python
# YANLIŞ: raise_for_status() → RuntimeError
resp = httpx.Response(200, content=b"[]")

# DOĞRU: request= parametresi zorunlu
dummy_request = httpx.Request("GET", url)
resp = httpx.Response(200, content=b"[]", request=dummy_request)
```

**shared/tests/test_logger.py kapsamı:**
- `setup_logger` idempotency (çift çağrı = tek handler)
- Log formatı doğrulama (`[bracket]` format)
- stdout StreamHandler varlığı
- `LOG_LEVEL` env var override

### Task 4.4 — Optimizasyon, Güvenlik ve Yük Testi

#### Docker İmaj Optimizasyonu (Multi-Stage Build)

**db-service — en büyük kazanım (-65%):**

```dockerfile
# Stage 1: Builder (derleme araçları)
FROM python:3.11-slim AS builder
RUN apt-get install -y build-essential libpq-dev
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Production (sadece runtime)
FROM python:3.11-slim AS production
RUN apt-get install -y libpq5 curl  # libpq5: asyncpg binary runtime (~600KB)
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
```

**İmaj boyutları:**

| Servis | Önce | Sonra | Azalma |
|--------|------|-------|--------|
| db-service | 773 MB | **270 MB** | -65% |
| query-service | 304 MB | **281 MB** | -8% |
| gui-service | 607 MB | **589 MB** | -3% |

**Neden db-service bu kadar küçüldü?**
`asyncpg` C extension'ı derleme için `build-essential` (~200MB+) ve `libpq-dev` gerektirir. Multi-stage build ile bu araçlar builder'da kalır; production stage'e sadece derlenmiş `.so` dosyaları kopyalanır. `libpq5` runtime `~600KB`.

#### Production Server Konfigürasyonu

```yaml
# gui-service
CMD: gunicorn --bind 0.0.0.0:8050 --workers 2 --timeout 120 app:server

# db-service
CMD: uvicorn src.main:app --host 0.0.0.0 --port 8001 --workers 2

# query-service
CMD: uvicorn src.main:app --host 0.0.0.0 --port 8002
# (1 worker — sampler task çakışma riski)
```

#### Test Bağımlılıkları Ayrıştırması

```
services/query-service/
  requirements.txt      → prod bağımlılıkları (pytest YOK)
  requirements-dev.txt  → -r requirements.txt + pytest + pytest-asyncio + pytest-httpx

services/gui-service/
  requirements.txt      → prod bağımlılıkları (pytest YOK)
  requirements-dev.txt  → -r requirements.txt + pytest + pytest-mock
```

`.dockerignore` güncellendi:
```
services/*/tests/
shared/tests/
*.md
scripts/
```

#### IP Kısıtlama Middleware (Defense-in-Depth)

**`shared/utils/trusted_network.py`:**

```python
class TrustedNetworkMiddleware(BaseHTTPMiddleware):
    """
    Starlette BaseHTTPMiddleware — stdlib ipaddress.
    ALLOWED_SUBNETS env var: virgülle ayrılmış CIDR listesi.
    /health: her zaman açık (Docker healthcheck bypass).
    Yetkisiz IP: 403 JSON response.
    """
```

**Varsayılan izin verilen ağlar:**
```
172.16.0.0/12  — Docker bridge ağı (172.17.x.x, 172.18.x.x, ...)
10.0.0.0/8     — Private ağlar
127.0.0.1/32   — Localhost
```

**Uygulama:**
```python
# db-service/src/main.py + query-service/src/main.py
app.add_middleware(TrustedNetworkMiddleware)
```

**docker-compose.yml:**
```yaml
environment:
  - ALLOWED_SUBNETS=172.16.0.0/12,10.0.0.0/8,127.0.0.1/32
```

#### Yük Testi Script'i

**`scripts/load_test.py`** — Harici bağımlılık gerektirmez (sadece `httpx`):
```bash
python scripts/load_test.py --host http://localhost:8050 --concurrency 5 --rounds 3
```

Ölçülen metrikler: istek/saniye, ort/max/min gecikme, hata oranı

---

## 7. Karşılaşılan Kritik Sorunlar ve Çözümler

### 7.1 `.env` CRLF Problemi (Phase 1)
- **Sorun:** Windows'ta kaydedilen `.env` → `\r` karakteri şifreye ekleniyor → asyncpg bağlanamıyor
- **Tespit:** `file .env` → "with CRLF line terminators"
- **Çözüm:** `.env` dosyası LF formatına dönüştürüldü
- **Kural:** Her `.env` değişikliğinde `file .env` ile format kontrolü yapılacak

### 7.2 `curl` Eksik — Healthcheck Kırık (Phase 1)
- **Sorun:** `python:3.11-slim` `curl` içermiyor; `CMD curl` healthcheck asla `healthy` olamıyor → `depends_on: service_healthy` zinciri kırılıyor → downstream servisler başlamıyor
- **Çözüm:** Tüm Dockerfile'lara `apt-get install -y curl` eklendi
- **Kural:** Tüm yeni Dockerfile'lara curl ekleme zorunlu

### 7.3 Nutanix Storage Birimi Hatası (Phase 2)
- **Sorun:** `storage_capacity` bytes cinsindeydi, TB değil → DC11: **258 trilyon TB** gösteriyordu
- **Tespit:** NutanixProvider sanity check logu yakaladı
- **Çözüm:** `_aggregate_dc`'de `/ (1024 ** 4)` bytes→TB dönüşümü eklendi → DC11: **3,957 TB**

### 7.4 IBM Enerji Astronomik Değerler (Phase 2)
- **Sorun:** `ibm_server_power` sorgusunda zaman filtresi yoktu → tüm geçmiş SUM ediliyor → milyonlarca kW
- **Çözüm:** DISTINCT ON + `AND timestamp >= NOW() - INTERVAL '4 hours'` eklendi → DC11: **18.64 kW**

### 7.5 asyncpg Decimal + Python float TypeError (Phase 2)
- **Sorun:** asyncpg `NUMERIC/DECIMAL` sütunlarını `decimal.Decimal` döndürür; `Decimal + float` → `TypeError`
- **Çözüm:** `float(row[0] or 0)` explicit cast eklendi

### 7.6 DMC v2.x LoadingOverlay Positional Arg Tuzağı (Phase 3)
- **Sorun:** `dmc.LoadingOverlay(dmc.Stack(...), visible=False)` → "detected a Component for a prop other than children: Prop transitionProps has value Stack"
- **Kök neden:** DMC v2.6.0'da `LoadingOverlay.__init__` ilk parametresi `transitionProps`, `children` değil
- **Çözüm:** `dmc.LoadingOverlay(children=dmc.Stack(...), visible=False)` — keyword arg zorunlu
- **Kural:** DMC bileşenlerine child geçerken her zaman `children=` keyword yazılacak

### 7.7 DuplicateCallbackError (Phase 3)
- **Sorun:** Intel ve Power filtre callback'leri aynı `Output` id'lerini paylaşıyordu
- **Çözüm:** 2 callback → 1 unified callback; `ctx.triggered_id` ile tetikleyici ayırt edildi

### 7.8 httpx.Response `raise_for_status()` RuntimeError (Phase 4)
- **Sorun:** Test mock'larında `httpx.Response(200, ...)` → `resp.raise_for_status()` → `RuntimeError: request instance not set`
- **Çözüm:** `dummy_request = httpx.Request("GET", url); resp = httpx.Response(200, request=dummy_request)`

### 7.9 Çift Test Discovery (Phase 4)
- **Sorun:** Container'da `/app/tests/tests/` nested dizin → pytest 14 test yerine 28 keşfetti
- **Kök neden:** Eski Docker layer kalıntısı
- **Çözüm:** `shutil.rmtree('/app/tests/tests/')` + `docker cp` ile güncel conftest kopyalandı

### 7.10 asyncpg Pool Başlatma Zamanlaması (Phase 4 — Final)
- **Sorun:** Kullanıcı VPN'i servisleri başlattıktan sonra bağladı → db-service lifespan'da `asyncpg.create_pool()` başarısız → `pool = None` → `/health` yine de 200 döndürüyor (pool kontrolü yok) → query-service healthy görüyor → gui başlıyor → DB sorgusu → **503 hatası**
- **Çözüm:** `docker restart datalake-platform-gui-db-service-1` → lifespan yeniden çalıştı → pool oluşturuldu
- **Log kanıtı:** `asyncpg pool created — host=10.134.16.6 port=5000 db=bulutlake` × 2 (2 worker)
- **Operasyonel kural:** Sistem VPN aktifken başlatılmalı. Soğuk başlatma sırasında VPN kapalıysa db-service restart gerekir.

---

## 8. Proje Dosya Haritası

```
Datalake-Platform-GUI/
│
├── docker-compose.yml          # 4 servis orkestrasyon + 2 ağ (internal/external)
├── .env                        # DB credentials + INTERNAL_API_KEY (git ignore)
├── .dockerignore               # Build exclusion: tests/, *.md, scripts/
├── PHASE.md                    # 4 aşamalı roadmap + tüm task detayları
├── Finish.md                   # Bu dosya — kapanış dokümantasyonu
│
├── shared/                     # Servisler arası paylaşılan kod
│   ├── schemas/
│   │   ├── infrastructure.py   # DCMeta, PowerInfo, ClusterInfo
│   │   ├── metrics.py          # IntelMetrics, EnergyMetrics, DCStats
│   │   └── responses.py        # DCSummary, DCDetail, GlobalOverview, TrendSeries
│   ├── utils/
│   │   ├── logger.py           # setup_logger() — kurumsal [bracket] format
│   │   └── trusted_network.py  # TrustedNetworkMiddleware — CIDR IP filtresi
│   └── tests/
│       └── test_logger.py      # 11 test — setup_logger idempotency + format
│
├── services/
│   │
│   ├── db-service/             # Port 8001 — DAL (Data Access Layer)
│   │   ├── Dockerfile          # Multi-stage: builder (build-essential) → production (libpq5)
│   │   ├── requirements.txt    # fastapi, uvicorn, asyncpg, pydantic, python-dotenv
│   │   └── src/
│   │       ├── main.py         # FastAPI app + asyncpg lifespan + TrustedNetworkMiddleware
│   │       ├── database.py     # asyncpg pool: min=2 max=8 timeout=60s
│   │       ├── dependencies.py # verify_internal_key + get_pool DI
│   │       ├── queries/        # SQL sorgu fonksiyonları
│   │       │   ├── vmware.py   # VMware vCenter metrik sorguları
│   │       │   ├── nutanix.py  # Nutanix cluster sorguları
│   │       │   ├── ibm.py      # IBM Power server sorguları
│   │       │   ├── energy.py   # Enerji tüketim sorguları (DISTINCT ON + 4h filter)
│   │       │   └── loki.py     # Rack ve topoloji sorguları
│   │       ├── routers/
│   │       │   ├── health.py   # GET /health, GET /db-status
│   │       │   └── data.py     # GET /datacenters/*, GET /overview
│   │       └── services/
│   │           └── database_service.py  # Pydantic model dönüşümleri
│   │
│   ├── query-service/          # Port 8002 — Business Logic + Cache
│   │   ├── Dockerfile          # python:3.11-slim + curl (--no-install-recommends)
│   │   ├── requirements.txt    # fastapi, uvicorn, httpx, redis[hiredis], pydantic
│   │   ├── requirements-dev.txt # -r requirements.txt + pytest + pytest-asyncio + pytest-httpx
│   │   ├── src/
│   │   │   ├── main.py         # FastAPI + httpx/Redis lifespan + sampler task + Middleware
│   │   │   ├── dependencies.py # verify_internal_key + get_db_client + get_redis DI
│   │   │   ├── providers/
│   │   │   │   ├── base.py     # BaseProvider ABC + status thresholds
│   │   │   │   ├── vmware.py   # VMwareProvider
│   │   │   │   ├── nutanix.py  # NutanixProvider (+ sanity check + TB dönüşümü)
│   │   │   │   └── ibm.py      # IBMProvider
│   │   │   ├── routers/
│   │   │   │   ├── health.py   # GET /health, GET /service-status
│   │   │   │   └── data.py     # GET /datacenters/*, GET /overview, GET /overview/trends
│   │   │   ├── services/
│   │   │   │   └── query_service.py  # Cache-aside logic (Redis + db-service)
│   │   │   └── tasks/
│   │   │       └── sampler.py  # Redis sliding window örnekleyici (5dk, max 30 nokta)
│   │   └── tests/
│   │       ├── conftest.py     # DI override + httpx mock (dummy_request fix)
│   │       └── test_endpoints.py  # 14 test: Health + Trends + Summary
│   │
│   └── gui-service/            # Port 8050 — Dash Frontend
│       ├── Dockerfile          # python:3.11-slim + gunicorn (2 workers)
│       ├── requirements.txt    # dash, dash-mantine-components, dash-iconify, plotly, gunicorn
│       ├── requirements-dev.txt # -r requirements.txt + pytest + pytest-mock
│       ├── app.py              # Dash entry point (use_pages=True, setup_logger)
│       ├── layout.py           # AppShell factory
│       ├── assets/
│       │   └── style.css       # Glassmorphism + mesh gradient + NavLink neon + chart-paper
│       ├── components/
│       │   ├── header.py       # DashIconify logo + başlık
│       │   └── navbar.py       # Floating sidebar (3 NavLink)
│       ├── pages/
│       │   ├── overview.py     # /overview — Executive Command Center
│       │   ├── datacenters.py  # /datacenters — DC kart listesi + auto-refresh
│       │   └── dc_detail.py    # /datacenters/<dc_code> — Tabs + charts + unified callback
│       ├── services/
│       │   └── api_client.py   # query-service HTTP wrapper (log-and-rethrow)
│       └── tests/
│           └── test_api_client.py  # 10 test: 3 fonksiyon × hata senaryoları
│
├── docs/
│   ├── architecture.md         # Port haritası, veri akışı, ağ yapılandırması
│   ├── lessons.md              # 12 kategoride öğrenilen dersler ve kurallar
│   ├── todolist.md             # Görev takip çizelgesi (tüm tasklar [x])
│   ├── test_results.md         # Her phase sonundaki test kanıtları ve log çıktıları
│   └── legacy/
│       ├── db_logic.md         # Eski senkron DB mantığı (migrasyon referansı)
│       ├── query_logic.md      # Eski vendor sorgu mantığı (migrasyon referansı)
│       └── ui_components.md    # Eski UI bileşen yapısı (migrasyon referansı)
│
└── scripts/
    ├── load_test.py            # asyncio + httpx yük testi (--concurrency --rounds)
    └── e2e_healthcheck.py      # End-to-end sağlık kontrolü
```

---

## 9. Deployment ve Çalıştırma Rehberi

### Ön Koşullar

1. **Docker Desktop** kurulu ve çalışıyor
2. **VPN aktif** — PostgreSQL 16.4 @ `10.134.16.6:5000` erişimi için
3. **`.env` dosyası** proje kökünde (LF satır sonu):
   ```
   DB_HOST=10.134.16.6
   DB_PORT=5000
   DB_NAME=bulutlake
   DB_USER=bulutlake
   DB_PASS=<şifre>
   INTERNAL_API_KEY=<api-key>
   ```

### İlk Başlatma

```bash
# Tüm servisleri build et ve başlat
docker compose up --build -d

# Sağlık durumunu kontrol et
docker compose ps
# Beklenen: db-service (healthy), redis (healthy), query-service (healthy), gui-service (Up)

# db-service loglarını kontrol et (pool oluşturuldu mu?)
docker logs datalake-platform-gui-db-service-1 | grep "pool"
# Beklenen: asyncpg pool created — host=10.134.16.6 port=5000 db=bulutlake (×2)
```

### Tarayıcıda Aç

```
http://localhost:8050
```

İlk veri yüklemesi ~40-74 saniye sürer (Redis cache boş). Sonraki yüklemeler < 1ms.

### VPN Bağlantı Sorunu

Servisler VPN kapalıyken başlatıldıysa:
```bash
docker restart datalake-platform-gui-db-service-1
docker logs datalake-platform-gui-db-service-1 | grep "pool"
# pool created → tarayıcıyı yenile
```

### Servis Güncelleme

```bash
# Sadece belirli bir servisi yeniden build et
docker compose up --build -d gui-service
docker compose up --build -d query-service
docker compose up --build -d db-service

# Redis cache'i temizle (veri değişikliği sonrası)
docker exec datalake-platform-gui-redis-1 redis-cli FLUSHALL
```

### Test Çalıştırma

```bash
# query-service testleri
docker exec datalake-platform-gui-query-service-1 \
  pip install pytest pytest-asyncio pytest-httpx -q && \
  docker exec datalake-platform-gui-query-service-1 \
  python -m pytest tests/ -v

# gui-service testleri
docker exec datalake-platform-gui-gui-service-1 \
  pip install pytest pytest-mock -q && \
  docker exec datalake-platform-gui-gui-service-1 \
  python -m pytest tests/ -v

# Yük testi
python scripts/load_test.py --host http://localhost:8050 --concurrency 5 --rounds 3
```

### Loglara Bakma

```bash
# Tüm servisler
docker compose logs -f

# Sadece belirli servis
docker logs datalake-platform-gui-query-service-1 -f

# Son 100 satır
docker logs datalake-platform-gui-db-service-1 --tail 100
```

---

## 10. Teknik Metrikler ve Sonuçlar

### Performans

| Endpoint | İlk İstek (Cold) | Sonraki İstekler (Cache HIT) |
|----------|-----------------|------------------------------|
| `/datacenters/summary` | ~39–74s | **< 1ms** |
| `/overview` | ~41s | **< 1ms** |
| `/datacenters/DC11` | ~18s | **< 1ms** |
| Redis cache TTL | — | 900s (15 dakika) |

### İmaj Boyutları

| Servis | Başlangıç | Final | Azalma |
|--------|-----------|-------|--------|
| db-service | ~773 MB | **270 MB** | **-65%** |
| query-service | ~304 MB | **281 MB** | -8% |
| gui-service | ~607 MB | **589 MB** | -3% |

### Test Kapsamı

| Paket | Testler | Sonuç |
|-------|---------|-------|
| `shared` (logger) | 11 | ✅ 11/11 PASS |
| `query-service` (endpoints) | 14 | ✅ 14/14 PASS |
| `gui-service` (api_client) | 10 | ✅ 10/10 PASS |
| **TOPLAM** | **35** | **✅ 35/35 PASS** |

### Güvenlik Katmanları

| Katman | Yöntem | Koruma Kapsamı |
|--------|--------|----------------|
| Ağ izolasyonu | Docker bridge (internal-net) | db-service ve query-service host'a açık değil |
| API Key | `X-Internal-Key` header | Tüm data endpoint'leri |
| IP Kısıtlama | `TrustedNetworkMiddleware` | Docker subnet dışı IP'lere 403 |
| `/health` bypass | Middleware whitelist | Healthcheck her zaman geçer |

### Servis Konfigürasyonu

| Servis | Server | Workers | Neden |
|--------|--------|---------|-------|
| db-service | uvicorn | 2 | asyncpg pool per-worker, güvenli |
| query-service | uvicorn | 1 | sampler task çakışma riski |
| gui-service | gunicorn | 2 | Dash WSGI, dcc.Store client-side |

### Kullanılan Teknolojiler

| Kategori | Teknoloji | Versiyon |
|----------|-----------|---------|
| Web Framework | FastAPI | latest |
| Async DB | asyncpg | latest |
| HTTP Client | httpx | latest |
| Cache | redis[hiredis] | latest |
| Dashboard | Dash | v4.0 |
| UI Bileşenleri | dash-mantine-components | v2.6.0 |
| İkonlar | dash-iconify | latest |
| Grafikler | Plotly | latest |
| Production Server | gunicorn / uvicorn | latest |
| Validation | Pydantic | v2 |
| Veri Tabanı | PostgreSQL (TimescaleDB) | 16.4 |
| Container | Docker | — |
| Orkestraion | Docker Compose | v3.8 |

---

*Bu dokümantasyon, Datalake-Platform-GUI projesinin tüm geliştirme sürecini kapsamaktadır. Proje 4 fazda tamamlanmış olup production-ready durumundadır.*
