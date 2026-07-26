# TASK-01 — CRM Inventory Cache Optimizasyonu

**Tip:** Performans / Backend · **Efor:** M · **Öncelik:** Yüksek (sayfa çöküyor)

## Hedef
`/crm/inventory-overview` sayfası veri yüklerinde çöküyor. Sayfanın her koşulda ayakta kalması,
soğuk cache'te bile kullanıcıya anlamlı bir şey göstermesi.

## Mevcut durum (kodda ne var)

| Katman | Dosya |
|---|---|
| Sayfa (2 fazlı shell) | `src/pages/crm_inventory_overview.py` — Faz A skeleton, Faz B `_fill_crm_inventory_content` |
| Shell/skeleton | `src/components/crm_inventory_shell.py`, `src/components/crm_inventory_loading.py` |
| Tablo render | `src/components/crm_inventory_report.py` (988 satır) |
| API client | `src/services/api_client.py :: get_crm_inventory_overview(dc_code, force_recompute)` |
| Endpoint | `services/crm-engine/app/routers/inventory.py :: GET /api/v1/crm/inventory-overview` |
| Hesap | `services/customer-api/app/services/inventory_overview_service.py` |

Mevcut cache/parallel ayarları (`inventory_overview_service.py` başı):
```python
_INVENTORY_CACHE_TTL_SEC = float(os.getenv("INVENTORY_OVERVIEW_CACHE_TTL", "600"))
_INVENTORY_REDIS_PREFIX  = "crm:inventory_overview:"
_INVENTORY_DC_PARALLELISM = int(os.getenv("INVENTORY_DC_PARALLELISM", "4"))
```
Cache okuma satır ~1045, yazma ~1228, warm fonksiyonu `warm_inventory_cache(dc_code="*")` ~1237.
Ayrıca servis içi 120 sn'lik mapping/pages/panel-defs mikro-cache'leri var (satır ~524-561).

## Kök neden hipotezleri (sırayla test edilecek)

1. **TTL/refresh oranı bozuk** — TTL 600 sn, scheduler 15 dk (900 sn). TTL < refresh ⇒ her turda
   *mutlaka* bir soğuk pencere oluşuyor ve o pencerede tam hesap request path'te çalışıyor.
   `docs/CACHE_STRATEGY_COMPARISON.md` §4a'ya göre **TTL ≥ 4 × refresh** olmalı.
2. **`last_good` shadow key yok** — Redis miss + DB timeout = boş sayfa / 500.
3. **Thundering herd** — cache expire anında N kullanıcı aynı anda tam hesabı tetikliyor; distributed lock yok.
4. **DC fan-out belleği** — `INVENTORY_DC_PARALLELISM=4` ile ThreadPool, her DC için tam panel seti;
   `datacenter-api` tarafında benzer bir OOM daha önce yaşandı (bkz. commit `180431ae` — IBM batch SQL aggregation).
5. **Frontend payload boyutu** — tüm aileler tek `dash_table` setinde; satır sayısı arttıkça tarayıcı kilitleniyor.

## Yapılacaklar

- [ ] **Ölç:** `force_recompute=true` ile soğuk süre, sıcak süre, payload boyutu, crm-engine RSS (`docker stats`).
- [ ] **TTL düzelt:** `INVENTORY_OVERVIEW_CACHE_TTL=3600` (env + `.env.example` + docker-compose default).
- [ ] **`last_good` shadow key ekle:** `cache_set` her başarılı yazmada `{key}:last_good` (TTL ×2) yazar;
      request path'te primary miss ⇒ `last_good` ⇒ `X-Cache: stale` header. 503 yalnızca ikisi de yoksa.
- [ ] **Single-flight lock:** Redis `SET key:lock NX EX 300`. Lock alamayan istek `last_good` döner,
      hesabı tekrarlamaz.
- [ ] **Warm scheduler:** `warm_inventory_cache("*")` uygulama açılışında **background thread**'de
      (datacenter-api'de `warm_cache()` için yapılan çözümün aynısı — `/health` bloklanmasın) + 15 dk periyot.
- [ ] **Bellek:** DC fan-out'unda ara sonuçları biriktirmek yerine akümülatöre indirgeyin; gerekirse
      `INVENTORY_DC_PARALLELISM=2`'ye düşürüp ölçün.
- [ ] **Frontend:** `dash_table` için `page_size` / `virtualization=True`; aile bazlı accordion'da yalnızca
      açık olan aile render edilsin (lazy children).
- [ ] **Hata dayanıklılığı:** `_fill_crm_inventory_content` içindeki `except` boş liste yerine
      "veri hazırlanıyor / son bilinen veri" durumunu göstersin (LOADING_UX standardı).

## Doğrulama

```bash
# Soğuk / sıcak süre
time curl -s "http://10.134.52.250:8070/api/v1/crm/inventory-overview?dc_code=*&force_recompute=true" -o /tmp/inv_cold.json
time curl -s "http://10.134.52.250:8070/api/v1/crm/inventory-overview?dc_code=*" -o /tmp/inv_warm.json
python3 -c "import json;d=json.load(open('/tmp/inv_warm.json'));print({k:(len(v) if isinstance(v,list) else v) for k,v in d.items()})"

# Cache anahtarları ve TTL
docker exec bulutistan-redis redis-cli -n 2 --scan --pattern "crm:inventory_overview:*"
docker exec bulutistan-redis redis-cli -n 2 TTL "crm:inventory_overview:*"

# Bellek/CPU
docker stats --no-stream bulutistan-crm-engine bulutistan-customer-api

# Eşzamanlılık (thundering herd testi) — 20 paralel soğuk istek
seq 20 | xargs -P20 -I{} curl -s -o /dev/null -w "%{http_code} %{time_total}\n" \
  "http://10.134.52.250:8070/api/v1/crm/inventory-overview?dc_code=*"
```

```sql
-- Kaç ürün satırı işleniyor (yükün büyüklüğü)
SELECT COUNT(DISTINCT d.productid) AS satilan_urun,
       COUNT(*)                    AS siparis_satiri
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
WHERE  so.statecode = 0;

-- Panel tanımı sayısı (fan-out çarpanı)
SELECT COUNT(*) FROM gui_panel_definition;            -- bulutwebui
SELECT COUNT(*) FROM gui_crm_service_mapping_seed;    -- bulutwebui
```

## Kabul kriterleri

- [ ] Sıcak cache ile `GET /crm/inventory-overview` p95 **< 800 ms**
- [ ] Soğuk cache'te sayfa **çökmüyor**; skeleton + `X-Cache: stale` ile son bilinen veri geliyor
- [ ] 20 paralel soğuk istekte tek hesap çalışıyor (log'da tek "computing" satırı), hepsi 200 dönüyor
- [ ] crm-engine RSS soğuk hesap sırasında konteyner limitinin %70'ini aşmıyor
- [ ] Redis restart edilse bile sayfa 500 vermiyor (memory fallback)

## Cursor / Claude Code prompt

```
Bağlam dosyaları: task/GUI/00-ortam-ve-dogrulama-rehberi.md, docs/CACHE_STRATEGY_COMPARISON.md (§4a),
docs/PROD_ARCHITECTURE.md (Faz 1), services/customer-api/app/services/inventory_overview_service.py,
services/crm-engine/app/routers/inventory.py, src/pages/crm_inventory_overview.py

Görev: /crm/inventory-overview sayfasının soğuk cache'te çökmesini engelle.

1. Önce ölç: force_recompute=true ve normal istek için süre + crm-engine bellek kullanımını raporla.
   Ölçmeden kod değiştirme.
2. inventory_overview_service.py içinde:
   - INVENTORY_OVERVIEW_CACHE_TTL varsayılanını 3600'e çek (env ile override edilebilir kalsın).
   - Her başarılı cache_set'te "{key}:last_good" shadow key'i TTL*2 ile yaz.
   - Request path: primary miss -> last_good -> (yoksa) hesapla. last_good servis edilirken
     yanıt meta'sına stale=true ekle, router X-Cache: stale header'ı döndürsün.
   - Redis SET NX EX 300 ile single-flight lock ekle; lock alamayan istek last_good döner.
   - warm_inventory_cache uygulama açılışında background thread'de çalışsın, /health'i bloklamasın.
3. src/pages/crm_inventory_overview.py: hata durumunda boş liste yerine
   docs/LOADING_UX_DESIGN.md standardında "son bilinen veri" uyarı bandı göster.
   dash_table'lara virtualization=True + page_size ekle.
4. tests/ altında: TTL varsayılanı, last_good fallback, lock davranışı için unit test yaz (TDD).
5. .env.example ve docker-compose.yml'deki ilgili varsayılanları güncelle.

Kısıt: "yeni veri gelmeden eski veri silinmez" ilkesi bozulmayacak. Cross-DB JOIN ekleme.
Değişiklik sonrası aynı ölçümleri tekrarla ve önce/sonra tablosu ver.
```

## Notlar / risk
- TTL büyütmek "bayat veri" şikayeti doğurabilir → warm scheduler 15 dk'da bir yazdığı için pratikte veri tazeliği değişmez.
- `INVENTORY_DC_PARALLELISM` düşürmek süreyi uzatır, belleği düşürür — ölçüme göre karar verin.
- TASK-10 (network/switch satırları) bu sayfaya satır ekleyecek; cache düzeltmesi **önce** bitmeli.
