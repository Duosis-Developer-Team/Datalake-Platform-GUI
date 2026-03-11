# FAZ 1 — Feature Parity: Monolitten FastAPI Mikro Servis Çıkarma

> **Hedef:** Mevcut Dash monolitindeki tüm backend mantığını FastAPI tabanlı bağımsız bir servise
> taşımak. Frontend (Dash) dosyalarına DOKUNULMAZ. Mevcut davranış birebir korunur.
>
> **Executer Referansları:**
> - Anayasa: `task/microservis_remake/mcrsrvc_skills.md`
> - Öğretiler: `task/microservis_remake/mcrsrvc_lessons.md`
> - Test Standartları: `task/microservis_remake/mcrsrvc_tests.md`

---

> [!CAUTION]
> ## EXECUTER İÇİN MUTLAK YASAKLAR
>
> 1. **KODLARDA ASLA YORUM SATIRI (COMMENT) OLMAYACAK.** Docstring YASAK. Fonksiyon/sınıf/değişken
>    isimleri tek başına okunabilir olacak. İstisna: `TODO:` ve `FIXME:` etiketleri.
>
> 2. **FRONTEND DOSYALARINA DOKUNULMAYACAK.** `app.py`, `src/pages/`, `src/components/` ve
>    `assets/` dizinleri bu fazda READ-ONLY'dir. Tek bir satır bile değiştirilmeyecek.
>
> 3. **HER ADIM `mcrsrvc_tests.md`'DEKİ STANDARTLARLA DOĞRULANMADAN BİR SONRAKİ ADIMA
>    GEÇİLMEYECEK.** "İşe yarıyor gibi görünüyor" KABUL EDİLMEZ. `pytest` çıktısı, `docker build`
>    logu veya `curl` yanıtı kanıt olarak sunulacak.

---

## ADIM 1: Altyapı İzolasyonu

Backend mikro servisi için bağımsız dizin yapısını kur.

- [ ] `backend/` kök dizinini oluştur
- [ ] Aşağıdaki alt dizin iskeletini oluştur:
  ```
  backend/
  ├── app/
  │   ├── __init__.py
  │   ├── main.py
  │   ├── config.py
  │   ├── routers/
  │   │   ├── __init__.py
  │   │   ├── datacenters.py
  │   │   ├── customers.py
  │   │   ├── dashboard.py
  │   │   └── queries.py
  │   ├── services/
  │   │   ├── __init__.py
  │   │   ├── db_service.py
  │   │   ├── cache_service.py
  │   │   └── scheduler_service.py
  │   ├── models/
  │   │   ├── __init__.py
  │   │   └── schemas.py
  │   ├── db/
  │   │   ├── __init__.py
  │   │   └── queries/
  │   │       ├── __init__.py
  │   │       ├── nutanix.py
  │   │       ├── vmware.py
  │   │       ├── ibm.py
  │   │       ├── energy.py
  │   │       ├── loki.py
  │   │       ├── customer.py
  │   │       └── registry.py
  │   └── utils/
  │       ├── __init__.py
  │       └── time_range.py
  ├── tests/
  │   ├── __init__.py
  │   ├── conftest.py
  │   ├── test_dc_regex.py
  │   ├── test_unit_conversion.py
  │   ├── test_ibm_aggregation.py
  │   ├── test_cache_keys.py
  │   ├── test_customer_patterns.py
  │   └── test_endpoints.py
  ├── requirements.txt
  ├── Dockerfile
  └── .dockerignore
  ```
- [ ] `backend/requirements.txt` oluştur — içerik:
  ```
  fastapi>=0.111.0
  uvicorn[standard]>=0.30.0
  psycopg2-binary>=2.9.9
  cachetools>=5.3.0
  python-dotenv>=1.0.0
  APScheduler>=3.10.0
  pydantic>=2.7.0
  httpx>=0.27.0
  pytest>=8.0.0
  pytest-asyncio>=0.23.0
  ruff>=0.4.0
  ```
- [ ] `backend/.dockerignore` oluştur — içerik:
  ```
  __pycache__
  *.pyc
  .git
  .env
  .pytest_cache
  tests/
  ```

### ADIM 1 — Doğrulama

- [ ] Dizin yapısı tam olarak yukarıdaki iskelete uyuyor (`find backend/ -type f` çıktısı kanıt)
- [ ] `cd backend && pip install -r requirements.txt` hatasız tamamlanıyor
- [ ] `python -c "import fastapi; print(fastapi.__version__)"` çıktısı versiyon döndürüyor

---

## ADIM 2: Core Modüllerin Taşınması ve Temizliği

Mevcut iş mantığını `backend/app/` altına taşı. CTO kararlarını uygula.

### 2.1 — Query Modüllerinin Kopyalanması

- [ ] `src/queries/nutanix.py` → `backend/app/db/queries/nutanix.py` kopyala (yorum satırlarını sil)
- [ ] `src/queries/vmware.py` → `backend/app/db/queries/vmware.py` kopyala (yorum satırlarını sil)
- [ ] `src/queries/ibm.py` → `backend/app/db/queries/ibm.py` kopyala (yorum satırlarını sil)
- [ ] `src/queries/energy.py` → `backend/app/db/queries/energy.py` kopyala (yorum satırlarını sil)
- [ ] `src/queries/loki.py` → `backend/app/db/queries/loki.py` kopyala (yorum satırlarını sil)
- [ ] `src/queries/customer.py` → `backend/app/db/queries/customer.py` kopyala (yorum satırlarını sil)
- [ ] `src/queries/registry.py` → `backend/app/db/queries/registry.py` kopyala (yorum satırlarını sil)
- [ ] `src/queries/__init__.py` içeriğini uygun import path'leriyle `backend/app/db/queries/__init__.py`'ye taşı

### 2.2 — Utility Modüllerinin Taşınması

- [ ] `src/utils/time_range.py` → `backend/app/utils/time_range.py` kopyala (yorum satırlarını sil)

### 2.3 — db_service.py Taşınması ve CTO Kararlarının Uygulanması

> [!IMPORTANT]
> Bu adım FAZ 0'daki 3 CTO kararını uygular. `mcrsrvc_lessons.md`'yi okumadan başlama.

- [ ] `src/services/db_service.py` → `backend/app/services/db_service.py` olarak kopyala
- [ ] **CTO KARAR 1 — ICT11 Düzeltmesi:** `DC_LOCATIONS` dict'inden mükerrer `"ICT11": "İngiltere"` satırını sil. Yalnızca `"ICT11": "Almanya"` kalacak
- [ ] **CTO KARAR 2 — Dead cursor Temizliği:** `_fetch_all_batch` fonksiyon imzasından `cursor` parametresini kaldır. Mevcut imza:
  ```python
  def _fetch_all_batch(self, cursor, dc_list: list[str], start_ts, end_ts)
  ```
  Yeni imza:
  ```python
  def _fetch_all_batch(self, dc_list: list[str], start_ts, end_ts)
  ```
  Bu fonksiyonu çağıran `_rebuild_summary` metodundaki `self._fetch_all_batch(None, dc_list, ...)` çağrısından da `None` argümanını kaldır
- [ ] **CTO KARAR 3 — Boyner Hardcoded:** `get_customer_list` metodu olduğu gibi bırakılacak: `return ["Boyner"]`. Dinamik yapı FAZ 2'ye ertelendi
- [ ] Tüm yorum satırlarını (`#` ile başlayan açıklamalar) ve docstring'leri sil. Fonksiyon/sınıf/değişken isimleri kendini açıklasın
- [ ] Import path'lerini güncelle: `from src.queries` → `from app.db.queries`, `from src.services` → `from app.services`, `from src.utils` → `from app.utils`
- [ ] `_DC_CODE_RE` pattern'ini BİREBİR koru:
  ```python
  _DC_CODE_RE = re.compile(r'(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)', re.IGNORECASE)
  ```

### 2.4 — cache_service.py Taşınması

- [ ] `src/services/cache_service.py` → `backend/app/services/cache_service.py` kopyala (yorum satırlarını sil)
- [ ] Import path'lerini güncelle

### 2.5 — scheduler_service.py Taşınması

- [ ] `src/services/scheduler_service.py` → `backend/app/services/scheduler_service.py` kopyala (yorum satırlarını sil)
- [ ] Import path'lerini güncelle: `from src.utils.time_range` → `from app.utils.time_range`

### 2.6 — query_overrides.py Taşınması

- [ ] `src/services/query_overrides.py` → `backend/app/services/query_overrides.py` kopyala (yorum satırlarını sil)
- [ ] Import path'lerini güncelle

### 2.7 — config.py Oluşturma

- [ ] `backend/app/config.py` oluştur. Ortam değişkenlerini Pydantic `BaseSettings` ile yönet:
  ```python
  from pydantic_settings import BaseSettings

  class Settings(BaseSettings):
      db_host: str = "10.134.16.6"
      db_port: str = "5000"
      db_name: str = "bulutlake"
      db_user: str = "datalakeui"
      db_pass: str = ""

      class Config:
          env_file = ".env"

  settings = Settings()
  ```
  `requirements.txt`'e `pydantic-settings>=2.3.0` ekle

### ADIM 2 — Doğrulama

- [ ] `cd backend && python -c "from app.services.db_service import DatabaseService; print('Import OK')"` çalışıyor
- [ ] `cd backend && python -c "from app.db.queries import nutanix, vmware, ibm, energy, loki, customer; print('Queries OK')"` çalışıyor
- [ ] `grep -rn "^#" backend/app/ --include="*.py" | grep -v "^.*:#!" | grep -v "TODO\|FIXME"` → SIFIR sonuç (yorum satırı yok)
- [ ] `grep -rn '"""' backend/app/ --include="*.py"` → SIFIR sonuç (docstring yok)
- [ ] `grep -rn "''''" backend/app/ --include="*.py"` → SIFIR sonuç (docstring yok)
- [ ] `_DC_CODE_RE` pattern'i birebir korunmuş (`grep "_DC_CODE_RE" backend/app/services/db_service.py`)
- [ ] `DC_LOCATIONS` dict'inde `ICT11` yalnızca bir kez geçiyor ve değeri `"Almanya"`
- [ ] `_fetch_all_batch` imzasında `cursor` parametresi YOK
- [ ] `_rebuild_summary` içinde `_fetch_all_batch` çağrısında `None` argümanı YOK

---

## ADIM 3: FastAPI Katmanının İnşası

Taşınan iş mantığını HTTP endpoint'lerine bağla.

### 3.1 — Pydantic Şemaları (`backend/app/models/schemas.py`)

- [ ] Aşağıdaki response model'leri oluştur (mevcut `db_service.py` dönüş yapılarına birebir uyumlu):

  | Model Adı                  | Karşılık Geldiği Metot               |
  |----------------------------|--------------------------------------|
  | `DCMeta`                   | `meta` dict'i                        |
  | `DCIntel`                  | `intel` dict'i                       |
  | `DCPower`                  | `power` dict'i                       |
  | `DCEnergy`                 | `energy` dict'i                      |
  | `DCPlatforms`              | `platforms` dict'i                   |
  | `DCDetail`                 | `get_dc_details` dönüş değeri        |
  | `DCSummaryStats`           | `stats` dict'i (summary list içinde) |
  | `DCSummary`                | summary list elemanı                 |
  | `GlobalOverview`           | `get_global_overview` dönüş değeri   |
  | `GlobalDashboard`          | `get_global_dashboard` dönüş değeri  |
  | `CustomerResources`        | `get_customer_resources` dönüş değeri|
  | `QueryResult`              | `execute_registered_query` dönüşü    |
  | `HealthResponse`           | `/health` endpoint yanıtı           |
  | `ReadinessResponse`        | `/ready` endpoint yanıtı            |

### 3.2 — Router: Datacenters (`backend/app/routers/datacenters.py`)

- [ ] `GET /api/v1/datacenters` → `DatabaseService.get_all_datacenters_summary(time_range)` çağırır
  - Query params: `start: str | None`, `end: str | None`
  - Response model: `list[DCSummary]`
- [ ] `GET /api/v1/datacenters/{dc_id}` → `DatabaseService.get_dc_details(dc_id, time_range)` çağırır
  - Path param: `dc_id: str`
  - Query params: `start: str | None`, `end: str | None`
  - Response model: `DCDetail`
  - 404: DC bulunamazsa veya tüm değerler sıfırsa

### 3.3 — Router: Dashboard (`backend/app/routers/dashboard.py`)

- [ ] `GET /api/v1/dashboard/overview` → `DatabaseService.get_global_overview(time_range)` çağırır
  - Query params: `start: str | None`, `end: str | None`
  - Response model: `GlobalOverview`
- [ ] `GET /api/v1/dashboard` → `DatabaseService.get_global_dashboard(time_range)` çağırır
  - Query params: `start: str | None`, `end: str | None`
  - Response model: `GlobalDashboard`

### 3.4 — Router: Customers (`backend/app/routers/customers.py`)

- [ ] `GET /api/v1/customers` → `DatabaseService.get_customer_list()` çağırır
  - Response: `list[str]` (şimdilik `["Boyner"]`)
- [ ] `GET /api/v1/customers/{customer_name}` → `DatabaseService.get_customer_resources(customer_name, time_range)` çağırır
  - Path param: `customer_name: str`
  - Query params: `start: str | None`, `end: str | None`
  - Response model: `CustomerResources`

### 3.5 — Router: Query Explorer (`backend/app/routers/queries.py`)

- [ ] `POST /api/v1/queries/execute` → `DatabaseService.execute_registered_query(query_key, params_input)` çağırır
  - Request body: `{"query_key": str, "params": str}`
  - Response model: `QueryResult`

### 3.6 — Health & Readiness (`backend/app/main.py` içinde)

- [ ] `GET /health` → `{"status": "healthy"}` her zaman 200
- [ ] `GET /ready` → DB pool durumuna göre 200 veya 503

### 3.7 — main.py Entrypoint

- [ ] `backend/app/main.py` oluştur:
  - FastAPI instance'ı oluştur (`title="Bulutistan Dashboard API"`)
  - Tüm router'ları dahil et
  - `lifespan` context manager ile startup'ta `DatabaseService` singleton oluştur ve cache'i ısıt
  - Scheduler'ı başlat
  - CORS middleware ekle (frontend'in bağlanabilmesi için `allow_origins=["*"]` — FAZ 2'de kısıtlanacak)

### ADIM 3 — Doğrulama

- [ ] `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000` hatasız başlıyor
- [ ] `curl -s http://localhost:8000/health | python -m json.tool` → `{"status": "healthy"}`
- [ ] `curl -s http://localhost:8000/docs` → Swagger UI açılıyor (tüm endpoint'ler listelenmiş)
- [ ] `curl -s "http://localhost:8000/api/v1/datacenters"` → JSON array dönüyor (DB bağlantısı varsa verili, yoksa boş array)
- [ ] `curl -s "http://localhost:8000/api/v1/customers"` → `["Boyner"]`
- [ ] `curl -s "http://localhost:8000/api/v1/dashboard/overview"` → JSON object dönüyor
- [ ] `curl -s "http://localhost:8000/ready"` → 200 veya 503 (DB durumuna bağlı)
- [ ] Tüm endpoint'ler için response body'ler Pydantic model'lerine uyuyor (validation hatası yok)
- [ ] `mcrsrvc_tests.md` Bölüm 3.1'deki tüm HTTP senaryo testleri geçiyor

---

## ADIM 4: Unit Test Süitinin Yazılması

> [!WARNING]
> Bu adım ADIM 3'ten ÖNCE de başlanabilir (TDD yaklaşımı). Ancak tüm testler ADIM 3 sonunda geçiyor olmalı.

### 4.1 — conftest.py

- [ ] `backend/tests/conftest.py` oluştur:
  - FastAPI TestClient fixture'ı
  - Mock DatabaseService fixture'ı (DB bağlantısı gerektirmeyen testler için)

### 4.2 — test_dc_regex.py

- [ ] `mcrsrvc_tests.md` Bölüm 2.1'deki 10 test case'in TAMAMINI implement et
- [ ] `cd backend && pytest tests/test_dc_regex.py -v` → 10/10 PASSED

### 4.3 — test_unit_conversion.py

- [ ] `mcrsrvc_tests.md` Bölüm 2.2'deki dönüşüm testlerini implement et
- [ ] `cd backend && pytest tests/test_unit_conversion.py -v` → tümü PASSED

### 4.4 — test_ibm_aggregation.py

- [ ] `mcrsrvc_tests.md` Bölüm 2.3'teki aggregasyon senaryolarını implement et
- [ ] `cd backend && pytest tests/test_ibm_aggregation.py -v` → tümü PASSED

### 4.5 — test_cache_keys.py

- [ ] `mcrsrvc_tests.md` Bölüm 2.4'teki cache key format testlerini implement et
- [ ] `cd backend && pytest tests/test_cache_keys.py -v` → tümü PASSED

### 4.6 — test_customer_patterns.py

- [ ] `mcrsrvc_tests.md` Bölüm 2.5'teki LIKE pattern testlerini implement et
- [ ] `cd backend && pytest tests/test_customer_patterns.py -v` → tümü PASSED

### 4.7 — test_endpoints.py

- [ ] `mcrsrvc_tests.md` Bölüm 3.1'deki endpoint senaryolarını implement et (MockDB ile)
- [ ] `cd backend && pytest tests/test_endpoints.py -v` → tümü PASSED

### ADIM 4 — Doğrulama

- [ ] `cd backend && pytest tests/ -v --tb=short` → TÜMLÜ PASSED, SIFIR FAILED
- [ ] `cd backend && pytest tests/ --cov=app --cov-report=term-missing` → coverage %85+
- [ ] Test dosyalarında yorum satırı yok (test açıklamaları fonksiyon isimleriyle verilmiş)

---

## ADIM 5: Konteynerizasyon

### 5.1 — Multi-stage Dockerfile

- [ ] `backend/Dockerfile` oluştur (multi-stage build):
  - **Stage 1 (builder):** `python:3.12-slim` base, requirements install
  - **Stage 2 (runtime):** `python:3.12-slim` base, yalnızca gerekli paketler kopyalanır
  - `EXPOSE 8000`
  - `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]`
  - `.dockerignore` dosyasının `tests/`, `__pycache__/`, `.env` içerdiğini doğrula

### 5.2 — Docker Compose Güncelleme

- [ ] Proje kökündeki `docker-compose.yml`'a `backend` servisini ekle (mevcut `app` servisine DOKUNMA):
  ```yaml
  backend:
    build: ./backend
    container_name: bulutistan-backend-api
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      - db
    profiles:
      - microservice
  ```

### ADIM 5 — Doğrulama

- [ ] `cd backend && docker build -t bulutistan-backend:test .` → hatasız tamamlanıyor
- [ ] Image boyutu < 500MB: `docker images bulutistan-backend:test --format "{{.Size}}"`
- [ ] `docker run -d --name test-backend -p 8000:8000 --env-file ../.env bulutistan-backend:test`
- [ ] `sleep 5 && curl -f http://localhost:8000/health` → `{"status": "healthy"}`
- [ ] `docker logs test-backend` → hata satırı yok
- [ ] `docker stop test-backend && docker rm test-backend` → graceful shutdown

---

## ADIM 6: Kubernetes Manifestoları

### 6.1 — Dizin Yapısı

- [ ] `k8s/backend/` dizinini oluştur

### 6.2 — deployment.yaml

- [ ] `k8s/backend/deployment.yaml` oluştur:
  - `replicas: 2`
  - Container: `bulutistan-backend:latest`, port 8000
  - Resource limits: `cpu: 500m`, `memory: 512Mi`
  - Resource requests: `cpu: 250m`, `memory: 256Mi`
  - `livenessProbe`: `GET /health`, `initialDelaySeconds: 10`, `periodSeconds: 30`
  - `readinessProbe`: `GET /ready`, `initialDelaySeconds: 5`, `periodSeconds: 10`
  - Environment variables: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` → ConfigMap'ten, `DB_PASS` → Secret'tan

### 6.3 — service.yaml

- [ ] `k8s/backend/service.yaml` oluştur:
  - `type: ClusterIP`
  - Port: `80 → 8000` (target)

### 6.4 — configmap.yaml

- [ ] `k8s/backend/configmap.yaml` oluştur:
  - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` değerleri

### 6.5 — secret.yaml

- [ ] `k8s/backend/secret.yaml` oluştur (şablon — gerçek değerler OLMAYACAK):
  - `DB_PASS`: `<base64-encoded-placeholder>`

### 6.6 — hpa.yaml

- [ ] `k8s/backend/hpa.yaml` oluştur:
  - `minReplicas: 2`, `maxReplicas: 8`
  - `targetCPUUtilizationPercentage: 70`

### ADIM 6 — Doğrulama

- [ ] `kubectl apply --dry-run=client -f k8s/backend/` → tüm manifest'ler geçerli
- [ ] Manifest'lerde `livenessProbe` ve `readinessProbe` tanımlı
- [ ] Secret'ta gerçek şifre YOK (placeholder)
- [ ] Her manifest'in `apiVersion` ve `kind` alanları doğru

---

## FAZ 1 TAMAMLANMA KRİTERLERİ

Aşağıdaki koşulların TAMAMI sağlanmadan FAZ 1 "tamamlandı" olarak işaretlenemez:

| #  | Kriter                                                   | Kanıt                                |
|----|----------------------------------------------------------|--------------------------------------|
| 1  | `backend/` dizini tam ve çalışır durumda                 | `uvicorn` hatasız başlatma logu      |
| 2  | Tüm endpoint'ler yanıt veriyor                           | `curl` çıktıları                     |
| 3  | Unit test coverage ≥ %85                                 | `pytest --cov` raporu                |
| 4  | Docker build başarılı                                    | `docker build` logu                  |
| 5  | Container health check yanıt veriyor                     | `curl /health` çıktısı              |
| 6  | K8s manifest'leri dry-run geçiyor                        | `kubectl --dry-run` çıktısı          |
| 7  | Kod içinde SIFIR yorum satırı var                        | `grep` çıktısı (0 sonuç)            |
| 8  | Frontend dosyaları DEĞİŞMEMİŞ                           | `git diff src/ app.py` → boş        |
| 9  | `_DC_CODE_RE` pattern birebir korunmuş                   | `grep` ile doğrulama                 |
| 10 | ThreadPoolExecutor paralel batch mantığı çalışıyor       | Log çıktısı veya test kanıtı        |
