# FAZ 4 — Prod-Ready: Kubernetes, CI/CD, Load Testing ve Observability

> **Hedef:** Docker Compose ile local'de çalışan sistemi gerçek sunucu standartlarına (Production)
> çıkarmak. Kubernetes cluster üzerinde 3 servisin (Backend, Redis, Frontend) otomatik
> ölçeklenen, CI/CD pipeline'ı ile korunan, yük testleriyle doğrulanmış ve anlık
> izlenebilirliğe sahip tam bir Production ortamı inşa etmek.
>
> **Öncül:** FAZ 1 (Feature Parity), FAZ 2 (Redis + Adapters + TimeFilter), FAZ 3 (Frontend
> REST Entegrasyon) %100 tamamlandı. 329 regresyon testi firesiz geçiyor (%95 coverage).
> Backend dondurulmuş durumdadır. Frontend, `api_client.py` ile HTTP üzerinden veri çeker.
>
> **Executer Referansları:**
> - Anayasa: `task/microservis_remake/mcrsrvc_skills.md`
> - Öğretiler: `task/microservis_remake/mcrsrvc_lessons.md`
> - Test Standartları: `task/microservis_remake/mcrsrvc_tests.md`
> - K8s Mevcut Durum: `k8s/backend/`, `k8s/redis/`

---

> [!CAUTION]
> ## EXECUTER İÇİN MUTLAK YASAKLAR (KIRMIZI ÇİZGİLER)
>
> 1. **SIFIR YORUM SATIRI KURALI:** Pipeline YAML dosyaları, test scriptleri, Dockerfile,
>    Kubernetes manifest'leri veya Python dosyaları dahil — yazılacak HİÇBİR dosyada tek
>    bir yorum satırı (`#`) dahi barındırılmayacak. Docstring YASAK. YAML açıklama satırı
>    YASAK. Tek istisna: YAML'ın zorunlu kıldığı teknik satırlar
>    (örn. `#!/bin/bash` shebang veya `#syntax=docker/dockerfile`).
>
> 2. **API ÇEKİRDEK KODU DOKUNULMAZLIĞI:** `backend/app/` dizini, `src/` dizini ve tüm
>    mevcut test dosyaları KESİNLİKLE değiştirilmeyecek. Pipeline bu kodları SADECE test
>    eder, asla değiştirmez.
>
> 3. **329 TEST'LİK SÜİT KORUNACAK:** Pipeline'da çalışan testler mevcut `pytest` süitinin
>    birebir aynısıdır. Yeni test eklenmez, mevcut test atlanmaz.
>
> 4. **HER ADIM DOĞRULANMADAN BİR SONRAKİNE GEÇİLMEYECEK.** Kanıt: terminal çıktısı,
>    `kubectl` logu veya Locust rapor grafikleri.

---

## BÖLÜM A: MEVCUT ALTYAPI KEŞFİ

### A.1 — Proje Kök Yapısı (DevOps Perspektifi)

```
Datalake-Platform-GUI/
├── Dockerfile                     ← Frontend (single-stage, gunicorn, port 8050)
├── docker-compose.yml             ← 4 servis: app/db/redis/backend (profiles: microservice)
├── backend/
│   ├── Dockerfile                 ← Backend (multi-stage builder, uvicorn, port 8000)
│   ├── app/                       ← FROZEN: Çekirdek API kodu
│   ├── tests/                     ← 329 test
│   └── requirements.txt
├── k8s/
│   ├── backend/
│   │   ├── deployment.yaml        ← 2 replika, 250m/256Mi req, 500m/512Mi lmt
│   │   ├── hpa.yaml               ← min:2, max:8, CPU targetUtilization: %70
│   │   ├── service.yaml           ← ClusterIP, port 80 → targetPort 8000
│   │   ├── configmap.yaml         ← DB_HOST: 10.134.16.6, REDIS_HOST: bulutistan-redis
│   │   └── secret.yaml            ← DB_PASS: REPLACE_WITH_BASE64_ENCODED_PASSWORD
│   └── redis/
│       ├── deployment.yaml        ← 1 replika, redis:7-alpine, 256mb maxmemory
│       └── service.yaml           ← ClusterIP, port 6379
├── .github/                       ← ❌ MEVCUT DEĞİL (sıfırdan oluşturulacak)
├── src/                           ← Frontend kodu (FAZ 3'te refactor edildi)
├── tests/                         ← Frontend testleri
└── requirements.txt               ← Frontend bağımlılıkları
```

### A.2 — Mevcut Durum Matrisi

| Bileşen | Docker | K8s Manifest | HPA | Health Check | CI/CD | Load Test | Logging |
|---------|--------|-------------|-----|-------------|-------|-----------|---------|
| Backend | ✅ multi-stage | ✅ deployment | ✅ min:2 max:8 | ✅ `/health` + `/ready` | ❌ YOK | ❌ YOK | ✅ stdlib logging |
| Redis | ✅ `redis:7-alpine` | ✅ deployment | ❌ gereksiz | ✅ `redis-cli ping` | ❌ YOK | ❌ YOK | — |
| Frontend | ✅ single-stage | ❌ **YOK** | ❌ YOK | ❌ **YOK** | ❌ YOK | ❌ YOK | ✅ basicConfig |
| PostgreSQL | ✅ compose only | ❌ Harici DB | — | — | — | — | — |

### A.3 — Kritik Keşif Bulguları

| # | Bulgu | Etki |
|---|-------|------|
| 1 | **Frontend K8s manifestosu YOK.** Sadece backend ve redis var | ADIM 1'de oluşturulacak |
| 2 | **Frontend'te health endpoint YOK.** Gunicorn saf WSGI sunuyor | K8s liveness/readiness için `/` path kullanılacak veya basit HTTP 200 check |
| 3 | **ConfigMap'te gerçek DB IP hardcoded** (`10.134.16.6:5000`) | Prod ortama özel, cluster-içi DB için güncellenmeli |
| 4 | **Secret.yaml placeholder** (`REPLACE_WITH_BASE64_ENCODED_PASSWORD`) | CI/CD'de `kubectl create secret` veya Sealed Secrets kullanılacak |
| 5 | **HPA sadece CPU metriği var** — memory yok | Prod'da memory metriği eklenmesi önerilir |
| 6 | **Loki** projede bir monitoring aracı DEĞİL — `loki_locations`, `loki_racks` gibi NetBox DB tabloları | Observability için Grafana Loki ayrıca kurulacak |
| 7 | **Backend loglama:** Tüm modüllerde `logging.getLogger(__name__)` pattern'i | JSON formatter ile yapılandırılabilir (structured logging) |
| 8 | **Backend `initialDelaySeconds: 10` (readiness)** — warm_cache 17 sn sürüyor | `initialDelaySeconds` artırılmalı (en az 25s) |
| 9 | **Frontend Dockerfile single-stage** — prod'da builder pattern uygulanabilir | Optimization ADIM 4'te yapılabilir |
| 10 | **Docker Compose `profiles: microservice`** — backend/redis ayrı profilde | `COMPOSE_PROFILES=microservice docker compose up` ile çalıştırılıyor |

---

## BÖLÜM B: VERİ AKIŞ DİYAGRAMI (CLUSTER-İÇİ)

```
                          ┌─────────────────────────────────────────────────────────┐
                          │                  Kubernetes Cluster                      │
                          │                                                         │
  İnternet / İntranet     │  ┌──────────────────┐                                   │
  ──────────────────▶     │  │   Ingress / LB    │                                   │
                          │  │  (NGINX Ingress)  │                                   │
                          │  └───────┬──────┬────┘                                   │
                          │          │      │                                         │
                          │    /     │      │  /api/v1/*                              │
                          │          ▼      ▼                                         │
                          │  ┌───────────┐  ┌───────────────────┐                    │
                          │  │ Frontend  │  │ Backend (FastAPI)  │                    │
                          │  │   (Dash)  │  │  2-8 pod (HPA)    │                    │
                          │  │  port:8050│  │  port:8000         │                    │
                          │  │  ──────── │  │  ──────────────── │                    │
                          │  │ gunicorn  │  │ uvicorn            │                    │
                          │  │ 4 worker  │  │ liveness: /health  │                    │
                          │  └───────────┘  │ readiness: /ready  │                    │
                          │       │         └──────┬─────────────┘                    │
                          │       │                │                                   │
                          │       │  HTTP (port 80)│                                   │
                          │       └────────────────┤                                   │
                          │        api_client.py   │                                   │
                          │                        ▼                                   │
                          │               ┌──────────────┐    ┌───────────────────┐   │
                          │               │   Redis      │    │ PostgreSQL        │   │
                          │               │  port:6379   │    │ (Harici DB)       │   │
                          │               │  ClusterIP   │    │ 10.134.16.6:5000  │   │
                          │               └──────────────┘    └───────────────────┘   │
                          └─────────────────────────────────────────────────────────┘
```

**Trafik Yönlendirme Kuralları:**

| Host / Path | Hedef Service | Port |
|------------|---------------|------|
| `bulutistan.local/` | `bulutistan-frontend` | 8050 |
| `bulutistan.local/api/v1/*` | `bulutistan-data-api` | 8000 |
| `bulutistan.local/health` | `bulutistan-data-api` | 8000 |

> [!IMPORTANT]
> Frontend'in `api_client.py`'si şu anda `API_BASE_URL = http://localhost:8000` kullanıyor.
> K8s ortamında bu `http://bulutistan-data-api` (ClusterIP service adı) olarak
> değiştirilecek. Bu bir ortam değişkenidir ve Frontend ConfigMap'e eklenecek.

---

## BÖLÜM C: KADEMELİ İCRA PLANI (4 ROTA)

### ROTA A — Kubernetes Uyandırması (Frontend K8s + Ingress)

**Hedef:** Frontend pod'unu K8s'e taşı, Ingress ile tüm sistemi tek domain'den sun.

#### A.1 — Frontend K8s Manifestoları [YENİ DOSYALAR]

##### [YENİ] `k8s/frontend/deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: bulutistan-frontend
  labels:
    app: bulutistan-frontend
spec:
  replicas: 2
  selector:
    matchLabels:
      app: bulutistan-frontend
  template:
    metadata:
      labels:
        app: bulutistan-frontend
    spec:
      containers:
        - name: bulutistan-frontend
          image: bulutistan-frontend:latest
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8050
          resources:
            requests:
              cpu: 200m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
          livenessProbe:
            httpGet:
              path: /
              port: 8050
            initialDelaySeconds: 15
            periodSeconds: 30
            timeoutSeconds: 5
          readinessProbe:
            httpGet:
              path: /
              port: 8050
            initialDelaySeconds: 10
            periodSeconds: 10
            timeoutSeconds: 3
          env:
            - name: API_BASE_URL
              valueFrom:
                configMapKeyRef:
                  name: bulutistan-frontend-config
                  key: API_BASE_URL
          envFrom:
            - configMapRef:
                name: bulutistan-frontend-config
```

**Tasarım kararları:**
- `livenessProbe` → `GET /` (Dash ana sayfası HTTP 200 döner)
- `readinessProbe` → aynı path (frontend hazır demek = gunicorn worker aktif demek)
- `replicas: 2` — yüksek erişilebilirlik (HA)
- `API_BASE_URL` ConfigMap'ten okunuyor → cluster-içi service adı

##### [YENİ] `k8s/frontend/service.yaml`

```yaml
apiVersion: v1
kind: Service
metadata:
  name: bulutistan-frontend
  labels:
    app: bulutistan-frontend
spec:
  type: ClusterIP
  selector:
    app: bulutistan-frontend
  ports:
    - port: 80
      targetPort: 8050
      protocol: TCP
```

##### [YENİ] `k8s/frontend/configmap.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: bulutistan-frontend-config
data:
  API_BASE_URL: "http://bulutistan-data-api"
```

> [!WARNING]
> `API_BASE_URL` değeri `http://bulutistan-data-api` olmalıdır — `http://localhost:8000` DEĞİL.
> Bu K8s Service DNS adıdır. Backend service.yaml'ın `metadata.name` alanıyla BİREBİR eşleşir.

##### [YENİ] `k8s/frontend/hpa.yaml`

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: bulutistan-frontend
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: bulutistan-frontend
  minReplicas: 2
  maxReplicas: 6
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 75
```

#### A.2 — Ingress Controller [YENİ DOSYA]

##### [YENİ] `k8s/ingress.yaml`

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: bulutistan-ingress
  annotations:
    nginx.ingress.kubernetes.io/proxy-connect-timeout: "30"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "60"
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
spec:
  ingressClassName: nginx
  rules:
    - host: bulutistan.local
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: bulutistan-data-api
                port:
                  number: 80
          - path: /health
            pathType: Exact
            backend:
              service:
                name: bulutistan-data-api
                port:
                  number: 80
          - path: /ready
            pathType: Exact
            backend:
              service:
                name: bulutistan-data-api
                port:
                  number: 80
          - path: /
            pathType: Prefix
            backend:
              service:
                name: bulutistan-frontend
                port:
                  number: 80
```

**Yönlendirme mantığı:** `/api/*`, `/health`, `/ready` → Backend, geri kalan her şey → Frontend.

#### A.3 — Backend Deployment Düzeltmeleri [MODIFY]

##### [MODIFY] `k8s/backend/deployment.yaml`

```diff
 readinessProbe:
   httpGet:
     path: /ready
     port: 8000
-  initialDelaySeconds: 5
+  initialDelaySeconds: 25
   periodSeconds: 10
```

**Sebep:** `warm_cache` 17 saniye sürüyor. `initialDelaySeconds: 5` ile readiness
probe'u backend hazır olmadan PASSED verebilir. 25 saniye bu marjı güvenli karşılar.

##### [MODIFY] `k8s/backend/hpa.yaml` — Memory Metriği Ekleme

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: bulutistan-data-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: bulutistan-data-api
  minReplicas: 2
  maxReplicas: 8
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
```

#### A.4 — Rota A Doğrulama

- [ ] `kubectl apply -f k8s/redis/` → Redis pod RUNNING
- [ ] `kubectl apply -f k8s/backend/` → Backend 2 pod RUNNING, readiness 25s sonra PASSED
- [ ] `kubectl apply -f k8s/frontend/` → Frontend 2 pod RUNNING
- [ ] `kubectl apply -f k8s/ingress.yaml` → Ingress oluşturuldu
- [ ] `curl http://bulutistan.local/api/v1/health` → `{"status": "ok", "redis": "connected"}`
- [ ] `curl http://bulutistan.local/` → HTML 200 (Dash sayfası)
- [ ] `kubectl get hpa` → Backend (min:2 max:8) ve Frontend (min:2 max:6) listeleniyor

---

### ROTA B — CI/CD Pipeline (GitHub Actions)

**Hedef:** Kod push'landığında otomatik test, lint, Docker build ve (isteğe bağlı)
push yapan pipeline oluşturmak.

#### B.1 — Dizin Yapısı

```
.github/
└── workflows/
    └── main.yml          ← [YENİ] Tek pipeline dosyası
```

#### B.2 — Pipeline Mimarisi

```
┌──────────────────────────────────────────────────────────────┐
│                    GitHub Actions Workflow                     │
│                                                                │
│  Trigger: push (main, develop) / pull_request (main)          │
│                                                                │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐  │
│  │   Stage 1    │  │   Stage 2    │  │      Stage 3         │  │
│  │  LINT        │  │  TEST        │  │  BUILD & PUSH        │  │
│  │  ─────────── │→│  ─────────── │→│  ──────────────────── │  │
│  │  ruff check  │  │  pytest      │  │  docker build        │  │
│  │  backend/    │  │  329 tests   │  │  backend + frontend  │  │
│  │              │  │  coverage≥85%│  │  push to registry    │  │
│  │              │  │  PostgreSQL  │  │  (only on main)      │  │
│  │              │  │  + Redis svc │  │                      │  │
│  └─────────────┘  └─────────────┘  └──────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

#### B.3 — main.yml Detaylı Yapı

##### [YENİ] `.github/workflows/main.yml`

Pipeline şu iş parçalarından (jobs) oluşacak:

**Job 1: `lint`**
- Python 3.11 runner
- `pip install ruff`
- `ruff check backend/app/ --select E,F,W --ignore E501`
- Fail → pipeline durur

**Job 2: `test`** (depends_on: lint)
- Python 3.11 runner
- **Services:** PostgreSQL 15 + Redis 7 (GitHub Actions service containers)
- PostgreSQL: `bulutlake` DB, `datalakeui` user, otomatik port
- Redis: standart port 6379
- `pip install -r backend/requirements.txt`
- `pip install pytest pytest-cov`
- `cd backend && pytest tests/ -v --tb=short --cov=app --cov-report=term-missing`
- Coverage threshold: `--cov-fail-under=85`
- Fail → pipeline durur

**Job 3: `build`** (depends_on: test, only on `main` branch)
- Docker Buildx setup
- Backend image: `docker build -t $REGISTRY/bulutistan-data-api:$SHA -f backend/Dockerfile ./backend`
- Frontend image: `docker build -t $REGISTRY/bulutistan-frontend:$SHA -f Dockerfile .`
- Tag: Git SHA + `latest`
- Push: Container registry'ye (GitHub Container Registry veya özel registry)

> [!IMPORTANT]
> Pipeline YAML dosyasında SIFIR açıklama satırı (`#`) kullanılacak. YAML'ın native yapısı
> (key-value) zaten kendini açıklar. İhtiyaç duyulan context, `name:` alanlarında verilecek.

#### B.4 — Pipeline Ortam Değişkenleri

| Değişken | Değer | Kaynak |
|----------|-------|--------|
| `DB_HOST` | `localhost` (service container) | Pipeline env |
| `DB_PORT` | `5432` | Pipeline env |
| `DB_NAME` | `bulutlake` | Pipeline env |
| `DB_USER` | `datalakeui` | Pipeline env |
| `DB_PASS` | `test_password` | Pipeline env |
| `REDIS_HOST` | `localhost` | Pipeline env |
| `REDIS_PORT` | `6379` | Pipeline env |
| `REGISTRY` | `ghcr.io/bulutistan` | GitHub Secrets |

#### B.5 — Rota B Doğrulama

- [ ] `.github/workflows/main.yml` oluşturulmuş
- [ ] Local test: `act -j test` (veya GitHub'a push edip Actions tab kontrol)
- [ ] Lint job geçiyor: ruff hataları yok
- [ ] Test job: 329 test PASSED, coverage ≥ %85
- [ ] Build job: 2 Docker image başarıyla build ediliyor
- [ ] YAML dosyasında SIFIR `#` satırı: `grep "^[[:space:]]*#" .github/workflows/main.yml` → SIFIR

---

### ROTA C — Stres ve Yük Testi (Locust)

**Hedef:** Sistemin cold-start karakteristiğini ve yoğun yük altındaki davranışını test
ederek HPA'nın otomatik ölçekleme yeteneğini kanıtlamak.

#### C.1 — Dizin Yapısı

```
loadtest/
├── locustfile.py          ← [YENİ] Yük testi senaryoları
├── requirements.txt       ← [YENİ] locust>=2.20
└── reports/               ← [YENİ] Test sonuç raporları (gitignore'a ekle)
```

#### C.2 — Test Senaryoları

`locustfile.py` şu user sınıflarını içerecek:

**UserClass 1: `DashboardUser`** (ağırlık: 3)
- `GET /api/v1/dashboard/overview?preset=7d` — ana dashboard yükü
- `GET /api/v1/datacenters/summary?preset=7d` — DC listesi
- Wait time: 2-5 saniye arası

**UserClass 2: `DetailUser`** (ağırlık: 2)
- `GET /api/v1/datacenters/DC11?preset=7d` — tekil DC detay
- `GET /api/v1/datacenters/DC11?preset=30d` — farklı time range
- Wait time: 3-8 saniye arası

**UserClass 3: `CustomerUser`** (ağırlık: 1)
- `GET /api/v1/customers` — müşteri listesi
- `GET /api/v1/customers/Boyner/resources?preset=7d` — müşteri kaynakları
- Wait time: 5-10 saniye arası

**UserClass 4: `HealthCheckUser`** (ağırlık: 1)
- `GET /health` — health check bombardımanı
- Wait time: 1-2 saniye arası

#### C.3 — Yük Testi Aşamaları

| Aşama | Süre | Kullanıcı Sayısı | Amaç |
|-------|------|-----------------|------|
| 1 — Isınma (Warm-up) | 60 sn | 5 → 20 | Cold-start davranışını gözlemle |
| 2 — Normal Yük | 120 sn | 20 (sabit) | Baseline performansı belirle |
| 3 — Yoğun Yük (Stress) | 180 sn | 20 → 100 | HPA tetiklenmesini gözlemle |
| 4 — Spike | 60 sn | 100 → 200 | Ani yük artışında sistemi test et |
| 5 — Soğuma (Cool-down) | 120 sn | 200 → 10 | HPA scale-down davranışını gözlemle |

**Toplam Süre:** ~9 dakika

#### C.4 — HPA Kanıtlama Stratejisi

Test sırasında paralel terminalden şu komutlar çalıştırılacak:

```
Terminal 1: locust -f loadtest/locustfile.py --host=http://bulutistan.local --headless
            --users 200 --spawn-rate 10 --run-time 9m
            --csv=loadtest/reports/report --html=loadtest/reports/report.html

Terminal 2: kubectl get hpa -w
            (Anlık HPA durumu — pod sayısı artışını izle)

Terminal 3: kubectl top pods -l app=bulutistan-data-api --containers
            (CPU/RAM kullanımını izle)
```

**Beklenen sonuç:**
- Aşama 3'te CPU %70'i aştığında HPA pod sayısını 2 → 4-5 arası artıracak
- Aşama 5'te yük düşünce 5 dakika sonra pod sayısı 2'ye dönecek
- Tüm süre boyunca Locust p99 latency < 5 saniye olmalı (cold-start hariç)

#### C.5 — Cold-Start Test Senaryosu

Ayrı bir senaryo olarak:
1. Tüm backend pod'larını sıfırla: `kubectl rollout restart deployment bulutistan-data-api`
2. Hemen ardından Locust başlat (5 kullanıcı)
3. İlk 20 saniye TIMEOUT veya yüksek latency beklenir (warm_cache süreci)
4. 20. saniyeden sonra yanıt süreleri normalleşmeli (<500ms)
5. Bu davranış `readinessProbe initialDelaySeconds: 25` ile korunuyor — Kubernetes
   pod'u hazır olarak işaretlemeden trafik yönlendirmez

#### C.6 — Rota C Doğrulama

- [ ] `loadtest/locustfile.py` oluşturulmuş, 4 UserClass tanımlı
- [ ] `pip install locust` ve local test: `locust -f loadtest/locustfile.py --host=http://localhost:8000 --headless --users 10 --spawn-rate 2 --run-time 30s`
- [ ] K8s üzerinde tam test: 200 kullanıcılı yük testi çalıştırıldı
- [ ] **HPA KANITI:** `kubectl get hpa -w` çıktısında pod sayısının 2'den en az 4'e çıktığı görülmeli
- [ ] **LATENCY KANITI:** Locust raporu p95 < 3s, p99 < 5s (cold-start hariç)
- [ ] `loadtest/reports/report.html` dosyası oluşturulmuş
- [ ] Cold-start testi: restart sonrası 25s boyunca trafik yönlendirilmediği doğrulandı

---

### ROTA D — Gözlemlenebilirlik (Observability)

**Hedef:** Prod ortamda hataları, performans sorunlarını ve sistem durumunu
anlık izleyebilmek için structured logging ve metrik toplama altyapısı kurmak.

#### D.1 — Mevcut Loglama Durumu

| Modül | Mevcut Yöntem | Çıktı Formatı |
|-------|--------------|----------------|
| `backend/app/main.py` | `logging.basicConfig(level=INFO)` | Plain text |
| `backend/app/services/*.py` | `logging.getLogger(__name__)` | Plain text |
| `backend/app/core/*.py` | `logging.getLogger(__name__)` | Plain text |
| `backend/app/adapters/*.py` | `logging.getLogger(__name__)` | Plain text |
| `app.py` (frontend) | `logging.basicConfig(...)` | Custom format string |

**Problem:** Plain text loglar K8s ortamında Fluentd/Loki ile parse edilemez.

> [!IMPORTANT]
> Backend kodu FROZEN olduğu için `backend/app/` içindeki logging çağrılarına
> dokunulmayacak. Çözüm: **Container seviyesinde log formatter konfigürasyonu.**
> - `logging.basicConfig` runtime'da `LOGGING_FORMAT` ortam değişkenine göre JSON formatter
>   seçecek şekilde yapılandırılabilir.
> - VEYA: Kubernetes seviyesinde Fluentd/Fluent Bit ile stdout loglarını parse edip
>   yapılandırılmış (structured) hale getirebiliriz.
>
> **Karar:** Fluentd sidecar/DaemonSet yaklaşımı (backend koduna DOKUNMAZ).

#### D.2 — Observability Stack Seçimi

| Katman | Araç | Görev |
|--------|------|-------|
| Log Toplama | **Fluent Bit** (DaemonSet) | Container stdout'tan log toplama |
| Log Depolama | **Loki** (veya ElasticSearch) | Log indexleme ve saklama |
| Metrik Toplama | **Prometheus** | HPA metrikleri + custom metrikler |
| Görselleştirme | **Grafana** | Dashboard + alerting |
| Health Monitoring | **Mevcut `/health` endpoint** | Uptime izleme |

#### D.3 — Kubernetes Manifest'leri

##### [YENİ] `k8s/monitoring/namespace.yaml`

Monitoring stack'i `bulutistan-monitoring` namespace'inde çalışacak.

##### [YENİ] `k8s/monitoring/fluent-bit-configmap.yaml`

Fluent Bit konfigürasyonu:
- Input: Kubernetes container logları (tail)
- Parser: Regex ile timestamp, level, module, message ayrıştırma
- Output: Loki'ye HTTP push (veya stdout → Grafana Cloud)
- Filter: `app=bulutistan-*` label'ına sahip pod'lardan log toplama

##### [YENİ] `k8s/monitoring/fluent-bit-daemonset.yaml`

Her node'da bir Fluent Bit pod'u çalışacak.

##### [YENİ] `k8s/monitoring/prometheus-config.yaml`

Prometheus scrape konfigürasyonu:
- Backend `/health` endpoint'inden metrik toplama (15s interval)
- Node exporter metrikleri
- Kubernetes API server metrikleri

#### D.4 — Grafana Dashboard Tasarımı

3 ana dashboard:

| Dashboard | Paneller |
|-----------|---------|
| **System Overview** | Pod count, CPU/RAM kullanım trendleri, HPA current/target replicas |
| **API Performance** | Request rate, latency (p50/p95/p99), error rate, endpoint breakdown |
| **Cache & DB** | Redis hit/miss ratio, connection pool utilization, slow query count |

#### D.5 — Alert Kuralları

| Alert | Koşul | Severity |
|-------|-------|----------|
| `HighErrorRate` | 5xx oranı > %5 (5 dk pencere) | Critical |
| `HighLatency` | p99 > 5s (5 dk pencere) | Warning |
| `PodCrashLoop` | Pod restart count > 3 (10 dk pencere) | Critical |
| `HighCPU` | CPU > %90 (10 dk pencere) | Warning |
| `RedisDown` | `/health` Redis status != connected (2 dk pencere) | Critical |
| `HPAMaxReached` | HPA current == max replicas (15 dk pencere) | Warning |

#### D.6 — Rota D Doğrulama

- [ ] Fluent Bit DaemonSet çalışıyor: `kubectl get ds -n bulutistan-monitoring`
- [ ] Backend logları toplanıyor: Grafana'da son 5 dakikanın logları görünüyor
- [ ] Prometheus metrikleri: `kubectl port-forward svc/prometheus 9090:9090` → targets UP
- [ ] Grafana dashboard'lar: System Overview, API Performance, Cache & DB
- [ ] Alert test: Backend pod'unu kill et → PodCrashLoop alert'i tetikleniyor

---

## BÖLÜM D: DOSYA DEĞİŞİKLİK HARİTASI

### Yeni Dosyalar

| Dosya | Rota | İçerik |
|-------|------|--------|
| `k8s/frontend/deployment.yaml` | A | Frontend Deployment (2 replika) |
| `k8s/frontend/service.yaml` | A | Frontend ClusterIP Service |
| `k8s/frontend/configmap.yaml` | A | `API_BASE_URL` ve env vars |
| `k8s/frontend/hpa.yaml` | A | Frontend HPA (min:2 max:6) |
| `k8s/ingress.yaml` | A | NGINX Ingress (path-based routing) |
| `.github/workflows/main.yml` | B | CI/CD Pipeline (lint → test → build) |
| `loadtest/locustfile.py` | C | 4 UserClass, 5 aşamalı yük testi |
| `loadtest/requirements.txt` | C | `locust>=2.20` |
| `k8s/monitoring/namespace.yaml` | D | monitoring namespace |
| `k8s/monitoring/fluent-bit-configmap.yaml` | D | Log parser konfigürasyonu |
| `k8s/monitoring/fluent-bit-daemonset.yaml` | D | Log toplama DaemonSet |
| `k8s/monitoring/prometheus-config.yaml` | D | Metrik scrape konfigürasyonu |

### Değiştirilecek Dosyalar

| Dosya | Rota | Değişiklik |
|-------|------|-----------|
| `k8s/backend/deployment.yaml` | A | readiness `initialDelaySeconds: 5 → 25` |
| `k8s/backend/hpa.yaml` | A | Memory metriği ekleme |
| `.gitignore` | C | `loadtest/reports/` ekleme |

### Dokunulmayacak Dosyalar (FROZEN)

| Dizin/Dosya | Sebep |
|-------------|-------|
| `backend/app/` | CTO yasağı — çekirdek kod |
| `backend/tests/` | 329 test süiti |
| `src/` | FAZ 3'te tamamlanan frontend |
| `docker-compose.yml` | Local geliştirme ortamı |
| `Dockerfile` (kök) | Frontend Docker image |
| `backend/Dockerfile` | Backend Docker image |

---

## BÖLÜM E: TAMAMLANMA MATRİSİ

| # | Kriter | Kanıt Tipi | Rota |
|---|--------|------------|------|
| 1 | Frontend K8s manifestoları oluşturulmuş (4 dosya) | `ls k8s/frontend/` çıktısı | A |
| 2 | Ingress YAML oluşturulmuş ve path-based routing çalışıyor | `curl` çıktıları | A |
| 3 | Backend readiness `initialDelaySeconds: 25` olarak güncellendi | `cat` çıktısı | A |
| 4 | Backend HPA'ya memory metriği eklendi | `kubectl get hpa -o yaml` çıktısı | A |
| 5 | Tüm pod'lar RUNNING: `kubectl get pods` | Terminal çıktısı | A |
| 6 | `.github/workflows/main.yml` oluşturulmuş, SIFIR `#` satırı | `grep` çıktısı | B |
| 7 | Pipeline lint job geçiyor | GitHub Actions veya `act` çıktısı | B |
| 8 | Pipeline test job: 329 test PASSED, coverage ≥ %85 | GitHub Actions çıktısı | B |
| 9 | Pipeline build job: 2 Docker image başarıyla build | GitHub Actions çıktısı | B |
| 10 | `loadtest/locustfile.py` oluşturulmuş, 4 UserClass tanımlı | Dosya içeriği | C |
| 11 | **HPA OTOMATİK ÖLÇEKLEME KANITI:** Locust yük testi altında HPA'nın pod sayısını 2'den en az 4'e çıkardığı `kubectl get hpa -w` terminal logu sunulmalıdır | Terminal screenshot | C |
| 12 | Locust raporu: p95 < 3s, p99 < 5s | `loadtest/reports/report.html` | C |
| 13 | Cold-start testi: 25s boyunca trafik yönlendirilmediği doğrulandı | `kubectl` logu | C |
| 14 | Fluent Bit DaemonSet çalışıyor | `kubectl get ds` çıktısı | D |
| 15 | Grafana dashboard'lar oluşturulmuş | Ekran görüntüsü | D |
| 16 | Alert kuralları tanımlı, en az 1 test alert tetiklenmiş | Alert logu | D |
| 17 | `backend/app/` dizinine SIFIR değişiklik | `git diff backend/app/` → boş | ALL |
| 18 | Tüm yeni dosyalarda SIFIR `#` satırı | `grep` çıktısı | ALL |
