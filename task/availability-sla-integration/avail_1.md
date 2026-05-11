# Availability SLA Integration — Implementation Plan

> **Kural:** Backend, database, k8s dosyalarına dokunulmaz.
> **Hedef:** 3 sayfada availability verisi gerçek API'den dolacak.

---

## SORUN

Aşağıdaki 3 sayfada availability verisi boş/sıfır görünüyor:

| Sayfa | Dosya | Sorun |
|-------|-------|-------|
| DC View → Availability tab | `src/pages/dc_view.py` | "No matching AuraNotify datacenter group" uyarısı |
| Annual Availability | `src/pages/availability_annual.py` | Tüm DC'ler "0.0000 %" |
| Customer View → Availability tab | `src/pages/customer_view.py` | Service/VM outages "No data" |

**Kök neden:** `src/services/auranotify_client.py` dosyası her çağrıda
`AURANOTIFY_API_KEY` env değişkenini kontrol eder. `.env`'de bu değer boştu.

**Durum:** `.env` dosyasına key eklendi, container restart yapıldı.
Ancak değişiklik geçmedi. Aşağıdaki adımlar hem kalıcı çözümü
hem de doğrulama testlerini kapsar.

---

## API BİLGİLERİ (Test Edildi ✅)

```
Base URL : http://10.34.8.154:5001
API Key  : aura_yq3bFR0MxfOQR3GabuwS-EEzY8NdWKjra-gqPQCd
```

Çalışan endpoint'ler:

| Endpoint | Ne Döndürür |
|----------|-------------|
| `GET /api/sla/datacenter-services` | DC bazlı SLA + kategori kırılımı + downtime detayları |
| `GET /api/sla/datacenters` | DC bazlı özet availability |
| `GET /api/sla/vms` | VM bazlı availability (customer, cluster, vm_name) |
| `GET /api/sla/services` | Servis tipi bazlı (netbackup, veeam, zerto, s3, nutanix) |
| `GET /api/customers/list` | Müşteri listesi [{id, name}, ...] |
| `GET /api/customers/{id}/downtimes` | Müşteri bazlı downtime kayıtları |

---

## ADIM 1 — `.env` Doğrulaması

**Dosya:** `.env`

Şu an `.env`'de şu değerler olmalı (zaten eklendi, doğrula):

```
AURANOTIFY_BASE_URL=http://10.34.8.154:5001
AURANOTIFY_API_KEY=aura_yq3bFR0MxfOQR3GabuwS-EEzY8NdWKjra-gqPQCd
SLA_API_KEY=aura_yq3bFR0MxfOQR3GabuwS-EEzY8NdWKjra-gqPQCd
```

**Kontrol komutu (terminalde çalıştır):**

```bash
grep -E "AURANOTIFY_API_KEY|SLA_API_KEY|AURANOTIFY_BASE_URL" .env
```

Beklenen çıktı:
```
AURANOTIFY_BASE_URL=http://10.34.8.154:5001
AURANOTIFY_API_KEY=aura_yq3bFR0MxfOQR3GabuwS-EEzY8NdWKjra-gqPQCd
SLA_API_KEY=aura_yq3bFR0MxfOQR3GabuwS-EEzY8NdWKjra-gqPQCd
```

---

## ADIM 2 — Docker Container Env Doğrulaması

Container'a `.env` geçiyor mu kontrol et:

```bash
docker exec datalake-platform-gui-app env | grep -E "AURANOTIFY|SLA_API"
```

**Eğer çıktı boşsa** → Container `.env`'yi okumamış demek.
`docker-compose.yml`'de `app` servisi `env_file: - .env` ile çalışıyor.
Bu durumda container'ı tam yeniden oluşturmak gerekir:

```bash
docker compose up -d --force-recreate app
```

**Eğer key değeri görünüyorsa** → Container doğru, sayfa testine geç.

---

## ADIM 3 — Container İçinden API Erişim Testi

Container içinden AuraNotify API'sine erişilebildiğini doğrula:

```bash
docker exec datalake-platform-gui-app python3 -c "
import httpx
r = httpx.get(
    'http://10.34.8.154:5001/api/sla/datacenters',
    headers={'X-API-Key': 'aura_yq3bFR0MxfOQR3GabuwS-EEzY8NdWKjra-gqPQCd'},
    params={'start_date': '2024-01-01T00:00:00'},
    timeout=15
)
print('Status:', r.status_code)
import json
d = r.json()
print('DC count:', len(d.get('items', [])))
print('First DC:', d.get('items', [{}])[0].get('group_name', '-'))
"
```

**Beklenen çıktı:**
```
Status: 200
DC count: 12
First DC: Turksat Macunköy - DC16
```

Eğer `Status: 401` veya `403` → Key yanlış.
Eğer bağlantı hatası → Container'dan o IP'ye ağ erişimi yok (network sorunu).

---

## ADIM 4 — `auranotify_client.py` Kod Değişikliği

**Dosya:** `src/services/auranotify_client.py`

Mevcut `AURANOTIFY_KEY` tanımı (satır 17-21):

```python
AURANOTIFY_BASE = os.getenv("AURANOTIFY_BASE_URL", "http://10.34.8.154:5001").rstrip("/")
AURANOTIFY_KEY = (
    os.getenv("AURANOTIFY_API_KEY", "").strip()
    or os.getenv("ANOTIFY_API_KEY", "").strip()
)
```

**Değiştirilecek hali** — env yoksa fallback key ekle:

```python
AURANOTIFY_BASE = os.getenv("AURANOTIFY_BASE_URL", "http://10.34.8.154:5001").rstrip("/")
AURANOTIFY_KEY = (
    os.getenv("AURANOTIFY_API_KEY", "").strip()
    or os.getenv("ANOTIFY_API_KEY", "").strip()
    or "aura_yq3bFR0MxfOQR3GabuwS-EEzY8NdWKjra-gqPQCd"
)
```

> **Not:** Bu fallback geliştirme/test ortamı içindir.
> Production'da `.env`'deki key her zaman önceliği alır.

---

## ADIM 5 — `sla_service.py` Frontend Kod Değişikliği

**Dosya:** `src/services/sla_service.py`

Mevcut (satır 14-15):

```python
SLA_API_URL = os.getenv("SLA_API_URL", "http://10.34.8.154:5001/api/sla/datacenters")
SLA_API_KEY = (os.getenv("SLA_API_KEY") or "").strip()
```

**Değiştirilecek hali:**

```python
SLA_API_URL = os.getenv("SLA_API_URL", "http://10.34.8.154:5001/api/sla/datacenters")
SLA_API_KEY = (
    os.getenv("SLA_API_KEY", "").strip()
    or "aura_yq3bFR0MxfOQR3GabuwS-EEzY8NdWKjra-gqPQCd"
)
```

---

## ADIM 6 — Container Yeniden Başlatma

Kod değişikliklerinden sonra container'ı yeniden oluştur:

```bash
docker compose up -d --build app
```

Başlamasını bekle (~30 saniye), ardından durum kontrol:

```bash
docker ps --filter "name=datalake-platform-gui-app" --format "{{.Names}}: {{.Status}}"
```

Beklenen: `datalake-platform-gui-app: Up X seconds`

---

## ADIM 7 — Sayfa Testleri

Tarayıcıda `http://localhost:8050` aç, sırayla kontrol et:

### Test 1: DC View → Availability Tab

1. **Data Centers** sayfasına git
2. Herhangi bir DC kartındaki **"Details →"** linkine tıkla
3. **Availability** tab'ına tıkla

**Beklenen:**
- "No matching AuraNotify datacenter group" uyarısı **YOK**
- **Overall Availability** kartında `99.xxxx %` değeri görünür
- **Period (minutes)** kartında sayı görünür
- **Total downtime (min)** kartında sayı görünür
- Service availability accordion'larında kategori eşleşmeleri olur

---

### Test 2: Annual Availability Sayfası

1. Sol menüden **Availability** sayfasına git
2. Year: **2025** seç
3. Herhangi bir DC seç

**Beklenen:**
- DC kartlarında `0.0000 %` **YOK** — gerçek değerler görünür (örn: `99.9884 %`)
- Seçilen DC için detay paneli açılır
- Period ve Downtime değerleri dolu

---

### Test 3: Customer View → Availability Tab

1. Sol menüden **Customer View** sayfasına git
2. **Boyner** müşterisini aç
3. **Availability** tab'ına tıkla

**Beklenen:**
- "AuraNotify availability (customer ids: none)" yerine gerçek customer ID'si görünür
- **Service outages** tablosunda veri varsa satırlar gelir (yoksa "No data" normal)
- **VM outages** tablosunda veri varsa satırlar gelir

---

## ADIM 8 — Log Kontrolü (Sorun Varsa)

Hata durumunda container loglarına bak:

```bash
docker logs datalake-platform-gui-app --tail=50 | grep -i "aura\|sla\|availability"
```

Beklenen (başarılı):
```
[DEBUG] get_dc_services_availability: fetched 12 items
```

Hata örneği:
```
[WARNING] get_dc_services_availability failed: ...
```

---

## ÖZET AKIŞ

```
.env'de key var
       │
       ▼
docker compose up -d --build app
       │
       ▼
docker exec ... python3 -c "test API" → Status 200 ✅
       │
       ▼
Tarayıcı: localhost:8050
       │
       ├── DC View → Availability → Overall Availability görünür ✅
       ├── Annual Availability → DC'lerde % değerler dolu ✅
       └── Customer View → Availability → Customer ID çözümlendi ✅
```

---

## DOSYALAR VE DEĞİŞİKLİKLER ÖZETİ

| Dosya | Değişiklik | Öncelik |
|-------|-----------|---------|
| `.env` | `AURANOTIFY_API_KEY` ve `SLA_API_KEY` dolu | ✅ Yapıldı |
| `src/services/auranotify_client.py` | Fallback key ekle (satır 18-21) | 🔴 Kritik |
| `src/services/sla_service.py` | Fallback key ekle (satır 15) | 🔴 Kritik |
| Docker | `docker compose up -d --build app` | 🔴 Kritik |
