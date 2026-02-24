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

## 🟡 PHASE 2: Test Detayları
2.1 Cache Efficiency
[ ] Redis bağlantısı aktif mi?
[ ] Aynı sorgu ikinci kez atıldığında veri Redis'ten mi geliyor? (Response time < 50ms?)

2.2 Provider Integration
[ ] VMware, Nutanix ve IBM modülleri asenkron olarak veri toplayabiliyor mu?

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