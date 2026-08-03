# Datalake Platform GUI — Cache Defect Raporu ve Production Öncesi Düzeltme Planı

**Tarih:** 2026-08-03 · **Kapsam:** Datalake-Platform-GUI + services/ (customer-api, datacenter-api, crm-engine) · **Durum:** production launch öncesi blocker listesi

---

## 0. Yönetici Özeti

Müşterinin "sayfa gidip geliyor" şikâyeti **tek bir bug değil**. Birbirinden bağımsız **11 farklı mekanizma** aynı görsel semptomu üretiyor. Ekibin daha önce yaptığı düzeltmelerin tutmamasının sebebi de bu: her seferinde en son görülen semptom düzeltildi, altındaki mimari varsayım korundu.

Bu raporda **32 bulgu**, **7 kök nedene** indirgendi. Bunlardan **9 tanesi çalışan stack üzerinde canlı olarak reprodüksiyon edildi** (curl / redis-cli / docker logs / browser) — bunlar en yüksek güvenilirlikteki maddeler ve fix planının çekirdeğini oluşturuyor.

**Production'a bu haliyle çıkılamaz.** Üç blocker:

| # | Blocker | Kanıt |
|---|---|---|
| B1 | `POST /_dash-update-component` **auth'suz** tam sayfa verisi döndürüyor (12 DC, host/VM sayıları, CRM satış) | LIVE: cookie'siz curl → `200`, 133.617 byte |
| B2 | datacenter-api'nin admin refresh'i **GUI'nin tüm cache'ini siliyor** (aynı Redis db 0) | LIVE: `dl:fecache` 1390 → 9 key, canary yok oldu |
| B3 | Cache entry'leri **kalıcı olarak donabiliyor** (`__ts__` side-car kaybı = sonsuza kadar "fresh") | LIVE: side-car DEL → 4 çağrıda backend'e 0 istek; şu an prod state'te 7 donmuş key var, biri **boş** DC12 host tablosu |

---

## 1. Kanıt Seviyeleri

Rapordaki her bulgu üç seviyeden birinde:

- **[LIVE]** — çalışan stack'te reprodüksiyon edildi. Tartışmaya kapalı.
- **[STATIC-CONFIRMED]** — kaynak kodda uçtan uca doğrulandı, çürütme denemesi başarısız oldu. Runtime ölçümü yok.
- **[OPEN]** — mekanizma doğrulandı ama kullanıcıya yansıması ölçülmedi. Bölüm 7'de listelendi.

Statik analizde bulunup **canlı olarak da doğrulanan** bulgular (en yüksek öncelik): datacenter-api flush, `compute:` key collision, `__ts__` immortality, singleflight follower zeros, Redis eviction, gunicorn recycle, `/_dash` auth gap, `/_dash-component-suites` no-store.

---

## 2. Kök Nedenler

Ekip semptom düzeltti; aşağıdaki 7 mimari varsayım hiç dokunulmadı. Her biri için **"önceki point fix neden tutmadı"** açıkça yazıldı.

---

### RC-1 — Tek Redis database, sahipsiz `"*"` flush

GUI (`REDIS_URL=redis://redis:6379/0`, namespace `dl:fecache:`) ve datacenter-api (`redis_db: int = 0`, `services/datacenter-api/app/config.py:12`) **aynı database'i** paylaşıyor. customer-api `REDIS_DB=1`, crm-engine `REDIS_DB=2` ile doğru şekilde izole — datacenter-api tek istisna, çünkü compose'da `REDIS_DB` env'i hiç set edilmemiş.

`services/datacenter-api/app/routers/admin_cache.py:23`:
```python
cache_flush_pattern("*")
```
`app/core/cache_backend.py:134-149` bunu tüm db üzerinde `SCAN match="*"` + `DELETE` olarak çalıştırıyor. Prefix guard yok.

**Yıkım tek yönlü:** GUI'nin kendi `RedisBackend.clear()`'ı doğru şekilde namespace-scoped (`src/services/cache_service.py:158-163`, sadece `dl:fecache:*`).

**Neden önceki fix tutmadı:** Ders zaten öğrenilmiş — customer-api'nin route docstring'i *"Rebuild customer caches without flushing Redis (stale-until-overwrite)"*, crm-engine'inki *"Does not flush Redis up front"*. İki servis düzeltildi, datacenter-api atlandı. Düzeltme **servis bazında** yapıldı, **mimari kural** (paylaşılan db'de bare `*` yasak) konmadı.

---

### RC-2 — Freshness, değerin yanında değil ayrı key'de; "bilinmiyorsa taze" varsayılanı

`src/services/api_client.py:466-497`:
```python
def _fetched_ts_key(cache_key): return f"api:__ts__:{cache_key}"
def _swr_age(cache_key):
    ts = _api_response_cache.get(_fetched_ts_key(cache_key))
    return None if ts is None else (time.time() - ts)
def _is_fresh(cache_key) -> bool:
    ...
    age = _swr_age(cache_key)
    return age is None or age <= _SWR_TTL_SECONDS   # ← eksik timestamp = TAZE
```
Data key ve side-car **iki ayrı, atomik olmayan write** (`api_client.py:601-603`). İkisi de TTL'siz. Redis `allkeys-lru` ikisini **bağımsız** evict ediyor. Küçük side-car gidip büyük data key kaldığında entry **kalıcı olarak taze** oluyor: `_is_fresh` True döner → `api_client.py:568` fast path erken döner → fetch hiç çalışmaz → side-car hiç yeniden yazılmaz. Kapalı döngü.

**[LIVE] Kanıt:**
```
A) side-car eski (ts=1.0)  → callback t=0.045  datacenter-api yeni log satırı: 1   (refetch OLDU)
B) side-car DEL, data kalır → callback t=0.028  datacenter-api yeni log satırı: 0   (refetch YOK)
   3 tekrar daha → 0, 0, 0.  __ts__ yeniden yaratıldı mı: 0
```
Prod state'te hâlihazırda mevcut donmuş key'ler:
```
dl:fecache:api:hyperconv_hosts_all:DC12:[["anchor_latest","true"],["preset","7d"]]  age=None fresh=True hosts=0  ← BOŞ, ölümsüz
dl:fecache:api:hyperconv_hosts_all:DC11:[["preset","7d"]]  hosts=27
dl:fecache:api:hyperconv_hosts_all:AZ11:[["preset","7d"]]  hosts=5
```

**Neden önceki fix tutmadı:** `age is None → fresh` **bilinçli bir carve-out**. Docstring'i `api_client.py:492-494` bunu yazıyor: *"warm-written (no timestamp)"*. Yani warm job'ların gereksiz refetch'ini önlemek için konmuş bir semptom fix'i. Eviction ile birleşince kalıcı freeze üretiyor. İki ayrı key yazma kararı hiç sorgulanmadı — oysa kod tabanı **aynı problemi başka yerde doğru çözmüş**: `api_client.py:2121` ve `:2288` timestamp'i değerin **içinde** `(now, data)` tuple olarak saklıyor.

---

### RC-3 — "Entry'ler asla kaybolmaz" invariant'ı ile `allkeys-lru` çelişkisi

`src/services/cache_service.py:9-11` modül başlığı:
> *"Cache entries never disappear until explicitly overwritten by fresh data. TTL is only used as a staleness hint (not for eviction)."*

`RedisBackend.set` (`cache_service.py:136-141`) gerçekten `ex=` geçmiyor — tüm GUI key'leri `TTL -1`. Ama `docker-compose.yml:213`:
```
redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
```
`allkeys-lru` **TTL'siz key'leri de** evict eder. Kod, Redis'in vermediği bir garanti üzerine kurulu. Bu garanti üzerine kurulu üç kritik path var:
- follower fallback: `api_client.py:583` `hit is not None`
- last-good hata path'i: `api_client.py:610-612`
- `__ts__` side-car'ın varlığı (RC-2)

**[LIVE] Kanıt:** eviction zorlandı ve GUI key'lerini anında sildi:
```
maxmemory 256M → used 61.9M, evicted_keys:0   (rest halinde temiz)
CONFIG SET maxmemory (used-6MB) → evicted_keys:176
dl:fecache 427 → 415   (12 no-TTL GUI entry yok oldu)
```
Bütçenin ~%94'ü datacenter-api'nin: tek bir key **16.777.312 byte** (`stale:dc_nutanix_snap:DC13:2026-07-01:2026-07-31`). GUI, üretmediği bellek baskısıyla evict ediliyor.

**Neden önceki fix tutmadı:** İki dosya (`cache_service.py` başlığı ve `docker-compose.yml:213`) hiç birlikte okunmadı. Invariant kodda yazıldı, infra'da uygulanmadı.

---

### RC-4 — Cache key, isteğin gerçek boyutlarını taşımıyor

Key correctness dört ayrı yerde bozuk:

**(a) `anchor_latest` key'de yok, üstelik key anchor'dan ÖNCE kuruluyor** — `services/datacenter-api/app/services/dc_service.py:1076-1078`:
```python
return f"compute:{kind}:{dc_code}:{tr.get('start','')}:{tr.get('end','')}:{cluster_part}"
```
`:1266` key kurulur → `:1267` cache okunur/erken döner → `:1271-1272` `if tr.get("anchor_latest"): tr = self._smart_1h_tr(tr)`. Anchor **lookup'tan sonra** uygulanıyor.

**[LIVE] Kanıt — sıra bağımlı, iki yönde de:**
```
Yön 1: un-anchored cold (t=6.484s) → anchored istek t=0.011s, body IDENTICAL  (toggle sessizce yok sayıldı)
Yön 2: anchored cold  (t=5.738s) → un-anchored istek t=0.005s, body IDENTICAL  (anchored payload yanlış kullanıcıya)
Redis'te tek key: compute:classic:DC13:2026-07-27:2026-08-02:DC13-KM2-CLS-NVME,DC13-KM3-CLS-NVME
```
Ayrı bir probe'da sayısal fark da ölçüldü: DC18, aynı cluster subset → `cpu_pct 17.6` vs `17.3`, hangisi önce cache'i doldurursa 600 s boyunca herkes onu görüyor.

**Neden önceki fix tutmadı:** Aynı dosyada **doğru pattern zaten var** — `get_dc_details` (`dc_service.py:2833-2836`), `get_all_datacenters_summary` (`:3426-3428`), `get_global_overview` (`:3710-3712`) hepsi key'den **önce** anchor'lıyor. `get_classic_metrics_filtered` yeni yazılırken kopyalanan pattern yanlış olan oldu. Kural yazılı olmadığı için tekrar etti.

**(b) GUI key'i request'ten daha spesifik (1H preset)** — `src/utils/time_range.py:39-48` 1H için `_now_utc()` ile **saniye çözünürlüklü** start/end üretiyor, `_serialize_tr_cache_key` (`api_client.py:500-513`) bunları key'e koyuyor; ama `_build_time_params` (`:279-292`) 1h/1d/7d/30d için sunucuya **sadece `preset`** gönderiyor. Sonuç: her 1H seçimi garanti miss + TTL'siz Redis'e kalıcı yeni kopya.

**(c) cluster sırası** — GUI `",".join(selected)` (`api_client.py:1420-1423`, sıralamasız), backend `",".join(sorted(clusters))` (`dc_service.py:1077`). N! GUI key'i → 1 backend entry. Sadece israf, yanlış veri değil.

**(d) RBAC/tenant boyutu hiç yok** — `grep -n 'ck = f"api:' src/services/api_client.py` → 75 key builder, aktör (user/role/tenant/permission) boyutu içeren: **0**. Tek `role` geçen `api:phys_inv_loc:{role}:...` (`:1535`) NetBox *device* role'ü. Bugün sızıntı üretmiyor çünkü backend'ler zaten global veri döndürüyor; ama B1 (auth gap) ile birleşince "anonim çağıran, admin'in cache'inden okuyor" oluyor.

---

### RC-5 — Degrade sinyali yok: `empty_fallback` veri gibi render ediliyor

Üç ayrı path uydurulmuş sıfır döndürüyor:
- follower timeout: `api_client.py:581-584` → `_clone(empty_fallback)`
- HTTP hard-fail, cache boş: `api_client.py:610-613` → `_clone(empty_fallback)`
- leader'ın kendi interactive timeout'u: aynı `except _HTTP_ERRORS` kolu

`_EMPTY_DASHBOARD` (`api_client.py:32-70`) tamamen şekilli bir sıfır dict'i. Sayfa bunu gerçek ölçümden ayırt edemiyor: `src/pages/home.py:413` `overview.get('total_vms', 0)` doğrudan KPI kartına gidiyor.

**[LIVE] Kanıt:**
```
docker stop bulutistan-datacenter-api; overview key silindi
POST /_dash-update-component → 200, t=3.13s, len=43390
Render edilen KPI değerleri: 0 , 0 , 0 , 0
Yanıt içinde 'hata|error|unavailable|veri yok|no data' araması:
  sadece Plotly template key'leri "error_x"/"error_y"  → kullanıcıya HİÇBİR hata göstergesi yok
Zeros cache'lendi mi? EXISTS ... → 0  (hayır, doğru)
```

**Follower bütçesi leader'dan kısa:** `_INFLIGHT_WAIT_SECONDS = max(25.0, _INTERACTIVE_READ_TIMEOUT + 5.0)` (`api_client.py:205-208`). Canlı container'da `API_INTERACTIVE_READ_TIMEOUT=120` → follower 125 s bekliyor. Leader warm thread ise `_INVENTORY_READ_TIMEOUT=300` (`:213-217`, `:248`). 125 s < 300 s → warm leader'ın arkasındaki her follower sıfır alıyor.

**[LIVE] Kanıt:** gerçek kod path'i container içinde `_INFLIGHT_WAIT_SECONDS = 3.0` ile çalıştırıldı → follower `_EMPTY_DASHBOARD` döndürdü (`is _EMPTY_DASHBOARD → True`). Ayrıca cold `/api/v1/dashboard/overview` = **66.1 s** ölçüldü (warm 0.003 s); `api_client.py:220-222` yorumunun kendisi *">60s overview"* diyor.

**Neden önceki fix tutmadı:** `_should_persist_api_cache` (`api_client.py:516-525`) — "sıfırları cache'leme" düzeltmesi — **doğru çalışıyor** (live doğrulandı). Ama bu fix flip'in *sebebi*: sıfırlar cache'lenmediği için sonraki reload gerçek değeri gösteriyor → kullanıcı "veri kayboldu, sonra geldi" görüyor. Persist etmemek doğruydu; eksik olan **degrade'i UI'a taşımak**.

---

### RC-6 — Dash layout sahipliği belirsiz: aynı Input'tan iki yazar

`render_main_content` (`app.py:807-812`) `Input("app-time-range","data")` alıyor ve `main-content.children`'ı **komple yeniden kuruyor**. Aynı anda alt sayfaların `*-page-root` callback'leri de **aynı Input'tan** tetikleniyor ve `main-content`'in **içindeki** node'a yazıyor. İki yazar, sıra garantisi yok.

Ek olarak dash-renderer, yeni bir layout chunk enjekte edildiğinde output'u o chunk'a düşen callback'leri **initialCall olarak yeniden çalıştırıyor** (`dash_renderer.dev.js:6967-6980` — `if (!cb.callback.prevent_initial_call) { cb.initialCall = true; addCallback(cb) }`). Sonuç: tek tıkta çift dispatch.

**[LIVE] Kanıt — Overview, tek 30D tıklaması, 8 POST:**
```
6 main-content.children
7 overview-page-root.children   changedPropIds: ["app-time-range.data"]
8 overview-page-root.children   changedPropIds: []          ← duplicate, değişen input YOK
```
**[LIVE] Kanıt — DC View tab reset:** `/datacenter/DC13`, Backup & Replication açıkken 30D tıklandı:
```
önce: "Summary,Virtualization,Storage,Backup & Replication*,..."
sonra: "Summary*,Virtualization,Storage,Backup & Replication,..."
~9 s içinde 4 ara render: content length 2186 → 2179 → 2190 → 5571
```
Kök: shell her seferinde `dcc.Store(id="dc-view-loaded-tabs", data=["summary"])` ve `dcc.Store(id="dc-view-active-tab", data="summary")` ile yeniden kuruluyor (`src/pages/dc_view.py:6596-6597`), `render_dc_loading_page` `active_outer_tab` almadan çağrılıyor (`:6618`) → `_resolve_outer_tab(None,...)` → `default_tab="summary"` (`:5576-5585`, `:6525`).

Aynı sınıf, üç yerde daha:
- **Customer View perspective** `customer_view_callbacks.py:127` `perspective = default_perspective(access)` — mevcut perspective State olarak bile okunmuyor. Customer'a ekran paylaşırken Manager-only bloklar geri geliyor. [STATIC-CONFIRMED]
- **Virt cluster filter** `app.py:1148-1157` ile `dc_view_callbacks.py:63-68` aynı Input'tan iki yazar; `virt_cluster_filter.py:29-35` applied Store'u her rebuild'de **tüm cluster'lara** resetliyor. [STATIC-CONFIRMED]
- **Customer View Backup** `customer-backup-category-tab-store` iki kez tanımlı (`customer_view.py:3693` ve `:3854`), renderer last-write-wins ile page-root içindekini seçiyor; ayrıca `_fill_backup` (`:3716-3736`) sekiz tab fill callback'i içinde **tek guard'sız olan** — kullanıcı Summary'deyken bile `render_backup_tab` çalışıyor. [STATIC-CONFIRMED]

**Neden önceki fix tutmadı:** Race'in farkındalar — `dc_view_callbacks.py:103`'te yorum var: *"Tabs UI is source of truth when present (avoids Summary race)"*. Yani workaround yazılmış, teardown kökü (shell'in `Input("app-time-range")` alması) duruyor. `customer_view.py:3738-3756`'daki guard yorumu da aynı hikâye: *"opening one customer ran eight renders at once against a gunicorn pool of eight threads"* — yedi tab'a guard eklendi, Backup atlandı.

---

### RC-7 — Tek worker + agresif recycle + warm thread'in leader olması

`Dockerfile:39`:
```
--workers 1 --threads 8 --timeout 300 --graceful-timeout 120 --max-requests 2000 --max-requests-jitter 200
```
Tek worker recycle olduğunda **hiç worker kalmıyor**.

**[LIVE] Kanıt (2400 istek ile zorlandı):**
```
22:51:46 [7]   Autorestarting worker after current request.
22:53:46 [7]   Worker exiting (pid: 7)        ← tam 120 s: graceful-timeout tamamen yandı
22:55:02 [183] Booting worker with pid: 183   ← 76 s daha SIFIR worker
toplam: 196 s
```
Bu, tarayıcıda gözlenen davranışla birebir eşleşiyor: `/crm/inventory-overview` `document.title="Updating..."` ile t=20 s → t=139 s arası tam sayfa spinner; `/` de blank oldu (`rootLen:0`), ~140 s'de döndü. Aynı anda GUI'nin static route'u 3 ms yanıt veriyordu (`/login: 200 0.003s`) — yani master soketi tutuyor, worker yok.

**Cache kaybolmuyor** (H1'in bu kısmı çürütüldü): `REDIS_URL` set olduğu için `RedisBackend` seçiliyor, recycle öncesi yazılan canary sonrasında okunabildi. Kayıp **availability** + `_inflight` (`api_client.py:141`) sıfırlanması + her recycle'da `warm_common()`'ın `app.py:239-244`'te **ilk sleep'ten önce** çalışıp backend'lere stampede yapması.

**Neden önceki fix tutmadı:** `--max-requests 2000` bilinçli konulmuş (`Dockerfile:37`: *"recycle worker to limit long-lived memory growth (mitigate OOM)"*). OOM semptomu için konan mitigation, tek worker ile birleşince düzenli outage'a dönüştü. Memory leak hiç aranmadı.

---

### RC-8 — Auth gate page route'ta, callback layer'da değil

`src/auth/middleware.py:64-72`:
```python
if path.startswith("/_dash"):
    _hydrate_g_from_session()
    if getattr(g, "auth_user_id", None) is not None:
        logger.debug(...)
    return None            # ← hydration BAŞARISIZ olsa da izin veriyor
```
`else: return redirect(...)` yok. Enforcement tek tek callback'lere bırakılmış ve **sadece `render_main_content`** uyguluyor (`app.py:835-844`). `*-page-root` callback'lerinin hiçbirinde `g`/`auth_user_id`/`can_view` referansı yok — örn. `src/pages/dc_view_callbacks.py:65-116`, RBAC'ı tarayıcıdaki `State("dc-view-visible-sections","data")` Store'undan alıyor.

Aşağıda ayrıca `_auth_headers()` (`api_client.py:297-311`) user yoksa boş dict dönüyor ve backend'ler `API_AUTH_REQUIRED` default `false` olduğu için (`services/customer-api/app/core/api_auth.py:11,15-17`) auth'suz isteği kabul ediyor. `grep -rn API_AUTH_REQUIRED k8s/ .env` → sadece `k8s/chatbot-api/configmap.yaml:18` true.

**[LIVE] Kanıt:**
```
Page route'lar KORUNUYOR:      /  → 302 /login?next=/    /datacenter/DC13 → 302
Dash endpoint'leri KORUNMUYOR: /_dash-layout 200 (9633)  /_dash-dependencies 200 (130774)
curl -X POST /_dash-update-component  (Cookie header YOK)
  → 200, 133.617 byte
  → "Executive Dashboard", "Total VMs" = "16,903",
     home-export-store.data.summaries = 12 gerçek DC:
     {"DC":"DC11 - Premier DC","Location":"Istanbul","Hosts":32,"VMs":1584,"CPU_pct":47.7,"RAM_pct":71.1}
Kontrol: aynı auth'suz replay ile output="main-content.children" → 131 byte boş Div (gated)
```

**Neden önceki fix tutmadı:** Yorum (`middleware.py:61-63`) niyeti açıklıyor: *"must still populate g from the session cookie so callbacks see auth_user_id"*. Hydration ihtiyacı doğru teşhis edilmiş, ama hydration'ın **başarısız olma** durumu hiç ele alınmamış. Bir callback'e (`render_main_content`) manuel guard eklenerek "çözüldü" sanılmış.

---

## 3. "Sayfa Gidip Geliyor" — Mekanizmaların Tam Listesi

Müşterinin gördüğü semptomu üreten her mekanizma, **karşılaşma olasılığına göre** sıralı:

| # | Mekanizma | Kullanıcının gördüğü | Kanıt | Kök |
|---|---|---|---|---|
| **1** | Aynı sayfada **iki bağımsız cache entry'si** farklı yaşlanıyor | Overview'da "Total VMs" KPI'ı ile DC Landscape treemap **farklı toplam** gösteriyor; KPI reload'lar arası değişiyor, treemap sabit kalıyor | **[LIVE]** 6 ardışık replay, 4 s arayla: KPI **16.903**, treemap toplamı **16.892**, 12 DC, her seferinde aynı. Redis yaşları: `api:global_dashboard` age=438.8 s, `api:datacenters_summary` age=821.5 s, SWR_TTL=900 → 383 s arayla expire oluyorlar. Tarayıcıda da: run1 16.885 vs 16.892, run2 16.903 vs 16.892 | `src/pages/home.py:399` + `:406` |
| **2** | datacenter-api flush → **tüm GUI cache'i aynı anda cold** | Settings → Refresh sonrası her sayfa boşalıp tek tek dolmaya başlıyor; anlık sayfalar dakikalarca yükleniyor | **[LIVE]** `dl:fecache` 1390 → 9, canary silindi, DBSIZE 2302 → 99 | RC-1 |
| **3** | Worker recycle → **196 s hiç worker yok** | Sayfa spinner'da donuyor, kendiliğinden geri geliyor; refresh daha kötü yapıyor | **[LIVE]** gunicorn logları + tarayıcıda 140 s "Updating..." | RC-7 |
| **4** | Follower timeout / backend hatası → **tüm KPI'lar 0**, sonraki reload'da gerçek | "Veri kayboldu, sonra geri geldi" | **[LIVE]** backend down → 0,0,0,0 hata mesajı olmadan; follower 3 s deneyi `_EMPTY_DASHBOARD` | RC-5 |
| **5** | Report period değişimi → **shell teardown**, tab reset, ara render'lar | Backup tab'ında okurken 30D'ye basınca Summary'e düşüyor; 4 ara render | **[LIVE]** DC13 tab-state before/after + Overview'da 2 duplicate callback | RC-6 |
| **6** | `__ts__` kaybı → panel **kalıcı donuyor**, flush/eviction sonrası **aniden zıplıyor** | "Sayı hiç güncellenmiyor" → sonra bir gün bambaşka bir değer | **[LIVE]** side-car DEL → 4 çağrı, 0 backend isteği; 7 mevcut donmuş key | RC-2 |
| **7** | `compute:` key collision → **başka kullanıcının variant'ı** | Cluster filtresi uygulanmışken CPU/RAM sayıları toggle'a rağmen değişmiyor, ya da kimse dokunmadan değişiyor | **[LIVE]** iki yönde de byte-identical yanıt | RC-4a |
| **8** | LRU eviction → **rastgele panel** cold | "Bir dakika önce iyiydi" | **[LIVE]** forced eviction, 427→415 GUI key | RC-3 |
| **9** | `_VIRT_TL_CACHE` time-range'siz key | Data Centers'da "Satılabilir Potansiyel" TL'si önceki range'in değeri; partial warm'da **eksik toplam final gibi** gösteriliyor, poll disable olduğu için düzelmiyor | [STATIC-CONFIRMED] `src/utils/datacenters_virt_sellable.py:26-28`, `:238-248` | RC-4 |
| **10** | Logout sonrası callback data + shell blank **yarışı** | Çıkış yaptıktan sonra sekmede veri dolup boşalıyor | [STATIC-CONFIRMED] + auth gap [LIVE] | RC-8 + RC-6 |
| **11** | customer-api read-through refresh **no-op** | "Refresh Platform Caches" basılıyor, yeşil OK geliyor, sayılar değişmiyor; UTC gece yarısında kendiliğinden zıplıyor | [STATIC-CONFIRMED] `cache_run_singleflight` ilk işi `cache_get` (`cache_backend.py:246-249`), `factory()` (`:267`) ulaşılamaz | RC-2 varyantı |

**Çürütülen hipotez (önemli):** H3 — "SWR stale-then-fresh swap kullanıcıya görünüyor" — **YANLIŞ**. `_api_cache_get_with_stale` gerçekten no-stale (`api_client.py:565-572`: stale entry serve edilmiyor, refetch ediliyor). Görünen swap **tek key'in stale→fresh geçişinden değil, iki farklı key'in bağımsız yaşlanmasından** geliyor (#1). Bu ayrım kritik: ekip SWR TTL'i ayarlamaya çalışırsa hiçbir şey düzelmez.

---

## 4. Öncelikli Düzeltme Planı

### P0 — Production öncesi zorunlu (correctness + data-leak + outage)

---

#### **P0-1 · Dash callback endpoint'lerine session gate**  `[LIVE]`

**Dosya:** `src/auth/middleware.py:63-72`

**Değişiklik:**
```python
if path.startswith("/_dash"):
    _hydrate_g_from_session()
    if getattr(g, "auth_user_id", None) is None and not AUTH_DISABLED:
        # /_dash-layout ve /_dash-component-suites shell boot için açık kalmalı
        if path.startswith("/_dash-update-component"):
            return jsonify({"error": "session_expired"}), 401
    return None
```
Yanına client-side handler: 401 gelince `window.location.href = "/login"`. Ayrıca `API_AUTH_REQUIRED=true` — `docker-compose.yml:73,410,551` ve customer-api/datacenter-api k8s configmap'leri (JWT plumbing zaten var: `api_client.py:297-311`, `services/customer-api/app/core/api_auth.py:15-30`).

**Risk:** Orta. Session'ı geçici kaybeden aktif sekmeler artık sessizce çalışmak yerine login'e gidecek — istenen davranış, ama `AUTH_DISABLED=true` ile çalışan dev/test ortamlarında regresyon yaratmamak için `AUTH_DISABLED` kontrolü şart. `/_dash-layout` ve `/_dash-dependencies`'i kapatmayın, aksi halde shell hiç boot edemez.

**Doğrulama:**
```bash
curl -sX POST http://localhost:8050/_dash-update-component -H 'Content-Type: application/json' \
  -d '{"output":"overview-page-root.children",...}' -o /dev/null -w '%{http_code}\n'
# beklenen: 401  (bugün: 200, 133617 byte)
```
Ardından cookie ile aynı istek → 200. Regresyon testi: bkz. §5 T-1.

---

#### **P0-2 · datacenter-api'yi ayrı Redis db'ye al + bare `*` flush'ı yasakla**  `[LIVE]`

**Dosyalar:** `docker-compose.yml:238-241` (env), `services/datacenter-api/app/config.py:12`, `services/datacenter-api/app/routers/admin_cache.py:23`, `services/datacenter-api/app/core/cache_backend.py:134`

**Değişiklik (üçü de gerekli):**
1. `docker-compose.yml` datacenter-api bloğuna `REDIS_DB: "3"` ekle (customer-api `"1"` `:292`, crm-engine `"2"` `:341` ile aynı pattern). k8s tarafında da configmap'e ekle.
2. `admin_cache.py:23` → `cache_flush_pattern("*")` yerine sahip olunan prefix'ler: `for p in ("dc_*", "stale:dc_*", "compute:*", "global_*", "sla_*", "phys_inv*", "netbox:*"): cache_flush_pattern(p)`. Daha iyisi: customer-api/crm-engine pattern'ini izle ve **flush'ı tamamen kaldır**, `warm_cache()` üzerine yazsın (önceki değerler görünür kalır).
3. `cache_backend.py:134` başına guard: `if pattern.strip() in ("*", ""): raise ValueError("bare '*' flush forbidden on a shared db")`.
4. `src/services/api_client.py:3222-3247` — GUI kendi cache'ini backend çağrılarından **önce** temizlesin (bugün 3 × 600 s timeout'lu çağrıdan sonra, `:3247`), yoksa cold pencere gereksiz yere dakikalarca uzuyor.

**Risk:** Düşük. DB değişimi datacenter-api'nin mevcut cache'ini bir kereye mahsus cold bırakır (kabul edilebilir, warm loop dolduruyor). Guard'ın herhangi bir meşru çağrıyı kırmadığını doğrulayın (`grep -rn 'cache_flush_pattern' services/`).

**Doğrulama:**
```bash
redis-cli -n 0 SET 'dl:fecache:api:CANARY' x
redis-cli -n 0 --scan --pattern 'dl:fecache:*' | wc -l      # N
curl -X POST http://localhost:8000/api/v1/admin/cache/refresh
redis-cli -n 0 --scan --pattern 'dl:fecache:*' | wc -l      # N olmalı (bugün: 9)
redis-cli -n 0 GET 'dl:fecache:api:CANARY'                  # x olmalı (bugün: nil)
redis-cli INFO keyspace                                      # db3 görünmeli
```

---

#### **P0-3 · Freshness timestamp'i değerin İÇİNE al (side-car'ı kaldır)**  `[LIVE]`

**Dosyalar:** `src/services/api_client.py:466-497`, `:601-603`, `:2045`, `:2142`

**Değişiklik (tercih edilen — atomik):** `_api_cache_get_with_stale` payload'ı `{"__fetched_at": time.time(), "__v": out}` olarak tek `set` ile yazsın; `_swr_age` bunu değerin içinden okusun. `_fetched_ts_key`/`_mark_fetched` tamamen silinsin. Kod tabanı bu pattern'i zaten `api_client.py:2121` ve `:2288`'de doğru kullanıyor.

**Değişiklik (minimum — aynı deploy'da yapılabilir):** `api_client.py:497`:
```python
return age is not None and age <= _SWR_TTL_SECONDS
```
ve `:2045` (`get_auranotify_customer_options`) + `:2142` (`get_dc_availability_sla_item`) write'larına `_mark_fetched(ck)` ekle; `:2032` read'ini `_is_fresh(ck)` ile guard'la.

**Risk:** Minimum fix'in riski: deploy anında Redis'te bulunan **timestamp'siz eski entry'ler** anında stale olur → tek seferlik cold storm. `warm_common()` zaten boot'ta çalıştığı için kabul edilebilir, ama P0-7 (multi-worker) ile aynı deploy'da yapılmalı. Atomik fix'in riski: key şekli değişir → `CACHE_VERSION` bump'ı veya tek seferlik `delete_prefix("api:")` gerekir.

**Doğrulama:**
```bash
# 1) key'i ısıt, 2) side-car'ı sil, 3) 4 kez çağır, backend loglarını izle
redis-cli -n 0 DEL 'dl:fecache:api:__ts__:api:global_dashboard:[...]'
for i in 1 2 3 4; do curl -sX POST .../_dash-update-component -d @payload.json -o /dev/null; done
docker logs --since 1m bulutistan-datacenter-api | wc -l    # >0 olmalı (bugün: 0)
```
Ayrıca mevcut 7 donmuş key'i temizle: `redis-cli -n 0 --scan --pattern 'dl:fecache:api:*'` ile data key'i olup `__ts__` twin'i olmayanları sil.

---

#### **P0-4 · Degrade sentinel: uydurulmuş sıfır asla veri olarak render edilmesin**  `[LIVE]`

**Dosyalar:** `src/services/api_client.py:32-70` (`_EMPTY_DASHBOARD`), `:120` (`_EMPTY_CUSTOMER`), `:122`, `:583-584`, `:610-613`; `src/pages/home.py:390-415`, `src/pages/datacenters.py:729`

**Değişiklik:**
1. Her `_EMPTY_*` sabitine `"_degraded": True` ekle.
2. `api_client.py:584` ve `:613` — `_clone(empty_fallback)` dönerken bu marker'ı koru.
3. `home.py:399` sonrası: `if data.get("_degraded"): return _error_card("Veri alınamadı — tekrar deneyin")`. Aynısı `datacenters.py`, `customer_view.py`, `dc_view.py`, `unmapped_resources.py` için.
4. Follower bütçesini leader'ın en kötü durumuna eşitle — **kod değişikliği bile gerekmiyor**, env override var (`api_client.py:206`): `API_INFLIGHT_WAIT_SECONDS=305`. Kalıcı çözüm `:208`:
```python
_INFLIGHT_WAIT_SECONDS = max(25.0, _INVENTORY_READ_TIMEOUT + 5.0)
```

**Risk:** Düşük. Tek dikkat: `_degraded` marker'ı `_should_persist_api_cache`'e (`:516-525`) takılıp da yanlışlıkla persist edilmemeli — zaten `value.get("totals") == {}` gibi şekil kontrolleri yapıyor, marker eklenince o kontrollerin hâlâ tuttuğunu test edin. Follower bekleme süresini uzatmak, backend gerçekten çökmüşse kullanıcıyı 305 s bekletir — bu yüzden `_degraded` UI'ı **birlikte** shipping edilmeli.

**Doğrulama:**
```bash
docker stop bulutistan-datacenter-api
redis-cli -n 0 --scan --pattern 'dl:fecache:*global_dashboard*' | xargs redis-cli -n 0 DEL
# / sayfasını aç → "Veri alınamadı" kartı görünmeli, "0" KPI'ları DEĞİL
docker start bulutistan-datacenter-api
```

---

#### **P0-5 · Overview tek atomik snapshot'tan render edilsin**  `[LIVE]`

**Dosya:** `src/pages/home.py:399` + `:406`

**Değişiklik (küçük olan, önerilen):** KPI'ları ikinci endpoint'ten değil, `summaries`'ten türet:
```python
summaries = api.get_all_datacenters_summary(tr)
total_vms   = sum(s["vm_count"]   for s in summaries)
total_hosts = sum(s["host_count"] for s in summaries)
dc_count    = len(summaries)
```
`home.py:413`'teki `overview.get('total_vms', 0)` yerine bunlar. `get_global_dashboard` sadece treemap'in kullanmadığı alanlar (energy_breakdown, platform kırılımı) için kalsın.

**Alternatif:** `api_client`'a `get_overview_bundle(tr)` ekle; iki upstream çağrıyı **tek** `_api_cache_get_with_stale` içinde, tek key (`api:overview_bundle:{tr}`) altında yap.

**Risk:** Düşük-orta. `overview.total_platforms` ve enerji alanlarının summaries'te karşılığı yok — bunları global_dashboard'da bırakırsanız o alanlar hâlâ bağımsız yaşlanır (ama KPI/treemap tutarsızlığı, yani şikâyet edilen kısım, biter). Tam tutarlılık isteniyorsa bundle yaklaşımı gerekir. `vm_count`/`host_count` alan adlarını `home.py:506-508` ile birebir eşleştirin.

**Doğrulama:** 6 ardışık HTTP replay (bugünkü probe'un aynısı), 4 s arayla → KPI toplamı ile treemap toplamı **her seferinde eşit** olmalı. Bugün 16.903 vs 16.892.

---

#### **P0-6 · `compute:` key'i anchor'lanmış range'ten kurulsun + stale flag onurlandırılsın**  `[LIVE]`

**Dosya:** `services/datacenter-api/app/services/dc_service.py:1076-1082`, `:1266-1272`, `:1385-1395`

**Değişiklik:**
1. `:1271-1272`'deki anchor bloğunu `:1266`'nın **üstüne** taşı:
```python
tr = time_range or default_time_range()
if tr.get("anchor_latest"):
    tr = self._smart_1h_tr(tr)
cache_key = self._compute_cache_key("classic", dc_code, tr, selected_clusters)
```
2. `_compute_cache_key` (`:1076-1078`) key'e açık flag ekle — `_smart_1h_tr` latest-ts bulamazsa `tr`'yi değiştirmeden döndürüyor (`:3782-3783`), bu durumda collision geri gelir:
```python
a = "a1" if tr.get("anchor_latest") else "a0"
return f"compute:{kind}:{dc_code}:{tr.get('preset','')}:{a}:{tr.get('start','')}:{tr.get('end','')}:{cluster_part}"
```
3. `_get_compute_cached` (`:1080-1082`) `is_stale` flag'ini atıyor. `cache_service.py:119-124` docstring'i açıkça *"arayan kişi arka planda revalidate tetiklemeli"* diyor, hiçbir yer tetiklemiyor. Flag'i döndür ve stale ise mevcut thread pool ile arka planda recompute + `_set_compute_cached` çağır.
4. `get_hyperconv_metrics_filtered` (`:1385-1395`) `_smart_1h_tr`'i **hiç çağırmıyor** — cluster-filtered hyperconv path'i `anchor_latest`'ı sessizce yok sayıyor. Ya anchor'ı uygula ya da flag'i key'e koyup davranışı açıkla.

**Risk:** Düşük. Key şekli değişiyor → mevcut `compute:*` entry'leri orphan kalır, TTL ile (600/1800 s) kendiliğinden düşer. Background revalidate eklerken thread pool'un doygunluğuna dikkat (`--workers 1 --threads 8` GUI tarafı, burası ayrı servis).

**Doğrulama:**
```bash
C=DC13-KM2-CLS-NVME,DC13-KM3-CLS-NVME
redis-cli -n 0 --scan --pattern 'compute:*' | xargs -r redis-cli -n 0 DEL
curl -sG .../DC13/compute/classic --data-urlencode preset=7d --data-urlencode "clusters=$C" > a.json
curl -sG .../DC13/compute/classic --data-urlencode preset=7d --data-urlencode "clusters=$C" \
     --data-urlencode anchor_latest=true > b.json
diff a.json b.json    # FARKLI olmalı (bugün identical)
redis-cli -n 0 --scan --pattern 'compute:*'   # 2 ayrı key (a0/a1) olmalı
```
Stale revalidate için: key'i ısıt, 601 s bekle, çağır → yeni `compute:` (stale değil) key'i yazılmış olmalı; bugün yazılmıyor (canlı ölçüm: stale TTL 938 → 919, sadece geri sayıyor).

---

#### **P0-7 · gunicorn: en az 2 worker, recycle penceresini kapat**  `[LIVE]`

**Dosya:** `Dockerfile:39`

**Değişiklik:**
```
--workers 2 --threads 8 --timeout 300 --graceful-timeout 30 --keep-alive 5
--max-requests 20000 --max-requests-jitter 2000
```
Ayrıca `app.py:239-244` — `_periodic_common_warm` ilk `warm_common()`'ı **sleep'ten önce** çağırıyor; recycle sonrası stampede'i kırmak için `time.sleep(random.uniform(5, 30))` ile başlat.

**Risk:** Düşük. Cache Redis'te olduğu için ikinci worker cache duplikasyonu yaratmıyor (bu canary testiyle doğrulandı) — asıl maliyet RAM (iki Python process). `--graceful-timeout 30` düşürmek, 300 s'lik warm fetch'in ortasında recycle olursa o fetch'i kesecek — kabul edilebilir, bir sonraki istek yeniden dener. `--max-requests` yükseltmek OOM riskini geri getirir: **memory leak'i ayrı bir iş olarak açın** ve container'a `mem_limit` koyun.

**Doğrulama:**
```bash
docker logs --timestamps datalake-platform-gui-app | grep -E 'Autorestarting|Worker exiting|Booting worker'
# "Worker exiting" ile bir sonraki "Booting worker" arasında >0 s boşluk olsa bile
# ikinci worker ayakta olmalı:
seq 1 5000 | xargs -P 12 -I{} curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8050/login | sort | uniq -c
# non-200 SIFIR olmalı
```

---

#### **P0-8 · Redis: GUI'ye ayrı db + gerçek TTL, veya `volatile-lru`**  `[LIVE]`

**Dosyalar:** `docker-compose.yml:137,213`, `src/services/cache_service.py:9-11,136-141`

**Değişiklik — iki tutarlı modelden birini seçin (bugünkü hâli çelişki):**

*Model A (önerilen):* GUI'yi kendi db'sine al (`REDIS_URL=redis://redis:6379/4`), `RedisBackend.set`'e sınırlı `ex=` ver:
```python
def set(self, key, value, ttl: int | None = None):
    self._r.set(self._k(key), pickle.dumps(value), ex=ttl or _DEFAULT_MAX_AGE)  # ör. SWR_TTL*8
```
ve Redis policy'sini `volatile-lru` yap.

*Model B:* Invariant'ı literal koru — GUI için ayrı Redis instance, `maxmemory-policy noeviction`, kendi bütçesi. Bu durumda `cache_service.py:9-11` yorumuna **"bu invariant Redis config'ine bağımlıdır"** notu düşün.

Her iki modelde de ayrıca: datacenter-api'nin 16 MB'lık tek cache value'su (`stale:dc_nutanix_snap:DC13:2026-07-01:2026-07-31`) kendi başına bir bug — blob boyutunu sınırlayın.

**Risk:** Model A'da TTL, `_prefer_stale_over_empty_fetch`'in last-good davranışını değiştirir (entry expire olursa last-good yok) — bu yüzden TTL, SWR TTL'in belirgin katı olmalı (≥ 8×). Model B daha fazla infra işi.

**Doğrulama:**
```bash
redis-cli INFO memory | grep -E 'maxmemory_policy|used_memory_human'
redis-cli -n 4 TTL "$(redis-cli -n 4 --scan --pattern 'dl:fecache:*' | head -1)"   # >0 olmalı (bugün -1)
redis-cli CONFIG SET maxmemory <used-6MB>; sleep 3
redis-cli -n 4 --scan --pattern 'dl:fecache:*' | wc -l   # değişmemeli (bugün 427→415)
redis-cli CONFIG SET maxmemory 268435456
```

---

### P1 — Flip-flop eliminasyonu

---

#### **P1-1 · `render_main_content`'in `app-time-range` Input'unu State'e çevir**  `[LIVE semptom]`

**Dosya:** `app.py:810`

`Input("app-time-range","data")` → `State("app-time-range","data")`. `/` ve `/datacenters` shell'leri `tr`'yi zaten hiç kullanmıyor (`app.py:862-868`); `/datacenter/*`, `/customer-view` vb. sadece header metni için kullanıyor — o metin için ayrı, küçük bir `Output("...-period-badge","children")` callback'i yazın.

Beraberinde:
- `src/pages/dc_view.py:6595-6607` — `dc-view-loaded-tabs` / `dc-view-active-tab` Store'larını shell dışına taşı (veya `State` ile seed et), `:6618`'e `active_outer_tab` geçir.
- `src/components/virt_cluster_filter.py:29-35` — `virt-*-cluster-applied` / `-all` Store'larını `build_dc_view_layout_shell`'e hoist et; MultiSelect `value`'sunu `initial` yerine Store'dan seed et. Sonra `app.py:1148-1157` ve `:1190-1199`'dan `Input("app-time-range","data")`'i kaldır (ikinci yazar tamamen gereksiz).
- `src/pages/home.py:369-371` ve `src/pages/datacenters.py:1038-1041` — boş `*-page-root` div'lerine skeleton placeholder koy, hard blank olmasın.

**Risk:** Orta — bu, en geniş yüzeyli değişiklik. Her route'un shell'inin `tr` bağımlılığını tek tek denetleyin (`app.py:860-908`). Yanlış yaparsanız period değişimi bazı sayfaların body'sini hiç güncellemez. Route bazında test edin.

**Doğrulama:** DevTools'ta `fetch` interceptor ile tek 30D tıklaması → `overview-page-root.children` output'lu POST sayısı **1** olmalı (bugün 2, ikincisi `changedPropIds: []`). DC13'te Backup tab'ı açıkken 30D → tab **Backup'ta kalmalı**, ara render sayısı ≤1 (bugün 4, ~9 s).

---

#### **P1-2 · Customer View perspective ve nested tab state'i koru**

- `src/pages/customer_view_callbacks.py:96-108`'e `State("customer-view-perspective-store","data")` ekle; `:127`'yi `perspective = effective_perspective(stored, access)` yap (helper zaten var: `src/pages/customer_view_perspective.py:32`).
- `src/pages/customer_view.py:3820` — `build_customer_layout_shell` da `default_perspective` yerine geçirilen değeri kullansın.
- `src/pages/customer_view.py:3693`'teki duplicate `customer-backup-category-tab-store` tanımını sil (`:3854`'teki stabil olan kalsın) — **ama asıl düzeltme** bu Store'un page-root dışında yaşaması.
- `_fill_backup` (`customer_view.py:3716-3736`) diğer yedi tab'la aynı guard'ı alsın: `Input("customer-main-tabs","value")` + `if active_tab and str(active_tab) != "backup": return dash.no_update`.

**Risk:** Düşük. `effective_perspective` zaten kullanıcının görebileceğine clamp ediyor, yetki genişlemesi riski yok.

**Doğrulama:** Perspective'i "Customer" yap → 30D'ye bas → SegmentedControl **Customer'da kalmalı**, PostDedup/sold-vs-used blokları görünmemeli. Summary'de otururken app log'da `render_backup_tab` upstream çağrıları **olmamalı**.

---

#### **P1-3 · `_VIRT_TL_CACHE`'i time-range ile key'le**

**Dosya:** `src/utils/datacenters_virt_sellable.py:26-28`, `:32-34`, `:238-248`

`_VIRT_TL_CACHE`'i `dict[tr_key, dict[dc_id, VirtTlEntry]]` yap, `_VIRT_CACHE_TR_KEY` global'ini sil. `has_stale_val` (`:241`) per-(tr_key, dc) lookup olsun → range değişimi gerçek miss olur, `loading` True olur, 2 s poll kollanır (`src/pages/datacenters.py:830-835`), `_build_resolve_result` (`:128-137`) iki range'i toplayamaz. `virt_cache_tr_key`'e (`:32-34`) `anchor_latest` ekle.

Ayrıca partial warm'da agrega KPI: bugün `loading = (warming or not cache_complete) and not (has_stale and total > 0.0)` (`:248`) — eksik DC'lerle hesaplanmış toplam **final gibi** gösteriliyor. Agrega için ayrı `partial` flag'i ekleyip KPI'ı skeleton'da tutun.

**Risk:** Düşük. `_publish_virt_cache`'in partial merge kolu (`:106-110`) tek bucket içinde çalışacak, olduğu gibi güvenli.

**Doğrulama:** 7D'de KPI dolsun → 3M'ye geç → KPI **spinner**'a düşmeli, sonra 3M değeriyle dolmalı. Bir DC'nin fetch'ini fail ettir → `cache_complete` sonsuza kadar False kalmamalı, her render'da yeni warm başlamamalı.

---

#### **P1-4 · customer-api refresh path'ini write-through yap**

**Dosya:** `services/customer-api/app/services/customer_service.py:1200-1243`

`_rebuild_customer_caches_for_customer` şu an sadece `get_customer_resources(...)` çağırıyor — ki bu `cache_run_singleflight` (`app/core/cache_backend.py:246-249`) üzerinden **cache okuyor**, `factory()` (`:267`) hiç çalışmıyor. Yani Settings → Refresh, 15-dk scheduler, `warm_cache`, `refresh_warm_tier_caches`, `refresh_all_tier_caches` — hepsi no-op.

**Değişiklik:** rebuild'den önce sil. `cache_delete` primary + `:last_good`'u birlikte düşürüyor (`cache_backend.py:155-164`):
```python
for tr in cache_time_ranges():
    cache.delete(customer_assets_cache_key(name, tr['start'], tr['end']))
    # aynısı S3 vaults ve unique-jobs key'leri için
```
Alternatif: `get_customer_resources` → `cache_run_singleflight` zincirine `force: bool = False` parametresi geçirip `:246`/`:263`'teki short-circuit'i atlat.

**`LAST_GOOD_TTL_SECONDS`'ı (86400, `cache_backend.py:26`) KISALTMAYIN** — shadow, outage fallback'i. Bug, *bilinçli bir refresh'in* shadow'a danışması.

**Risk:** Düşük-orta. Delete-then-rebuild penceresinde eşzamanlı bir okuma cold SQL'e düşer. `cache_run_singleflight` bunu coalesce ediyor, ama refresh sırasında latency artar.

**Doğrulama:** Refresh'e bas → customer-api loglarında ilgili customer için `Loaded infra bundle` / SQL satırı **görünmeli** (bugün görünmüyor). `redis-cli -n 1 TTL customer_assets:...` refresh sonrası tam TTL'e resetlenmiş olmalı.

---

#### **P1-5 · Yazma sonrası eksik invalidation'lar**

| Ne | Nerede | Ne eklenecek |
|---|---|---|
| Mapping write, infra-türevli CRM cache'lerini düşürmüyor | `src/services/api_client.py:2544-2560` (`_invalidate_customer_views_cache`) | `api:crm_efficiency_by_cat:`, `api:crm_resource_compliance:`, `api:deleted_machines:` prefix'lerini ekle (bunlar `_customer_infra_bundle`'dan besleniyor: `sales_service.py:472-483`, `:545`, `:560-600`) |
| `delete_crm_alias` sadece `api:crm_aliases`'i siliyor | `api_client.py:2632-2636` | `_invalidate_customer_views_cache()` çağır |
| CRM Inventory Overview hiçbir şeyle invalidate edilmiyor | `api_client.py:3170-3182` (`_invalidate_sellable_caches`) + `services/customer-api/app/services/inventory_overview_service.py:35` | GUI tarafında `api:crm_inventory_overview:` prefix'ini ekle; engine tarafında `invalidate_result_cache` (`sellable_service.py:4105-4131`) `crm:inventory_overview:*`'ı da tarasın |
| Service-mapping override 120 s memo'yu resetlemiyor | `services/customer-api/app/services/sales_service.py:1122-1143` | `upsert_service_mapping_override` / `delete_service_mapping_override` sonunda `self._product_mapping_cache = None` ve `self._catalog_price_cache = None` (`:89`); aynısı `inventory_overview_service.py:899,906-915` için |

**Risk:** Düşük. Her biri sadece daha fazla key siliyor — worst case fazladan cold fetch.

**Doğrulama:** Mapping kaydet → Customer View'da efficiency-by-category ve resource-compliance **anında** yeni değeri göstermeli (bugün 900 s'e kadar eski).

---

#### **P1-6 · CRM Service Mapping route'ları doğru servise gitsin**

**Dosya:** `src/services/api_client.py:2433, 2441, 2457, 2464`

Dördü de `_get_client_cust()` kullanıyor (→ `CUSTOMER_API_URL`, `:24`/`:259-260`), ama route'lar sadece crm-engine'de mount'lu (`services/crm-engine/app/routers/service_mapping.py:26,32,38,57`; `main.py:281`). customer-api'nin `/crm/*` route'ları: aliases, accounts, internal-alias, source-mappings, seed-boyner, resync (`routers/sales.py:159-278`) + colocation — service-mapping **yok**. Komşu CRM çağrıları doğru şekilde `_get_client_crm()` kullanıyor.

**Değişiklik:** Dördünü `_get_client_crm()` yap.

Ayrı ama **daha önemli** yan bulgu: 404, `_HTTP_ERRORS`'a düşüp (`:450-456`) `_api_cache_get_with_stale`'in except kolunda (`:605-613`) **yaş sınırsız last-good** döndürüyor. TTL'siz `RedisBackend` ile birlikte bu, *herhangi bir* endpoint 4xx vermeye başladığında o key'in son snapshot'ını **sonsuza kadar, hata göstermeden** oynatması demek. P0-4'ün `_degraded` sentinel'i ve P0-8'in TTL'i bunu birlikte kapatıyor — ayrıca last-good'a açık yaş sınırı ekleyin (`age > 4 * _SWR_TTL_SECONDS` ise `empty_fallback` + `_degraded`).

**Risk:** Düşük. Compose default'unda bugün zaten çalışmıyor (`docker-compose.yml:117-118` iki farklı host).

**Doğrulama:** Settings → CRM Service Mapping tablo dolmalı (bugün sarı "no mappings" uyarısı, `src/pages/settings/crm_service_mapping.py:52-60`); Save yeşil dönmeli (bugün kırmızı 404, `:294-299`).

---

#### **P1-7 · `_prefer_stale_over_empty_fetch` — kalıcı miss döngüsünü kır**

**Dosya:** `src/services/api_client.py:528-543`, `:600-606`

`resolved is cached` kolu (`:604-605`) `_mark_fetched` çağırmıyor → timestamp hiç tazelenmiyor → `_is_fresh` sonsuza kadar False → **her istek** full upstream round-trip + singleflight leadership alıyor, üstelik `logger.warning` her seferinde basıyor.

**Değişiklik:** `_prefer_stale_over_empty_fetch`'e `age` parametresi geçir, sadece `age <= 4 * _SWR_TTL_SECONDS` iken stale'i tercih et; ötesinde empty döndür (ve `_degraded` işaretle). Stale servis edildiğinde kısa bir retry timestamp'i yaz (ör. `_SWR_TTL_SECONDS - 60` yaşındaymış gibi) ki her request cold fetch olmasın.

**Risk:** Düşük. Bu davranış degrade olmuş upstream'lerde tetikleniyor; yaş sınırı, eski veriyi güncel göstermeyi durduruyor.

**Doğrulama:** Bir endpoint'i kalıcı olarak empty döndürecek şekilde mock'la → ilk N istekte stale, sonra `_degraded` gelmeli; log'da her istekte warning **olmamalı**.

---

#### **P1-8 · `_CUSTOMER_AVAIL_LOCK` — global lock'u kaldır, last-good'a yaş sınırı koy**

**Dosya:** `src/services/api_client.py:2016`, `:2103`, `:2110-2122`

Tek global `threading.Lock()`, tüm customer + tüm time-range için, ve **network fetch'in tamamı boyunca** tutuluyor (AuraNotify, `src/services/auranotify_client.py:36-41` timeout 20 s; warm mode'da 300 s). `now = time.time()` fetch'ten **önce** alınıp (`:2103`) fetch'ten sonra saklanıyor (`:2121`) → TTL fetch süresi kadar kısa. `except Exception` kolu (`:2117-2119`) `prev`'i yaş kontrolü olmadan döndürüyor → tek bir AuraNotify hıçkırığı keyfi eski bir bundle'ı güncel gibi gösteriyor, sonraki başarılı istek gerçeğine döndürüyor. Bu tam olarak A-sonra-B flip'i.

**Değişiklik:** Per-key singleflight kullan (`cache_service.try_acquire` + `_inflight`), lock'u HTTP çağrısı boyunca tutma; `now`'ı fetch'ten **sonra** al; except kolunda `now - prev[0] < 4 * CUSTOMER_AVAIL_TTL_SECONDS` sınırı koy. Aynı yaş sınırı `_crm_sales_cache_get` (`:2276-2293`) için de.

**Risk:** Düşük.

---

### P2 — Hardening ve observability

| # | İş | Dosya:satır | Not |
|---|---|---|---|
| P2-1 | `/_dash-component-suites/*` immutable cache | `app.py:127` | `if path.startswith("/_dash-component-suites/"): response.headers["Cache-Control"]="public, max-age=31536000, immutable"` — **erken return**, sonra mevcut `/_dash` no-store kolu. **[LIVE]** her reload'da 13 bundle / 5.223.960 byte. Repo'nun kendi dokümanı bunu zaten yazıyor: `docs/FRONTEND_PERFORMANCE.md:200-207`. URL'ler zaten fingerprint'li (`.venv/.../dash/backends/_flask.py:203-218` `max_age=31536000` set ediyor, biz üzerine yazıyoruz). **Not: bu bir staleness bug'ı DEĞİL** — tam tersi, hiçbir şey cache'lenmiyor. |
| P2-2 | `flask-compress` veya ingress gzip | `requirements.txt`, `k8s/ingress.yaml:4-7` | Şu an sıkıştırma yok; ilk yükleme ~3.8 MB ham |
| P2-3 | CDN bağımlılıklarını vendor'la | `app.py:63-67` (Mantine CSS + DM Sans), `dash_iconify` (api.iconify.design) | **Yük taşıyan sadece ikisi:** Mantine stylesheet'in local kopyası **yok** (`find .venv/.../dash_mantine_components -name '*.css'` boş) → unpkg engellenirse sayfa **stilsiz**. Iconify → ikon yok. PDF export (`assets/export_pdf.js:8-9`) lazy, sadece buton ölür. `src/pages/global_view.py:762` `globeImageUrl` ölü kod, silin. DC içinden çalışan operatörler için gerçek risk. |
| P2-4 | 1H preset key churn | `api_client.py:500-513` | `preset in {"1h","1d","7d","30d"}` iken key'e sadece `preset` (+`anchor_latest`) koy, `start`/`end` koyma — çünkü `_build_time_params` (`:279-292`) sunucuya zaten sadece preset gönderiyor. **Uyarı:** bu, gün-dönümü invalidation'ını kaldırır; cross-midnight doğruluğu tamamen `_is_fresh`/`_SWR_TTL_SECONDS`'a kalır (ki sağlıyor, ama bilinçli bir karar olmalı). Key şekli değişimi → `CACHE_VERSION` bump. |
| P2-5 | Cluster CSV'yi sırala | `api_client.py:1420-1423`, `:2884`, `:2907-2910`, `:2927` | `sorted()` ekle — backend zaten sıralıyor (`dc_service.py:1077`, `sellable_service.py:4059-4062`). `_normalize_clusters_arg` (`:2843-2858`) doğru yer. Sadece israf, yanlış veri değil. |
| P2-6 | Singleflight lock lease'i | `cache_service.py:176-189`, `api_client.py:588` | Lease 50 s (bugün 125 s), korunan fetch 300 s olabilir; `release()` token kontrolü olmadan `delete` ediyor. Tek-worker'da erişilemez, **multi-pod'da gerçek**. P0-7 ile 2 worker'a çıkınca **aktif hâle gelir** — birlikte düzeltin. Ayrıca `:590-594` lock-loser kolu `_is_fresh` kontrolü yapmadan stale döndürüyor (fast path'in reddettiği payload). |
| P2-7 | Background warm'da refresh-ahead yok | `api_client.py:494,497`, `app_background_warm.py:78-81` | Warm, entry **stale olduktan sonra** yeniliyor; refresh-ahead threshold'u yok. TTL=900 / warm=240 s ile her cycle'da ~0-240 s'lik pencerede ilk gelen kullanıcı senkron cold fetch ödüyor (~%12 load). `_is_fresh`'e `age > TTL * 0.75` iken warm-mode'da refetch ekleyin. |
| P2-8 | k8s `:latest` + `IfNotPresent` | `k8s/*/deployment.yaml:19-20` | Immutable tag (`${GIT_SHA}`) kullanın — Dockerfile zaten `ARG GIT_SHA`/`ARG APP_BUILD_ID` kabul ediyor (`Dockerfile:11-16`). Bugünkü hâliyle çalışan build tanımlanamaz ve rollback edilemez. Split-brain iddiası **kanıtlanmadı** (bkz. §7). |
| P2-9 | Permission fail-open | `src/auth/permission_service.py:303-306`, `src/components/sidebar.py:44-54` | `return None` → `return {}`; sidebar'da `None`=AUTH_DISABLED ile `{}`=deny ayrılsın. Gerçek etki dar: sadece statik menü etiketleri, veri sızıntısı değil. |
| P2-10 | Time range reload'da 7D'ye dönüyor | `app.py:388` civarı Store tanımı | `storage_type="session"` + `?preset=30d` query param. **[LIVE]** F5 → 30D kayboluyor, kullanıcı iki farklı pencereyi aynı sanıyor. |
| P2-11 | `/datacenters` iki fazlı render | `src/pages/datacenters.py` | Geç gelen Potential Sales KPI'ı ve per-card satırlar DOM'a **enjekte** ediliyor (append değil) → t=1.36 s ve t=4.0 s'de layout reflow. `dmc.Skeleton` ile yer ayırın. **[LIVE]** |
| P2-12 | Cache observability | yeni | `get_cache_as_of` (`api_client.py:483-488`) zaten var ve `__ts__` kaybında `None` dönüyor — yani UI'daki "as-of" damgasının kaybolması **hazır bir detection sinyali**. Bunu metrik yapın: `cache_entries_without_timestamp`, `redis_evicted_keys`, `singleflight_follower_timeouts`, `degraded_fallback_renders`. Bu dört metrik olsaydı P0-2/3/4/8'in hiçbiri production'a kadar gelmezdi. |

---

## 5. Cache Invariant'ları ve Regresyon Testleri

Bu kurallar yazılı olmadığı için aynı hatalar tekrar etti. Bunları `docs/` altına koyun ve PR review checklist'ine ekleyin.

### Invariant'lar

**I-1 — Key, isteğin tam bir fonksiyonudur.** Bir cache key'i, yanıtı etkileyen **her** boyutu içermeli ve **hiçbir** fazlasını içermemeli.
- *Fazla boyut* → sonsuz key churn (1H preset, RC-4b) ve TTL'siz Redis'te sınırsız büyüme.
- *Eksik boyut* → collision (`anchor_latest`, RC-4a; `_VIRT_TL_CACHE` time range).
- Key **daima** effective (dönüştürülmüş) parametrelerden kurulur, ham parametrelerden değil. Bir transform (anchor, normalize, clamp) varsa key'den **önce** uygulanır.
- Set-tipi parametreler her iki tarafta da aynı şekilde normalize edilir (sorted).

**I-2 — Freshness, değerden ayrılamaz.** Bir entry'nin yaşı, o entry'nin **kendisiyle aynı atomik write'ta** saklanır. İki ayrı key yasak.

**I-3 — Bilinmeyen yaş = stale.** Yaşı belirlenemeyen entry refetch edilir. "Bilinmiyorsa taze" varsayımı yasak.

**I-4 — Eviction ve staleness aynı şey değildir.** Kod, "entry kaybolmaz" garantisine dayanamaz — **ancak** Redis policy'si (`noeviction` veya `volatile-lru` + gerçek TTL) bunu sağlıyorsa dayanabilir. Kod yorumundaki invariant, infra config'i ile aynı PR'da doğrulanır.

**I-5 — Namespace sahipliği.** Her servis yalnızca kendi prefix'ini siler. Paylaşılan bir db'de `match="*"` yasaktır (kod seviyesinde guard'la). Servisler ayrı logical db kullanır.

**I-6 — Uydurulmuş veri, veri değildir.** Fallback/empty/last-good payload'ları **etiketli** döner ve UI'da ölçüm olarak render **edilemez**. Sıfır göstermek, hiçbir şey göstermemekten kötüdür.

**I-7 — Refresh, write-through'dur.** Bilinçli bir invalidation/refresh, hiçbir koşulda cache okumasıyla short-circuit olmaz. "Refresh" butonu ile "read" aynı fonksiyonu çağırıyorsa bug vardır.

**I-8 — Yazma, kendi türevlerini invalidate eder.** Bir write, doğrudan yazdığı tablodan **türeyen** her cache ailesini düşürür (in-process memo'lar dahil). Türev haritası kodda dokümante edilir.

**I-9 — Tek layout node'unun tek yazarı vardır.** Bir DOM node'una yazan iki callback aynı Input'tan tetiklenemez. Kullanıcı seçimi (tab, filter, perspective) taşıyan Store, o seçimin gösterildiği subtree'nin **dışında** yaşar.

**I-10 — Follower, leader'dan uzun bekler.** Herhangi bir coalescing bekleme süresi, korunan işlemin **en uzun** timeout'undan büyüktür.

**I-11 — Cache, authorization'ın yerine geçmez.** Auth, callback layer'ında enforce edilir; ve bir cache key, farklı yetkilere sahip iki aktör arasında paylaşılıyorsa ya aktör boyutunu taşır ya da içeriği aktörden bağımsızdır.

### Her P0'ı yakalayacak regresyon testleri

| Test | Yakaladığı | Nasıl |
|---|---|---|
| **T-1** `test_dash_update_component_requires_session` | P0-1 | Cookie'siz `POST /_dash-update-component` (`overview-page-root.children`) → `401` assert. Cookie'li → `200`. |
| **T-2** `test_admin_flush_does_not_touch_foreign_namespace` | P0-2 | `dl:fecache:CANARY` yaz → datacenter-api `POST /admin/cache/refresh` → canary hâlâ var. Ayrıca `cache_flush_pattern("*")` → `ValueError` assert. |
| **T-3** `test_entry_without_timestamp_is_stale` | P0-3 | Key'i ısıt, timestamp'i düşür, `_is_fresh(key) is False` assert; getter'ı çağır → upstream mock'u **çağrılmış** olmalı. |
| **T-4** `test_degraded_payload_is_flagged_and_not_rendered_as_zero` | P0-4 | Upstream'i `httpx.ConnectError` fırlatacak şekilde mock'la, cache boş → dönen dict `_degraded is True`; `build_overview` çıktısında "0" KPI **yok**, hata kartı **var**. |
| **T-5** `test_inflight_wait_exceeds_max_leader_timeout` | P0-4 | `_INFLIGHT_WAIT_SECONDS >= _INVENTORY_READ_TIMEOUT` assert (config invariant testi, çalıştırması bedava). |
| **T-6** `test_overview_kpi_matches_treemap_total` | P0-5 | `build_overview` çıktısındaki "Total VMs" KPI'ı == treemap `dc_vms` toplamı. Endpoint'lerin farklı payload döndürdüğü mock ile de geçmeli. |
| **T-7** `test_compute_cache_key_distinguishes_anchor` | P0-6 | `_compute_cache_key(...tr_anchored) != _compute_cache_key(...tr_plain)`; ayrıca `get_classic_metrics_filtered`'ı iki farklı anchor ile çağırıp SQL mock'unun **iki kez** çağrıldığını assert et. |
| **T-8** `test_compute_stale_triggers_revalidate` | P0-6 | Fresh TTL'i geçmiş entry ile çağır → stale değer döner **ve** `_set_compute_cached` çağrılır. |
| **T-9** `test_gui_cache_entries_have_bounded_ttl` | P0-8 | `RedisBackend.set` sonrası fake redis'te `ex` parametresi geçilmiş olmalı (`> 0`). |
| **T-10** `test_refresh_is_write_through` | P1-4 | `_rebuild_customer_caches_for_customer` çağrısında `cache.delete` **çağrılmış** ve `factory` **çalışmış** olmalı. |
| **T-11** `test_page_root_has_single_writer_per_input` | P1-1 | Statik test: `app.dash_app.callback_map` üzerinde, aynı `app-time-range.data` Input'unu paylaşan ve output'ları ata-torun ilişkisinde olan callback çifti **olmamalı**. Bu tek test RC-6'nın tüm varyantlarını yakalar. |
| **T-12** `test_no_cache_key_builder_omits_dimension` | I-1 | Statik: `api_client` içindeki her `ck = f"api:..."` için, fonksiyonun parametrelerinin key'de temsil edildiğini kontrol eden bir lint. (Başlangıç olarak allow-list ile.) |

---

## 6. Sıralı Uygulama Önerisi

Bağımlılıklar var, bu sırayı takip edin:

1. **Dalga A (tek deploy, ~1 gün):** P0-1 (auth), P0-2 (db + flush), P0-7 (worker), P0-8 (Redis TTL/policy). Bunlar birbirinden bağımsız ve infra ağırlıklı; en büyük riski en hızlı düşürüyorlar.
2. **Dalga B (~2 gün):** P0-3 (timestamp atomik) + P0-4 (degrade sentinel + follower budget). **Birlikte** shipping edilmeli — P0-3 tek başına deploy'da cold storm yaratır, P0-7 ve P0-4 onu absorbe eder.
3. **Dalga C (~1 gün):** P0-5 (Overview snapshot), P0-6 (compute key + revalidate). Bağımsız, hızlı, ölçülebilir.
4. **Dalga D (~3 gün):** P1-1 (Dash tek yazar) — en geniş yüzey, en dikkatli test. P1-2/3 bunun üstüne oturuyor.
5. **Dalga E:** P1-4…P1-8 backend invalidation'ları.
6. **Dalga F:** P2 hardening + observability. **P2-12'yi (metrikler) öne alın** — Dalga A ile birlikte gitsin ki sonraki dalgaların etkisi ölçülebilsin.

---

## 7. DOĞRULANMAMIŞ / AÇIK

Bunlar rapordan çıkarılmadı, çünkü gizlemek yanlış olur. Hiçbiri "temiz" varsayılmamalı.

### Mekanizması doğrulandı, kullanıcı etkisi ölçülmedi

- **Customer View perspective reset** (`customer_view_callbacks.py:127`) — kaynak kodda uçtan uca doğrulandı, **tarayıcıda tekrarlanmadı**. Browser session gerekiyor.
- **Virt cluster filter desync** (`app.py:1148-1157`) — cache defect'i API seviyesinde kanıtlandı, **UI akışı olarak denenmedi**. İki sonuçtan hangisinin baskın olduğu (filtre sessizce resetleniyor mu, yoksa selector/panel gerçekten uyumsuz mu) ölçülmedi; ilki çok daha olası.
- **Customer View Backup duplicate Store + `_fill_backup` guard eksiği** — statik doğrulandı, "page-root write başına iki dispatch" iddiası **kanıtlanamadı** (bir dispatch kanıtlandı).
- **customer-api `:last_good` 24 saatlik freeze** — yapı statik olarak doğrulandı ve db1'de canlı `:last_good` twin'leri görüldü (`customer_assets:netbackup-policy-v4:Boyner:2026-07-27:2026-08-03:last_good`), ama **çok saatlik zamanlama deneyi yapılmadı**. Not: "gece yarısı zıplaması"nın tetikleyicisi shadow expiry değil, **UTC tarih rollover'ı** (`services/customer-api/app/utils/time_range.py:61-67` `_today_utc()` → yeni key → cold SQL).
- **Follower timeout'un production'da gerçekten sıfır ürettiği** — local'de leader 66 s'de bitti, 125 s'lik pencereye sığdı, yani **yerel olarak bir follower timeout'u tetiklenemedi**. Rapor edilen şey konfigürasyon boşluğu (125 < 300) + zaten ölçülmüş 66 s cold fetch + kodun kendi yorumundaki ">60s overview". Production VPN DB'sinde bu süre daha uzun.
- **1H preset'in Redis'i doldurup warm key'leri evict ettirdiği** — key churn mekanizması kanıtlandı, kaskad (`INFO memory` / `evicted_keys` ile) **kanıtlanmadı**.

### Hiç dokunulmamış yüzeyler

Aşağıdaki sayfalar **ne tarayıcıda ne de probe ile** çalıştırıldı. Temiz sayılmamalı:
`/availability-annual`, tekil `/customer-view?customer=X`, `/crm/sellable-potential`, `/unmapped-resources`, `/query-explorer`, `/administration` (Settings), floor map sayfası.

`POST /api/v1/admin/cache/refresh` bir kez **kasıtlı olarak** çalıştırıldı (finding'in kanıtı buydu) ama bunun uçtan uca kullanıcı deneyimi (tüm sayfaların aynı anda cold'a düşmesi) scratch instance'ta ayrıca doğrulanmalı.

### Çürütülen iddialar (tekrar araştırılmasın)

- **H3 (SWR stale-then-fresh swap görünür)** — YANLIŞ. `_api_cache_get_with_stale` gerçekten no-stale (`api_client.py:565-572`). SWR TTL'i ayarlamak hiçbir şeyi düzeltmez.
- **H1'in cache kısmı** — worker recycle **cache'i kaybettirmiyor** (Redis'te; canary testiyle kanıtlandı). Kaybettirdiği availability ve `_inflight`.
- **H4 (namespace mismatch)** — prefix'ler doğru, customer-api db1 / crm-engine db2 düzgün izole. Sorun **paylaşılan database** + `*` flush.
- **H8 (stale bundle serve ediliyor)** — YANLIŞ, tam tersi: hiçbir şey cache'lenmiyor. Bu bir bandwidth defect'i, correctness defect'i değil, ve "içerik render olup eski değere dönüyor" semptomunu **üretemez**.
- **Backend read-path nondeterminizmi** — YOK. 6 datacenter-api endpoint'i × 5 ardışık çağrı, md5 ile karşılaştırıldı: 30/30 identical. Flip'ler cache katmanından geliyor, backend'den değil.
- **`_should_persist_api_cache` bozuk** — DEĞİL, doğru çalışıyor (live doğrulandı: backend down iken sıfırlar persist edilmedi). Bu iyi mühendislik; sorun sıfırların **render edilmesi**.
- **k8s multi-pod split-brain** — kanıtlanmadı. `app.py:137-155`'teki `CallbackException("Inputs do not match")` handler'ı bunun kanıtı **değil** — o, herhangi bir redeploy'u straddle eden uzun ömürlü sekmenin normal semptomu (tek-pod docker-compose restart'ında da olur). Ayrıca pod-to-pod cache divergence'ı zaten `k8s/frontend/configmap.yaml`'daki paylaşılan `REDIS_URL` ile kapatılmış. Geriye kalan gerçek sorun: mutable `:latest` tag'i (P2-8).
- **Permission fail-open'ın DB outage ile tetiklendiği** — YANLIŞ. DB ölüyse istek zaten `before_request`'te 500 veriyor (`src/auth/middleware.py:64-70` → `src/auth/db.py:71-75`, exception handling yok). Gerçek tetikleyici: `/_dash*` path'inde `g.auth_user_id`'nin None olması. Etki: sadece statik menü etiketleri.

### Tooling notu (tekrar denenecekse)

Tarayıcı tarafında `read_page`/`find` her denemede boş döndü; tüm DOM incelemesi `javascript_tool` + screenshot ile yapıldı. Büyük `textContent` dump'ları privacy filter'a takıldı → küçük hedefli regex'ler gerekti. `javascript_tool` ~8 s'den uzun sampling loop'larında 45 s CDP timeout'u verdi → `setInterval` recorder + ayrı dump gerekti. Trailing-debounce'lu `MutationObserver` sürekli mutation akışında hiç ateşlemedi ve ara blank state'leri gizledi → leading-edge throttle kullanıldı.