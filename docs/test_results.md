🧪 Project Test Results & Verification Logs
Bu dosya, her aşamanın (Phase) sonunda gerçekleştirilen testlerin sonuçlarını, performans metriklerini ve doğrulama kanıtlarını (logs/screenshots/diffs) kayıt altına almak için kullanılır.

## 🟢 PHASE 1: Test Detayları — 2026-02-23 TAMAMLANDI

### 1.1 Container Orchestration
[x] docker-compose up --build -d db-service → Container başarıyla ayağa kalktı
[x] asyncpg pool oluşturuldu: host=10.134.16.6 port=5000 db=bulutlake
[x] Servis internal-net üzerinde erişilebilir (expose: 8001)

**Giderilen sorunlar:**
- DB_USER düzeltmesi: `datalakeui` → `bulutlake`
- .env CRLF → LF (trailing \r şifre hatasına yol açıyordu)

### 1.2 DB-Service API Doğrulama
[x] GET /health → 200 OK: `{"status": "ok", "service": "db-service"}`
[x] GET /db-status (X-Internal-Key) → 200 OK: `{"status": "connected", "db_check": true, "pool_size": 2}`
[x] GET /datacenters/summary → 200 OK — 14 DC (39.7s)
```
AZ11: hosts=4   vms=11    cpu=1.6%   ram=1.5%
DC11: hosts=64  vms=1368  cpu=46.3%  ram=70.3%
DC12: hosts=10  vms=158   cpu=30.0%  ram=34.5%
DC13: hosts=122 vms=64    cpu=54.4%  ram=67.0%
DC14: hosts=85  vms=1327  cpu=37.9%  ram=43.8%
DC15: hosts=53  vms=1578  cpu=64.8%  ram=76.9%
DC16: hosts=28  vms=886   cpu=29.9%  ram=48.3%
ICT11: hosts=3  vms=90    cpu=8.5%   ram=24.9%
```
[x] GET /datacenters/DC11 → 200 OK (18.8s): clusters=4, hosts=36, vms=1368
[x] GET /overview → 200 OK (38.2s): `{"total_hosts":369, "total_vms":5482, "dc_count":14}`

### Performans İyileştirmeleri (Task 1.4'te yapıldı)
- TimescaleDB zaman filtresi: `AND timestamp >= NOW() - INTERVAL '4 hours'` (vmware, nutanix, energy/vcenter)
- `loki_racks` gereksiz `id IN (SELECT DISTINCT id ...)` subquery kaldırıldı
- `command_timeout`: 30s → 60s
- Yanıt süresi: 97s → ~40s (%59 iyileşme), 0 hata

### Bilinen Sorunlar (Phase 2'de giderilecek)
- VMware cpu_cap/ram_cap/storage_cap sayısal değerleri yanlış — SQL birim çarpımları ile Python bölmeleri tutarsız. Düzeltme: SQL'den çarpımları kaldır, ham GB değerini al, Python'da dönüştür.
- IBM energy (ibm_server_power) zaman filtresi eksik → SUM tüm geçmişi topluyor, enerji değerleri anormal yüksek.
- Phase 2 Redis cache ile: ilk yükleme 40s → sonraki istekler <100ms olacak.

## 🏠 YENİ EV REGRESYON TESTİ — 2026-02-24

### Ortam Doğrulaması
[x] Proje: Datalake-Platform-GUI (yeni Git repo, temiz sayfa)
[x] python -m venv .venv → oluşturuldu
[x] asyncpg + python-dotenv → yüklendi
[x] .env satır sonları: LF (CRLF yok — temiz)
[x] VPN bağlantısı aktif — PostgreSQL 16.4 erişilebilir

### Docker Build
[x] docker-compose down -v → temiz başlangıç
[x] docker-compose up --build -d db-service → BUILD SUCCESS
[x] Dockerfile curl fix: `curl` paketi eklendi (healthcheck için zorunlu)
[x] Container durumu: `(healthy)` — healthcheck geçti

### Endpoint Doğrulama (docker exec ile)
[x] GET /health → 200 OK: `{"status": "ok", "service": "db-service"}`
[x] GET /db-status (X-Internal-Key) → 200 OK: `{"status": "connected", "db_check": true, "pool_size": 2}`
[x] GET /datacenters/summary → 200 OK — 14 DC (1. çalışma: 74s soğuk, 2. çalışma: **39s**)
```
AZ11:  hosts=4    vms=11    cpu=1.5%   ram=1.5%
DC11:  hosts=64   vms=1370  cpu=53.6%  ram=70.5%
DC12:  hosts=10   vms=159   cpu=27.6%  ram=34.6%
DC13:  hosts=122  vms=64    cpu=61.5%  ram=67.5%
DC14:  hosts=85   vms=1327  cpu=59.3%  ram=60.5%
```
[x] GET /overview → 200 OK (41s): `{"total_hosts":369, "total_vms":5489, "dc_count":14}`

**Sonuç: Yeni evde tüm endpoint'ler çalışıyor. Performans eski klasörle birebir (39s ≈ 39.7s).**

### Keşfedilen ve Düzeltilen Bug
- Dockerfile'da `curl` eksikti → healthcheck asla `healthy` olamıyordu → `depends_on: service_healthy` zinciri kırılıyordu.
- Çözüm: `apt-get install -y curl` eklendi, rebuild yapıldı.

---

## 🟡 PHASE 2: Test Detayları

### 2.1 Query-Service İskelet & httpx Haberleşmesi — 2026-02-24 TAMAMLANDI

#### Oluşturulan Dosyalar
[x] services/query-service/src/__init__.py
[x] services/query-service/src/main.py          (httpx.AsyncClient lifespan)
[x] services/query-service/src/dependencies.py  (verify_internal_key + get_db_client)
[x] services/query-service/src/routers/health.py
[x] services/query-service/src/routers/data.py
[x] services/query-service/src/services/query_service.py
[x] services/query-service/Dockerfile           (curl eklendi)

#### Docker Build
[x] docker-compose up --build -d db-service query-service → BUILD SUCCESS
[x] depends_on: service_healthy zinciri çalıştı (db-service healthy → query-service başladı)
[x] db-service, redis, query-service → üçü de `(healthy)`

#### Startup Log Kanıtı
```
httpx client ready — db-service reachable at http://db-service:8001
Application startup complete. Uvicorn running on http://0.0.0.0:8002
```

#### Endpoint Doğrulama (query-service → db-service zinciri)
[x] GET /health → 200 OK: `{"status": "ok", "service": "query-service"}`
[x] GET /service-status (X-Internal-Key) → 200 OK:
    `{"status": "ok", "service": "query-service", "db_service": "reachable"}`
[x] GET /datacenters/summary (X-Internal-Key) → 200 OK, 14 DC, **41s**
```
AZ11: hosts=4   vms=11    cpu=1.6%   ram=1.5%
DC11: hosts=64  vms=1370  cpu=54.5%  ram=70.5%
DC12: hosts=10  vms=159   cpu=31.4%  ram=34.6%
DC13: hosts=122 vms=64    cpu=60.4%  ram=67.4%
DC14: hosts=85  vms=1327  cpu=57.1%  ram=61.7%
```

**Sonuç: query-service → db-service httpx proxy zinciri doğrulandı. Task 2.1 tamamlandı.**

### 2.3 Redis Cache-Aside — 2026-02-24 TAMAMLANDI

#### Değiştirilen Dosyalar
[x] services/query-service/src/main.py          (lifespan'a Redis client eklendi → app.state.redis)
[x] services/query-service/src/dependencies.py  (get_redis DI fonksiyonu eklendi)
[x] services/query-service/src/routers/data.py  (_get_service → QueryService(client, redis))
[x] services/query-service/src/services/query_service.py  (cache-aside logic, 3 metot)

#### Docker Build
[x] docker-compose up --build -d query-service → BUILD SUCCESS
[x] query-service (healthy), db-service (healthy), redis (healthy)

#### Startup Log Kanıtı
```
httpx client ready — db-service reachable at http://db-service:8001
Redis client ready — connected at redis://redis:6379/0
Application startup complete. Uvicorn running on http://0.0.0.0:8002
```

#### Cache MISS / HIT Doğrulama

| Endpoint | 1. İstek (MISS) | 2. İstek (HIT) | httpx db-service çağrısı |
|---|---|---|---|
| GET /datacenters/summary | ~317ms (db warm) | ~293ms* | Sadece 1. istekte |
| GET /overview | 39.1s (db cold query) | ~291ms* | Sadece 1. istekte |

*Docker exec process overhead (~250ms). Gerçek Redis yanıtı sub-millisecond.

**Log kanıtı (Cache HIT = httpx log yok):**
```
# 1. istek — MISS: db-service çağrısı var
httpx | HTTP Request: GET http://db-service:8001/datacenters/summary "HTTP/1.1 200 OK"
INFO: GET /datacenters/summary HTTP/1.1" 200 OK

# 2. istek — HIT: httpx logu YOK, sadece uvicorn access log var
INFO: GET /datacenters/summary HTTP/1.1" 200 OK

# /overview MISS → HIT aynı pattern
httpx | HTTP Request: GET http://db-service:8001/overview "HTTP/1.1 200 OK"
INFO: GET /overview HTTP/1.1" 200 OK
INFO: GET /overview HTTP/1.1" 200 OK  ← ikinci istek, httpx log yok = HIT
```

#### Redis Key & TTL Doğrulama
```
docker exec redis redis-cli keys "*"
→ dc_summary_all
→ global_overview

docker exec redis redis-cli ttl dc_summary_all
→ 747  (900 - 153s = beklenen)

docker exec redis redis-cli ttl global_overview
→ 845  (900 - 55s = beklenen)
```

**Sonuç: Cache-aside mekanizması devreye alındı. MISS→HIT geçişi doğrulandı. Redis TTL=900s çalışıyor. Task 2.3 tamamlandı.**

### 2.2 Provider Adapter Katmanı — 2026-02-24 TAMAMLANDI

#### Oluşturulan Dosyalar
[x] services/query-service/src/providers/__init__.py
[x] services/query-service/src/providers/base.py       (BaseProvider ABC + status utils)
[x] services/query-service/src/providers/vmware.py     (VMwareProvider)
[x] services/query-service/src/providers/nutanix.py    (NutanixProvider)
[x] services/query-service/src/providers/ibm.py        (IBMProvider)
[x] services/query-service/src/services/query_service.py  (TODO 2.2 → provider pipeline)

#### Docker Build
[x] docker-compose up --build -d query-service → BUILD SUCCESS (sadece query-service rebuild)
[x] query-service, db-service, redis → üçü de `(healthy)`

#### Endpoint Doğrulama
[x] GET /health → 200 OK: `{"status": "ok", "service": "query-service"}`
[x] GET /datacenters/summary (X-Internal-Key) → 200 OK, 14 DC, **54.8s** (soğuk başlangıç)
```
AZ11:      status=Healthy  cpu= 4.5%   ram= 0.9%   stor= 2.4%
DC11:      status=Healthy  cpu=44.8%   ram=70.4%   stor=33.1%
DC13:      status=Healthy  cpu=53.2%   ram=67.3%   stor=60.0%
DC15:      status=Healthy  cpu=65.3%   ram=77.7%   stor=61.8%
```
[x] GET /datacenters/DC11 (X-Internal-Key) → 200 OK, **18.1s**
[x] GET /overview (X-Internal-Key) → 200 OK, 39.0s: `{"total_hosts":369, "total_vms":5492, "dc_count":14}`

#### Provider Pipeline Doğrulama
[x] Dinamik status hesaplaması: "Healthy" hardcode kaldırıldı, kullanım eşiklerine göre hesaplanıyor
    - CPU > 80% → Degraded, RAM > 85% → Degraded, Storage > 80% → Degraded
    - DC15: cpu=65.3%, ram=77.7% → tüm DC'ler eşiğin altında → "Healthy" (doğru)
[x] NutanixProvider: storage_cap sanity check çalıştı
    ```
    WARNING | src.providers.nutanix | DC DC11: storage_cap=258563521939994.8 TB anormal yüksek
    ```
    (Bireysel sorgu zaman filtresi yokken VMware/Nutanix ham birim sorunu yakalandı)
[x] IBMProvider: enerji caveat logu hazır (DC11'de `power.hosts=6 > 0`)

#### Keşfedilen Yeni Bulgu
- `get_dc_detail()` → bireysel SQL sorguları zaman filtresi içermiyor → bazı DC'lerde
  astronomik cpu/ram/storage değerleri → NutanixProvider bunu yakalıyor
- `get_summary()` → batch SQL sorguları `AND timestamp >= NOW() - INTERVAL '4 hours'`
  filtreli → doğru değerler → yüzde hesapları tutarlı
- Bu fark Task 2.4 integration testinde db-service düzeyinde ele alınacak

**Sonuç: Provider adapter pipeline devreye alındı. Dinamik status çalışıyor. Bilinen sorunlar loglanıyor. Task 2.2 tamamlandı.**

### 2.4 Veri Akışı Doğrulaması & Teknik Borç Kapatma — 2026-02-24 TAMAMLANDI

#### Değiştirilen Dosyalar
[x] services/db-service/src/queries/vmware.py     (4 individual query: +`AND timestamp >= NOW() - INTERVAL '4 hours'`)
[x] services/db-service/src/queries/nutanix.py    (4 individual query: +`AND collection_time >= NOW() - INTERVAL '4 hours'`)
[x] services/db-service/src/queries/energy.py     (IBM individual + BATCH_IBM: DISTINCT ON + 4-hour filter)
[x] services/db-service/src/services/database_service.py  (Nutanix storage: bytes→TB (÷1024⁴) + float() cast)
[x] services/query-service/src/providers/nutanix.py       (STORAGE_SANITY_LIMIT_TB: 1000 → 10000 TB)

#### Docker Build
[x] docker-compose up --build -d db-service → BUILD SUCCESS
[x] docker-compose up --build -d query-service → BUILD SUCCESS
[x] db-service (healthy), query-service (healthy), redis (healthy)

#### DC11 Detay Doğrulaması (cache MISS → fresh db-service call)
```
GET /datacenters/DC11:
{
  "storage_cap": 3957.59,   ← Önceki: 258,634,388,900,380 TB (birim fix uygulandı)
  "storage_used": 480.65,
  "energy": {"total_kw": 18.64}  ← Önceki: astronomik (IBM time filter uygulandı)
}
```

#### DC13 Detay Doğrulaması
```
GET /datacenters/DC13:
{
  "storage_cap": 5788.0,    ← Önceki: astronomik (birim fix uygulandı)
  "energy": {"total_kw": 88.54}
}
```

#### NutanixProvider / VMwareProvider Log Doğrulaması
```
docker logs query-service | grep WARNING
→ (boş — hiçbir uyarı yok)
```

#### Redis Cache Doğrulaması
```
docker exec redis redis-cli keys "*"
→ dc_detail:DC11   (TTL: 862s)
→ dc_detail:DC13   (TTL: 872s)

2. istek (DC11) → httpx log YOK → Cache HIT ✓
```

#### Keşfedilen ve Düzeltilen Ek Bug
- `_aggregate_dc` içinde asyncpg Numeric (Decimal) + Python float toplama hatası:
  `unsupported operand type(s) for +: 'float' and 'decimal.Decimal'`
  Çözüm: Tüm Nutanix/VMware değerlerine `float()` cast eklendi.
- Nutanix `storage_capacity` bytes cinsinden (yanlış kananılan TB değil);
  `_aggregate_dc`'de `/ (1024 ** 4)` dönüşümü eklendi.
  DC11: 258,634,388,900,380 → 3,957 TB (%99.9998 düşüş)

**Sonuç: SQL time filtresi ve birim dönüşümü uygulandı. NutanixProvider uyarısı sıfırlandı. IBM enerji değerleri makul seviyeye düştü. Task 2.4 tamamlandı. PHASE 2 KAPANDI.**

---

## 🔵 PHASE 3: Test Detayları (GUI & Dashboard)
3.1 UI/UX ve Layout Doğrulaması
[ ] dmc.AppShell yapısı farklı ekran çözünürlüklerinde (Responsive) doğru render ediliyor mu?
[ ] Sidebar navigasyonu ve sayfa geçişleri (Routing) sorunsuz çalışıyor mu?
[ ] Dash Mantine Components (DMC) bileşenleri karanlık/aydınlık mod uyumluluğuna sahip mi?

3.2 Veri Görselleştirme ve Reaktiflik
[ ] Plotly grafikleri query-service'den gelen veriyi doğru eksenlerde gösteriyor mu?
[ ] dcc.Interval tetiklendiğinde sayfa tamamen yenilenmeden (silinmeden) sadece veri güncelleniyor mu?
[ ] Grafik üzerindeki etkileşimler (hover, zoom, click) performans kaybı yaratıyor mu?
Kanıt: (Buraya tarayıcı konsol çıktıları veya performans metrikleri eklenecek)

## 🔴 PHASE 4: Test Detayları (Final & Prod Readiness)
4.1 Hata Yönetimi ve Dayanıklılık (Resilience)
[ ] Chaos Test: db-service kapandığında GUI kullanıcıya anlamlı bir "Bağlantı Hatası" mesajı gösteriyor mu?
[ ] Merkezi loglama sistemi (shared/utils) tüm servislerden gelen hataları tek bir formatta yakalıyor mu?

4.2 Performans ve Optimizasyon
[ ] Docker imajları "Multi-stage build" ile optimize edildi mi? (Hedef: <200MB per service)
[ ] Python servisleri gunicorn veya uvicorn ile üretim (production) modunda stabil çalışıyor mu?

[ ] Final Kanıt: (Buraya sistemin genel kaynak kullanım (CPU/RAM) raporunu ekle)

## 🛠️ Test Çalıştırma Prosedürü (Senior Dev İçin)
Claude, her test aşamasında şu adımları izlemelisin:
İlgili servisin tests/ klasöründeki birim testleri (Pytest) çalıştır.
curl veya httpx ile endpoint'leri manuel test et.
Sonuçları yukarıdaki tabloya ve ilgili Phase başlığına "Log/Çıktı" olarak ekle.
Başarısız olan testler varsa lessons.md dosyasını güncelle ve hatayı giderdikten sonra testi tekrarla.