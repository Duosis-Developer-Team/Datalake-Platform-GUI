# FAZ 5 — Domain Decomposition & Microservice Split

> **Hedef:** Tek parça (Modular Monolith) FastAPI uygulamasını Domain-Driven Design (DDD)
> prensiplerine göre bağımsız mikroservislere parçalamak. Her servis kendi veritabanı
> bağlantısına sahip olacak, bağımsız deploy edilebilecek ve ayrı ölçeklenebilecek.
>
> **Öncül:** FAZ 1-4 %100 tamamlandı. Modüler monolit K8s üzerinde çalışıyor, CI/CD
> pipeline aktif, 329 test firesiz geçiyor, observability stack kurulu.

---

> [!CAUTION]
> ## EXECUTER İÇİN MUTLAK YASAKLAR
>
> 1. **SIFIR YORUM SATIRI KURALI:** Tüm yeni servis kodlarında, Dockerfile'larda, K8s
>    manifest'lerinde ve test dosyalarında tek bir `#` satırı dahi barındırılmayacak.
>
> 2. **VERİ BÜTÜNLÜĞÜ:** Veritabanı parçalanması sırasında mevcut `bulutlake` DB'sindeki
>    HİÇBİR tablo silinmeyecek veya şeması değiştirilmeyecek. Yeni servisler mevcut
>    tablolara READ-ONLY erişim sağlayacak.
>
> 3. **GERİYE UYUMLULUK:** Frontend'in `api_client.py`'si mevcut endpoint imzalarıyla
>    (`/api/v1/dashboard/overview`, `/api/v1/datacenters/summary` vb.) çalışmaya devam
>    edecek. API Gateway bu uyumluluğu şeffaf sağlayacak.
>
> 4. **HER ADIM DOĞRULANMADAN BİR SONRAKİNE GEÇİLMEYECEK.**

---

## BÖLÜM A: MEVCUT MONOLİT ANATOMİSİ

### A.1 — Modüler Monolit Yapısı

```
backend/app/
├── main.py                        ← 67s — FastAPI + lifespan + 4 router mount
├── config.py                      ← 23s — pydantic_settings (DB + Redis + Cache)
├── models/schemas.py              ← 146s — 14 Pydantic response modeli
├── routers/
│   ├── dashboard.py               ← 20s — 1 endpoint: GET /dashboard/overview
│   ├── datacenters.py             ← 31s — 2 endpoint: GET /summary + GET /{dc_code}
│   ├── customers.py               ← 28s — 2 endpoint: GET /customers + GET /{name}/resources
│   └── queries.py                 ← 22s — 1 endpoint: GET /queries/{key}
├── services/
│   ├── db_service.py              ← 471s — ÇEKİRDEK: TEK DatabaseService sınıfı
│   ├── db_service_support.py      ← 248s — aggregate_dc + rebuild_summary + DC_LOCATIONS
│   ├── cache_service.py           ← cache get/set proxy
│   ├── scheduler_service.py       ← APScheduler warm_cache
│   └── query_overrides.py         ← JSON SQL override
├── adapters/
│   ├── base.py                    ← PlatformAdapter abstract class
│   ├── nutanix_adapter.py         ← Nutanix SQL sorguları
│   ├── vmware_adapter.py          ← VMware SQL sorguları
│   ├── ibm_power_adapter.py       ← IBM Power + _DC_CODE_RE regex
│   ├── energy_adapter.py          ← Enerji metrikleri (IBM + vCenter)
│   └── customer_adapter.py        ← 13K — 16 sorgu pipeline
├── core/
│   ├── redis_client.py            ← Redis bağlantı yönetimi
│   ├── cache_backend.py           ← Dual-layer cache (Redis L1 + Memory L2)
│   └── time_filter.py             ← FastAPI TimeFilter dependency
├── db/queries/
│   ├── nutanix.py                 ← 5K SQL tanımları
│   ├── vmware.py                  ← 4K SQL tanımları
│   ├── ibm.py                     ← 4K SQL tanımları
│   ├── energy.py                  ← 3K SQL tanımları
│   ├── customer.py                ← 16K SQL tanımları (en büyük)
│   ├── loki.py                    ← 0.5K — DC listesi (loki_locations)
│   └── registry.py                ← 9K — Sorgu kayıt defteri
└── utils/
    └── time_range.py              ← Tarih aralığı yardımcıları
```

### A.2 — Bağımlılık Grafiği (Dependency Graph)

```
                    ┌─────────────────────────────────────────┐
                    │         DatabaseService (Singleton)       │
                    │    TEK ThreadedConnectionPool (min:2 max:16) │
                    └────────┬───────┬───────┬───────┬────────┘
                             │       │       │       │
                    ┌────────┘       │       │       └────────┐
                    ▼                ▼       ▼                ▼
            ┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐
            │NutanixAdapter│ │VMwareAdpt│ │IBMPwrAdpt│ │EnergyAdapter │
            │  nutanix.py  │ │vmware.py │ │  ibm.py  │ │  energy.py   │
            └──────┬───────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘
                   │              │             │              │
                   └──────────────┼─────────────┼──────────────┘
                                  │             │
                                  ▼             ▼
                          ┌──────────────────────────┐
                          │    _aggregate_dc()        │
                          │  (db_service_support.py)  │
                          │  4 platform → 1 DC dict   │
                          └──────────┬───────────────┘
                                     │
                    ┌────────────────┤
                    ▼                ▼
           ┌──────────────┐  ┌──────────────────┐
           │get_dc_details│  │_fetch_all_batch   │
           │  (single DC) │  │(ThreadPoolExecutor│
           └──────────────┘  │ parallel batch)   │
                             └───────┬──────────┘
                                     │
                    ┌────────────────┤
                    ▼                ▼
           ┌──────────────────┐ ┌───────────────────┐
           │get_all_datacenters│ │get_global_dashboard│
           │    _summary      │ │   (aggregation)    │
           └──────────────────┘ └───────────────────┘

                    ~~ BAĞIMSIZ DALLAR ~~

           ┌──────────────────┐  ┌──────────────────┐
           │CustomerAdapter   │  │execute_registered │
           │  customer.py     │  │    _query         │
           │16 sorgu pipeline │  │ (query_overrides) │
           │  BAĞIMSIZ        │  │   BAĞIMSIZ        │
           └──────────────────┘  └──────────────────┘
```

### A.3 — Veritabanı Tablo-Domain Eşleştirmesi

Mevcut `bulutlake` veritabanındaki tablolar ve hangi domain'e ait oldukları:

| Tablo Grubu | Tablolar | Erişen Adapter | Domain |
|------------|---------|---------------|--------|
| Nutanix | `nutanix_hosts`, `nutanix_vms`, `nutanix_clusters`, `nutanix_storage` | `nutanix_adapter.py` | **Infrastructure** |
| VMware | `vmware_hosts`, `vmware_vms`, `vmware_clusters`, `vmware_datastores` | `vmware_adapter.py` | **Infrastructure** |
| IBM Power | `ibm_hosts`, `ibm_vios`, `ibm_lpars` | `ibm_power_adapter.py` | **Infrastructure** |
| Energy | `ibm_energy`, `vcenter_energy` | `energy_adapter.py` | **Infrastructure** |
| Loki/NetBox | `loki_locations`, `loki_racks`, `loki_devices`, `loki_platforms` | `loki.py` | **Infrastructure** |
| Customer VMware | `vmware_vms` (LIKE filter) | `customer_adapter.py` | **Customer** |
| Customer Nutanix | `nutanix_vms` (LIKE filter) | `customer_adapter.py` | **Customer** |
| Customer IBM | `ibm_lpars` (LIKE filter) | `customer_adapter.py` | **Customer** |
| Customer Veeam | `veeam_sessions`, `veeam_protected_vms` | `customer_adapter.py` | **Customer** |
| Customer Zerto | `zerto_vpgs` | `customer_adapter.py` | **Customer** |
| Customer NetBackup | `netbackup_clients` | `customer_adapter.py` | **Customer** |
| Customer Storage | `ibm_storage_volumes` | `customer_adapter.py` | **Customer** |

### A.4 — Çapraz-Domain Bağımlılık Analizi

| Etkileşim | Detay | Yön |
|-----------|-------|-----|
| `get_global_dashboard` → `get_all_datacenters_summary` | Dashboard, TÜM DC'lerin özetini çekerek agregasyon yapıyor | Dashboard → Datacenter |
| `get_all_datacenters_summary` → `_fetch_all_batch` | Batch işlem 4 adapter'ı paralel çalıştırıyor | Datacenter → Platform Adapters |
| `customer_adapter` → `nutanix_vms`, `vmware_vms`, `ibm_lpars` | Customer sorguları platform tablolarını LIKE ile filtreliyor | Customer → Infrastructure |
| `_load_dc_list` → `loki_locations` | DC listesi Loki/NetBox'tan çekiliyor | Core → Loki/NetBox |
| `aggregate_dc` → `DC_LOCATIONS` dict | Statik DC → Lokasyon eşleştirmesi | Core → Static data |

> [!IMPORTANT]
> ## ÇAPRAZ-DOMAIN BAĞIMLILIK KRİTİK BULGU
>
> `customer_adapter.py` müşteri VM'lerini bulmak için `nutanix_vms`, `vmware_vms` ve
> `ibm_lpars` tablolarını DOĞRUDAN sorguluyor. Bu tablolar Infrastructure domain'ine ait.
>
> **Fiziksel DB ayrımı yapılırsa** Customer servisi Infrastructure DB'sine de erişmek
> zorunda kalır — bu anti-pattern'dir.
>
> **Çözüm A (Önerilen):** Mantıksal ayrım (Schema-per-Service) — tüm servisler aynı
> PostgreSQL instance'ını kullanır ama farklı schema veya view'lar üzerinden.
>
> **Çözüm B:** Customer servisine ihtiyaç duyduğu veriyi Infrastructure servisi bir
> internal API ile sunar (ek latency + karmaşıklık).
>
> **KARAR:** Çözüm A — Schema-per-Service. PostgreSQL'de `infra` ve `customer` schema'ları
> oluşturulacak, cross-schema view'lar ile erişim sağlanacak.

---

## BÖLÜM B: DOMAIN SINIRLARININ BELİRLENMESİ

### B.1 — Bounded Context Haritası

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Bulutistan Mikroservis Ekosistemi                 │
│                                                                       │
│  ┌───────────────────────────┐    ┌──────────────────────────────┐   │
│  │  INFRASTRUCTURE SERVICE   │    │     CUSTOMER SERVICE          │   │
│  │  (datacenter-api)         │    │     (customer-api)            │   │
│  │  ─────────────────────── │    │     ──────────────────────── │   │
│  │  Router:                  │    │     Router:                   │   │
│  │   GET /datacenters/summary│    │      GET /customers           │   │
│  │   GET /datacenters/{dc}   │    │      GET /customers/{name}/   │   │
│  │   GET /dashboard/overview │    │          resources             │   │
│  │  ─────────────────────── │    │     ──────────────────────── │   │
│  │  Adapters:                │    │     Adapter:                  │   │
│  │   NutanixAdapter          │    │      CustomerAdapter          │   │
│  │   VMwareAdapter           │    │     ──────────────────────── │   │
│  │   IBMPowerAdapter         │    │     Queries: customer.py      │   │
│  │   EnergyAdapter           │    │     Tables: veeam_*, zerto_*, │   │
│  │  ─────────────────────── │    │       netbackup_*, storage_*  │   │
│  │  Support:                 │    │     + cross-schema views:     │   │
│  │   aggregate_dc            │    │       nutanix_vms, vmware_vms │   │
│  │   rebuild_summary         │    │       ibm_lpars               │   │
│  │  ─────────────────────── │    │                               │   │
│  │  Queries: nutanix.py,     │    │                               │   │
│  │   vmware.py, ibm.py,      │    │                               │   │
│  │   energy.py, loki.py      │    │                               │   │
│  │  Tables: nutanix_*, vmware_*│   │                               │   │
│  │   ibm_*, *_energy, loki_* │    │                               │   │
│  └───────────────────────────┘    └──────────────────────────────┘   │
│                                                                       │
│  ┌───────────────────────────┐    ┌──────────────────────────────┐   │
│  │   QUERY SERVICE            │    │     SHARED LIBRARIES          │   │
│  │   (query-api)              │    │     (bulutistan-common)       │   │
│  │   ──────────────────────  │    │     ──────────────────────── │   │
│  │   Router:                  │    │     time_range.py             │   │
│  │    GET /queries/{key}      │    │     time_filter.py            │   │
│  │   ──────────────────────  │    │     cache_backend.py          │   │
│  │   query_overrides.py       │    │     redis_client.py           │   │
│  │   registry.py              │    │     cache_service.py          │   │
│  │   TÜM SQL sorguları        │    │     config.py (base)          │   │
│  └───────────────────────────┘    └──────────────────────────────┘   │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    API GATEWAY (NGINX Ingress)                 │    │
│  │   /api/v1/datacenters/* → datacenter-api                      │    │
│  │   /api/v1/dashboard/*   → datacenter-api                      │    │
│  │   /api/v1/customers/*   → customer-api                        │    │
│  │   /api/v1/queries/*     → query-api                           │    │
│  │   /health, /ready       → datacenter-api (primary)            │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### B.2 — Servis Sorumluluk Dağılımı

| Servis | Sorumluluk | Mevcut Kaynaklar | Bağımsız Deploy | Ölçekleme |
|--------|-----------|-----------------|----------------|-----------|
| **datacenter-api** | DC listeleme, detay, dashboard, platform metrikleri, enerji | `datacenters.py`, `dashboard.py` routers, nutanix/vmware/ibm/energy adapters, `aggregate_dc`, `rebuild_summary`, scheduler | ✅ Evet | HPA CPU/Memory |
| **customer-api** | Müşteri listesi, müşteri kaynakları (16 sorgu pipeline) | `customers.py` router, `customer_adapter.py` | ✅ Evet | HPA CPU |
| **query-api** | Ad-hoc sorgu çalıştırma, SQL override CRUD | `queries.py` router, `query_overrides.py`, `registry.py` | ✅ Evet | Sabit 1-2 pod |
| **bulutistan-common** | Paylaşılan kütüphane (pip paketi veya git submodule) | `time_range.py`, `time_filter.py`, `cache_backend.py`, `redis_client.py`, `cache_service.py` | N/A (kütüphane) | N/A |

### B.3 — Domain'e Göre Endpoint Dağılımı

| Mevcut Endpoint | Hedef Servis | Port |
|----------------|-------------|------|
| `GET /api/v1/dashboard/overview` | `datacenter-api` | 8001 |
| `GET /api/v1/datacenters/summary` | `datacenter-api` | 8001 |
| `GET /api/v1/datacenters/{dc_code}` | `datacenter-api` | 8001 |
| `GET /api/v1/customers` | `customer-api` | 8002 |
| `GET /api/v1/customers/{name}/resources` | `customer-api` | 8002 |
| `GET /api/v1/queries/{key}` | `query-api` | 8003 |
| `GET /health` | tüm servisler (kendi health'i) | her biri |
| `GET /ready` | tüm servisler (kendi ready'si) | her biri |

---

## BÖLÜM C: VERİTABANI PARÇALANMASI (Schema-per-Service)

### C.1 — Strateji: Mantıksal Ayrım (Logical Separation)

**Fiziksel ayrım yerine mantıksal ayrım seçilmesinin sebepleri:**

1. Customer servisi `nutanix_vms`, `vmware_vms`, `ibm_lpars` tablolarını LIKE filtresiyle
   sorguluyor — bu tablolar Infrastructure domain'ine ait
2. Fiziksel ayrımda cross-database JOIN imkansız → ek API çağrısı + latency
3. Tek PostgreSQL instance'ı yönetim basitliği sağlıyor
4. İleride fiziksel ayrıma geçiş mantıksal ayrımdan çok daha kolay

### C.2 — Schema Haritası

```
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL: bulutlake                      │
│                                                               │
│  ┌──────────────────────┐  ┌──────────────────────────────┐  │
│  │    Schema: infra       │  │      Schema: customer         │  │
│  │    ─────────────────  │  │      ──────────────────────── │  │
│  │    nutanix_hosts       │  │      veeam_sessions           │  │
│  │    nutanix_vms         │  │      veeam_protected_vms      │  │
│  │    nutanix_clusters    │  │      zerto_vpgs               │  │
│  │    nutanix_storage     │  │      netbackup_clients        │  │
│  │    vmware_hosts        │  │      ibm_storage_volumes      │  │
│  │    vmware_vms          │  │      ─────────────────────── │  │
│  │    vmware_clusters     │  │      CROSS-SCHEMA VIEWS:      │  │
│  │    vmware_datastores   │  │       v_customer_nutanix_vms  │  │
│  │    ibm_hosts           │  │       v_customer_vmware_vms   │  │
│  │    ibm_vios            │  │       v_customer_ibm_lpars    │  │
│  │    ibm_lpars           │  │                               │  │
│  │    ibm_energy          │  └──────────────────────────────┘  │
│  │    vcenter_energy      │                                     │
│  │    loki_locations      │  ┌──────────────────────────────┐  │
│  │    loki_racks          │  │      Schema: query             │  │
│  │    loki_devices        │  │       (registry.py erişimi)    │  │
│  │    loki_platforms      │  │       HERHANGİ BİR tabloyu     │  │
│  │    loki_virtual_machines│  │       READ-ONLY sorgulayabilir │  │
│  └──────────────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### C.3 — Cross-Schema View Tanımları

```sql
CREATE SCHEMA IF NOT EXISTS customer;

CREATE OR REPLACE VIEW customer.v_customer_nutanix_vms AS
SELECT vm_name, num_vcpus, memory_capacity_mib, storage_capacity_bytes, cluster_name
FROM public.nutanix_vms;

CREATE OR REPLACE VIEW customer.v_customer_vmware_vms AS
SELECT vm_name, num_cpu, memory_size_mib, committed_storage, host_name
FROM public.vmware_vms;

CREATE OR REPLACE VIEW customer.v_customer_ibm_lpars AS
SELECT lpar_name, curr_procs, curr_mem, state, managed_system
FROM public.ibm_lpars;
```

### C.4 — DB Kullanıcı İzolasyonu

| Servis | DB Kullanıcı | Erişim Kapsamı |
|--------|-------------|---------------|
| `datacenter-api` | `infra_svc` | `public.*` tablolar (mevcut tüm tablolar) — READ ONLY |
| `customer-api` | `customer_svc` | `customer.*` + `customer.v_customer_*` views — READ ONLY |
| `query-api` | `query_svc` | `public.*` — READ ONLY (ad-hoc sorgular için) |

> [!WARNING]
> **Migration sırası kritik:** Önce view'lar oluşturulacak, sonra yeni DB kullanıcıları,
> en son servis kodları değiştirilecek. View'ları oluşturmadan önce mevcut tablolar
> bozulmadı mı kontrol edilecek.

---

## BÖLÜM D: KOD PARÇALANMASI (Code Split)

### D.1 — Proje Dizin Yapısı (Hedef)

```
Datalake-Platform-GUI/
├── services/
│   ├── datacenter-api/              ← [YENİ] Bağımsız FastAPI projesi
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── routers/
│   │   │   │   ├── datacenters.py
│   │   │   │   └── dashboard.py
│   │   │   ├── adapters/
│   │   │   │   ├── base.py
│   │   │   │   ├── nutanix_adapter.py
│   │   │   │   ├── vmware_adapter.py
│   │   │   │   ├── ibm_power_adapter.py
│   │   │   │   └── energy_adapter.py
│   │   │   ├── services/
│   │   │   │   ├── dc_service.py      ← db_service.py'den DC metotları
│   │   │   │   ├── dc_support.py      ← aggregate_dc + rebuild_summary
│   │   │   │   ├── cache_service.py
│   │   │   │   └── scheduler_service.py
│   │   │   ├── db/queries/
│   │   │   │   ├── nutanix.py
│   │   │   │   ├── vmware.py
│   │   │   │   ├── ibm.py
│   │   │   │   ├── energy.py
│   │   │   │   └── loki.py
│   │   │   ├── core/                  ← bulutistan-common'dan
│   │   │   │   ├── redis_client.py
│   │   │   │   ├── cache_backend.py
│   │   │   │   └── time_filter.py
│   │   │   ├── models/schemas.py
│   │   │   └── utils/time_range.py
│   │   └── tests/
│   │
│   ├── customer-api/                  ← [YENİ] Bağımsız FastAPI projesi
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── routers/customers.py
│   │   │   ├── adapters/
│   │   │   │   └── customer_adapter.py
│   │   │   ├── services/
│   │   │   │   ├── customer_service.py
│   │   │   │   └── cache_service.py
│   │   │   ├── db/queries/customer.py
│   │   │   ├── core/                  ← bulutistan-common'dan
│   │   │   │   ├── redis_client.py
│   │   │   │   ├── cache_backend.py
│   │   │   │   └── time_filter.py
│   │   │   ├── models/schemas.py
│   │   │   └── utils/time_range.py
│   │   └── tests/
│   │
│   └── query-api/                     ← [YENİ] Bağımsız FastAPI projesi
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── app/
│       │   ├── main.py
│       │   ├── config.py
│       │   ├── routers/queries.py
│       │   ├── services/
│       │   │   └── query_service.py
│       │   ├── db/queries/registry.py
│       │   ├── models/schemas.py
│       │   └── utils/time_range.py
│       └── tests/
│
├── backend/                           ← [ARCHIVE] Eski monolith (read-only referans)
├── k8s/
│   ├── datacenter-api/                ← [YENİ] K8s manifestoları
│   ├── customer-api/                  ← [YENİ] K8s manifestoları
│   ├── query-api/                     ← [YENİ] K8s manifestoları
│   ├── redis/                         ← mevcut
│   ├── frontend/                      ← mevcut
│   └── ingress.yaml                   ← [MODIFY] Path routing güncelleme
└── src/                               ← Frontend (api_client.py değişmez)
```

### D.2 — Paylaşılan Kod Stratejisi

**Seçenek A (Önerilen — Basitlik):** Kopyala ve Yapıştır (Copy & Own)
- Her servis `core/`, `utils/` dosyalarının kendi kopyasını barındırır
- Bağımsızlık garantisi — sürüm çakışması riski yok
- Küçük proje (<5 servis) için ideal

**Seçenek B (Gelecek):** Git Subtree veya Private PyPI Paketi
- `bulutistan-common` adlı paylaşılan kütüphane
- 10+ servis olduğunda mantıklı — şu an aşırı mühendislik (over-engineering)

**KARAR:** Her servis ortak kodun kendi kopyasını tutar. Gelecekte büyüme olursa
paylaşılan pakete geçilir.

### D.3 — db_service.py Parçalanma Haritası

Mevcut `DatabaseService` sınıfı (471 satır, 26 metot) üç parçaya ayrılacak:

| Mevcut Metot (db_service.py) | Hedef Servis | Yeni Dosya | Satır Aralığı |
|------------------------------|-------------|-----------|---------------|
| `__init__`, `_init_pool`, `_get_connection` | datacenter-api | `dc_service.py` | 29-68 |
| `_run_value`, `_run_row`, `_run_rows` | datacenter-api | `dc_service.py` | 70-109 |
| `_load_dc_list` | datacenter-api | `dc_service.py` | 160-178 |
| `get_dc_details` | datacenter-api | `dc_service.py` | 180-222 |
| `_fetch_all_batch` | datacenter-api | `dc_service.py` | 224-375 |
| `get_all_datacenters_summary` | datacenter-api | `dc_service.py` | 377-383 |
| `_rebuild_summary` | datacenter-api | `dc_support.py` | 385-386 |
| `get_global_overview` | datacenter-api | `dc_service.py` | 388-404 |
| `get_global_dashboard` | datacenter-api | `dc_service.py` | 406-417 |
| `warm_cache`, `warm_additional_ranges`, `refresh_all_data` | datacenter-api | `dc_service.py` | 433-466 |
| `dc_list` (property) | datacenter-api | `dc_service.py` | 468-470 |
| `get_customer_resources` | customer-api | `customer_service.py` | 419-428 |
| `get_customer_list` | customer-api | `customer_service.py` | 430-431 |
| `_prepare_params` | query-api | `query_service.py` | 111-123 |
| `execute_registered_query` | query-api | `query_service.py` | 125-158 |

### D.4 — Servis İç İletişim (Inter-Service Communication)

```
┌─────────────────┐         ┌─────────────────┐
│ datacenter-api  │────X────│  customer-api   │
│                 │         │                 │
│ Birbirine HTTP  │         │ DOĞRUDAN DB'den │
│ çağrısı YAPMAZ  │         │ view üzerinden  │
│                 │         │ infra verisi    │
└────────┬────────┘         └────────┬────────┘
         │                           │
         │   Aynı PostgreSQL         │
         └───────────┬───────────────┘
                     ▼
              ┌──────────────┐
              │  bulutlake   │
              │  PostgreSQL  │
              └──────────────┘
```

**Servisler arası HTTP çağrısı YOK.** Tüm veri erişimi doğrudan veritabanı üzerinden
(kendi schema/view'ları ile). Bu basitliği korur ve latency eklemez.

---

## BÖLÜM E: API GATEWAY / BFF (Backend for Frontend)

### E.1 — Gateway Stratejisi: NGINX Ingress Path Routing

Mevcut FAZ 4'te oluşturulan Ingress yapısı genişletilecek. Yeni bir gateway servisi
yazmak yerine NGINX Ingress kuralları ile path-based routing yapılacak.

**Sebep:** Proje 3 servisten oluşuyor — ayrı bir API gateway servisi yazmak bu ölçekte
over-engineering. NGINX Ingress zaten bunu ücretsiz sağlıyor.

### E.2 — Ingress Routing Güncellemesi

##### [MODIFY] `k8s/ingress.yaml`

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
          - path: /api/v1/datacenters
            pathType: Prefix
            backend:
              service:
                name: bulutistan-datacenter-api
                port:
                  number: 80
          - path: /api/v1/dashboard
            pathType: Prefix
            backend:
              service:
                name: bulutistan-datacenter-api
                port:
                  number: 80
          - path: /api/v1/customers
            pathType: Prefix
            backend:
              service:
                name: bulutistan-customer-api
                port:
                  number: 80
          - path: /api/v1/queries
            pathType: Prefix
            backend:
              service:
                name: bulutistan-query-api
                port:
                  number: 80
          - path: /health
            pathType: Exact
            backend:
              service:
                name: bulutistan-datacenter-api
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

### E.3 — Frontend Uyumluluğu

Frontend'in `api_client.py` dosyası **HİÇBİR DEĞİŞİKLİK GEREKTİRMEZ** çünkü:

| Mevcut api_client.py çağrısı | Ingress yönlendirmesi | Sonuç |
|-----------------------------|----------------------|-------|
| `GET {BASE}/api/v1/dashboard/overview` | → `datacenter-api` | ✅ Aynı response |
| `GET {BASE}/api/v1/datacenters/summary` | → `datacenter-api` | ✅ Aynı response |
| `GET {BASE}/api/v1/datacenters/{dc}` | → `datacenter-api` | ✅ Aynı response |
| `GET {BASE}/api/v1/customers` | → `customer-api` | ✅ Aynı response |
| `GET {BASE}/api/v1/customers/{n}/resources` | → `customer-api` | ✅ Aynı response |
| `GET {BASE}/api/v1/queries/{key}` | → `query-api` | ✅ Aynı response |

**SIFIR frontend değişikliği.** API Gateway şeffaf yönlendirme sağlar.

---

## BÖLÜM F: KADEMELİ İCRA PLANI (BÖL VE YÖNET)

### ADIM 1: Veritabanı Hazırlığı (Risk: SIFIR — Ek yapı, mevcut bozulmaz)

- [ ] PostgreSQL'de `infra` ve `customer` schema'ları oluştur
- [ ] Cross-schema view'ları oluştur (`v_customer_nutanix_vms`, `v_customer_vmware_vms`, `v_customer_ibm_lpars`)
- [ ] Yeni DB kullanıcıları oluştur: `infra_svc`, `customer_svc`, `query_svc`
- [ ] Her kullanıcıya sadece kendi schema'sına READ erişimi ver
- [ ] Mevcut `datalakeui` kullanıcısı ve tabloları KESİNLİKLE bozulmadan kalacak
- [ ] Test: View'lar üzerinden sorgu çalıştırarak veri doğrulaması yap

**Doğrulama:**
- [ ] `SELECT * FROM customer.v_customer_nutanix_vms LIMIT 5` → veri dönüyor
- [ ] `SELECT * FROM customer.v_customer_vmware_vms LIMIT 5` → veri dönüyor
- [ ] Mevcut monolit backend hâlâ sorunsuz çalışıyor (329 test geçiyor)

### ADIM 2: datacenter-api Servisini Oluştur (İlk ve En Kritik)

- [ ] `services/datacenter-api/` dizin yapısını oluştur
- [ ] `db_service.py`'den DC metotlarını `dc_service.py`'ye taşı (D.3 tablosuna göre)
- [ ] `db_service_support.py`'yi `dc_support.py` olarak kopyala
- [ ] Adapter'ları kopyala: `nutanix_adapter.py`, `vmware_adapter.py`, `ibm_power_adapter.py`, `energy_adapter.py`
- [ ] Query dosyalarını kopyala: `nutanix.py`, `vmware.py`, `ibm.py`, `energy.py`, `loki.py`
- [ ] `core/` dosyalarını kopyala: `redis_client.py`, `cache_backend.py`, `time_filter.py`
- [ ] `main.py` oluştur: lifespan + router mount + health/ready
- [ ] `Dockerfile` oluştur (backend Dockerfile'ı temel al — multi-stage)
- [ ] `requirements.txt` oluştur
- [ ] Mevcut testleri adapte et (sadece DC/dashboard testleri)
- [ ] K8s manifestoları: `k8s/datacenter-api/deployment.yaml`, `service.yaml`, `configmap.yaml`, `hpa.yaml`

**Doğrulama:**
- [ ] `docker build -t bulutistan-datacenter-api services/datacenter-api/` → başarılı
- [ ] Container'ı çalıştır, `curl /api/v1/datacenters/summary?preset=7d` → JSON response
- [ ] `curl /api/v1/dashboard/overview?preset=7d` → dashboard JSON
- [ ] `curl /health` → `{"status": "ok"}`
- [ ] Testler geçiyor: `cd services/datacenter-api && pytest tests/ -v`

### ADIM 3: customer-api ve query-api Servislerini Oluştur

**customer-api:**
- [ ] `services/customer-api/` dizin yapısını oluştur
- [ ] `customer_adapter.py`'yi kopyala, SQL sorgularını `customer.v_customer_*` view'larına yönlendir
- [ ] `customer_service.py` oluştur (`get_customer_resources`, `get_customer_list`)
- [ ] `main.py`, `Dockerfile`, `requirements.txt` oluştur
- [ ] K8s manifestoları oluştur

**query-api:**
- [ ] `services/query-api/` dizin yapısını oluştur
- [ ] `query_service.py` oluştur (`execute_registered_query`, `_prepare_params`)
- [ ] `registry.py` ve `query_overrides.py` kopyala
- [ ] `main.py`, `Dockerfile`, `requirements.txt` oluştur
- [ ] K8s manifestoları oluştur

**Doğrulama:**
- [ ] `docker build -t bulutistan-customer-api services/customer-api/` → başarılı
- [ ] `curl /api/v1/customers` → `["Boyner"]`
- [ ] `curl /api/v1/customers/Boyner/resources?preset=7d` → resource JSON
- [ ] `docker build -t bulutistan-query-api services/query-api/` → başarılı
- [ ] `curl /api/v1/queries/nutanix_host_count?params=DC11` → sonuç

### ADIM 4: Ingress Güncelleme, Integration Test ve Cutover

- [ ] `k8s/ingress.yaml` güncelle (Bölüm E.2'deki yeni routing)
- [ ] 3 servisi K8s'e deploy et:
  ```
  kubectl apply -f k8s/datacenter-api/
  kubectl apply -f k8s/customer-api/
  kubectl apply -f k8s/query-api/
  ```
- [ ] Ingress'i güncelle: `kubectl apply -f k8s/ingress.yaml`
- [ ] Frontend'i değiştirmeden tüm sayfaları test et
- [ ] Eski `backend/` deployment'ını scale-to-zero yap (silme, sadece 0 replica)
- [ ] CI/CD pipeline'ı güncelle: 3 servis için ayrı build job'ları

**Doğrulama (TAM REGRESYON):**
- [ ] Frontend tüm sayfalar çalışıyor (/, /datacenters, /datacenter/DC11, /customer-view, /query-explorer)
- [ ] Tarih filtreleme çalışıyor (1D, 7D, 30D, Custom)
- [ ] Her servisin kendi `/health` endpoint'i 200 dönüyor
- [ ] HPA'lar aktif: `kubectl get hpa` → 3 servis listeleniyor
- [ ] Frontend `api_client.py`'de SIFIR değişiklik yapılmış (`git diff src/services/api_client.py` → boş)

---

## BÖLÜM G: YENİ MİKROSERVİS MİMARİ ŞEMASI

```
                            ┌──────────────────┐
                            │  NGINX Ingress    │
                            │  (Path Routing)   │
                            └───┬──────┬──────┬─┘
                                │      │      │
                    ┌───────────┘      │      └───────────┐
                    ▼                  ▼                  ▼
       ┌────────────────────┐ ┌──────────────────┐ ┌──────────────┐
       │  datacenter-api    │ │  customer-api    │ │  query-api   │
       │  ───────────────── │ │  ────────────── │ │  ─────────── │
       │  port: 8001        │ │  port: 8002      │ │  port: 8003  │
       │  replicas: 2-8     │ │  replicas: 1-4   │ │  replicas: 1 │
       │  HPA: CPU %70      │ │  HPA: CPU %70    │ │  statik      │
       │  ───────────────── │ │  ────────────── │ │  ─────────── │
       │  /datacenters/*    │ │  /customers/*    │ │  /queries/*  │
       │  /dashboard/*      │ │                  │ │              │
       │  ───────────────── │ │  ────────────── │ │  ─────────── │
       │  NutanixAdapter    │ │  CustomerAdapter │ │  registry.py │
       │  VMwareAdapter     │ │  (16 query)      │ │  overrides   │
       │  IBMPowerAdapter   │ │                  │ │              │
       │  EnergyAdapter     │ │                  │ │              │
       │  scheduler         │ │                  │ │              │
       └────────┬───────────┘ └────────┬─────────┘ └──────┬───────┘
                │                      │                   │
                │    ┌─────────────────┤                   │
                │    │                 │                   │
                ▼    ▼                 ▼                   ▼
       ┌──────────────┐      ┌──────────────┐     ┌──────────────┐
       │   Redis       │      │  PostgreSQL   │     │  PostgreSQL  │
       │  (Paylaşılan) │      │   bulutlake   │     │  bulutlake   │
       │   ClusterIP   │      │ ──────────── │     │ (aynı DB)    │
       └──────────────┘      │ Schema: infra │     └──────────────┘
                              │ Schema:customer│
                              │ public (query) │
                              └──────────────┘
```

---

## BÖLÜM H: TAMAMLANMA MATRİSİ

| # | Kriter | Kanıt Tipi | Adım |
|---|--------|------------|------|
| 1 | PostgreSQL schema'ları oluşturulmuş (infra, customer) | `\dn` çıktısı | 1 |
| 2 | Cross-schema view'lar çalışıyor | `SELECT` sonuçları | 1 |
| 3 | Mevcut 329 test HÂLÂ geçiyor (monolit bozulmadı) | `pytest` çıktısı | 1 |
| 4 | `datacenter-api` bağımsız ayağa kalkıyor | `docker run` + `curl /health` | 2 |
| 5 | `datacenter-api` dashboard ve DC endpoint'leri çalışıyor | `curl` çıktıları | 2 |
| 6 | `datacenter-api` testleri geçiyor | `pytest` çıktısı | 2 |
| 7 | `customer-api` bağımsız ayağa kalkıyor | `docker run` + `curl /health` | 3 |
| 8 | `customer-api` müşteri endpoint'leri çalışıyor | `curl` çıktıları | 3 |
| 9 | `query-api` bağımsız ayağa kalkıyor ve sorgu çalıştırabiliyor | `curl` çıktısı | 3 |
| 10 | 3 servis K8s'te RUNNING | `kubectl get pods` | 4 |
| 11 | Ingress path routing 3 servise doğru yönlendiriyor | `curl` çıktıları | 4 |
| 12 | Frontend TÜM sayfalar çalışıyor (SIFIR frontend değişikliği) | UI test | 4 |
| 13 | `api_client.py`'de SIFIR satır değişikliği | `git diff` çıktısı | 4 |
| 14 | Her servisin kendi HPA'sı aktif | `kubectl get hpa` | 4 |
| 15 | CI/CD pipeline 3 servis için ayrı build yapıyor | GitHub Actions çıktısı | 4 |
| 16 | Eski backend deployment scale-to-zero (arşiv) | `kubectl get deploy` | 4 |
| 17 | Tüm yeni dosyalarda SIFIR `#` satırı | `grep` çıktısı | ALL |
