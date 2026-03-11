# Bulutistan Dashboard — Mikro Servis Dönüşümü: Test Stratejisi

> Bu dosya, yeni FastAPI mikro servislerin, Docker build sürecinin ve K8s manifest'lerinin
> nasıl test edileceğini tanımlar.
> Her servis bu test matrisinin ilgili bölümlerini geçmeden "tamamlandı" olarak işaretlenemez.

---

## 1. Test Katmanları

```
┌─────────────────────────────────────────────────┐
│  E2E Tests (Browser / Playwright)               │
├─────────────────────────────────────────────────┤
│  Contract Tests (servisler arası API sözleşmesi)│
├─────────────────────────────────────────────────┤
│  Integration Tests (DB + Cache + API)           │
├─────────────────────────────────────────────────┤
│  Unit Tests (iş mantığı, dönüşümler, regex)    │
└─────────────────────────────────────────────────┘
```

---

## 2. Unit Test Gereksinimleri

### 2.1 _DC_CODE_RE Regex Testleri

**Araç:** `pytest`
**Dosya:** `services/<servis>/tests/test_dc_regex.py`

Aşağıdaki test case'lerin TAMAMI geçmeli:

| Girdi                    | Beklenen Çıktı | Açıklama                    |
|--------------------------|-----------------|-----------------------------|
| `"srv-DC14-hmc01"`       | `"DC14"`        | Standart DC kodu            |
| `"ICT11-vios-prod"`      | `"ICT11"`       | ICT prefix                  |
| `"AZ11-lpar-db"`         | `"AZ11"`        | Azerbaycan DC               |
| `"UZ11-power-app"`       | `"UZ11"`        | Özbekistan DC               |
| `"DH01-test-server"`     | `"DH01"`        | DH prefix                   |
| `"random-server-name"`   | `None`          | Eşleşme yok                 |
| `""`                     | `None`          | Boş string                  |
| `None`                   | `None`          | None değer                  |
| `"dc14-lowercase-test"`  | `"DC14"`        | Case insensitive            |
| `"multi-DC11-DC12-name"` | `"DC11"`        | İlk eşleşme döner           |

### 2.2 Birim Dönüşüm Testleri

**Dosya:** `services/<servis>/tests/test_unit_conversion.py`

Aşağıdaki dönüşümler doğrulanmalı:

```
Nutanix Memory:  1 TiB → 1024 GB
VMware Memory:   1073741824 bytes → 1.0 GB
VMware Storage:  1099511627776 bytes → 1.0 TB
VMware CPU:      1000000000 Hz → 1.0 GHz
Energy:          1000 W → 1.0 kW
```

### 2.3 IBM Aggregasyon Testleri

**Dosya:** `services/<servis>/tests/test_ibm_aggregation.py`

Test edilecek senaryolar:
- Aynı DC'ye ait 3 host → unique sayım = 3
- Aynı host adı 2 kez gelirse → unique sayım = 1 (set deduplikasyonu)
- Memory ortalama: [(100, 80), (200, 160)] → (150.0, 120.0)
- CPU ortalama: [(10, 8, 6), (20, 16, 12)] → (15.0, 12.0, 9.0)
- DC kodu bulunamayan satır → atlanır (None check)

### 2.4 Cache Key Format Testleri

**Dosya:** `services/<servis>/tests/test_cache_keys.py`

Doğrulanacak format:
```
f"dc_details:{dc_code}:{start}:{end}"
f"all_dc_summary:{start}:{end}"
f"global_dashboard:{start}:{end}"
f"customer_assets:{name}:{start}:{end}"
```

### 2.5 Customer LIKE Pattern Testleri

**Dosya:** `services/customer-service/tests/test_patterns.py`

| Müşteri Adı | Pattern Tipi     | Beklenen Çıktı  |
|-------------|------------------|------------------|
| `"Boyner"`  | Intel VM         | `"Boyner-%"`     |
| `"Boyner"`  | Power/Backup     | `"Boyner%"`      |
| `"Boyner"`  | Storage/NetBackup| `"%Boyner%"`     |
| `"Boyner"`  | Zerto            | `"Boyner%-%"`    |
| `""`        | Herhangi         | `"%"`            |

---

## 3. Integration Test Gereksinimleri

### 3.1 FastAPI Endpoint Testleri

**Araç:** `pytest` + `httpx.AsyncClient` (FastAPI TestClient)

Her mikro servisin endpoint'leri şu senaryoları kapsamalı:

| Senaryo                     | HTTP Method | Expected Status | Doğrulama                           |
|-----------------------------|-------------|-----------------|-------------------------------------|
| Geçerli DC detayı           | GET         | 200             | JSON yapısı + gerekli alan kontrolü |
| Var olmayan DC              | GET         | 404             | Hata mesajı formatı                 |
| Geçersiz parametre          | GET         | 422             | Validation error detayı             |
| DB erişilemez               | GET         | 200             | Fallback (sıfır) verisi döner       |
| Zaman aralığı ile sorgu     | GET         | 200             | start/end parametreleri çalışıyor   |
| Health check                | GET         | 200             | `{"status": "healthy"}`             |
| Readiness check             | GET         | 200/503         | DB bağlantısına bağlı               |

### 3.2 Veritabanı Bağlantı Testleri

**Araç:** `pytest` + `testcontainers` (PostgreSQL container)

Test edilecek senaryolar:
- Connection pool başarılı başlatma
- Pool tükendiğinde hata yönetimi
- Bağlantı kesildikten sonra otomatik yeniden bağlanma
- Transaction rollback (sorgu hatası sonrası bağlantının temiz kalması)

### 3.3 Cache Entegrasyon Testleri

**Araç:** `pytest` + Redis testcontainer veya `fakeredis`

Test edilecek senaryolar:
- Cache miss → DB sorgusu → cache set → cache hit
- TTL süresi dolunca cache miss
- Cache invalidation (explicit delete)
- Eşzamanlı yazma (thread safety)

---

## 4. Docker Build Test Gereksinimleri

### 4.1 Build Doğrulama

Her mikro servisin Dockerfile'ı için:

```bash
docker build -t <servis-adı>:test .
```

Geçme kriterleri:
- Build hatası SIFIR
- Image boyutu < 500MB (slim base image kullanımı)
- Gereksiz dosya yok (.git, __pycache__, .env)

### 4.2 Container Çalışma Testi

```bash
docker run -d --name test-<servis> -p <port>:<port> <servis-adı>:test
sleep 5
curl -f http://localhost:<port>/health
docker stop test-<servis> && docker rm test-<servis>
```

Geçme kriterleri:
- Container 5 saniye içinde health check'e yanıt veriyor
- Log'larda hata yok (`docker logs test-<servis>`)
- Container graceful shutdown yapabiliyor

### 4.3 Docker Compose Entegrasyon

```bash
docker compose up -d
sleep 10
curl -f http://localhost:<gateway-port>/health
docker compose down
```

Tüm servisler birlikte ayağa kalkabiliyor ve birbirleriyle iletişim kurabiliyor.

---

## 5. Kubernetes Manifest Test Gereksinimleri

### 5.1 Manifest Validasyonu

**Araç:** `kubeval` veya `kubeconform`

```bash
kubeval services/<servis>/k8s/*.yaml
```

Tüm YAML dosyaları K8s API şemasına uygun olmalı.

### 5.2 Dry-run Testi

```bash
kubectl apply --dry-run=server -f services/<servis>/k8s/
```

K8s cluster'a uygulanabilirlik kontrolü.

### 5.3 K8s Manifest Kontrol Listesi

Her servis için aşağıdaki manifest'ler bulunmalı:

| Manifest          | İçerik                                                  |
|-------------------|---------------------------------------------------------|
| `deployment.yaml` | replicas, resource limits, liveness/readiness probes    |
| `service.yaml`    | ClusterIP veya LoadBalancer tipi, port mapping          |
| `configmap.yaml`  | Ortam değişkenleri (hassas olmayan)                     |
| `secret.yaml`     | DB şifresi, API key'ler (base64 encoded)                |
| `hpa.yaml`        | Horizontal Pod Autoscaler (CPU %70 hedef, min:2 max:8)  |

### 5.4 Probe Gereksinimleri

Her Deployment'ta aşağıdaki probe'lar tanımlı olmalı:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

---

## 6. Regresyon Test Matrisi

Mikro servis dönüşümü sonrası mevcut davranışın KORUNDUĞUNU doğrulamak için:

| Mevcut Endpoint / Davranış              | Yeni Karşılık                     | Test Yöntemi                      |
|-----------------------------------------|-----------------------------------|------------------------------------|
| Home page global özet                   | `GET /api/v1/dashboard/overview`  | JSON diff (mevcut vs yeni)         |
| DC listesi ve summary                   | `GET /api/v1/datacenters`         | Aynı DC sayısı ve metrik değerleri |
| Tek DC detayı                           | `GET /api/v1/datacenters/{id}`    | Tüm alanlar mevcut ve doğru       |
| Customer assets (Boyner)                | `GET /api/v1/customers/Boyner`    | Intel+Power+Backup verileri eşit   |
| Query Explorer                          | `POST /api/v1/queries/execute`    | Aynı query aynı sonucu döner      |
| Paralel batch fetch performansı         | Internal batch logic               | Süre < 5s (mevcut ~3s)            |

### 6.1 Regresyon Test Çalıştırma Prosedürü

1. Mevcut monoliti çalıştır, tüm endpoint'lerden snapshot al (JSON dosyalarına kaydet)
2. Yeni mikro servisleri çalıştır, aynı endpoint'lerden veri çek
3. `deepdiff` veya benzeri araçla karşılaştır
4. Farklılık SIFIR olmalı (izin verilen fark: kayan nokta yuvarlama ±0.01)

---

## 7. CI Pipeline Test Sırası

```
1. Lint (ruff / flake8)
2. Type Check (mypy --strict)
3. Unit Tests (pytest -v --cov=. --cov-report=term)
4. Docker Build
5. Integration Tests (testcontainers)
6. Contract Tests (schemathesis veya pact)
7. Security Scan (trivy image scan)
```

Minimum kapsam hedefi:
- Unit test coverage: %85
- Integration test: Tüm endpoint'ler en az 1 kez test edilmiş
- Docker build: Hata SIFIR

---

## 8. Test Araç Seti

| Araç               | Amaç                        | Versiyon       |
|---------------------|------------------------------|---------------|
| `pytest`            | Test framework               | ≥ 8.0         |
| `httpx`             | Async HTTP client (FastAPI)  | ≥ 0.27        |
| `pytest-asyncio`    | Async test desteği           | ≥ 0.23        |
| `testcontainers`    | PostgreSQL/Redis container   | ≥ 4.0         |
| `fakeredis`         | Redis mock (unit test)       | ≥ 2.0         |
| `deepdiff`          | JSON regresyon karşılaştırma | ≥ 7.0         |
| `kubeval`           | K8s manifest validasyonu     | latest         |
| `ruff`              | Python linter                | ≥ 0.4         |
| `mypy`              | Static type checker          | ≥ 1.10        |
| `trivy`             | Container güvenlik taraması  | latest         |
| `schemathesis`      | API contract testing         | ≥ 3.0         |
