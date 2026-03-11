# Bulutistan Dashboard — Mikro Servis Dönüşümü: Workflow Anayasası (Skills)

> Bu dosya, Executer (Claude Code / Cursor) ajanının çalışma şeklini belirleyen MUTLAK KURALLARDIR.
> Hiçbir ajan, hiçbir koşulda bu kuralları ihlal edemez.

---

## 1. Plan Mode Default

Trivial olmayan her görev için Executer önce bir plan dosyası oluşturur.
Plan onaylanmadan kodlamaya geçilmez.
Plan içeriği: etkilenen dosyalar, değişiklik özeti, risk analizi ve geri dönüş stratejisi.

## 2. Subagent Strategy

Her alt ajan TEK BİR görev üstlenir.
Bir ajanın bağlamı kirlenmemeli; görev bitince ajan sonlandırılır.
Bu sayede token bütçesi korunur ve hallüsinasyon riski minimize edilir.

## 3. Self-Improvement Loop

Her hata veya beklenmeyen davranış `mcrsrvc_lessons.md` dosyasına öğreti olarak eklenir.
Aynı hata ikinci kez yapılamaz; Executer, göreve başlamadan önce `mcrsrvc_lessons.md` dosyasını okur.

## 4. Verification Before Done

Bir görevin "tamamlandı" olarak işaretlenmesi için aşağıdaki koşullar sağlanmalıdır:

- Unit test'ler geçiyor (`pytest` çıktısı kanıt olarak sunulur)
- Docker build başarılı (`docker build` log'u kanıt olarak sunulur)
- Endpoint'ler yanıt veriyor (`curl` veya `httpx` ile test edilir)
- Mevcut davranış korunuyor (regresyon testi geçiyor)

"İşe yarıyor gibi görünüyor" KABUL EDİLMEZ. Kanıt olmadan done işareti KONULMAZ.

## 5. Demand Elegance & No Laziness

Geçici yama (monkey-patch, quick-fix) YASAKTIR.
Sorunun KÖK NEDENİ bulunur ve en temiz çözüm uygulanır.
Kod tekrarı (DRY ihlali) kabul edilmez; ortak mantık her zaman ayrı bir modüle çıkarılır.

## 6. Autonomous Bug Fixing

Executer bir hata ile karşılaştığında CTO'dan talimat beklemez.
Log'lara bakar, stack trace'i analiz eder ve hatayı kendi çözer.
Çözemediği durumda sorunu, denenen çözümleri ve başarısızlık nedenlerini raporlar.

---

## 7. CTO KIRMIZI ÇİZGİSİ (MUTLAK KURAL)

> **KODLARDA ASLA YORUM SATIRI (COMMENT) KULLANILMAYACAK. KOD KENDİNİ AÇIKLAYACAK.**

Bu kuralın istisnaları:

- `TODO:` veya `FIXME:` etiketleri (yalnızca geçici, izlenebilir iş takibi için)
- Lisans başlıkları (zorunlu olduğu durumlarda)
- Regex açıklamaları (`re.VERBOSE` flag'i ile inline açıklama kullanılmalı, dışarıya yorum yazılmamalı)

Yukarıdaki istisnalar dışında hiçbir yorum satırı kabul edilmez.
Fonksiyon/sınıf isimleri, parametre isimleri ve modül yapısı tek başına okunabilir olmalıdır.
Docstring KULLANILMAZ; fonksiyon imzası ve dönüş tipi yeterli olmalıdır.

---

## 8. Proje Spesifik Kurallar (Bulutistan Dashboard)

### 8.1 Mevcut Mimari Özeti

| Katman         | Mevcut Teknoloji          | Hedef Teknoloji             |
|----------------|---------------------------|-----------------------------|
| Frontend       | Dash + Mantine (Monolitik)| Next.js veya ayrı SPA       |
| Backend        | Dash callbacks (app.py)   | FastAPI mikro servisler      |
| Veritabanı     | PostgreSQL (psycopg2 pool)| PostgreSQL (asyncpg/SQLAlchemy async) |
| Cache          | cachetools TTLCache       | Redis                        |
| Scheduler      | APScheduler (in-process)  | Celery / K8s CronJob         |
| Container      | Docker (tek konteyner)    | Docker + Kubernetes          |

### 8.2 Servis Ayrıştırma Haritası

Monolitik `DatabaseService` sınıfı (1290 satır) aşağıdaki mikro servislere ayrılacak:

| Mikro Servis             | Sorumluluk                                    | Kaynak Metotlar                                      |
|--------------------------|-----------------------------------------------|------------------------------------------------------|
| `dc-service`             | Datacenter detayları ve özet listesi           | `get_dc_details`, `get_all_datacenters_summary`      |
| `platform-service`       | Nutanix / VMware / IBM platform metrikleri     | `get_nutanix_*`, `get_vmware_*`, `get_ibm_*`         |
| `energy-service`         | Enerji tüketimi (kW/kWh) hesaplamaları         | `get_ibm_energy`, `get_vcenter_energy`, `*_kwh`      |
| `customer-service`       | Müşteri bazlı kaynak görünümü                  | `get_customer_resources`, `get_customer_list`         |
| `query-explorer-service` | Kayıtlı sorgu çalıştırma                       | `execute_registered_query`                           |
| `cache-service`          | Merkezi cache yönetimi (Redis)                  | `cache_service.py` modülü                            |
| `scheduler-service`      | Periyodik veri yenileme                         | `scheduler_service.py` modülü                        |
| `gateway`                | API Gateway (routing, auth, rate-limit)         | Yeni                                                 |

### 8.3 Veritabanı Bağlantı Kuralları

Mevcut sistemde `ThreadedConnectionPool(minconn=2, maxconn=16)` kullanılıyor.
Mikro servis yapısında her servisin kendi pool'u olacak.
Toplam bağlantı sayısı PostgreSQL `max_connections` limitini aşmamalı.
Her servis için önerilen pool boyutu: `minconn=1, maxconn=4`.

### 8.4 Birim Dönüşüm Tablosu (Kritik)

Aşağıdaki birim dönüşümleri `_aggregate_dc` fonksiyonunda uygulanmaktadır ve yeni servislere birebir aktarılmalıdır:

| Metrik           | Nutanix Kaynak Birimi | VMware Kaynak Birimi | Hedef Birim |
|------------------|-----------------------|----------------------|-------------|
| Memory           | TiB → GB (×1024)      | Bytes → GB (÷1024³)  | GB          |
| Storage          | TB (olduğu gibi)      | Bytes → TB (÷1024⁴)  | TB          |
| CPU              | GHz (olduğu gibi)     | Hz → GHz (÷10⁹)      | GHz         |
| Energy (IBM/vC)  | Watt                  | Watt                 | kW (÷1000)  |

---

## 9. Git & CI/CD Kuralları

- Her mikro servis kendi dizininde yaşar: `services/<servis-adı>/`
- Branch stratejisi: `feature/<servis-adı>/<özellik>` → `develop` → `main`
- PR açılmadan build ve test pipeline'ı geçmeli
- Docker image'leri semantic versioning ile tag'lenir: `v1.0.0`, `v1.0.1`

---

## 10. Dosya ve Dizin Yapısı Şablonu (Her Yeni Mikro Servis İçin)

```
services/<servis-adı>/
├── app.py                  # FastAPI entrypoint
├── config.py               # Ortam değişkenleri ve ayarlar
├── models/                 # Pydantic şemaları
│   └── schemas.py
├── routers/                # API endpoint tanımları
│   └── v1.py
├── core/                   # İş mantığı
│   └── logic.py
├── db/                     # Veritabanı bağlantı ve sorgu yönetimi
│   ├── connection.py
│   └── queries.py
├── tests/                  # Birim ve entegrasyon testleri
│   ├── test_logic.py
│   └── test_endpoints.py
├── Dockerfile
├── requirements.txt
└── k8s/
    ├── deployment.yaml
    ├── service.yaml
    └── configmap.yaml
```
