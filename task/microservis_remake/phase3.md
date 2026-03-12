# FAZ 3 — Monolitik Frontend'in REST API'ye Entegrasyonu

> **Hedef:** Dash frontend'in `src/services/db_service.py` ve `src/services/shared.py` üzerinden
> yaptığı tüm doğrudan veritabanı çağrılarını kopararak, FAZ 1-2'de inşa edilen
> `http://localhost:8000/api/v1/...` REST endpoint'lerine yönlendirmek.
>
> **Öncül:** FAZ 1 (FastAPI + Feature Parity) ve FAZ 2 (Redis + Adapters + TimeFilter) %100
> tamamlandı. 329 regresyon testi firesiz geçiyor (%95 coverage). Backend dondurulmuş durumdadır.
>
> **Executer Referansları:**
> - Anayasa: `task/microservis_remake/mcrsrvc_skills.md`
> - Öğretiler: `task/microservis_remake/mcrsrvc_lessons.md`
> - Test Standartları: `task/microservis_remake/mcrsrvc_tests.md`

---

> [!CAUTION]
> ## EXECUTER İÇİN MUTLAK YASAKLAR
>
> 1. **SIFIR YORUM SATIRI KURALI:** Değiştirilecek veya eklenecek HİÇBİR UI dosyasında
>    tek bir yorum satırı (`#`) dahi barındırılmayacak. Docstring YASAK.
>    Tek istisna: `TODO:` ve `FIXME:` etiketleri.
>
> 2. **BACKEND DOKUNULMAZLIĞI:** `backend/app/` dizini ve 329 testlik süit KESİNLİKLE
>    değiştirilmeyecek. Backend **FROZEN STATE**'dedir. Uyumsuzluk varsa Frontend kendini
>    API'ye uyduracak, backend'e patch atılmayacak. `backend/tests/` de dahil.
>
> 3. **GÖRSEL KORUMA:** Mevcut UI tasarımı, renk paleti, Mantine component yapısı ve
>    CSS class'ları bozulmadan sadece **veri çekme katmanı** (data-fetching layer) değişecek.
>    Hiçbir `.nexus-card`, `.nexus-glass`, `dmc.RingProgress`, `DashIconify` kullanımı
>    kaldırılmayacak veya değiştirilmeyecek.
>
> 4. **HER ADIM DOĞRULANMADAN BİR SONRAKİNE GEÇİLMEYECEK.** Kanıt: UI ekran görüntüsü,
>    API response karşılaştırması veya test çıktısı.

---

## BÖLÜM A: MEVCUT DURUM KEŞFİ

### A.1 — Frontend Proje Yapısı

```
Datalake-Platform-GUI/
├── app.py                         ← Ana Dash uygulaması (269 satır, 5 callback)
├── src/
│   ├── services/
│   │   ├── shared.py              ← BAĞIMLILIK NOKTASI: DatabaseService singleton
│   │   ├── db_service.py          ← 59K monolitik DB service (DOĞRUDAN DB bağlantısı)
│   │   ├── cache_service.py       ← In-memory TTLCache
│   │   ├── scheduler_service.py   ← APScheduler (warm_cache + Boyner refresh)
│   │   └── query_overrides.py     ← JSON SQL override sistemi
│   ├── pages/
│   │   ├── home.py                ← 581 satır — Executive Dashboard
│   │   ├── datacenters.py         ← 334 satır — DC grid kartları
│   │   ├── dc_view.py             ← 313 satır — Tekil DC detay (Intel/Power/Summary)
│   │   ├── customer_view.py       ← 506 satır — Müşteri varlıkları (4 tab)
│   │   ├── query_explorer.py      ← 282 satır — SQL sorgu aracı (5 callback)
│   │   └── cluster_view.py        ← 49 satır — Placeholder
│   ├── components/
│   │   ├── charts.py              ← 20K — Plotly chart factory fonksiyonları
│   │   ├── header.py              ← Sayfa header component
│   │   └── sidebar.py             ← Navigasyon sidebar
│   ├── utils/
│   │   └── time_range.py          ← Preset/custom tarih aralığı yönetimi
│   ├── queries/                   ← ESKİ SQL query modülleri (frontend kopyaları)
│   └── data/                      ← Statik veri
└── assets/                        ← CSS dosyaları
```

### A.2 — Sıkı Bağ (Tight-Coupling) Haritası

Mevcut sistemde **TEK bir bağımlılık noktası** var: `src/services/shared.py`

```python
from src.services.db_service import DatabaseService
service: DatabaseService = DatabaseService()
```

Bu singleton'ı `import` eden dosyalar ve çağırdıkları metotlar:

| Dosya | Import | Çağrılan Metot | Satır # |
|-------|--------|----------------|---------|
| `app.py` | `from src.services.shared import service` | `service.get_customer_list()` | 42 |
| `app.py` | `from src.services.scheduler_service import start_scheduler` | `start_scheduler(service)` | 265 |
| `home.py` | `from src.services.shared import service` | `service.get_global_dashboard(tr)` | 225 |
| `home.py` | (aynı) | `service.get_all_datacenters_summary(tr)` | 229 |
| `datacenters.py` | `from src.services.shared import service` | `service.get_all_datacenters_summary(tr)` | 216 |
| `dc_view.py` | `from src.services.shared import service` | `service.get_dc_details(dc_id, tr)` | 39 |
| `customer_view.py` | `from src.services.shared import service` | `service.get_customer_resources(name, tr)` | 108 |
| `query_explorer.py` | `from src.services.shared import service` | `service.execute_registered_query(key, params)` | 218 |
| `query_explorer.py` | `from src.services import query_overrides as qo` | `qo.get_merged_entry(key)` | 196 |
| `query_explorer.py` | (aynı) | `qo.list_all_query_keys()` | 13 |
| `query_explorer.py` | (aynı) | `qo.set_override(...)` | 238, 278 |
| `query_explorer.py` | (aynı) | `qo.remove_override(key)` | 254 |

**Ek bağımlılıklar:**
- `app.py:265` → `start_scheduler(service)` — backend scheduler'ın frontend kopyası
- `query_explorer.py:274` → `from src.queries.registry import QUERY_REGISTRY` — eski SQL registry

### A.3 — Time Range Mevcut Akışı

Time range zaten `dcc.Store(id='app-time-range')` ile merkezi yönetiliyor:

```
sidebar > SegmentedControl (1D/7D/30D/Cstm) ──▶ Callback #3 ──▶ dcc.Store
sidebar > DatePicker (custom range)           ──▶ Callback #3 ──▶ dcc.Store
                                                                      │
                                                                      ▼
                                              Callback #4 (render_main_content)
                                              page.build_*(time_range=tr)
```

Bu yapı zaten FAZ 2'nin `?preset=` ve `?start=&end=` parametreleriyle uyumlu.
Dönüşüm sırasında `time_range` dict'i doğrudan API query params'a çevrilecek.

---

## BÖLÜM B: ESKİ → YENİ EŞLEŞTİRME TABLOSU

### B.1 — Veri Çekme Çağrıları (service.* → HTTP GET)

| # | Eski Çağrı | Yeni API Endpoint | HTTP | Query Params |
|---|-----------|-------------------|------|--------------|
| 1 | `service.get_global_dashboard(tr)` | `/api/v1/dashboard/overview` | GET | `?start={tr.start}&end={tr.end}` veya `?preset={tr.preset}` |
| 2 | `service.get_all_datacenters_summary(tr)` | `/api/v1/datacenters/summary` | GET | `?start={tr.start}&end={tr.end}` veya `?preset={tr.preset}` |
| 3 | `service.get_dc_details(dc_id, tr)` | `/api/v1/datacenters/{dc_id}` | GET | `?start={tr.start}&end={tr.end}` veya `?preset={tr.preset}` |
| 4 | `service.get_customer_list()` | `/api/v1/customers` | GET | — |
| 5 | `service.get_customer_resources(name, tr)` | `/api/v1/customers/{name}/resources` | GET | `?start={tr.start}&end={tr.end}` veya `?preset={tr.preset}` |
| 6 | `service.execute_registered_query(key, params)` | `/api/v1/queries/{key}` | GET | `?params={params}` |

### B.2 — Query Override Çağrıları (qo.* → HTTP)

| # | Eski Çağrı | Yeni API Endpoint | HTTP | Not |
|---|-----------|-------------------|------|-----|
| 7 | `qo.list_all_query_keys()` | `/api/v1/queries/keys` | GET | **YENİ ENDPOINT GEREKLİ — veya local fallback** |
| 8 | `qo.get_merged_entry(key)` | `/api/v1/queries/{key}/metadata` | GET | **YENİ ENDPOINT GEREKLİ — veya local fallback** |
| 9 | `qo.set_override(...)` | `/api/v1/queries/{key}/override` | PUT | **YENİ ENDPOINT GEREKLİ — veya local fallback** |
| 10 | `qo.remove_override(key)` | `/api/v1/queries/{key}/override` | DELETE | **YENİ ENDPOINT GEREKLİ — veya local fallback** |

> [!IMPORTANT]
> ## QUERY EXPLORER KRİTİK KARAR
>
> Backend'de (FAZ 1-2) query override CRUD endpoint'leri **MEVCUT DEĞİL**. Sadece
> `GET /api/v1/queries/{query_key}?params=...` var.
>
> **Seçenek A (Önerilen):** Query Explorer'daki `list_all_query_keys`, `get_merged_entry`,
> `set_override`, `remove_override` çağrılarını **LOCAL** tutmak. `query_explorer.py` hâlâ
> `src/services/query_overrides.py`'yi doğrudan import eder. Bu dosya dosya-sistemi tabanlı
> JSON override sistemidir ve veritabanıyla iletişim kurmaz. Frontend'de kalması backend
> dokunulmazlığını ihlal ETMEZ.
>
> **Seçenek B:** Backend'e yeni CRUD endpoint'leri eklemek. Ama bu FAZ 2'de dondurulmuş
> backend'e dokunmak demektir — **CTO YASAĞI İHLAL**.
>
> **Karar: SEÇENEK A.** `query_overrides.py` ve `src/queries/registry.py` frontend'de
> local kalacak. Sadece `execute_registered_query` HTTP'ye taşınacak.

---

## BÖLÜM C: DEĞİŞECEK DOSYALAR HARİTASI

### C.1 — Değişecekler

| Dosya | Değişiklik Türü | Etki Alanı |
|-------|----------------|------------|
| `src/services/shared.py` | **TAM REFACTOR** | `DatabaseService` → `ApiClient` (httpx) |
| `src/services/api_client.py` | **YENİ DOSYA** | HTTP client wrapper — tüm API çağrıları burada |
| `src/pages/home.py` | **2 SATIR** | `service.get_*` → `api.get_*` |
| `src/pages/datacenters.py` | **1 SATIR** | `service.get_*` → `api.get_*` |
| `src/pages/dc_view.py` | **1 SATIR** | `service.get_*` → `api.get_*` |
| `src/pages/customer_view.py` | **1 SATIR** | `service.get_*` → `api.get_*` |
| `src/pages/query_explorer.py` | **1 SATIR** | `service.execute_*` → `api.execute_*` |
| `app.py` | **3 BÖLÜM** | import değişimi + scheduler kaldırma + customer_list |

### C.2 — Değişmeyecekler (FROZEN)

| Dosya/Dizin | Sebep |
|-------------|-------|
| `backend/` (tüm dizin) | CTO yasağı — FROZEN STATE |
| `src/components/charts.py` | Sadece Plotly figure üretiyor, veri çekmez |
| `src/components/header.py` | UI component, veri kaynağından bağımsız |
| `src/components/sidebar.py` | Navigasyon, veri kaynağından bağımsız |
| `src/utils/time_range.py` | Pure utility fonksiyonlar, her iki tarafta kullanılabilir |
| `src/pages/cluster_view.py` | Placeholder, `service` çağrısı yok |
| `src/services/query_overrides.py` | LOCAL kalacak (Bölüm B.2 kararı) |
| `src/queries/` | `query_explorer.py` local registry erişimi için kalacak |
| `assets/` | CSS dosyaları, veri katmanından bağımsız |

### C.3 — Silinecekler / Devre Dışı Bırakılacaklar

| Dosya | Aksiyon | Sebep |
|-------|---------|-------|
| `src/services/db_service.py` | **SİL** (veya `_legacy_db_service.py` olarak yeniden adlandır) | 59K monolitik DB service — artık backend'de yaşıyor |
| `src/services/cache_service.py` | **SİL** | Cache artık backend Redis'te |
| `src/services/scheduler_service.py` | **SİL** | Scheduler artık backend `main.py` lifespan'da |
| `app.py:265` → `start_scheduler(service)` | **KALDIR** | Scheduler frontend'den bağımsızlaştı |

---

## BÖLÜM D: MİMARİ — api_client.py Tasarımı

### D.1 — HTTP Client Stratejisi

**Kararlar:**
- **Kütüphane:** `httpx` (zaten `requirements.txt`'te mevcut, versiyon `>=0.27.0`)
- **Senkron:** `httpx.Client` (Dash callback'ler senkron çalışır, async gereksiz)
- **Singleton pattern:** `shared.py`'deki `service` yerine `api` singleton'ı
- **Timeout:** 30 saniye (warm_cache 17 sn. sürebilir, ilk istekte cold-start gecikme)
- **Retry:** 3 deneme, exponential backoff (0.5s, 1s, 2s)
- **Base URL:** Ortam değişkeni ile yapılandırılabilir: `API_BASE_URL` (varsayılan: `http://localhost:8000`)

### D.2 — api_client.py Public API

```
src/services/api_client.py    [YENİ DOSYA]
```

Aşağıdaki fonksiyonları implement et. Her fonksiyon FAZ 1-2'deki mevcut `service.*` çağrısının
BİREBİR karşılığıdır. Dönüş tipleri değişmeyecek.

| Fonksiyon | HTTP | Endpoint | Dönüş tipi | Sayfa kullanımı |
|-----------|------|----------|------------|-----------------|
| `get_global_dashboard(tr: dict) -> dict` | GET | `/api/v1/dashboard/overview` | `{"overview": {...}, "platforms": {...}, "energy_breakdown": {...}}` | `home.py:225` |
| `get_all_datacenters_summary(tr: dict) -> list[dict]` | GET | `/api/v1/datacenters/summary` | `[{"id": "DC11", "name": "DC11", "location": "Istanbul", ...}]` | `home.py:229`, `datacenters.py:216` |
| `get_dc_details(dc_id: str, tr: dict) -> dict` | GET | `/api/v1/datacenters/{dc_id}` | `{"meta": {...}, "intel": {...}, "power": {...}, "energy": {...}, "platforms": {...}}` | `dc_view.py:39` |
| `get_customer_list() -> list[str]` | GET | `/api/v1/customers` | `["Boyner"]` | `app.py:42` |
| `get_customer_resources(name: str, tr: dict) -> dict` | GET | `/api/v1/customers/{name}/resources` | `{"totals": {...}, "assets": {...}}` | `customer_view.py:108` |
| `execute_registered_query(key: str, params: str) -> dict` | GET | `/api/v1/queries/{key}` | `{"result_type": "...", "value": ..., "columns": [...], "data": [...]}` | `query_explorer.py:218` |

### D.3 — Time Range → Query Params Dönüşümü

```
Girdi: tr = {"start": "2026-03-05", "end": "2026-03-11", "preset": "7d"}

EĞER tr["preset"] in ("1d", "7d", "30d"):
    → ?preset=7d

EĞER tr["preset"] == "custom" VEYA preset yoksa:
    → ?start=2026-03-05&end=2026-03-11

EĞER tr None veya boşsa:
    → Parametre ekleme (backend varsayılan 7d kullanır)
```

Bu mantık `api_client.py` içinde `_build_time_params(tr)` adlı internal fonksiyonla yapılacak.

### D.4 — Cold Start / Loading UX Stratejisi

**Problem:** Backend ilk ayağa kalktığında `warm_cache` 17 saniye sürüyor.
Bu sürede API yanıt verebilir ama veri henüz cache'te olmadığı için yavaş olabilir.

**Çözüm stratejisi (Executer'ın uygulaması gereken):**

1. `api_client.py`'de `httpx.Client(timeout=30.0)` kullan — 17 sn. cold start'ı karşılar.

2. `api_client.py`'deki her public fonksiyona `try/except` ekle:
   - `httpx.ConnectError` → Backend henüz ayağa kalkmadı → **FALLBACK dict** dön
   - `httpx.TimeoutException` → Backend meşgul → **FALLBACK dict** dön
   - `httpx.HTTPStatusError` → 5xx → İçi boş yapı dön
   - Fallback dict örnekleri: `get_global_dashboard` → `_EMPTY_DASHBOARD`, `get_dc_details` → `_EMPTY_DC`

3. Mevcut sayfa kodları zaten `.get("key", 0)` ve `or 0` ile defensif yazılmış (ÖGRT-004).
   Boş dict döndüğünde sayfalar **çökmez**, sadece sıfır değerlerle render eder.

4. Frontend'de ek bir loading spinner GEREKMEZ çünkü Dash callback mekanizması zaten
   callback çalışırken `main-content` alanını mevcut haliyle tutar.
   Gerekirse `dcc.Loading` wrapper eklenebilir ama bu görsel değişiklik olacağı için
   CTO onayı gerektirir.

### D.5 — Hata Yönetimi Fallback Yapıları

```python
_EMPTY_DASHBOARD = {
    "overview": {
        "dc_count": 0, "total_hosts": 0, "total_vms": 0,
        "total_platforms": 0, "total_energy_kw": 0.0,
        "total_cpu_cap": 0.0, "total_cpu_used": 0.0,
        "total_ram_cap": 0.0, "total_ram_used": 0.0,
        "total_storage_cap": 0.0, "total_storage_used": 0.0,
    },
    "platforms": {
        "nutanix": {"hosts": 0, "vms": 0},
        "vmware": {"clusters": 0, "hosts": 0, "vms": 0},
        "ibm": {"hosts": 0, "vios": 0, "lpars": 0},
    },
    "energy_breakdown": {"ibm_kw": 0.0, "vcenter_kw": 0.0},
}

_EMPTY_DC_DETAIL = {
    "meta": {"name": "", "location": ""},
    "intel": {"clusters": 0, "hosts": 0, "vms": 0, "cpu_cap": 0.0, "cpu_used": 0.0,
              "ram_cap": 0.0, "ram_used": 0.0, "storage_cap": 0.0, "storage_used": 0.0},
    "power": {"hosts": 0, "vms": 0, "vios": 0, "lpar_count": 0, "cpu": 0,
              "cpu_used": 0.0, "cpu_assigned": 0.0, "ram": 0,
              "memory_total": 0.0, "memory_assigned": 0.0},
    "energy": {"total_kw": 0.0, "ibm_kw": 0.0, "vcenter_kw": 0.0,
               "total_kwh": 0.0, "ibm_kwh": 0.0, "vcenter_kwh": 0.0},
    "platforms": {
        "nutanix": {"hosts": 0, "vms": 0},
        "vmware": {"clusters": 0, "hosts": 0, "vms": 0},
        "ibm": {"hosts": 0, "vios": 0, "lpars": 0},
    },
}

_EMPTY_CUSTOMER = {"totals": {}, "assets": {}}

_EMPTY_QUERY = {"error": "API unreachable"}
```

---

## BÖLÜM E: KADEMELİ İCRA PLANI (BÖL VE YÖNET)

### ADIM 1: API Client Katmanı (Temel Oluştur — Sistem Bozmadan)

**Hedef:** Mevcut sisteme dokunmadan yeni `api_client.py` dosyasını oluştur ve test et.

- [ ] `src/services/api_client.py` dosyasını oluştur (Bölüm D.2'deki 6 fonksiyon)
- [ ] `_build_time_params(tr)` helper fonksiyonunu implement et (Bölüm D.3)
- [ ] Fallback dict'leri tanımla (Bölüm D.5)
- [ ] `httpx.Client` singleton: `_client = httpx.Client(base_url=API_BASE_URL, timeout=30.0)`
- [ ] Retry mantığı: `httpx.HTTPTransport(retries=3)` kullan
- [ ] `API_BASE_URL` ortam değişkeninden oku: `os.getenv("API_BASE_URL", "http://localhost:8000")`

**ADIM 1 — Doğrulama:**
- [ ] Backend'i ayağa kaldır: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000`
- [ ] Python REPL'den test:
  ```
  from src.services.api_client import get_global_dashboard, get_all_datacenters_summary
  print(get_global_dashboard({"start": "2026-03-05", "end": "2026-03-11", "preset": "7d"}))
  print(get_all_datacenters_summary(None))
  ```
- [ ] Backend kapalıyken aynı fonksiyonları çağır → fallback dict dönmeli, exception OLMAMALI
- [ ] `grep -rn "^#" src/services/api_client.py | grep -v "TODO\|FIXME"` → SIFIR sonuç

### ADIM 2: Veri Sayfalarını HTTP'ye Taşı (home, datacenters, dc_view, customer_view)

**Hedef:** 4 sayfa modülünü `service.*` → `api.*` çağrılarına geçir.

- [ ] `src/services/shared.py` güncelle:
  ```
  ÖNCEKİ:
  from src.services.db_service import DatabaseService
  service: DatabaseService = DatabaseService()

  SONRAKI:
  from src.services import api_client as api
  ```

- [ ] `src/pages/home.py` güncelle:
  ```
  ÖNCEKİ (satır 5):     from src.services.shared import service
  SONRAKI:               from src.services import api_client as api

  ÖNCEKİ (satır 225):   data = service.get_global_dashboard(tr)
  SONRAKI:               data = api.get_global_dashboard(tr)

  ÖNCEKİ (satır 229):   summaries = service.get_all_datacenters_summary(tr)
  SONRAKI:               summaries = api.get_all_datacenters_summary(tr)
  ```

- [ ] `src/pages/datacenters.py` güncelle:
  ```
  ÖNCEKİ (satır 5):     from src.services.shared import service
  SONRAKI:               from src.services import api_client as api

  ÖNCEKİ (satır 216):   datacenters = service.get_all_datacenters_summary(tr)
  SONRAKI:               datacenters = api.get_all_datacenters_summary(tr)
  ```

- [ ] `src/pages/dc_view.py` güncelle:
  ```
  ÖNCEKİ (satır 5):     from src.services.shared import service
  SONRAKI:               from src.services import api_client as api

  ÖNCEKİ (satır 39):    data = service.get_dc_details(dc_id, tr)
  SONRAKI:               data = api.get_dc_details(dc_id, tr)
  ```

- [ ] `src/pages/customer_view.py` güncelle:
  ```
  ÖNCEKİ (satır 6):     from src.services.shared import service
  SONRAKI:               from src.services import api_client as api

  ÖNCEKİ (satır 108):   data = service.get_customer_resources(customer_name or "Boyner", tr)
  SONRAKI:               data = api.get_customer_resources(customer_name or "Boyner", tr)
  ```

**ADIM 2 — Doğrulama:**
- [ ] Backend çalışır durumda: `uvicorn app.main:app --port 8000`
- [ ] Frontend başlat: `python app.py` (port 8050)
- [ ] `http://localhost:8050/` → Executive Dashboard yükleniyor, KPI'lar ve tablolar dolu
- [ ] `http://localhost:8050/datacenters` → DC kartları görünüyor
- [ ] `http://localhost:8050/datacenter/DC11` → DC11 detay sayfası (Intel/Power/Summary tabları)
- [ ] `http://localhost:8050/customer-view` → Boyner müşteri verileri (Summary/Intel/HANA/Backup)
- [ ] Sidebar tarih filtresini değiştir (7D → 30D) → Veriler güncelleniyor (loading süresi artabilir)
- [ ] Custom tarih seçimi yap → Veriler güncelleniyor
- [ ] Backend'i DURDUR → Sayfalar çökmeden fallback (sıfır) değerleriyle render

### ADIM 3: app.py ve query_explorer.py Entegrasyonu

**Hedef:** Ana uygulamayı ve Query Explorer'ı HTTP'ye geçir. Eski scheduler'ı kaldır.

- [ ] `app.py` güncelle:

  **Import değişiklikleri:**
  ```
  SİL:
  from src.services.shared import service
  from src.services.scheduler_service import start_scheduler

  EKLE:
  from src.services import api_client as api
  ```

  **Müşteri listesi (satır 42-44):**
  ```
  ÖNCEKİ:
  _customers = service.get_customer_list()

  SONRAKI:
  _customers = api.get_customer_list()
  ```

  **Scheduler kaldır (satır 265):**
  ```
  SİL: _scheduler = start_scheduler(service)
  ```
  Backend kendi scheduler'ını lifespan içinde çalıştırıyor. Frontend'de scheduler'a GEREK YOK.

- [ ] `src/pages/query_explorer.py` güncelle:

  **Import değişikliği:**
  ```
  ÖNCEKİ (satır 8):     from src.services.shared import service
  SONRAKI:               from src.services import api_client as api
  ```

  **Run callback (satır 218):**
  ```
  ÖNCEKİ:               result = service.execute_registered_query(query_key, params_input or "")
  SONRAKI:               result = api.execute_registered_query(query_key, params_input or "")
  ```

  **`qo.*` çağrıları DEĞİŞMEZ** — local kalıyor (Bölüm B.2 kararı).

**ADIM 3 — Doğrulama:**
- [ ] `python app.py` → Uygulama hatasız başlıyor (scheduler importu yok)
- [ ] `http://localhost:8050/query-explorer` → Query listesi yükleniyor
- [ ] Bir sorgu seç (örn. `nutanix_host_count`) → Metadata görünüyor
- [ ] Params gir (örn. `DC11`) + "Run" tıkla → Sonuç tablosu/değer görünüyor
- [ ] "Edit SQL" tab → SQL düzenlenebiliyor, "Save override" çalışıyor
- [ ] "Add new query" tab → Yeni sorgu eklenebiliyor
- [ ] Sidebar'da müşteri dropdown çalışıyor (Boyner seçili)

### ADIM 4: Temizlik ve Final Doğrulama

**Hedef:** Eski monolitik servis dosyalarını kaldır, son regresyon testlerini çalıştır.

- [ ] Eski dosyaları yeniden adlandır (silme yerine — geri dönüş koruması):
  ```
  src/services/db_service.py      → src/services/_legacy_db_service.py
  src/services/cache_service.py   → src/services/_legacy_cache_service.py
  src/services/scheduler_service.py → src/services/_legacy_scheduler_service.py
  ```

- [ ] `src/services/shared.py` sadeleştir:
  ```
  from src.services import api_client as api
  ```
  (`service` referansı artık hiçbir yerde kullanılmıyor)

- [ ] Import kontrolü — eski import'lar kalmamış olmalı:
  ```
  grep -rn "from src.services.shared import service" src/ --include="*.py"
  → SIFIR sonuç

  grep -rn "from src.services.db_service" src/ --include="*.py"
  → SIFIR sonuç (legacy hariç)

  grep -rn "from src.services.scheduler_service" src/ --include="*.py"
  → SIFIR sonuç (legacy hariç)

  grep -rn "from src.services.cache_service" src/ --include="*.py"
  → SIFIR sonuç (legacy hariç)
  ```

- [ ] Yorum satırı kontrolü:
  ```
  grep -rn "^#" src/services/api_client.py | grep -v "TODO\|FIXME"
  → SIFIR sonuç

  grep -rn '"""' src/services/api_client.py
  → SIFIR sonuç
  ```

**ADIM 4 — Doğrulama (Tam Regresyon):**
- [ ] Backend testleri hâlâ geçiyor: `cd backend && pytest tests/ -v --tb=short` → TÜMÜ PASSED
- [ ] Frontend tüm sayfalar çalışıyor:
  - `/` → Dashboard KPI'ları dolu
  - `/datacenters` → DC kartları mevcut
  - `/datacenter/DC11` → Intel/Power/Summary tabları
  - `/customer-view` → Boyner verileri (4 tab)
  - `/query-explorer` → Sorgu çalıştırma başarılı
- [ ] Tarih filtreleme çalışıyor: 1D, 7D, 30D, Custom
- [ ] Backend durdurulduğunda frontend çökmüyor (fallback ile render)
- [ ] `docker compose up` ile tüm sistem çalışıyor (backend + redis + frontend)

---

## BÖLÜM F: FİLTRE ENTEGRASYONU DETAYI

### F.1 — Mevcut Sidebar → API Akışı

```
SegmentedControl (value="7d")
        │
        ▼
Callback #3 (update_time_range_store)
        │
        ├── preset != "custom" → preset_to_range("7d")
        │                        → {"start": "2026-03-05", "end": "2026-03-11", "preset": "7d"}
        │
        └── DatePicker → {"start": "...", "end": "...", "preset": "custom"}
        │
        ▼
dcc.Store("app-time-range") = tr dict
        │
        ▼
Callback #4 (render_main_content)
        │
        ├── "/" → home.build_overview(tr)
        │           └── api.get_global_dashboard(tr)
        │                   └── GET /api/v1/dashboard/overview?preset=7d
        │
        ├── "/datacenters" → datacenters.build_datacenters(tr)
        │                       └── api.get_all_datacenters_summary(tr)
        │                               └── GET /api/v1/datacenters/summary?preset=7d
        │
        ├── "/datacenter/DC11" → dc_view.build_dc_view("DC11", tr)
        │                           └── api.get_dc_details("DC11", tr)
        │                                   └── GET /api/v1/datacenters/DC11?preset=7d
        │
        └── "/customer-view" → customer_view.build_customer_layout(tr, "Boyner")
                                   └── api.get_customer_resources("Boyner", tr)
                                           └── GET /api/v1/customers/Boyner/resources?preset=7d
```

### F.2 — _build_time_params İç Mantığı

```python
def _build_time_params(tr: dict | None) -> dict[str, str]:
    if not tr:
        return {}
    preset = tr.get("preset")
    if preset and preset in ("1d", "7d", "30d"):
        return {"preset": preset}
    start = tr.get("start")
    end = tr.get("end")
    if start and end:
        return {"start": start, "end": end}
    return {}
```

Bu dict doğrudan `httpx.Client.get(url, params=time_params)` şeklinde kullanılır.
httpx URL'ye `?preset=7d` veya `?start=2026-03-05&end=2026-03-11` olarak ekler.

---

## BÖLÜM G: TAMAMLANMA MATRİSİ

| # | Kriter | Kanıt Tipi |
|---|--------|------------|
| 1 | `api_client.py` oluşturulmuş ve 6 public fonksiyon çalışıyor | Python REPL test çıktısı |
| 2 | Backend kapalıyken tüm fonksiyonlar fallback döner, exception OLMAZ | Python REPL test çıktısı |
| 3 | `home.py` HTTP üzerinden veri çekiyor | Dashboard açılıyor + curl log |
| 4 | `datacenters.py` HTTP üzerinden veri çekiyor | DC grid kartları görünüyor |
| 5 | `dc_view.py` HTTP üzerinden veri çekiyor | DC detay tabları çalışıyor |
| 6 | `customer_view.py` HTTP üzerinden veri çekiyor | Boyner 4 tab verileri mevcut |
| 7 | `query_explorer.py` sorgu çalıştırma HTTP üzerinden | Run → sonuç tablosu |
| 8 | Query Override (save/reset/add) LOCAL çalışıyor | Edit SQL → Save → query_overrides.json güncellendi |
| 9 | Tarih filtreleme (1D/7D/30D/Custom) çalışıyor | Segment tıkla → veriler değişiyor |
| 10 | `start_scheduler` frontend'den kaldırılmış | `grep "start_scheduler" app.py` → SIFIR |
| 11 | Eski `db_service.py` import'u hiçbir aktif dosyada yok | `grep` çıktısı |
| 12 | SIFIR yorum satırı (değişen tüm dosyalarda) | `grep` çıktısı |
| 13 | Backend 329 test hâlâ firesiz geçiyor | `pytest` çıktısı |
| 14 | Backend dizinine SIFIR değişiklik | `git diff backend/` → boş |
| 15 | Docker Compose (backend + redis + frontend) tam çalışıyor | `docker compose up` + tüm sayfalar |
