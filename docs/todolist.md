## 🚀 Datalake-GUI Proje Takip Çizelgesi
Bu dosya, projenin monolitik yapıdan mikroservis mimarisine geçiş sürecindeki tüm görevleri ve mevcut durumu takip etmek için kullanılır. Her görev skills.md kurallarına uygun olarak icra edilecektir.

## 🟢 AŞAMA 1: Altyapı ve Veri Katmanı (Foundation & DB-Service)
Hedef: Temel orkestrasyonun kurulması ve veritabanı erişiminin API haline getirilmesi.
[x] Task 1.1: Merkezi docker-compose.yml ve .dockerignore dosyalarının oluşturulması (port düzeltme, network, Redis, dizin yapısı).
[x] Task 1.2: DB-Service (DAL Katmanı) — FastAPI + asyncpg ile async DAL; docs/legacy/db_logic.md ve query_logic.md mantığının taşınması; /health, /db-status, /datacenters/* endpoint'leri.
[x] Task 1.3: shared/schemas altında Pydantic modellerinin (DCMeta, PowerInfo, IntelMetrics, EnergyMetrics, DCStats, DCSummary, DCDetail, GlobalOverview) tanımlanması; build context migrasyonu; db-service entegrasyonu.
[x] Task 1.4: Veritabanı bağlantı testlerinin yapılması ve tüm endpoint'lerin doğrulanması; sonuçların docs/test_results.md'ye işlenmesi.

## 🟡 AŞAMA 2: İş Mantığı ve Sorgu Motoru (Query-Service)
Hedef: Veri kaynaklarına özel sorguların yönetilmesi ve performans optimizasyonu.
[x] Task 2.1: query-service FastAPI iskeletinin ve servisler arası iletişim (httpx) yapısının kurulması.
[x] Task 2.2: VMware, Nutanix ve IBM özel sorgu mantıklarının docs/legacy/query_logic.md üzerinden taşınması.
[x] Task 2.3: Redis entegrasyonu ile 15 dakikalık veri önbellekleme (Caching) mekanizmasının kurulması.
[x] Task 2.4: db-service ve query-service arasındaki veri akışının doğrulanması.

## 🔵 AŞAMA 3: Kullanıcı Arayüzü ve Entegrasyon (GUI-Service)
Hedef: Plotly Dash ve DMC ile modern, hızlı ve dinamik bir dashboard sunumu.
[x] Task 3.1: dmc.AppShell + Light Mode layout; Header (logo+başlık), Global Sidebar (3 NavLink: Overview, Data Centers, Customs), Dockerfile curl fix. NOT: Intel/Power/Backup global sidebar'da değil, DC detay sayfasında dmc.Tabs olarak yer alacak (Task 3.2+).
[x] Task 3.2: /datacenters (DC kart listesi + 4'lü Stats Row + RingProgress) + /datacenters/{dc_code} detay sayfası (Hero Section + dmc.Tabs: Intel/Power/Backup) + dcc.Location routing + Bulutistan Kurumsal Görsel Standardı: Mesh Gradient body, Glassmorphism, Floating Sidebar (cam panel, border-radius 20px), Active NavLink neon indikatör şerit, DC Card hover glow+lift.
[x] Task 3.3: Plotly grafik bileşenlerinin (Charts) query-service verileriyle beslenmesi — Intel sekmesi (CPU/RAM/Storage go.Pie donut + merkez % annotation), Power sekmesi (enerji KPI kutusu + IBM Hosts/VMs go.Bar), dmc.LoadingOverlay→dcc.Loading(type="dot"), chart-paper glassmorphism, responsive SimpleGrid (base:1 → sm:3) + Canlı Filtre Callback'leri: dcc.Store(dc-detail-store) + @callback (Intel: cluster seçimi → 3 donut güncelleme, oransal simülasyon; Power: kaynak seçimi → bar + KPI metni güncelleme, vcenter → 4 sütun), Premium Filter UI (mdi:filter-variant ThemeIcon, radius="xl", glassmorphism Paper).
[x] Task 3.4: dcc.Interval(900_000ms) ile 15 dakikalık "Zombisiz" otomatik veri yenileme döngüsünün kurulması — datacenters.py: dcc.Interval + _render_content() callback (prevent_initial_call=True, initial render fast); dc_detail.py: eski 2 filter callback → 1 unified _refresh_and_render() (interval+filtre Input, dc-code-store State, ctx.triggered_id ile veri fetch kararı, sessiz başarısızlık).
[x] Task 3.5: /overview Executive Command Center — 3 Sparkline (go.Scatter fill=tozeroy, CPU/RAM/Ağ, 24 saatlik mock seri), Vendor Donut (go.Pie hole=0.62, VMware/Nutanix/IBM), dmc.Timeline Sistem Olay Günlüğü (5 simüle olay, DashIconify bullet), CANLI badge, tüm paneller chart-paper glassmorphism. Phase 3 TAMAMEN TAMAMLANDI ✅

## 🔴 AŞAMA 4: Yayına Hazırlık ve Optimizasyon
Hedef: Hata yönetimi, loglama ve stabilite.
[x] Task 4.1: Redis Sliding Window (Kayan Pencere) Zaman Serisi Mimarisi. ✅
  - shared/schemas/responses.py: TrendSeries + OverviewTrends Pydantic modelleri eklendi.
  - Backend (query-service): tasks/sampler.py oluşturuldu — FastAPI lifespan'a asyncio.create_task ile bağlandı. Servis başlarken anında 1 örnek alır, ardından her 5 dakikada bir (CPU%, RAM%, Enerji kW) verilerini Redis'e LPUSH + LTRIM (max 30 nokta, ~2.5 saatlik pencere) ile yazar. Pipeline ile atomik yazma, tam hata toleransı.
  - API (query-service): GET /overview/trends endpoint'i eklendi (OverviewTrends şeması). Redis listelerini tersine çevirerek kronolojik TrendSeries döndürür. Boş/hata durumunda graceful degradation.
  - Frontend (gui-service): overview.py mock verileri silindi. dcc.Interval(300_000ms) + @callback(prevent_initial_call=False) ile gerçek zaman serisi verileri çekiliyor. 3. sparkline "Ağ Trafiği" → "Toplam Enerji (kW)" olarak güncellendi.

[x] Task 4.2: shared/utils altında merkezi loglama (Logging) sisteminin kurulması. ✅
  - shared/utils/logger.py (YENİ): setup_logger(service_name) fonksiyonu — kurumsal [tarih] [seviye] [logger-adı] formatı, idempotent handler, stdout çıktısı, LOG_LEVEL env override.
  - shared/utils/__init__.py (YENİ): paket işaretçisi + setup_logger public export.
  - query-service/src/main.py: logging.basicConfig kaldırıldı → setup_logger("query-service"). Modüllerdeki getLogger(__name__) değişmedi; Python hiyerarşisi formatı otomatik yayıyor.
  - gui-service/app.py: setup_logger("gui-service") eklendi — Dash entry-point log yapılandırması.
  - gui-service/services/api_client.py: logger.error ile Timeout/HTTPError/RequestException hataları loglanıyor; exception yeniden fırlatılıyor (callback no_update ile sessiz kalıyor).
[x] Task 4.3: Tüm servisler için temel unit testlerin yazılması. ✅
  - shared/tests/test_logger.py (11 test): setup_logger idempotency, format, stdout handler, LOG_LEVEL override — 11/11 PASS.
  - query-service/tests/conftest.py: httpx.Response dummy_request fix uygulandı (raise_for_status() RuntimeError çözüldü). DI izolasyonu: get_db_client → mock_db_client (gerçek httpx.Response), get_redis → mock_redis (AsyncMock), verify_internal_key bypass.
  - query-service/tests/test_endpoints.py (14 test): TestHealth(3) + TestOverviewTrends(6) + TestDatacentersSummary(5) — 14/14 PASS.
  - gui-service/tests/test_api_client.py (10 test): TestGetSummary(4) + TestGetDcDetail(3) + TestGetOverviewTrends(3) — 10/10 PASS.
  - Toplam: 35/35 PASS (shared:11 + query:14 + gui:10).
[x] Task 4.4: Genel sistem performans testi ve Docker imaj boyutlarının optimizasyonu. ✅
  - Docker İmaj Optimizasyonu (Derin — Multi-Stage): db-service 773 MB → 270 MB (-65%), query-service 304 MB → 281 MB (-8%), gui-service 607 MB → 589 MB (-3%).
  - db-service Dockerfile yeniden yazıldı: builder stage (build-essential + libpq-dev derleme), production stage (sadece libpq5 runtime + curl). COPY --from=builder + ENV PATH.
  - requirements.txt ayrıştırması: query-service ve gui-service için requirements-dev.txt oluşturuldu; pytest/* test bağımlılıkları prod imajından çıkarıldı.
  - .dockerignore güncellendi: services/*/tests/, shared/tests/, *.md, scripts/ eklendi.
  - Prodüksiyon Sunucusu: gui-service CMD python app.py → gunicorn --workers 2 --timeout 120. db-service uvicorn --workers 2. query-service 1 worker (sampler task çakışma riski).
  - Güvenlik (Defense-in-Depth): shared/utils/trusted_network.py — TrustedNetworkMiddleware (Starlette BaseHTTPMiddleware, stdlib ipaddress, ALLOWED_SUBNETS env var). db-service ve query-service main.py'e eklendi. docker-compose.yml ALLOWED_SUBNETS=172.16.0.0/12,10.0.0.0/8,127.0.0.1/32. /health her zaman açık (healthcheck bypass).
  - scripts/load_test.py oluşturuldu: asyncio + httpx, 3 endpoint, --concurrency / --rounds argümanları.
  - Phase 4 TAMAMEN TAMAMLANDI ✅ Proje PRODUCTION-READY.
