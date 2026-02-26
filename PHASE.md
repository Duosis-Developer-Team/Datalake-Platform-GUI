🗺️ Datalake-GUI Strategic Roadmap (Master Plan)
Bu döküman, projenin modüler mikroservis mimarisine geçiş sürecini teknik detaylarıyla tanımlar. Her aşama, bir önceki aşamanın stabilitesi üzerine inşa edilmelidir.

## 🟢 PHASE 1: Core Infrastructure & Data Abstraction
Odak: Veri erişimini standartlaştırmak ve konteynır orkestrasyonunu başlatmak.

1.1 Docker Orchestration
Task: docker-compose.yml dosyasında internal-net (bridge) ve external-net ağlarını tanımla.
Service Isolation: Her servisin kendi Dockerfile (python:3.11-slim) üzerinden izole build sürecini kur.
Environment Management: .env ve .dockerignore yapılandırmasını tamamla.

1.2 DB-Service (The DAL Layer)
Engine: FastAPI + SQLModel/SQLAlchemy (Async).
Legacy Migration: docs/legacy/db_logic.md içindeki SQL mantığını asenkron fonksiyonlara (async def) dönüştür.
Health Check: /health ve /db-status endpointlerini yayına al.

1.3 Shared Schemas
Contract: shared/schemas altında MetricBase, ClusterInfo, UserConfig gibi Pydantic modellerini tanımla. Tüm servisler veri transferinde bu modelleri kullanmak zorundadır.

## 🟡 PHASE 2: Intelligent Query Engine & Caching
Odak: İş mantığını merkezileştirmek ve API performansını maksimize etmek.

2.1 Query-Service Implementation
Adapter Pattern: VMware, Nutanix, IBM ve Loki için ayrı "Provider" modülleri oluştur.
Service Communication: db-service ile asenkron HTTP (httpx) üzerinden güvenli haberleşmeyi kur.

2.2 Redis & Performance
Caching Strategy: 15 dakikalık TTL (Time-to-Live) ile "Cache-aside" stratejisini uygula.
Heavy Lift: Karmaşık veri toplama (aggregation) işlemlerini backend'de yap; GUI'ye sadece "çizime hazır" JSON gönder.

## 🔵 PHASE 3: Advanced Reactive Dashboard (The GUI)
Odak: Kullanıcı deneyimini (UX) modern ve kesintisiz hale getirmek.

3.1 UI Architecture
Framework: Dash Mantine Components (DMC) v2.6.0.
Theme: Light Mode — beyaz/gri arka plan, pastel indigo/mavi tonlar. Dark mode hedeflenmez.
Layout: AppShell yapısı — Header (logo+başlık) + Global Sidebar + Main content area.
Global Sidebar (3 link): Overview (platform özeti), Data Centers (DC kart listesi), Customs (özel raporlar).
Dynamic Routing: Sayfa yenilenmeden (dcc.Location) URL bazlı navigasyon — Task 3.2'de eklenecek.

3.2 Page Hierarchy & Drill-down
/datacenters: Tüm veri merkezlerini kart halinde listeleyen ana sayfa (DC11, DC12...).
/datacenters/{dc_code}: Bir DC kartına tıklandığında açılan detay sayfası.
  Drill-down Tabs (dmc.Tabs — sadece bu sayfada, global sidebar'da değil):
    Intel Virtualization — VMware + Nutanix CPU/RAM metrikleri
    Power Virtualization — IBM + vCenter enerji tüketimi
    Backup               — Yedekleme durumu (ileriki aşamada)

### Bulutistan Kurumsal Görsel Standartları (Task 3.1–3.2 Çıktısı)
- Mesh Gradient Body: 4 katman radial-gradient (pastel indigo/violet, background-attachment: fixed)
- Glassmorphism: backdrop-filter blur(18px) — Header, Floating Sidebar, Stat Box, DC Card
- Floating Sidebar: AppShellNavbar şeffaf container → iç cam panel (sidebar-float), border-radius 20px, shadow
- Active NavLink: sol neon indikatör şerit (4px, indigo→violet gradient + box-shadow glow), pseudo-element ::before
- Stats Row: 4 ThemeIcon Paper kutusu (Cluster/Host/VM/Sağlık) — datacenters.py _stat_boxes()
- DC Card RingProgress: sağ köşe avg CPU+RAM+Storage %, renk eşikli (teal <60 / yellow <80 / red ≥80)
- Hover Micro-interactions: card translateY(-4px)+glow, ring scale(1.06), button box-shadow glow

3.3 Visualization & Interaction (Task 3.3 Çıktısı)
Plotly Integration: dc_detail.py içinde _donut_fig() + _bar_fig() factory fonksiyonları; şeffaf background + merkez annotation + legend.
Intel Sekmesi: CPU / RAM / Storage go.Pie(hole=0.62) donut charts — renk: Indigo / Violet / Sky, boş dilim: #e9ecef, merkez % annotation.
Power Sekmesi: Enerji KPI kutusu (id="power-kpi-kw") + IBM Hosts/VMs go.Bar chart (id="power-bar-graph") — Violet/Indigo palette.
Canlı Filtre Callback'leri:
  - dcc.Store(id="dc-detail-store"): layout fonksiyonunda API verisi (detail_raw) browser'a yazılır; callback'lere State olarak geçilir.
  - Intel @callback: Input(intel-cluster-filter.value) + State(dc-detail-store.data) → Output x3 (CPU/RAM/Storage figure). _apply_cluster_filter() ile oransal simülasyon (Cluster N → ağırlık=(N)/sum(1..k), kapasite=1/k).
  - Power @callback: Input(power-source-filter.value) + State(dc-detail-store.data) → Output (power-bar-graph figure + power-kpi-kw children). "vcenter" seçilirse 4 sütunlu bar (vCenter değerleri 0), KPI="Veri Yok".
  - prevent_initial_call=True: İlk render'da callback tetiklenmez; pre-rendered figürler korunur.
Premium Filter UI: mdi:filter-variant ThemeIcon (variant="light", radius="xl") + dmc.Select (size="sm", radius="xl") + dmc.Paper(radius="xl") — glassmorphism cam panel.
dcc.Loading: type="dot", color="#4c6ef5" — DMC LoadingOverlay yerine Dash çekirdek bileşeni (DMC v2.x uyumsuzluk sorunu nedeniyle).
chart-paper: Glassmorphism Paper wrapper (blur(14px), rgba(255,255,255,0.78)) — tüm grafik ve stat kutularında ortak sınıf.
Responsive Grid: cols={"base": 1, "sm": 3} — mobilde alt alta, desktopta yan yana.
3.4 Auto-Refresh (Task 3.4 Çıktısı)
Zombisiz Güncelleme: dcc.Interval(_INTERVAL_MS=900_000) — sayfa yenilenmeden arka planda sessiz 15 dakikalık döngü.
datacenters.py Mimarisi:
  - dcc.Interval(id="dc-list-interval", interval=900_000, n_intervals=0) + dmc.Box(id="dc-list-content", children=initial_content)
  - Layout pre-renders initial content (fast display); @callback(prevent_initial_call=True) → 15dk'da bir _refresh_dc_list() → get_summary() → _render_content().
  - İlk render'da sayfa anında açılır; callback sadece ilk 15dk dolduğunda tetiklenir.
dc_detail.py Mimarisi (Unified Callback):
  - dcc.Interval(id="dc-detail-interval") + dcc.Store(id="dc-code-store", data=dc_code) — dc_code sayfadan callback'e taşınır.
  - Eski ayrı filter callback'leri (2 adet) kaldırıldı → TEK _refresh_and_render() callback ile değiştirildi.
  - Input: dc-detail-interval.n_intervals + intel-cluster-filter.value + power-source-filter.value
  - State: dc-code-store.data + dc-detail-store.data
  - Output: 5 grafik (3 Intel donut + 1 Power bar + KPI text) + dc-detail-store.data (store güncellenir)
  - ctx.triggered_id == "dc-detail-interval" ise get_dc_detail(dc_code) → taze veri; aksi hâlde mevcut store verisi kullanılır.
  - Sessiz başarısızlık: API başarısız olursa mevcut veri korunur, hata sayfayı bozmaz.
  - prevent_initial_call=True: İlk render pre-built charts'ı korur; callback filtre/interval tetiklenince devreye girer.

3.5 Executive Overview (Task 3.5 Çıktısı — Phase 3 TAMAMLANDI)
Sayfa: /overview — "Executive Command Center" — C-Level anlık platform durumu.
Sparklines (3 adet Area Chart):
  - go.Scatter(fill='tozeroy', shape='spline') — CPU / RAM / Ağ Trafiği
  - 24 saatlik saatlik mock zaman serisi (deterministik, mantıklı dalgalanma)
  - Eksenler gizli, şeffaf arka plan, hafif gölge dolgu
  - Her kart: ThemeIcon + değer + chart-paper glassmorphism
Vendor Donut (Altyapı Dağılımı):
  - go.Pie(hole=0.62) — VMware %60 / Nutanix %25 / IBM Power %15
  - Renk: Indigo / Violet / Sky paleti, merkez "Vendor Mix" annotation
  - Özel renk legend (3 nokta + etiket, SimpleGrid)
Sistem Olay Günlüğü (dmc.Timeline):
  - 5 simüle edilmiş olay: CPU Alarmı, Yedekleme OK, Cluster Eklendi, Cache Miss, Cluster Sağlık
  - dmc.TimelineItem(title=dmc.Group([title, badge]), bullet=DashIconify)
  - active=4 (tüm maddeler aktif), bulletSize=22, color="indigo"
  - CANLI badge (teal, variant="dot") — sayfa başlığı yanında
Layout: dmc.Container → dmc.Group(başlık+badge) → SimpleGrid(3 spark) → SimpleGrid(donut|timeline)
Tüm paneller: className="chart-paper" + p="xl" + radius="xl" glassmorphism

## 🔴 PHASE 4: Production Readiness & Observability
Odak: Sistemin hatasız, hızlı ve izlenebilir olduğunu kanıtlamak.

4.1 Redis Sliding Window Zaman Serisi (Task 4.1 — TAMAMLANDI ✅)
  - shared/schemas/responses.py: TrendSeries + OverviewTrends modelleri eklendi.
  - tasks/sampler.py (YENİ): Her 5 dakikada bir CPU%, RAM%, Enerji kW → Redis LPUSH+LTRIM (max 30 nokta). Başlangıçta anında 1 örnek (warm-up). Pipeline atomik yazma. Hata → warn log, sessiz geçiş.
  - query_service.py: get_overview_trends() —LRANGE → reversed → kronolojik TrendSeries. Boş Redis → boş liste, graceful.
  - routers/data.py: GET /overview/trends endpoint'i eklendi (OverviewTrends response_model).
  - api_client.py (gui-service): get_overview_trends() HTTP wrapper.
  - overview.py (gui-service): Mock seriler kaldırıldı. dcc.Interval(300s) + @callback(prevent_initial_call=False) → gerçek veri. 3. sparkline: "Ağ Trafiği" → "Toplam Enerji (kW)" (mdi:lightning-bolt).
  - main.py: asyncio.create_task(run_sampler(app)) lifespan'da; shutdown'da cancel+suppress(CancelledError).

4.2 Merkezi Loglama (Task 4.2 — TAMAMLANDI ✅)
  - shared/utils/logger.py (YENİ): setup_logger(service_name, level) API.
    Format: [%(asctime)s] [%(levelname)-8s] [%(name)s] - %(message)s
    Özellikler: idempotent handler (Dash hot-reload güvenli), stdout StreamHandler,
    LOG_LEVEL env override, Python hiyerarşik logging ile tam uyumlu (propagation korunuyor).
  - shared/utils/__init__.py (YENİ): paket işaretçisi + setup_logger public export.
  - query-service/src/main.py: logging.basicConfig kaldırıldı → setup_logger("query-service").
    Tüm src.* modülleri (sampler, query_service, providers) getLogger(__name__) ile child
    logger açmaya devam eder — Python hiyerarşisi formatı otomatik yayar.
  - gui-service/app.py: setup_logger("gui-service") eklendi (Dash entry-point).
  - gui-service/services/api_client.py: Her 3 fonksiyon (get_summary, get_dc_detail,
    get_overview_trends) için Timeout / HTTPError / RequestException ayrı ayrı
    logger.error ile loglanıp yeniden fırlatılıyor.


4.3 Unit Tests (Task 4.3 — TAMAMLANDI ✅)
  Kapsam: 3 servis × pytest — shared (11) + query-service (14) + gui-service (10) = 35/35 PASS.
  Mimari Karar: FastAPI dependency_overrides ile tam DI izolasyonu (Option B) — QueryService mock'lanmaz.
  query-service conftest.py:
    - _httpx_response(url): dummy_request = httpx.Request("GET", url) + httpx.Response(request=dummy_request)
      → raise_for_status() RuntimeError çözüldü.
    - mock_db_client.get = _mock_get (async) → URL "summary" içeriyorsa SAMPLE_SUMMARY_RAW döner.
    - mock_redis: get→None (cache miss), lrange→[SAMPLE_TREND_ENTRY], set→True.
    - api_client fixture: dependency_overrides[3 bağımlılık] → TestClient(raise_server_exceptions=True).
  gui-service tests: pytest-mock mocker fixture + caplog.at_level(ERROR) + pytest.raises pattern.
  Container build notu: conftest.py değişirse container yeniden build edilmeli veya docker cp uygulanmalı.

4.4 Optimization & Security (Task 4.4 — TAMAMLANDI ✅)

Docker İmaj Optimizasyonu (Multi-Stage Build):
  db-service: builder stage (build-essential + libpq-dev) → production stage (libpq5 runtime only).
  773 MB → 270 MB (-65%). query-service 304→281 MB (-8%). gui-service 607→589 MB (-3%).
  requirements.txt ayrıştırması: requirements-dev.txt (pytest/*) oluşturuldu; prod imajından test deps çıkarıldı.
  .dockerignore: services/*/tests/, shared/tests/, *.md, scripts/ eklendi.

Production Server:
  gui-service: CMD python app.py → gunicorn --bind 0.0.0.0:8050 --workers 2 --timeout 120 app:server
  db-service: uvicorn --workers 2 (asyncpg pool per-worker, güvenli)
  query-service: 1 worker (sampler task çakışma riski nedeniyle)

Security — IP Kısıtlama (Defense-in-Depth):
  shared/utils/trusted_network.py (YENİ): TrustedNetworkMiddleware — Starlette BaseHTTPMiddleware,
  stdlib ipaddress, ALLOWED_SUBNETS env var (CIDR liste), /health bypass, 403 JSON response.
  db-service + query-service main.py: app.add_middleware(TrustedNetworkMiddleware)
  docker-compose.yml: ALLOWED_SUBNETS=172.16.0.0/12,10.0.0.0/8,127.0.0.1/32 her iki servise eklendi.

Yük Testi:
  scripts/load_test.py: asyncio + httpx, 3 endpoint, --concurrency / --rounds argümanları.
  Kullanım: python scripts/load_test.py --host http://localhost:8050

## 🛠️ Teknik Bağımlılık Matrisi
PHASE 1 bitmeden hiçbir kod query-service içine yazılamaz.
PHASE 2 onayı almadan GUI-Service, sahte (mock) veri dışında işlem yapamaz.
Her aşama sonunda docs/lessons.md güncellenmelidir.
Her aşama sonunda todolist.md güncellenmelidir.
Her aşama sonunda aşama testleri yapılmalıdır.
Her aşama sonunda aşama test sonuçları docs/test_results.md dosyasına eklenmelidir.
