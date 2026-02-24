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
[ ] Task 2.1: query-service FastAPI iskeletinin ve servisler arası iletişim (httpx) yapısının kurulması.
[ ] Task 2.2: VMware, Nutanix ve IBM özel sorgu mantıklarının docs/legacy/query_logic.md üzerinden taşınması.
[ ] Task 2.3: Redis entegrasyonu ile 15 dakikalık veri önbellekleme (Caching) mekanizmasının kurulması.
[ ] Task 2.4: db-service ve query-service arasındaki veri akışının doğrulanması.

## 🔵 AŞAMA 3: Kullanıcı Arayüzü ve Entegrasyon (GUI-Service)
Hedef: Plotly Dash ve DMC ile modern, hızlı ve dinamik bir dashboard sunumu.
[ ] Task 3.1: dmc.AppShell kullanarak Sidebar ve Header yapısının (Layout) kurulması.
[ ] Task 3.2: Dinamik sayfa yapısının (Multi-page app) ve routing mekanizmasının oluşturulması.
[ ] Task 3.3: Plotly grafik bileşenlerinin (Charts) query-service verileriyle beslenmesi.
[ ] Task 3.4: dcc.Interval kullanarak 15 dakikalık otomatik veri yenileme (Auto-refresh) döngüsünün kurulması.

## 🔴 AŞAMA 4: Yayına Hazırlık ve Optimizasyon
Hedef: Hata yönetimi, loglama ve stabilite.
[ ] Task 4.1: shared/utils altında merkezi loglama (Logging) sisteminin kurulması.
[ ] Task 4.2: Tüm servisler için temel unit testlerin yazılması.
[ ] Task 4.3: Genel sistem performans testi ve Docker imaj boyutlarının optimizasyonu.
