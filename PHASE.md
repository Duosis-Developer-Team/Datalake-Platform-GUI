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

4.1 Logging & Utilities
Centralized Logs: shared/utils altında yapılandırılmış (Structured) loglama sistemi.
Error Handling: Global Exception Handler ile tüm mikroservis hatalarını kullanıcıya anlamlı mesajlar olarak dön.

4.2 Optimization & Security
Image Squashing: Docker imaj boyutlarını optimize et.
Security: API endpointlerini internal IP kısıtlamalarıyla koruma altına al.

## 🛠️ Teknik Bağımlılık Matrisi
PHASE 1 bitmeden hiçbir kod query-service içine yazılamaz.
PHASE 2 onayı almadan GUI-Service, sahte (mock) veri dışında işlem yapamaz.
Her aşama sonunda docs/lessons.md güncellenmelidir.
Her aşama sonunda todolist.md güncellenmelidir.
Her aşama sonunda aşama testleri yapılmalıdır.
Her aşama sonunda aşama test sonuçları docs/test_results.md dosyasına eklenmelidir.
