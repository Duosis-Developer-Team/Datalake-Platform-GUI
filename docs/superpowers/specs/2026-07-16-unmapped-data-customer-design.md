# Unmapped Data Customer (Eşleşmeyen Veriler)

**Date:** 2026-07-16
**Task:** TASK-54, item 1
**Status:** Design → implementation
**Owner:** Arca

## Özet (TR)

Hiçbir müşteriye ait olmayan kaynakları toplayan sanal bir müşteri ("Eşleşmeyen
Veriler") oluşturuyoruz. Müşteri listesinde normal bir müşteri gibi görünür,
detay sayfasında sahipsiz kaynaklar hizmet hizmet listelenir. **Faz 1: yalnızca
sanallaştırma (VM).** Diğer 8 veri kaynağı sonra eklenir.

## Motivasyon

Platformda altyapı tablolarında `customer_id` yok — müşteri↔kaynak ilişkisi
sorgu anında isim benzerliğiyle (`vmname ILIKE '%müşteri%'`) kuruluyor
(`services/customer-api/app/db/queries/customer.py:5`). Sonuç: hiçbir müşterinin
desenine uymayan bir VM hiçbir sorgudan dönmüyor, **sessizce kayboluyor.** Bugün
"hangi VM'ler kimseye ait değil?" sorusuna cevap veren ters sorgu YOK. Toplam VM
ile müşteri-başı VM toplamı bu yüzden tutmuyor.

## Emsal: INTERNAL / "Bulutistan (Internal)"

`customer_mapping_resolver.py:30-34` — Bulutistan'ın kendi altyapısı için sanal
bir pseudo-account. Müşteri listesinde görünür, detay sayfası vardır. Bizim
"UNMAPPED" pseudo-account'umuz aynı deseni izler, tek farkla: mantık **ters** —
"şu kurallara uyanlar" değil, "hiçbir kurala uymayanlar."

## Veri kanıtı (canlı DB, 2026-07-16 ölçüldü)

- Son 7 gün: 14.363 distinct VM adı (VMware 2.034 + Nutanix 14.007).
- CRM hesabı: `discovery_crm_accounts` → 2.605 müşteri.
- **Python'da eşleştirme: 0,02 sn** (14k × 2,6k). SQL anti-join'e gerek yok.
- Sahipsiz görünenler ÜÇ gruba ayrılıyor:
  - **INTERNAL** (`Bulutistan-*`, ~1215): kural varsa INTERNAL'a aittir → hariç.
  - **Sistem VM'leri** (`vCLS`, `NTNX-*`, `Svm_*`): müşteri değil → hariç tutulur.
  - **Gerçek eşleşmeyenler**: ikiye ayrılır →
    - *alias eksik* — önek bir CRM hesabına benziyor ama kural yok
      (örn. `Ornek_Kilit`, `Deneme_Ltd`). Düzeltilebilir iş listesi.
    - *sahipsiz* — tanınmayan (`123host`, `342test`).

> Not: Lokal webui-db'de kural yok; gerçek eşleşmeyen sayısı canlıda ölçülecek.
> %86 ham oran şişkin (kural yokluğundan). Tasarım sayıdan bağımsızdır.

## Mimari

### 1. Sanal müşteri kaydı
`customer_mapping_resolver.py`'a INTERNAL'in yanına:
```
UNMAPPED_ACCOUNT_ID   = "UNMAPPED"
UNMAPPED_ACCOUNT_NAME = "Eşleşmeyen Veriler"
```

### 2. Pure classifier (TDD çekirdeği) — `shared/unmapped/classifier.py` (yeni)
Saf fonksiyon, DB'siz, tam test edilebilir:
```
classify_unmapped(
    names: list[str],
    owner_patterns: OwnerIndex,      # tüm müşteri desenleri + display-name'ler
    account_keys: dict[str, str],    # norm(hesap adı) -> gerçek ad (alias tahmini)
    system_prefixes: tuple[str,...], # vCLS, NTNX, SVM...
) -> list[UnmappedRow]
```
Her `UnmappedRow`: `name`, `guessed_owner | None`, `reason ∈ {system, alias_gap, orphan}`.
Kural: sistem-VM → atla; herhangi bir sahibe uyuyorsa → atla; önek bir hesap
adına gevşek uyuyorsa → `alias_gap`; yoksa → `orphan`.

`norm()`: küçült + Türkçe harf kıvır + alfanümerik dışını at (canlı ölçümde
`DENEME KOZMETİK…` ↔ `deneme_Kozmetik` eşleşmesi için gerekli).

### 3. Reverse service — `customer-api`
- Tüm müşteri desenlerini `_load_source_mapping_index()` (mevcut) + tüm display
  name'lerden bir `OwnerIndex` kur.
- Distinct VM adlarını çek (window-bounded, ~4 sn). Sistem VM önekleri hariç.
- `classify_unmapped()` çağır → eşleşmeyen ad listesi.
- Eşleşmeyenlerin detay satırlarını `WHERE vmname = ANY(%s)` ile çek (indeksli,
  hızlı) — leading-wildcard YOK.

### 4. Endpoint
`GET /customers/unmapped/resources?time_range=...` → gruplu satırlar + sayaçlar
(alias_gap / orphan). Ağır customer-perspective payload'ına DOKUNMA (INTERNAL
gibi ayrık yol).

### 5. GUI
- Müşteri listesine "Eşleşmeyen Veriler" kartını ekle (`customers_list.py`).
- Detay: hizmet sekmeleri (Faz 1: yalnız Sanallaştırma) + tablo:
  `Tahmini sahip · Makine adı · Neden`. `alias_gap` satırları vurgulu (aksiyon).

## Caching
Mevcut `_api_cache_get_with_stale` deseni. Anahtar: `api:unmapped_resources:{tr}`.
Sınıflandırma ucuz ama isim taraması değil → cache + warm (INTERNAL cadence).

## Kapsam dışı (Faz 1)
- 8 diğer veri kaynağı (backup/storage/s3/physical/itsm) — Faz 2.
- Bir eşleşmeyeni tek tıkla müşteriye atama — sadece "tahmini sahip" gösterilir,
  atama mevcut alias ekranından yapılır.

## Test
`tests/test_unmapped_classifier.py`:
- sahip eşleşince atlanır; sistem-VM atlanır (vCLS/NTNX/SVM);
- alias-gap tespiti (`Ornek_Kilit` → tahmin "Örnek Kilit A.Ş.");
- orphan (`123host`); Türkçe fold (`DENEME KOZMETİK…` ↔ `deneme_Kozmetik`);
- önek yok / boş / None dayanıklılığı.
```
