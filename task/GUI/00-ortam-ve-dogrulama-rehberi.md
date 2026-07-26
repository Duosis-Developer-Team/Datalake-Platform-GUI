# 00 — Ortam, Erişim ve Doğrulama Rehberi

Bu dosya tüm TASK-xx dosyalarının referans aldığı ortak bilgidir.

> **Yol notasyonu:** Öneki olmayan yollar `Datalake-Platform-GUI/` içinden görecelidir
> (örn. `src/pages/dc_view.py`). `<repo-kök>/` öneki `datalake-platform/` çalışma klasörünü
> işaret eder (örn. `<repo-kök>/scripts/`, `<repo-kök>/datalake/`, `<repo-kök>/datalake-platform-knowledge-base/`).

Cursor/Claude Code'a bir madde verirken **bu dosyayı da bağlam olarak ekleyin**.

---

## 1. Ortamlar

| Ortam | Host | Yol | Not |
|-------|------|-----|-----|
| **Test GUI** | `10.134.52.250` (ssh root) | `/opt/Datalake-Platform-GUI` | Tüm değişiklikler önce burada |
| **Prod GUI** | `10.134.52.251` (ssh root) | `/opt/Datalake-Platform-GUI` | `http://10.134.52.251:8050` |
| **Datalake DB (bulutlake)** | `10.134.16.6:5000` | db `bulutlake` | Ham telemetri + discovery |
| **WebUI DB (bulutwebui)** | test: container `bulutistan-webui-db` :5434 | db `bulutwebui`, user `webuiadmin` | GUI konfig tabloları |
| **Redis** | container `bulutistan-redis`, **db 2** | — | `sellable:panels:*`, `crm:inventory_overview:*`, `dl:fecache:*` |

Kimlik bilgileri: `Datalake-Platform-GUI/.env` (lokal) ve `.cursor/local-environment.local.json`.
**Bu dosyalardaki sırları asla commit'lemeyin, prompt'a yapıştırmayın.**

### Servis portları / health

```
:8050  Dash app            :8000  datacenter-api /health
:8001  customer-api        :8002  query-api
:8010  chatbot-api         :8060  admin-api
:8070  crm-engine          :8080  hmdl-api
```

---

## 2. DB'ye nasıl bağlanılır

**Lokal (bulutlake, read-only analiz):**
```bash
PGPASSWORD="$DB_PASS" psql -h 10.134.16.6 -p 5000 -U "$DB_USER" -d bulutlake -c "\dt public.raw_netbackup*"
```

**Test sunucusunda WebUI DB:**
```bash
ssh root@10.134.52.250
cd /opt/Datalake-Platform-GUI
docker compose --profile microservice exec -T webui-db psql -U webuiadmin -d bulutwebui -c "\dt gui_*"
```

**Python (repo scriptleri bu deseni kullanıyor):** `scripts/remote_sql_exec.py`, `scripts/run_sql_check.py`,
`scripts/inspect_crm_db.py`, `scripts/inspect_webui_db.py`.

---

## 3. Şema doğrulama — kod yazmadan önce ÇALIŞTIR

```sql
-- Tablo var mı, kolonları ne?
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema='public' AND table_name = :tablo
ORDER BY ordinal_position;

-- Tablo canlı mı (son veri ne zaman geldi)?
SELECT MAX(collection_timestamp) AS son_veri, COUNT(*) AS satir
FROM public.:tablo;

-- Şüpheli tablo isimlerini ara
SELECT table_name FROM information_schema.tables
WHERE table_schema='public' AND table_name ILIKE '%netbackup%'
ORDER BY 1;
```

> **Uyarı:** `datacenter_metrics` / `cluster_metrics` / `nutanix_cluster_metrics` isimleri
> `*_performance_metrics`'e geçiş sürecinde. Hangi ismin canlı olduğunu **her seferinde** doğrulayın.

---

## 4. "Bu sayının kaynağı ne?" — izleme yöntemi

1. **Ekran → sayfa dosyası:** `src/pages/*.py` (örn. DC View → `dc_view.py`)
2. **Sayfa → API çağrısı:** `src/services/api_client.py` içinde fonksiyonu bul
3. **API → router:** `services/<servis>/app/routers/*.py` içinde endpoint'i bul
4. **Router → service:** `app/services/*_service.py` (hesap burada)
5. **Service → SQL:** `app/db/queries/*.py`
6. **Doküman kısayolu:** `task/query-map/` — 11 dosyada ekran → SQL → formül eşlemesi hazır
   (`01-vmware`, `02-nutanix`, `03-ibm-power`, `04-ibm-storage-san`, `05-sellable-potential`,
   `06-backup-dr`, `07-energy`, `08-zabbix-monitoring`, `09-discovery-inventory`, `10-customer-crm`, `11-query-api`)

---

## 5. Loki (NetBox) baseline nedir

Loki = NetBox envanteri. Platformda **DC listesi ve lokasyon hiyerarşisinin tek doğruluk kaynağı**dır
(ADR-0006). `src/queries/loki.py` ve `services/datacenter-api/app/db/queries/loki.py`:

```sql
-- Aktif DC listesi (parent_id NULL ⇒ satırın kendisi DC)
SELECT DISTINCT CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name
FROM public.loki_locations
WHERE status_value = 'active'
ORDER BY 1;
```

**Baseline mantığı:** bir sayfada DC bazlı bir sayı gösteriliyorsa, o sayının kapsamı
`loki_locations`'tan gelen DC listesiyle **birebir** olmalı. Ham tablolarda DC kolonu yoksa
DC, serbest metinden regex ile çıkarılır — bu, sapmaların ana kaynağıdır:

```python
# services/datacenter-api/app/services/dc_service.py :: _extract_dc_from_text
r'(DC\d+|AZ\d+|ICT\d+|UZ\d+|DH\d+)'   # çıkan kod yalnızca dc_list içindeyse kabul edilir
```

Bilinen özel eşleme: `zabbix_network.py` içinde `parent_name = 'DH3' → 'DC13'`.

**Veri kaynağı erişilebilirliği (HMDL):** `hmdl.collector_target` + `hmdl.collector_check_log`,
`last_check_status='telnet_fail'` ⇒ NiFi proxy hedefe ulaşamıyor.
Rapor: `docs/erisilemeyen-sanallastirma-datasourceleri.md`

---

## 6. Cache katmanları (hangisi nerede)

| Katman | Yer | Anahtar | TTL |
|--------|-----|---------|-----|
| Dash süreç-içi | `src/services/cache_service.py` | serbest | ~20 dk (dict, TTL yok) |
| API in-process + Redis | `services/*/app/core/cache_backend.py` | `dl:fecache:*` | `cache_ttl_seconds` (prod 3600) |
| Inventory overview | `inventory_overview_service.py` | `crm:inventory_overview:{dc\|*}` | `INVENTORY_OVERVIEW_CACHE_TTL` (600) |
| Sellable panel | crm-engine | `sellable:panels:*` + `gui_panel_result_snapshot` | snapshot |
| Permission map | admin | `dl:perm_map:*` | `PERMISSION_MAP_CACHE_TTL_SEC` (300) |

**İlke (bağlayıcı):** TTL ≥ 4 × refresh aralığı, `{key}:last_good` shadow key (TTL ×2),
hata durumunda `X-Cache: stale` başlığıyla eski veri servis edilir. Detay: `docs/CACHE_STRATEGY_COMPARISON.md` §4a.

**Cache temizleme (test/prod):**
```bash
docker exec bulutistan-redis redis-cli -n 2 --scan --pattern "crm:inventory_overview:*" \
  | xargs -r docker exec -i bulutistan-redis redis-cli -n 2 DEL

curl -X POST http://localhost:8000/api/v1/admin/cache/refresh   # datacenter-api (~15 dk)
curl -X POST http://localhost:8001/api/v1/admin/cache/refresh   # customer-api
curl -X POST http://localhost:8070/api/v1/admin/cache/refresh   # crm-engine
curl -X POST http://localhost:8070/api/v1/crm/sellable-potential/refresh
```

---

## 7. Deploy akışı

**Test (`10.134.52.250`):**
```bash
ssh root@10.134.52.250
cd /opt/Datalake-Platform-GUI
git fetch origin && git checkout main && git pull origin main
export APP_BUILD_ID=$(git rev-parse --short HEAD)
./scripts/apply-webui-migrations-docker.sh
docker compose --profile microservice build <değişen-servisler> app
docker compose --profile microservice up -d
```

**Prod promote (`10.134.52.251`):** test ile aynı SHA doğrulandıktan sonra
`<repo-kök>/scripts/deploy_prod_gui_251.py` (fazlar: preflight+backup → pull+migrate+build → cache refresh → health smoke).
Bayraklar: `--preflight-only`, `--skip-build`, `--skip-cache`, `--cache-only`.

**Prod öncesi zorunlu:** `.env` / `.env.local` yedeği + `bulutwebui` ve `bulutauth` dump'ı.
**Prod `.env` asla ezilmez.**

**Doğrulama scriptleri:**
```bash
./scripts/verify-vip-consistency.sh          # CUSTOMER_API_URL=http://localhost:8001
./scripts/verify-netbox-viz-deployment.sh
```

> Tüm `docker compose exec` / migration komutları `--profile microservice` (veya
> `COMPOSE_PROFILES=microservice`) ile çalıştırılmalı — redis profile-gated.

### Migration yolları — ikisi ayrı, karıştırmayın

| Yol | Kapsam | Uygulama |
|-----|--------|----------|
| `Datalake-Platform-GUI/sql/migrations/` | WebUI DB uygulama tabloları (`002_…`, `003_…`) | `./scripts/apply-webui-migrations-docker.sh`, takip: `gui_schema_migrations` |
| `<repo-kök>/datalake/SQL/CRM/migrations/` | CRM service-mapping seed/view (`2026-04-24-gui-crm-service-mapping.sql` vb.) | Aynı script; dosya adlandırması tarih-önekli |

Denetim sorgusu: `datalake/SQL/CRM/audit_crm_service_mapping_gaps.sql`

---

## 8. Her madde için minimum kanıt seti

Bir maddeyi "bitti" saymadan önce şu üçünü dosyaya yazın:

1. **Önce/sonra sayı:** ilgili doğrulama SQL'inin çıktısı (ekran değeri = DB değeri mi?)
2. **API cevabı:** `curl` çıktısı (status + kritik alanlar), soğuk ve sıcak cache ile süre
3. **Smoke:** ilgili sayfada tarayıcı kontrolü + konsol hatası yok + build ID doğru

---

## 9. Faydalı referans dokümanlar

| Konu | Dosya |
|------|-------|
| Ekran → SQL → formül haritası | `task/query-map/*` |
| CRM ürün ↔ altyapı eşleşmesi | `datalake-platform-knowledge-base/wiki/CRM-Inventory-Infra-Matching.md`, ADR-0024 |
| CRM service mapping | `docs/CRM_SERVICE_MAPPING.md`, ADR-0011 |
| Müşteri kimliği | ADR-0008, ADR-0009 |
| Cache | `docs/CACHE_STRATEGY_COMPARISON.md`, ADR-0007, ADR-0015, ADR-0026 |
| Frontend performans | `docs/FRONTEND_PERFORMANCE.md` |
| Loading UX | `docs/LOADING_UX_DESIGN.md` |
| Prod mimari | `docs/PROD_ARCHITECTURE.md` |
| Deploy | `datalake-platform-knowledge-base/raw/test-server-deploy-workflow.md` |
| Erişilemeyen datasource'lar | `docs/erisilemeyen-sanallastirma-datasourceleri.md` |
| Power allocation-only kararı | ADR-0022 |
| Backup politika bazlı UI | ADR-0025, ADR-0026 |
