# Mapping Kaydında Cache Invalidation + Warm

**Date:** 2026-07-17
**Status:** Design → implementation
**Owner:** Arca

## Özet (TR)

Customer alias source-mapping kaydedildiğinde, o mapping'in etkilediği kaynak
cache'i **hiç temizlenmiyor**. Sonuç: kullanıcı mapping'i kaydediyor, ekran
"kaydedildi" diyor, rozet bile güncelleniyor — ama müşterinin kaynak görünümü
**~24 saate kadar** eski mapping'e göre kalıyor. Kendiliğinden düzelmesinin
garantisi yok.

Bu spec, mapping'i değiştiren **beş yazma yolunun** hepsine hedefli invalidation
ve debounce'lu arka plan warm ekliyor. Kök neden (singleflight'ın `last_good`
shadow'una düşmesi) **bu sprintte kapsam dışı** — ayrı spec'e bırakıldı.

## Motivasyon

Mapping özelliği, kaynakların hangi müşteriye ait olduğunu belirleyen tek
mekanizma. Yanlış veya bayat mapping = müşteriye yanlış kaynak atfı. Şu an
özellik **sessizce çalışmıyor**: kaydediyorsun, olmuyor, ama sistem sana
olduğunu söylüyor. Bir config aracının verebileceği en kötü geri bildirim bu.

Aciliyet sebebi: sistemde **352 müşteri** var ve şu an **0 mapping** tanımlı
(`GET /api/v1/crm/aliases` → tüm `source_mappings` boş). Yani rollout önde —
biri oturup yüzlerce müşteriyi maplerken her kayıt sessizce etkisiz kalacak.

## Kanıt (canlı sistemden ölçüldü, 2026-07-16)

Statik analiz değil, çalışan `bulutistan-redis` DB 1 üzerinde ölçüm:

**1. Zombie key'ler gerçek.** 11 `customer_assets:*` key'inin 3'ü primary,
8'i `:last_good`. Bunların **5'i zombie** — primary'si expire olmuş, shadow'u
hâlâ yaşıyor:

```
customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16
  primary  : YOK
  last_good: 64510s (~18 saat) yaşıyor
```

`cache_run_singleflight` (`cache_backend.py:219`) → `cache_get` (`:107-112`)
shadow'a düşüyor → factory hiç koşmuyor → mapping hiç yeniden uygulanmıyor.
15dk/6sa scheduled warm job'lar da aynı sebeple **no-op**.

**2. Bir hesap birden fazla display name altında cache'leniyor.**

```
customer_assets:cpu-usage-v3:Boyner:...
customer_assets:cpu-usage-v3:BOYNER BÜYÜK MAĞAZACILIK A.Ş.:...
```

`Boyner` hardcoded legacy pilot ismi (`src/services/db_service.py:45`
`WARMED_CUSTOMERS = ("Boyner",)`; aynısı `dc_service.py:85`), diğeri CRM ünvanı
(accountid `e876d81f-…`). O hesabın alias satırında `canonical_customer_key` ve
`netbox_musteri_value` **null** — yani `Boyner` ismi alias tablosundan
türetilemiyor. **Tek isimle silmek kanıtlanmış şekilde yetersiz.**

## Kök neden vs. bu sprintin kapsamı

| Katman | Sorun | Bu sprint |
|---|---|---|
| Invalidation yok | 5 yazma yolu kaynak cache'ini silmiyor | **Kapsamda** |
| `last_good` read-through | TTL dolunca recompute yerine shadow dönüyor | **Kapsam dışı** → ayrı spec |

Kök neden düzeltilirse şu an no-op olan tüm warm job'lar gerçekten koşmaya
başlar ve DB yükü ciddi artar. Ölçüm ve ADR-0007 revizyonu gerektirir; ayrı ele
alınacak. Bu sprint kök nedene **dokunmuyor**, sadece invalidation ekliyor —
invalidate edilen key'de zaten shadow da silindiği için read-through sorunu bu
akışı engellemiyor.

## Tasarım

### Çekirdek fikir: isimleri sayma, cache'ten oku

İsim listesi çıkarmak kırılgan (hardcoded `Boyner`, CRM ünvanı, null canonical
key). Onun yerine invalidation şöyle çalışır:

1. `customer_assets:{VER}:*` SCAN
2. Her key'i kuyruk-sabitli regex ile parse et → `name`
3. `name` → `account_id`, **okuma yolunun kendi resolver'ıyla**
   (`CustomerService._lookup_alias_for_display_name`), run başına memoize
4. `account_id == hedef` olan key'leri sil

**İnşaat gereği doğru:** okuma yolu (`_load_customer_resources` →
`resolve_source_patterns` → `_lookup_alias_for_display_name`) bir görünümü hangi
hesabın kurallarıyla hesaplıyorsa, invalidation aynı fonksiyondan aynı cevabı
alır. İsim listesi tutulmadığı için drift imkânsız. `Boyner` o hesaba
çözülüyorsa silinir; çözülmüyorsa zaten o hesabın mapping'i o görünümü
etkilemiyordur.

**Maliyet:** cache'teki distinct isim sayısı = *görüntülenmiş* müşteri sayısı
(bugün 3), 352 değil. Warm set (VIP + mapped non-VIP) ile sınırlı. Memoize
edilir. Config aksiyonu, hot path değil.

### Key parse regex

`split(":")` işe yaramaz: isimler boşluk/nokta/Türkçe karakter içeriyor ve `1h`
preset key'i `Boyner:2026-07-16T13:54:18Z:...` gibi **içinde iki nokta olan**
timestamp taşıyor. Tarih formatı kuyruğa sabitlenerek çözülür:

```python
KEY_RE = re.compile(
    r"^customer_assets:"
    r"(?P<version>[^:]+):"                                    # versiyona bağlanma
    r"(?P<name>.+):"
    r"(?P<start>\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}Z)?):"
    r"(?P<end>\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}Z)?)"
    r"(?P<shadow>:last_good)?$"
)
```

Doğrulandı: 11 gerçek key'in 11'i parse edildi (0 hata), ayrıca sentetik zor
vakalar — `Weird:Name:With:Colons`, `A.Ş.`, `4A KOZMETİK … ŞİRKETİ`, `1h`
timestamp preset'i.

**Versiyon token'ı `[^:]+` ile yakalanır, sabite bağlanmaz.** Sebebi teorik
değil: `CUSTOMER_ASSETS_CACHE_VERSION` şu anda `cpu-usage-v3` → `netbackup-policy-v4`
olarak değiştiriliyor (paralel iş, henüz commit'lenmemiş). Versiyon regex'e
gömülürse ilk bump'ta invalidation sessizce hiçbir key'i eşleştirmez —
**düzeltmeye çalıştığımız bug'ın aynısı, yeni kılıkta.** Versiyon token'ında iki
nokta olmadığı için `[^:]+` güvenli.

Yan fayda: eski sürüm key'leri (`cpu-usage-v3:*`, bump'tan sonra artık
okunmayan yetim kayıtlar) de eşleşir ve temizlenir. SCAN prefix'i sadece
`customer_assets:` — versiyonsuz.

Aynı gerekçeyle **GUI tarafı da versiyonsuz prefix siler**:
`delete_prefix("api:customer_resources:")`. GUI'de versiyon şu an hardcoded
(`api_client.py:709`) ve düzeltmesi paralel işte; versiyonsuz prefix her iki
halde de doğru çalışır ve o işle çakışmaz.

### İki katman, iki strateji

Maliyetler asimetrik olduğu için strateji de farklı:

| Katman | Namespace | Strateji | Neden |
|---|---|---|---|
| Backend | `customer_assets:` (Redis DB 1) | **Hedefli** | Yeniden kurmak DB sorgusu, pahalı |
| GUI | `api:customer_resources:` (`dl:fecache:`) | **Komple sil** | Backend'den çeker, o da cache'li → ucuz. Ayrıca GUI cache'inde **hiç TTL yok** (`cache_service.py:137`), silinmezse ölümsüz |

### Silinecekler (her mapping yazımında)

- Hedef hesabın `customer_assets:*` → primary + `:last_good`
  (`cache_delete_prefix` pattern'i `{prefix}*` olduğu için shadow'u da kapsar,
  `cache_backend.py:172`)
- `unmapped_resources:*` → **global**; complement değiştiği için her mapping
  yazımı tüm unmapped setini etkiler (`customer_service.py:484`)
- `ALIASES_SNAPSHOT_KEY`, `CATALOG_SNAPSHOT_KEY` → zaten var, korunur
- GUI tarafı: `api:customer_resources:*`, `api:customer_catalog`,
  `api:customer_overview`

### Warm

- **Debounce: 10sn**, hesap bazlı. Aynı hesaba 10sn içinde ikinci kayıt gelirse
  önceki warm iptal olur — rollout'ta ard arda düzeltmede boşuna sorgu atmaz.
- Debounce **process-içi** (timer + dict). Bugün güvenli: customer-api tek
  uvicorn process'i olarak koşuyor, `--workers` yok
  (`services/customer-api/Dockerfile:24`). Birden fazla replika'ya çıkılırsa en
  kötü senaryo replika sayısı kadar warm koşması — zararsız (idempotent, sadece
  fazladan sorgu). Cross-pod debounce gerekirse Redis lock'a taşınır; bugün
  gereksiz karmaşıklık.
- Daemon thread (mevcut pattern: `scheduler_service.py:112-126`)
- Mevcut primitive kullanılır: `_rebuild_customer_caches_for_customer(name)` —
  3 preset × (resources + s3) = 6 sorgu
- Invalidate **senkron** (kaydet dönmeden önce), warm **asenkron**. Kullanıcı
  hemen sayfaya giderse kendi read-through'u doğru veriyi hesaplar; sadece o ilk
  hit yavaş olur. Doğruluk her durumda garanti.
- Warm, invalidate edilen isim seti için koşar (genelde 1-2 isim)

### Kapsanan yazma yolları

Beşinin de mapping sonucunu değiştirdiği doğrulandı:

| Yol | Dosya | Şu anki durum |
|---|---|---|
| `save_source_mappings` | `sales_service.py:642` | 2 snapshot siliyor, asıl cache'i silmiyor |
| `seed_boyner_source_mappings` | `sales_service.py:692` | 14 mapping basıyor, **hiç invalidation yok** |
| `resync_aliases_from_datalake` | `sales_service.py:731` | Toplu mapping değiştiriyor, **hiç yok** |
| `upsert_alias` | `sales_service.py:836` | `netbox_musteri_value`/`canonical_key` → `resolve_infra_search_name` fallback'ini, dolayısıyla kaynak çözümünü değiştirir, **hiç yok** |
| `delete_alias` | `sales_service.py:851` | Aynı, **hiç yok** |

`resync` ve `seed` birden fazla hesabı etkileyebilir → invalidation hesap
listesi alacak şekilde tasarlanır (`invalidate_for_accounts(ids)`), tekil hal
onun özel durumu.

### Bileşenler

**Yeni:** `services/customer-api/app/services/mapping_cache_invalidator.py`

Tek sorumluluk: mapping değişiminin cache etkisini uygulamak. Dash/FastAPI
importu yok, saf fonksiyonlar + enjekte edilen resolver → izole test edilebilir.

```python
def parse_customer_assets_key(key: str) -> ParsedKey | None
def invalidate_for_accounts(
    account_ids: set[str],
    *,
    resolve_account_id: Callable[[str], str | None],
    scan_keys: Callable[[str], Iterable[str]],
    delete_keys: Callable[[Iterable[str]], None],
) -> InvalidationResult   # deleted_count, matched_names, unresolved_names
```

**Wiring:** `SalesService` zaten `main.py:48-56`'da `CustomerService`'ten
callable alıyor (`get_customer_assets`). Aynı pattern:

```python
app.state.sales = SalesService(
    ...,
    invalidate_mapping_caches=lambda ids: svc.invalidate_mapping_caches(ids),
)
```

Circular import yok, `SalesService` `CustomerService`'i tanımaz.

`CustomerService.invalidate_mapping_caches(ids)` — invalidator'ı gerçek
resolver/Redis ile bağlar, `unmapped_resources:*` siler, debounce'lu warm'ı
tetikler.

**GUI:** `src/services/api_client.py` — `put_crm_source_mappings` ve diğer 4
yazma sarmalayıcısı kendi namespace'ini temizler. `set_customer_vip`'teki
mevcut pattern (`api_client.py:703-704`) genişletilir.

### Veri akışı

```
Kullanıcı "Kaydet" → PUT /crm/aliases/{id}/source-mappings
  └─ SalesService.save_source_mappings
       ├─ DB: DELETE + UPSERT   (tek transaction — aşağı bakınız)
       ├─ cache.delete(ALIASES_SNAPSHOT_KEY, CATALOG_SNAPSHOT_KEY)
       └─ invalidate_mapping_caches({account_id})        [senkron]
            ├─ SCAN customer_assets:{VER}:*
            ├─ parse → name → resolve → account_id
            ├─ delete (primary + last_good)
            ├─ delete_prefix("unmapped_resources:")
            ├─ log(deleted_count)  → 0 ise WARNING
            └─ schedule_warm(names, debounce=10s)        [asenkron]
  └─ GUI api_client: kendi namespace'ini temizler
```

### Hata yönetimi

- Invalidation **hata yutmaz**. Şu anki `try/except: pass`
  (`sales_service.py:685-689`) bu bug'ın sessiz kalmasının sebebi.

  Redis erişilemezse: **log ERROR + kullanıcıya görünür uyarı**, ama 500 değil.
  Gerekçe: invalidation yazımdan *sonra* koştuğu için **DB zaten commit olmuş**
  durumda. Sert hata dönmek "başarısız" derken aslında kaydedilmiş olması
  demek — kullanıcıyı yanıltır. Sessizce başarı dönmek ise düzeltmeye
  çalıştığımız bug'ın ta kendisi. İkisi de yanlış; doğrusu gerçeği söylemek:

  > *"Mapping kaydedildi, ancak cache temizlenemedi — lütfen tekrar kaydedin."*

  Tekrar kaydetmek güvenli: `save_source_mappings` idempotent (DELETE + UPSERT),
  ikinci deneme invalidation'ı yeniden tetikler.

  **Cevap şekli değişikliği (gerekli):** `PUT /crm/aliases/{id}/source-mappings`
  şu an düz `List[dict]` dönüyor (`sales.py:166`, `response_model=List[dict]`) —
  uyarı taşıyacak yer yok. Şuna dönüşür:

  ```python
  {"mappings": [...], "cache_warning": str | None}
  ```

  Etkilenen üç yer, hepsi dar: router `response_model`, GUI istemcisi
  `put_crm_source_mappings` (`api_client.py:2233`, şu an
  `out if isinstance(out, list) else []` → yeni şekle uyarlanır) ve kaydet
  callback'i `save_editor_mappings_cb` (`crm_aliases_callbacks.py:317`, uyarıyı
  `dmc.Notification`/alert olarak gösterir).

- **`resolved is None` ile `resolution errored` ayrılır.** Kritik: bugünkü
  `_lookup_alias_for_display_name` istisnayı yutup `(None, None, None)` dönüyor
  (`customer_service.py:755-757`). Bu ayrım yapılmazsa geçici bir DB hıçkırığı
  → isim çözülemez → key silinmez → **sessizce bayat kalır**; yani düzelttiğimiz
  bug'ı yeni bir kılıkta geri getiririz.
  - `resolved is None` (temiz sonuç: isim hiçbir hesaba ait değil) → key
    atlanır, doğru davranış. Okuma yolu da `account_id=None` görüp
    `fallback_search_name`'e düşer, yani o hesabın kuralları o görünümü
    etkilemiyordur.
  - `resolution errored` (istisna) → **invalidation'ın tamamı başarısız sayılır**
    → Redis hatasıyla aynı muamele: log ERROR + `cache_warning`. Emin olmadığımız
    key'i sessizce atlamayız.
  - İhtiyaç: invalidator, istisnayı yutmayan bir resolver ile beslenir
    (`_lookup_alias_for_display_name`'in yutmayan bir varyantı ya da parametre).

- `deleted_count == 0` → **WARNING** (`account_id`, çözülemeyen isimlerle).
  Sessiz ıskalama bu bug'ın en tehlikeli hali.
- Warm hatası **yutulur** ve loglanır — warm bir optimizasyon; başarısız olması
  doğruluğu bozmaz (cache boş kalır, read-through hesaplar).

### Ek: `save_source_mappings` atomicity

`WebuiDb.execute` her statement'ta commit ediyor (`webui_db.py:105-111`).
`save_source_mappings`'teki DELETE (`:659`) loop ortasında patlarsa **zaten
commit olmuş** → hesabın mapping'leri yarım kalır (silinmiş ama yeniden
yazılmamış).

Bu, invalidation açısından da önemli: yarım kalmış bir yazımdan sonra
invalidation koşarsa cache'i *yanlış* duruma göre temizler. DELETE + UPSERT tek
transaction'a alınır.

Bu dosya (`sales_service.py`) zaten bu spec'in ana dokunma noktası ve başka
hiçbir plan atomicity'yi kapsamıyor → burada kalır.

## Test

**Birim (invalidator, izole):**
- `parse_customer_assets_key`: gerçek key örnekleri + `1h` timestamp preset'i +
  isimde iki nokta + Türkçe karakter + `:last_good` eki + parse edilemeyen key
- `invalidate_for_accounts`: eşleşen silinir, eşleşmeyen dokunulmaz,
  `deleted_count` doğru, `unresolved_names` doldurulur

**Entegrasyon (customer-api, fake Redis):**
- 5 yazma yolunun her biri invalidation'ı tetikliyor
- primary **ve** `:last_good` birlikte siliniyor (zombie bırakmıyor)
- `unmapped_resources:*` siliniyor
- Redis hatası → `cache_warning` dolu dönüyor, **500 değil**, log ERROR basılıyor,
  mapping DB'de duruyor
- Resolver istisnası → aynı muamele (`cache_warning`), sessizce atlanmıyor
- `deleted_count == 0` → WARNING loglanıyor
- Mutlu yol → `cache_warning is None`

**Regresyon (asıl bug):**
- Cache'i doldur → mapping kaydet → `get_customer_resources` **yeni** mapping'e
  göre hesaplıyor mu? (Şu an bu test kırmızı olmalı — fix'ten sonra yeşil.)

**auranotify:**
- `save_source_mappings(data_source="auranotify")` → 500 değil, kaydediyor
- Loop ortasında hata → mapping'ler yarım kalmıyor (transaction)

**Debounce:**
- 10sn içinde 2 kayıt → 1 warm koşuyor

## Kapsam dışı

- **Kök neden** (`cache_run_singleflight`'ın `last_good`'a düşmesi) → ayrı spec.
  Şu an no-op olan warm job'ları canlandırır, DB yük profili ölçümü ve ADR-0007
  revizyonu gerektirir.
- **GUI `_is_fresh` fails-open** (`api_client.py:486-493`): `age is None` →
  "sonsuza kadar taze". Warm-written key'ler timestamp sidecar taşımadığı için
  hiç yaşlanmıyor. Ayrı iş.
- **`1h` preset key sızıntısı**: key'e saniye çözünürlüklü timestamp gömülü
  (`customer_service.py:395-400`) → her görüntüleme 2 yeni key, biri 24h yaşıyor.
  Redis'te sınırsız birikim. Ayrı iş.
- **`Boyner` hardcoded legacy ismi** (`db_service.py:45`, `dc_service.py:85`) →
  temizlenmeli ama bu spec ona dokunmuyor; tasarım zaten ismin varlığına dayanmıyor.
- **Sellable / crm-engine**: `gui_crm_customer_source_mapping` okumuyor, bu
  akışta değil.
