🚀 Datalake-GUI Proje Takip Çizelgesi
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
[ ] Task 4.1: shared/utils altında merkezi loglama (Logging) sisteminin kurulması.
[ ] Task 4.2: Tüm servisler için temel unit testlerin yazılması.
[ ] Task 4.3: Genel sistem performans testi ve Docker imaj boyutlarının optimizasyonu.
