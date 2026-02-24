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
Framework: Dash Mantine Components (DMC) v0.14+.
Layout: AppShell yapısı ile Sidebar ve Navbar entegrasyonu.
Dynamic Routing: Sayfa yenilenmeden (dcc.Location) URL bazlı navigasyon.

3.2 Visualization & Interaction
Plotly Integration: Interaktif grafiklerde hoverData ve clickData ile derinlemesine analiz yeteneği.
Auto-Refresh: dcc.Interval ile 15 dakikalık "Zombisiz" (arka planda sessiz) güncelleme döngüsü.

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
