# Neden 17 cache fix tutmadı — ve 18. denemenin şartları

*Kaynak: `origin/development` (= `main`) çalışan ağacı, canlı docker-compose stack, prod datalake DB (10.134.16.200/bulutlake) ölçümleri. Her iddia file:line ile bağlıdır.*

---

## 1. Kısa cevap

Cache sorunu 17 fix'i atlattı çünkü **17 fix'in hiçbiri sorunun bulunduğu katmana dokunmadı.** Üç ölçülmüş gerçek:

1. **`cache_get()` 24 saat boyunca `None` dönemiyor.** `services/customer-api/app/core/cache_backend.py:107-112` primary miss'te `:last_good` shadow'una (86400s, `:26`, `:141`) sessizce düşüyor; `cache_run_singleflight` tam olarak bu çağrıyı miss testi olarak kullanıyor (`:246`, `:263`). Canlı ölçüm: **`factory()` 0 kez çağrıldı.** customer-api'deki her warm/VIP toggle/6h batch kendi gölgesini okuyup "ok" logluyor.
2. **`warm_common()` hiçbir key'i yenilemiyor.** Ölçüm: tam bir cycle **0.3 saniyede** bitti, `stats={'home':True,'dc_avail_sla':2,'customer_view':1,'unmapped':True,'network':6}` raporladı, **refetch edilen key sayısı = 0**. Warm, ordinary getter'ları çağırıyor, onlar da `src/services/api_client.py:568`'deki `_is_fresh` kapısına takılıyor. `app_background_warm.py` içinde `force_refresh` yok.
3. **pg_trgm index'i hiç uygulanmadı** — ve "DBA/superuser gerekiyor" gerekçesi yanlış. Prod DB'de `pg_trgm` extension yok, hedef 3 GIN index yok, tek bir `vmname ILIKE '%x%'` statement'ı **7.26 saniye** sürüyor (44 statement var). `pg_trgm` **trusted** extension, `bulutlake` role'ünün `CREATE` yetkisi var; `CREATE EXTENSION` app credential'ıyla çalıştırıldı ve rollback edildi.

Yani: root perf fix hiç uygulanmadı, warm dekoratif, backend cache'i asla recompute etmiyor — ve 17 fix bunların üzerinde TTL sabiti ayarladı.

---

## 2. Desen analizi

### 2.1 Tekrarlayan dört desen

**Desen A — "N+1 fix, N'i tamir etmek için yazıldı."** `crm-zero-downtime-cache` (2026-06-04) up-front invalidation'ı kaldırdı; **74 dakika sonra** `crm-cache-hit-recompute-fix` merge edildi çünkü refresh job'ı artık kendi cache'ini okuyup no-op olmuştu. Kimse altta yatan tasarımı yeniden türetmedi.

**Desen B — aynı branch, beş saat arayla, birbirini iptal eden iki commit.** `perf/shared-cache-fresh` item 2.2 (`da42f236`) "asla stale serve etme" kuralını koydu; aynı branch'te GAP1.1 (`87633152`) `_wait_for_shared_result`'ı ekledi (`api_client.py:547-556, 590-594`) ve **stale key zaten oradaysa anında stale dönüyor**, freshness kontrolü olmadan. İki test de yeşil: `tests/test_api_client_no_stale.py` sadece non-empty payload kullanıyor, `tests/test_api_client_stale_on_empty_fetch.py` zıt spec'i encode ediyor.

**Desen C — düzeltme, guard silinerek yapıldı.** "Stale serve et" ihtiyacı `src/utils/datacenters_virt_sellable.py`'de **`cache_key == tr_key` guard'ı silinerek** karşılandı. Bugün `:241-245` değeri `dc_id in cache_snapshot` ile okuyor, tr_key'e hiç bakmıyor; `cache_complete` sadece spinner'ı kontrol ediyor (`:248`). Sonuç: görünür geçici boşluk → **görünmez kalıcı yanlış değer.**

**Desen D — sonraki fix, öncekini sessizce silahsızlandırdı.** `trigger_customer_view_warm` self-heal'i sadece payload'da `totals` yoksa ateşleniyor (`src/pages/customer_view.py:2888-2892`). `_prefer_stale_over_empty_fetch` (`api_client.py:528-543`, 7 gün sonra) empty payload'ı tasarım gereği nadir hale getirdi. Self-heal artık hiç çalışmıyor. İki fix, iki yeşil test, hiçbiri diğerinden haberdar değil.

### 2.2 Tablo

| Branch | Tarih | Hedeflenen | Scope | Bugünkü durum |
|---|---|---|---|---|
| `cache-optimization-customer-datacenter` | 04-03 | stampede, TTL uyumsuzluğu | subsystem | **weakened** — singleflight sağlam; per-key `ttl` memory tier'da düşürülüyor (`cache_backend.py:19-22, 151`); TTL'ler `a7f97ed9` ile geri yükseltildi; dc-api hâlâ 1200 (`datacenter-api/app/config.py:15`) |
| `global-view-cache` | 05-05 | Global View yavaş, rack tıklaması kayboluyor | systemic | **weakened** — thread-local client + `_FigureCache` doğru; cache-first early return 5 commit sonra geri alındı; LRU fix'i RedisBackend altında **çalışmıyor** |
| `settings-redis-cache-refresh` | 05-05 | manuel escape hatch | subsystem | **weakened** — tek buton, üç farklı semantik (`datacenter-api/app/routers/admin_cache.py:25` flush'lıyor, diğer ikisi flush'lamıyor) |
| `crm-sellable-cache-tier2` | 05-31 | restart sonrası 0 TL | systemic | **weakened** — Tier-2 hiç expire olmuyor; prewarm read path'in yarattığı key'lerin alt kümesini kapsıyor |
| `crm-engine-redis-first-bugfix` | 06-04 | LPAR full scan | subsystem | **intact** — ama üçüncü bir kaynak-of-truth ekledi (Redis vs SQL vs span±1 key) |
| `crm-zero-downtime-cache` | 06-04 | recompute sırasında boş sayfa | systemic | **intact** — server yarısı doğru; GUI yarısı `tr_key` guard'ını sildi (C9) |
| `crm-cache-hit-recompute-fix` | 06-04 | bir üstteki fix'in yarattığı 0 TL | subsystem | **intact** — `force_recompute` doğru primitive, ama opt-in |
| `network-cache-eager` | 06-08 | Network tab boş | subsystem | **superseded** — eager load `28e30fa0` ile geri alındı; GUI warm tier hiç çalışmadı; `app-time-range` Input→State dönüşümü hâlâ zararlı (`app.py:2595, 2700`) |
| `fix/customer-cache-tier-refresh` | 06-08 | admin refresh her şeyi siliyordu | subsystem | **weakened** — yarısı `a7f97ed9` ile revert; `refresh_all_tier_caches` (`customer_service.py:2099`) **çağrısız dead code**; warm TTL 21600 == batch interval 6h |
| `fix/summary-used-column-and-compliance-cache` | 06-08 | used sütunu 0 | subsystem | **intact** — en sağlıklısı; key formatına dokunma |
| `sellable-cache-ui-fix` | 06-16 | Constrained Loss yanlış | point fix | **intact** — matematik doğru; ama aynı KPI için ikinci formül eklendi (C12) |
| `vip-cache-reliability` | 06-18 | VIP sayfaları 0 | subsystem | **weakened** — 3 gün sonra gelen implicit last_good ile **yapısal olarak iptal edildi** |
| `customer-list-aliases-cache` | 06-18 | Boyner-only liste cache'leniyor | subsystem | **weakened** — 120s snapshot'ın effective floor'u 24h oldu; degraded predicate 3 yerde 3 farklı |
| `customer-cache-crm-prod-fix` | 06-21 | CRM tile'ları 0'a düşüyor | systemic | **intact — ve diğer on altısını kıran fix bu** (`cache_backend.py:107-112`) |
| `perf/shared-cache-fresh` | 07-01/02 | per-pod cache adaları | systemic | **weakened** — backend abstraction doğru; `_is_fresh`'in `age is None → True` kuralı (`api_client.py:496-497`) + sidecar key + eviction = kalıcı stale |
| `backup-ui-redis-revamp` | 07-16 | backup panelleri yavaş | subsystem | **intact — ve zararlı** — key cardinality'yi user input'a bağladı (`api_client.py:1256-1287`); stale ratchet (`dc_service.py:5635-5638`) |
| `feat/cache-correctness` | 07-17 | empty fetch iyi veriyi siliyor | karışık | **intact** — version token yarısı (`shared/customer/cache_keys.py:7`) tek gerçekten doğru fix; `_prefer_stale_over_empty_fetch` kalıcı latch yarattı |
| `fix/customer-cache-never-holds` (R1-R7) | 07-10 | 5 katmanlı root-cause planı | systemic | **kısmen hiç yazılmadı** — R1 runbook'ta kaldı, R2/R3 hiç implemente edilmedi ama ✅ işaretlendi |

**Scope dağılımı:** 17 branch'in çoğu "subsystem" etiketli ama gerçekte tek sayfa/tek panel düzeltmesi. Gerçekten sistemik olan 4 tanesi (`global-view-cache`, `crm-sellable-cache-tier2`, `customer-cache-crm-prod-fix`, `perf/shared-cache-fresh`) **yeni katman ekledi**, mevcut katmanı düzeltmedi. Bugün aynı mantıksal değer için 4-7 rung'lık TTL merdivenleri var (bölüm 4).

---

## 3. Hâlâ açık olan gerçekler

### 3.1 CONFIRMED NOT DONE (ölçüldü, kanıtlandı)

**(a) pg_trgm index — HEADLINE. Hiç uygulanmadı ve blocker gerekçesi yanlış.**

Prod `bulutlake` DB'de ölçüldü:
```
extensions: plpgsql 1.0, timescaledb 2.16.1      -> pg_trgm YOK
target indexes found: []
vm_metrics: sadece vmname_idx btree(vmname,timestamp) -> '%x%' için kullanılamaz
nutanix_vm_metrics: vm_name üzerinde HİÇBİR index yok
```
Canlı EXPLAIN ANALYZE:
```
Filter: (vmname ~~* '%DEVUPS%')   Rows Removed by Filter: 2508052 + 3311758
Execution Time: 7259.892 ms       <- TEK statement, 7 günlük pencere
nutanix_vm_metrics:               Execution Time: 2059.029 ms
```
`services/customer-api/app/db/queries/customer.py` içinde **44 adet leading-wildcard ILIKE** var. Cold `/resources` planın dediği "~104s" değil, daha kötü.

`sql/dba/customer_resources_pg_trgm_indexes.sql:4-6` "app role superuser değil" diyor. **Yanlış:** role `bulutlake` `CREATE` yetkisine sahip, `pg_trgm` `trusted=True` (PG13+). `CREATE EXTENSION IF NOT EXISTS pg_trgm` app credential'ıyla başarıyla çalıştırıldı ve rollback edildi (`pg_trgm present after rollback: 0`). **18 haftadır beklenen DBA hiç gerekli değildi.**

Tek koruma `tests/test_dba_pg_trgm_indexes_sql.py` — bir metin dosyasında 4 substring arıyor. Yeşil. Hiç DB'ye dokunmadı. Repo "Phase 3 ✅ complete" diyor; prod'da index yok.

**(b) `cache_get` last_good fallthrough — recompute'u tamamen bloke ediyor.** db1'de canlı:
```
customer_catalog:snapshot   primary=0 last_good=1(ttl=85162) -> cache_get()=DATA
latest_vm_ts                primary=0 last_good=1(ttl=81993) -> cache_get()=DATA
cache_run_singleflight on expired-primary key: factory() invocations = 0
```
`GET /customers/Boyner/resources?preset=7d` → **HTTP 200, 414 KB, 0.2s**, tamamı gölgeden. GUI `_mark_fetched` bunu "şimdi taze" damgalıyor; `src/pages/customer_view.py:3306-3315` "as-of: HH:MM" = şimdi yazıyor, veri 1 günlük olabilir.

**(c) `warm_common()` no-op.** Ölçüm yukarıda. Ayrıca `warm_common` (`app_background_warm.py:294-322`) **hiç log basmıyor** — server-side timer'ın sıfır observability'si var. Loglardaki `app_background_warm done` satırları `_warm_guarded:334`'ten, yani user-triggered RBAC warm'dan geliyor.

Canlı staleness census (SWR=900s): `dc_racks` 12/12 stale (max 1873s), `dc_details` 11/13 stale — bu iki family'ye `warm_common` hiç dokunmuyor. 8 dakika önceki örnek 235 key'in 153'ü stale (%65).

**(d) `scheduler_service` ölü modül.** `grep -rn "start_scheduler" src app.py` → sadece `scheduler_service.py:123` (tanım) ve `app_background_warm.py:111` (yorum). **Sıfır çağıran.** Bu dosyadaki hiçbir job prod'da hiç çalışmadı.

**(e) Redis eviction zaten aktif; k8s'te persistence yok.** Local'de `evicted_keys:176`, `used_memory 50.63M / peak 196.07M`, hepsi 256MB içinde. `src/services/cache_service.py:9` "Cache entries never disappear" diyor — **zaten yanlış**. Her GUI key'i `ttl=-1` (`cache_service.py:139` — `self._r.set(..., pickle.dumps(value))`, expiry yok). k8s'te `k8s/redis/deployment.yaml:20-25` **volume/PVC yok**, `limits.memory: 256Mi == maxmemory` (LRU devreye girmeden OOMKill). Redis pod restart = tüm frontend replica'ları aynı anda %100 cold; `warm_common` sadece ~15 key dolduruyor, kalan ~230'u (104 `sellable_by_panel`, 12 `dc_racks`, 13 `dc_details`) yalnızca user request dolduruyor — prod'da 20s timeout ile → `empty_fallback` → sıfırlar.

**(f) k8s ≠ compose. Prod, tune edilen değerlerin hiçbirini çalıştırmıyor.** `k8s/frontend/configmap.yaml` toplam 3 key: `API_BASE_URL`, `CHATBOT_API_URL`, `REDIS_URL`.

| Ayar | compose/.env | k8s | Prod effective |
|---|---|---|---|
| `API_CACHE_SWR_TTL` | 900 | **unset** | **300** (`api_client.py:147`) |
| `API_INTERACTIVE_READ_TIMEOUT` | 45/120 | **unset** | **20** (`api_client.py:205`) |
| `_INFLIGHT_WAIT_SECONDS` | 125 | — | **25** (`api_client.py:206-208`) |
| frontend replicas | 1 | 2, HPA→6 | 6 ayrı in-process ada |
| Redis persistence | `redis_data:/data` | **yok** | tamamen ephemeral |
| Redis readiness gate | `depends_on: service_healthy` | **yok** | boot race serbest |

Prod'da SWR 300s, warm cycle 240s → **1.25× oranı** — `2d9023f5` commit'inin "bu patolojiyi düzelttik" dediği durum, çünkü fix yalnızca `docker-compose.yml`'a gitti. Ayrıca backend 7s × 44 statement gerektirirken interactive timeout 20s. **Müşterinin bug'ı local'de reproduce edilemez; local 6× daha müsamahakâr.**

**(g) `WARMED_CUSTOMERS` env variable'ı ölü.** `.env:15` `WARMED_CUSTOMERS=Boyner` set ediyor; `src/services/db_service.py:40` **`APP_WARMED_CUSTOMERS`** okuyor. Çalışan app'te doğrulandı: değer hardcoded fallback `("Boyner",)`'dan geliyor (`db_service.py:44`). Tenant eklemek isteyen herkes yanlış değişkeni set etmiş. Tek satırlık fix.

**(h) Worker recycle = tam kesinti.** `--workers 1 --threads 8 --max-requests 2000`. Gözlenen:
```
22:51:46 [7] Autorestarting worker
22:53:46 [7] Worker exiting        <- tam +120s, graceful-timeout DOLDU (forced kill)
22:55:02 [183] Booting worker      <- 3dk 16sn worker'sız
22:55:32 [183] Autorestarting      <- boot'tan 30 saniye sonra
```
**3 dakika 16 saniye hiçbir worker yok.** Bu pencerede kullanıcı sayfanın render olup sonra boşaldığını görür — cache ile hiçbir ilgisi yok. Müşteri şikayetlerini `Autorestarting worker` timestamp'leriyle korele etmeden cache'e yıkmayın.

### 3.2 UNVERIFIABLE LOCALLY — prod'da bakılacaklar

Öncelik sırasıyla: gerçek `evicted_keys`/`used_memory` (256Mi limitine karşı); `api:__ts__:` sidecar sayısı vs payload sayısı gerçek LRU baskısı altında; datacenter-api'nin 2-8 pod'u arasında `_memory_cache` divergence'ı; rolling deploy'da frontend boot race; `bulutistan-data-api`'nin gerçekte neyi resolve ettiği (k8s'te böyle bir Service tanımı yok, crm-engine manifest'i **hiç yok**).

Sidecar-orphan mekanizması local'de bile görünüyor: **243 payload key vs 235 timestamp sidecar** — 3 `hyperconv_hosts_all` payload'ı sidecar'sız, yani `_is_fresh` (`api_client.py:496-497`) onları **sonsuza kadar taze** okuyor ve asla refetch etmeyecek.

---

## 4. Çakışan mekanizmalar

### C0 — Master collision: `cache_get` miss dönemiyor, dört fix onu miss testi olarak kullanıyor
`cache_backend.py:107-112` (implicit shadow), `:141` (`max(ttl*2, 86400)`), `:246`/`:263` (singleflight miss testi). Sonuç: `vip-cache-reliability`'nin TTL'leri (`config.py:35`, `customer_service.py:97-100`), `customer-list-aliases-cache`'in 120s snapshot'ı, `fix/customer-cache-tier-refresh`'in 21600s warm tier'ı — **hepsi ölü sabit.** Effective floor 86400s.

Canlı örnek, `customer_service.py:1933-1942`:
```python
result = cache.run_singleflight(sf_key, factory, ttl=60)
cache.set_with_stale(cache_key, result, fresh_ttl=2100, stale_ttl=86400)
```
`factory()` çalışmıyor; "revalidator" 24 saatlik payload'ı 2100s taze diye yeniden yayınlıyor **ve** `stale:`'i 86400s daha uzatıyor — **her Backup tab açılışında.** Panel, bakıldıkça kendini yenileyen bir stale ratchet.

`cache_get_stale` (`:131-136`) bugün davranışsal olarak `cache_get` ile aynı — ölü API.

### C1 — Per-key TTL, global TTL'e yıkanıyor (iki bağımsız yol)
`cache_set(..., ttl=N)` Redis'i N ile yazıyor (`:146`) ama memory tier'ı `_memory_cache[key] = value` ile global `TTLCache(ttl=settings.cache_ttl_seconds)`'a koyuyor (`:19-22`, `:151-152`) — **ttl argümanı sessizce düşüyor.** Sonra `cache_get`'in memory-hit dalı Redis'e `ex=settings.cache_ttl_seconds, nx=True` ile backfill yapıyor (`:95-100`; aynısı `datacenter-api/.../cache_backend.py:60-73`). 60 saniyelik key bir saat yaşıyor. customer-api 3600'e, datacenter-api 1200'e yıkıyor — iki servis hiç aynı saatte olmadı.

### C2 — Aynı key, dört writer, dört ömür, iki reader farklı alt küme görüyor
`customer_service.py:1958-1978`, tek `cache_key`: Redis primary (3600→2100), `stale:` prefix (86400, sadece `get_with_stale` görüyor), `:last_good` (86400, sadece `cache_get` görüyor), pod-local `_memory_cache` (3600). `get_with_stale` (`services/customer-api/app/services/cache_service.py:101`) memory tier'ı ve `:last_good`'u **hiç görmüyor**; `cache_get` `stale:`'i hiç görmüyor. "Bu key için cache'te ne var?" sorusuna iki fonksiyon farklı yaş, farklı payload dönüyor.

### C3 — datacenter-api'nin admin refresh'i GUI cache'ini ve crm-engine'in kaynağını siliyor
`services/datacenter-api/app/routers/admin_cache.py:25` → `cache_flush_pattern("*")` → **DB 0**'ın tamamında SCAN+DEL. GUI de DB 0'a yazıyor (`docker-compose.yml:137`, `k8s/frontend/configmap.yaml:11`), crm-engine de DB 0'dan `dc_details`/`global_dashboard` okuyor. Non-destructive kanıt:
```
redis-cli -n 0 SCAN 0 MATCH '*' COUNT 60 | grep -c 'dl:fecache'  ->  16/60
db0 toplam 1264 key, bunun 477'si dl:fecache:*
```
Tek buton basışı 1264 key'i siliyor (tüm `api:__ts__:` sidecar'ları dahil), customer-api (db1) ve crm-engine (db2) dokunulmuyor → gözlenen sonuç tam olarak "DC sayıları sıfırlanıp panel panel geri geliyor, customer sayıları kıpırdamıyor."

### C4 — Sellable Tier-1 empty cache'liyor, Tier-2 reddediyor: 15 dakikalık oscillator
`sellable_service.py:4286-4287` empty durumda hem Tier-1'e `[]` hem Tier-2'ye `[]` yazmaya çalışıyor; `_snapshot_db_set:3985` `not results` ise **erken dönüyor** → Tier-2'de ESKİ satır kalıyor. Tier-1 900s sonra expire → `:4274-4278` Tier-2'den eski değeri Tier-1'e geri yazıyor. Veri hiç değişmeden: boş → eski sayılar → boş.

Ayrıca `invalidate_result_cache(None)` → `DELETE ... WHERE (%s IS NULL OR dc_code=%s)` (`db/queries/sellable.py:447-450`) **tüm DC/family satırlarını** siliyor ve 11 settings endpoint'ine bağlı. Tek fiyat düzenlemesi durable tier'ı global olarak yok ediyor.

### C5 — `_is_fresh`, metadata'sı evict edildiği anda "taze" diyor
`api_client.py:490-497`: `age is None` → **True**. `_swr_age` ayrı bir key okuyor (`api:__ts__:<key>`, `:466-468`). `RedisBackend.set` expiry yazmıyor (`cache_service.py:139`). Tek silme mekanizması `allkeys-lru` ve **data key ile sidecar'ı bağımsız evict ediyor.** Sidecar giderse payload sonsuza kadar taze okunuyor ve `api_client.py:568` her request'te onu dönüyor. Payload giderse miss → 20s timeout → sıfırlar. Her iki şikayet, aynı eviction'dan, sidecar'ı ekleyen fix yüzünden. Ve her değer artık iki key = LRU baskısı iki katı.

`backup-ui-redis-revamp` bunu user-driven yaptı: `api_client.py:1256-1287, 1304-1335` key'e `search`, `page`, `page_size` ve 5 filtre listesi gömüyor — **arama kutusuna basılan her tuş iki kalıcı Redis key'i üretiyor.**

### C6 — Docstring'i "stale serve etmez" diyen fonksiyonda üç stale yolu
`api_client.py:564-566` docstring. Çelişen dallar: `:581-584` (per-process follower, `_is_fresh` kontrolü yok), `:590-594` (cross-pod follower — `_wait_for_shared_result:547-556` `get(cache_key) is not None` olur olmaz True dönüyor, stale durumda key zaten orada), `:600-605` (`_prefer_stale_over_empty_fetch`, `_mark_fetched` çağırmıyor → key bir sonraki okumada yine stale → **her request'te full fetch, sonsuza kadar**; backend meşru olarak empty dönüyorsa UI silinmiş VM'in sayılarını kalıcı gösteriyor).

**Lock kırık:** `try_acquire(cache_key, 25s)` (`:588`) ama warm fetch'ler 300s read timeout altında. Lock fetch ortasında expire ediyor, ikinci pod alıyor, birinci pod'un `release()`'i (`:616`) **ikinci pod'un lock'unu siliyor** — `RedisBackend.release` düz `DELETE`, value `b"1"` (`cache_service.py:180, 185-189`). ADR-0007 D4 pod UUID + Lua compare-and-delete şart koşmuştu.

### C7 — Tek modülde dört freshness rejimi
sidecar (`api:__ts__:`), embedded tuple (`(ts, payload)` — `:2121`, `:2288`), **hiç yok** (`api:auranotify_customer_options:2045`, `api:dc_avail_sla_item:2142` — TTL yok, timestamp yok, invalidator yok, hiç expire olmayan RedisBackend'de = **sonsuza kadar cache**), ve downstream servis SWR. `_is_fresh`/`get_cache_as_of` tuple rejiminde anlamsız; settings cache-metrics paneli o key'leri sessizce dışarıda bırakıyor.

### C8 — Invalidation bir basamağı siliyor, sonraki basamak geri koyuyor
`_invalidate_customer_views_cache` (`api_client.py:2544-2561`) ve `mapping_cache_invalidator.py:26-32` doğru çalışıyor ama şunlara ulaşmıyor: (1) `api:__ts__:` sidecar'ları — `delete_prefix` `dl:fecache:api:customer_resources:*` eşliyor, sidecar `dl:fecache:api:__ts__:api:customer_resources:...` (aynı yetim `:2086`, `:3041-3042`, `:3177-3182`, `:1382`, `:1147`); (2) **diğer pod'ların `_memory_cache`'i** — `cache_delete` yalnızca local `TTLCache`'ten pop ediyor; Pod B bir sonraki okumada `cache_get:90-100` ile silinen key'i **paylaşılan Redis'e geri backfill ediyor** (`ex=3600, nx=True`). Invalidation başka bir pod'un okumasıyla geri alınıyor. Bu KB'de belgeli olay (`raw/gui-unmapped-alias-backup-lessons-2026-07-27.md §1b`) ve hâlâ açık.

### C9 — `/datacenters` yanlış time-range'in parasını gösteriyor, spinner bastırılmış
`src/utils/datacenters_virt_sellable.py:225-229` `cache_complete` tr_key'i kontrol ediyor, ama `:241-245` değeri `dc_id in cache_snapshot` ile okuyup topluyor — tr_key kontrolü yok. `:248` `loading = (warming or not cache_complete) and not (has_stale and total > 0.0)` → sıfırdan farklı herhangi bir stale toplam `loading=False` yapıyor → `src/pages/datacenters.py:830-835` Interval'ı `disabled=True` render ediyor, `:1104` PreventUpdate. **Sayfa oturum boyunca yanlış pencere sayısını gösteriyor.** Üstelik `_VIRT_TL_CACHE`/`_VIRT_CACHE_TR_KEY` modül global'i, `--workers 1 --threads 8` içinde tüm eşzamanlı kullanıcılar tarafından paylaşılıyor — iki kullanıcı birbirinin parasını görüyor.

### C10/C11/C12 — kısa
Üç warm path, biri hiç çalışmadı (bölüm 3.1d). `set_with_stale` memory tier'ı atlıyor ama `cache_get` oradan Redis'e backfill yapıyor (`datacenter-api/.../cache_backend.py:60-73`) → eviction sonrası **başka bir pod'un private snapshot'ı** paylaşılan Redis'e diriliyor. Aynı Constrained Loss KPI'ı backend'de (`sellable_service.py:4431-4442`) ve GUI'de (`virt_sellable_aggregate.py:258-276`) iki farklı formülle hesaplanıyor, üçüncü bir host-level track Dash process'inde (`dc_view.py:4290-4343`); threshold fetch yavaşsa `empty_fallback=[]` dönüp hardcoded 80/80/85'e düşüyor (`:4220-4227`) — **cache key hiç değişmeden reload'da farklı sayı.**

---

## 5. Mimari borç: ne silinmeli, neye dokunulmamalı

### SİLİNECEKLER (extend edilmeyecek)

| Ne | Nerede | Neden silinmeli |
|---|---|---|
| `cache_get`'in implicit last_good fallthrough'u | `services/customer-api/app/core/cache_backend.py:107-112` | Tüm customer-api recompute'unu bloke ediyor. `cache_get_primary()` ekleyin, `run_singleflight` onu kullansın; last_good yalnızca **explicit** `cache_get_last_good` (`:119`) üzerinden ve response'ta işaretlenerek servis edilsin (`X-Cache: stale` — ADR-0007 D3, hiç yapılmadı, kodda **0 occurrence**). |
| İki stale mekanizmasından biri | `stale:` prefix (`customer-api/app/services/cache_service.py:81`) **veya** `:last_good` | İkisi aynı key üzerinde birbirinden habersiz (C2). Biri silinecek. |
| `api:__ts__:` sidecar key'i | `api_client.py:466-468` | Timestamp payload'ın **içine** girecek. Eviction bug'ı, orphan invalidation gap'i, tuple rejimi ve no-timestamp rejimi tek değişiklikle ölür. |
| `refresh_all_tier_caches` | `customer_service.py:2099-2105` | Çağrısız dead code, "desteklenen giriş noktası" gibi okunuyor. |
| `src/services/scheduler_service.py` | tüm dosya | Sıfır çağıran. Ölü modül olduğu 17 gün fark edilmedi ve network cache platform genelinde boş kaldı. Wire et ya da sil — üçüncü seçenek yok. |
| `cache_get_stale` | `cache_backend.py:131-136` | `cache_get` ile davranışsal olarak aynı. Yanıltıcı API. |
| `cache_flush_pattern("*")` | `datacenter-api/app/routers/admin_cache.py:25` | DB 0 ortak; kendi key family'lerine `cache_delete_prefix` kullanacak. |
| `_memory_cache`'ten Redis'e nx-backfill | `cache_backend.py:95-100`, `datacenter-api/.../:60-73` | Invalidation'ı geri alıyor, pod-local snapshot'ı paylaşılan cache'e diriltiyor. |

### DOKUNULMAYACAKLAR (doğru, test edilmiş, hâlâ etkili)

- `src/pages/floor_map.py:57-95` `_FigureCache` — content fingerprint'e (last_observed dahil) bağlı; yapısal olarak yanlış veri servis edemez.
- `shared/customer/cache_keys.py:7,26` version token'ları + `tests/test_customer_cache_keys.py` — July dalgasının tek tam doğru fix'i.
- `services/customer-api/app/services/sales_service.py:95-120` time-range-aware bundle key.
- `src/auth/permission_service.py:18-47` Redis retry — en temiz fix, 5 sonraki commit'e rağmen bozulmadı.
- `services/crm-engine/app/routers/admin_cache.py:17-27` + `sellable_service.py:4622-4633` — zero-downtime publish'in **server yarısı** doğru; revert etmeyin.
- `sellable_service.py:4262-4280` `force_recompute` — doğru primitive, genişletilmeli (silinmemeli).
- `src/pages/customer_view_callbacks.py:8` `from dash.exceptions import PreventUpdate` — bu fix, şikayetlerin bir kısmının **hiç cache olmadığının** kanıtı.

---

## 6. 18. denemenin şartları

Her madde bir kabul kriteri + onu kanıtlayan regression testi. Bunlardan biri eksikse fix tutmaz — 17 kez tuttu bunu ispatladı.

**S1 — Key için tek kaynak-of-truth.**
Her cached payload family'si bir modülden gelen key builder kullanacak; ADR-0029 gereği shape değişebilen her payload **version token** taşıyacak. Bugün 40 family'nin 4'ünde var. `dc_details:*`, `global_dashboard:*`, `crm:inventory_overview:*`, `dc_zabbix_net_*`, tüm backup/colocation key'leri token'sız.
*Test:* `tests/test_cache_key_registry.py` — `src/services/api_client.py` içindeki tüm `_api_response_cache.set(` çağrılarını AST ile tarayıp key'in registry builder'ından geldiğini assert eder. Hardcoded f-string = fail.

**S2 — Her payload için tek owner, tek freshness rejimi.**
`api_client.py`'de dört rejim (C7) bire inecek: timestamp cached value'nun **içinde**, tek key, atomik. `age is None` artık **stale** demek (`api_client.py:496-497` tersine çevrilecek).
*Test:* `tests/test_api_client_single_freshness_regime.py` — tuple-shaped veya timestamp'siz `set()` çağrısı kalmadığını assert eder; `_is_fresh` metadata yokken **False** döndüğünü assert eder.

**S3 — empty ile missing dürüstçe ayrılacak.**
Cache üç durum ayırt edecek: *fresh value* / *stale value + yaşı* / *yok*. "Meşru boş" cache'lenebilir olacak (`computed_at` damgasıyla), "degraded boş" cache'lenmeyecek. `_prefer_stale_over_empty_fetch` (`api_client.py:528-543`) stale servis ettiğinde bunu görünür kılacak ve kendi timestamp'ini yenilemeyecekse en azından bir `stale_since` alanı dönecek. `_snapshot_db_set` (`sellable_service.py:3985`) empty sonucu **saklayabilecek** (C4).
*Test:* `tests/test_cache_empty_vs_missing.py` — meşru boş → cache'lenir + fresh okunur; degraded boş → cache'lenmez + önceki değer stale işaretli döner; hiç yok → miss. Ve `tests/test_api_client_no_stale.py` ile `tests/test_api_client_stale_on_empty_fetch.py` **birleştirilecek** — bugün ikisi zıt spec encode ediyor ve ikisi de yeşil.

**S4 — Eviction-safe tasarım.**
`src/services/cache_service.py:9-11`'deki "entries never disappear" invariant'ı ya **doğru yapılacak** (Redis 2GB + AOF, ADR-0007'nin 161MB working set hesabına göre) ya da **silinecek** ve tüm kod eviction'ın her an olabileceğini varsayacak. Bir değer asla iki key'e bölünmeyecek (S2). Key cardinality user input'a bağlanmayacak — `api_client.py:1256-1287`'deki `search`/`page` key'leri ya cache dışı ya da bounded olacak.
*Test:* `tests/test_cache_eviction_safety.py` — fake backend rastgele key'leri siler; hiçbir kod yolunun "sonsuza kadar taze" duruma düşmediğini ve hiçbir değerin iki ayrı key gerektirmediğini assert eder.

**S5 — Invalidation tüm merdiveni kapsayacak.**
Bugün Customer View merdiveni: GUI Redis DB0 (expiry yok) → sidecar → cust-api memory (per-pod 3600) → cust-api Redis DB1 primary → `:last_good` 86400 → (Postgres yok). Invalidation **delete değil, versioned key bump** olacak (ADR-0029'un kendi sonucu) — böylece per-pod memory ve orphan sidecar problemleri (C8) yapısal olarak ortadan kalkar. Kim hangi key'i invalidate eder matrisi yazılacak (KB gap 5).
*Test:* `tests/test_invalidation_ladder.py` — her rung için: bump sonrası eski key hiçbir okuma yolundan dönmüyor; ikinci bir "pod" (ayrı backend instance) eski değeri paylaşılan cache'e geri yazamıyor.

**S6 — Warm gerçekten refetch edecek.**
`app_background_warm.py` getter'lara `force_refresh=True` geçirecek, `api_client.py:568` freshness kapısını bypass edecek. `warm_common` **log basacak** (bugün sıfır observability) ve **cycle süresini ölçecek**; cycle süresi freshness penceresini aşarsa uyaracak. `warmed += 1` "exception yok" değil, "non-empty payload persist edildi" anlamına gelecek. `WARMED_CUSTOMERS` env adı düzeltilecek (`db_service.py:40`).
*Test:* `tests/test_warm_actually_refetches.py` — taze bir key üzerinde warm çalıştırılır; underlying HTTP fetch'in **çağrıldığı** assert edilir. Bugünkü kod bu testte fail eder (ölçüldü: 0 refetch).

**S7 — Recompute bloke edilemeyecek.**
`cache_run_singleflight`'ın miss testi primary-only okuma olacak (`cache_backend.py:246, 263`).
*Test:* `tests/test_singleflight_recomputes_after_primary_expiry.py` — primary silinmiş, `:last_good` var; `factory()` çağrı sayısı **1** olmalı. Bugün 0 (ölçüldü).

**S8 — Time-range guard geri gelecek.**
`src/utils/datacenters_virt_sellable.py:241-245` ve `:129-130` değer okumasında `cache_key == tr_key` kontrol edilecek; zero-downtime spinner yerine **stale badge** ile korunacak.
*Test:* `tests/test_virt_cache_tr_guard.py` — cache A range'i ile dolu, B range'i istenir → toplam 0/loading, önceki range'in TL'si **dönmez**.

**S9 — Stale servis gözlemlenebilir olacak.**
ADR-0007 D3'ün `X-Cache: stale` header'ı yazılacak (bugün `services/` ve `src/` içinde **0 occurrence**), GUI bunu bir badge'e bağlayacak, "as-of" damgası HTTP 200 zamanını değil **verinin hesaplanma zamanını** gösterecek (`customer_view.py:3306-3315` bugün yalan söylüyor).
*Test:* `tests/test_stale_serve_is_observable.py` — shadow'dan servis edilen response'un header'ı ve GUI badge'i stale gösterir.

**S10 — Distributed lock düzeltilecek.**
Lock value pod UUID olacak, release Lua compare-and-delete ile yapılacak (`cache_service.py:180, 185-189`), lock TTL guard ettiği fetch timeout'undan **uzun** olacak (bugün 25s vs 300s). `_maybe_upgrade_backend` `try_acquire`/`release`'den de çağrılacak (`cache_service.py:294-302`).
*Test:* `tests/test_lock_fencing.py` — pod A'nın release'i pod B'nin lock'unu silemez.

**Ve kodun önünde iki iş, kodsuz:**
- **pg_trgm'i uygulayın.** DBA gerekmiyor (bölüm 3.1a). `CREATE INDEX CONCURRENTLY`, transaction dışında, 92 chunk / 19 GB. Uygulandığını **runtime'da doğrulayan** bir startup check veya health endpoint ekleyin — `tests/test_dba_pg_trgm_indexes_sql.py` bir metin dosyasına bakıyor ve hiçbir zaman gerçeği söyleyemez.
- **`k8s/frontend/configmap.yaml`'a tune edilmiş env'i ekleyin.** Bugün prod SWR 300s ve 20s interactive timeout ile çalışıyor. 1-18 arası hiçbir kod değişikliği bunu kurtaramaz.

**Ve bir farklı diagnoz:** İlk teslimat bir fix olmasın. **Tek bir "sayfa gidip geliyor" instance'ı** olsun: timestamp, pod adı, cache key, browser network trace — ikinci değerin gerçekten ikinci bir HTTP çağrısından gelip gelmediğini gösteren. `45502bb3`, `14c0cf34`, `b6387a1f`, `1ddce10c`, `d6623c3e` aynı semptomu **Dash callback katmanında** düzeltti. Gözlenen 3dk16sn worker outage'ı da aynı semptomu üretir. 17 fix bu ayrımı hiç yapmadı.

---

## 7. Prod doğrulama borcu

Yalnızca gerçek cluster'da kanıtlanabilecekler ve tam komutları:

| Ne | Komut / sorgu | Ne ispatlar |
|---|---|---|
| pg_trgm gerçekten var mı | `psql -h <prod> -d bulutlake -c "SELECT extname FROM pg_extension" -c "\di+ *trgm*"` ve `EXPLAIN (ANALYZE,BUFFERS) SELECT ... WHERE vmname ILIKE '%X%' AND timestamp >= now()-'7 days'` | Bitmap Index Scan mı, `Rows Removed by Filter: 2.5M` mi. Bugün ikincisi. |
| Redis eviction basıncı | `redis-cli -h <redis-svc> INFO stats \| grep -E 'evicted_keys\|keyspace_hits\|keyspace_misses'` + `INFO memory \| grep -E 'used_memory_human\|maxmemory_human'` | 256Mi limitine karşı gerçek eviction oranı; `evicted_keys > 0` ise `cache_service.py:9` invariant'ı prod'da ölü. |
| Sidecar orphan | `redis-cli -n 0 --scan --pattern 'dl:fecache:api:__ts__:*' \| wc -l` vs `redis-cli -n 0 --scan --pattern 'dl:fecache:api:*' \| grep -vc '__ts__' ` | İki sayı eşit değilse fark kadar key **kalıcı taze** okunuyor ve asla refetch edilmiyor (`api_client.py:496-497`). Local'de zaten 243 vs 235. |
| DB layout | `redis-cli INFO keyspace` (db0/db1/db2 key sayıları) | C3'ün blast radius'u; k8s'te hiçbir servis `REDIS_DB` set etmiyor, layout şansa kalmış. |
| Prod env'in gerçeği | `kubectl exec deploy/<frontend> -- env \| grep -E 'API_CACHE_SWR_TTL\|API_INTERACTIVE_READ_TIMEOUT\|APP_WARMED_CUSTOMERS\|REDIS_URL\|API_BASE_URL'` | SWR 300 mü 900 mü; timeout 20 mi 45 mi; `APP_WARMED_CUSTOMERS` set mi (bölüm 3.1g). |
| `bulutistan-data-api` nedir | `kubectl get svc \| grep data-api` ve `kubectl get endpoints bulutistan-data-api` | Kodda üç client tek base URL'e çöküyor (`api_client.py:22-29`); repo'da bu Service tanımı yok. crm-engine manifest'i hiç yok. |
| İki pod divergence'ı | Aynı sayfayı iki farklı `datacenter-api` pod'una zorlayıp (`kubectl port-forward` ile pod'a doğrudan) aynı key'i sorgulamak; `kubectl exec <pod> -- python -c "from app.core.cache_backend import _memory_cache; print(len(_memory_cache))"` | C11'in resurrection mekanizması; local'de 1 replica olduğu için **imkânsız** doğrulanması. |
| Worker recycle korelasyonu | `kubectl logs deploy/<frontend> --since=24h \| grep -E 'Autorestarting\|Booting worker\|Worker exiting'` ve şikayet timestamp'leriyle karşılaştırma | Şikayetlerin kaçı 3dk'lık kesinti penceresinde? Cache'e yıkmadan önce bu ölçülmeli. |
| Rolling deploy boot race | `kubectl rollout restart deploy/<frontend>` sonrası ilk 60s'te `kubectl logs -f \| grep 'cache_service'` | R7'nin retry'ı devreye giriyor mu; `k8s/frontend/deployment.yaml:30-43` Redis readiness gate'i yok. |

**Kural:** Bu yedi ölçüm alınmadan 18. fix'in kapsamı seçilmesin. Dört ay boyunca "docker-compose'da doğrulandı" denen her şey, replica sayısı, timeout, SWR penceresi ve Redis persistence'ı farklı olan bir ortam hakkında hiçbir şey söylemiyor.