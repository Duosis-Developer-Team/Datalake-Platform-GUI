# Spec — TASK-99 CRM Inventory kolon standardizasyonu

**Kaynak task:** Hermes `TASK-99` · Bulutistan / BulutDL / Data Görselleştirme
**Task metni (birebir):**
> Tüm gruplarda ortak olan alanların (kolonlar) konumunun standartize edilmesi.
> Flat table'da mevcut olan tüm alanların eklenmesi ve rapor çıktısı kontrolü.

**Öncelik:** urgent · **Due:** 2026-08-07
**Mevcut durum analizi:** `implementation-plan.md` §1 (dosyalar okunarak doğrulandı)

---

## 1. Hangi problem çözülüyor

CRM Inventory Overview (`/crm/inventory-overview`) ekranında aynı bilgi her tabloda
farklı yerde duruyor. Kolon setleri 12 ayrı elle yazılmış listede tanımlı ve
`columns_for_family()` bunları 9 farklı efektif sete dönüştürüyor. Ortak kolonların
indeksi gruba göre kayıyor:

| Grup | 5. kolon |
|---|---|
| `standard` | Used |
| `replication` | Allocated |
| `virt_*` | Free |
| `backup_netbackup` | Used |
| `os_licence` | Lisanslanmalı |

Buna üç problem daha eşlik ediyor:

- **Flat tablo eksik.** 11 kolon gösteriyor, grouped'da olup flat'te olmayan 8 kolon var.
- **Rapor çıktısı ekranla ilgisiz.** Excel/PDF ham payload + formatlanmış satırı üst
  üste bindirip olduğu gibi döküyor; çift kolon, sızan iç alanlar, ham anahtar başlıkları.
- **Ölü kolon.** `Δ Used vs CRM` tanımlı ama üreticisi yok (`BUG-001`).

## 2. Hedef kullanıcı

CRM Inventory Overview ekranını kullanan Bulutistan iç kullanıcıları ve bu ekranın
Excel/PDF çıktısını rapor olarak alan taraf. Tek bir sayfa, tek bir izin düğümü
(`page:dashboard_crm_inventory`), rol ayrımı yok.

## 3. Beklenen davranış

Kullanıcı bir accordion grubundan diğerine geçtiğinde, ortak kolonlar **aynı sırada
ve aynı konumda** durur. Flat görünüme geçtiğinde hiçbir bilgi kaybetmez. Excel'e
bastığında ekranda gördüğü tabloyu, gördüğü başlıklarla ve gördüğü sırayla alır.

## 4. Functional requirements

### Kanonik omurga

**`REQ-F-001`** — Tek bir kanonik kolon omurgası tanımlanır ve her profil bu omurgayı
**aynı sırada** kullanır:

| Slot | Varsayılan başlık | Varsayılan `id` |
|---|---|---|
| 0 | Family | `family_label` — *yalnız flat view* |
| 1 | Service | `service_label` |
| 2 | Unit | `display_unit` |
| 3 | CRM Sold | `crm_sold_fmt` |
| 4 | Total | `total_fmt` |
| 5 | Used | `used_fmt` |
| 6 | Free | `free_fmt` |
| 7 | Unsold | `unsold_fmt` |
| 8+ | *(gruba özel blok)* | — |
| son | Birim Fiyat | `unit_price_fmt` |

**`REQ-F-002`** — Gruba özel kolonlar **slot 7 ile Birim Fiyat arasına** girer.
Omurga slotlarının arasına sokulmaz:

| Profil | Gruba özel blok |
|---|---|
| `standard`, `storage_s3` | *(yok)* |
| `dual_track`, `replication` | Sellable (Alloc) · Sellable (Max util) · Sellable (Ort.) |
| `allocation_only` | Sellable (Alloc) |
| `backup_netbackup` | Transfer (Pre) · PostDedup (Cost) · Dedup Savings % |
| `comparison_only` | Δ Used vs CRM |
| `os_licence` | Lisanslanmalı TL |

**`REQ-F-003`** — `Birim Fiyat` **her profilde son kolondur**. Bugün `os_licence`'ta
sondan ikinci; düzeltilir.

**`REQ-F-004`** — Bir profil için anlamsız olan omurga kolonu **listeden silinmez**,
yerinde `—` ile durur. Gerekçe: silme sonraki kolonları kaydırır ve standardizasyonun
kendisini bozar. Veri katmanı bunu zaten karşılıyor — `prepare_service_row`
(`crm_inventory_report.py:476`) ilgisiz alanlara `"—"` / `"—\n—"` yazıyor.

**`REQ-F-005`** — Bir profil bir omurga slotunu **kendi alanıyla yeniden
kullanabilir**; slot konumu değişmez, yalnız `id` ve başlık değişir. Repoda var olan
kalıp (`_REPLICATION_COLUMNS` `used_fmt`'i "Allocated" başlığıyla gösteriyor).
İzin verilen yeniden kullanımlar — bu liste kapalıdır, yenisi ADR ister:

| Profil | Slot | Başlık | `id` |
|---|---|---|---|
| `replication` (+veeam/zerto) | 5 | Allocated | `used_fmt` |
| `os_licence` | 4 | Tespit Edilen | `licence_detected_fmt` |
| `os_licence` | 7 | Lisanslanmalı | `licence_gap_fmt` |

Gerekçe: `Lisanslanmalı = Tespit Edilen − CRM Sold` aritmetiği
`Unsold = Total − CRM Sold` ile birebir aynı; slotlar semantik olarak örtüşüyor.
Sonuç: `os_licence`'ta ölü kolon sayısı 4'ten 2'ye iner (Used, Free).

### Flat tablo

**`REQ-F-006`** — Flat görünüm **tüm kolonların birleşimini** gösterir: omurga +
her gruba özel bloğun tamamı, sabit sırayla. 19 kolon:

```
Family · Service · Unit · CRM Sold · Total · Used · Free · Unsold
· Sellable (Alloc) · Sellable (Max util) · Sellable (Ort.)
· Transfer (Pre) · PostDedup (Cost) · Dedup Savings %
· Tespit Edilen · Lisanslanmalı · Lisanslanmalı TL
· Δ Used vs CRM · Birim Fiyat
```

Flat görünümde slot yeniden kullanımı **uygulanmaz** — `REQ-F-005`'teki eşlemeler
yalnız grouped görünüme aittir. Flat'te `Tespit Edilen` ve `Lisanslanmalı` kendi
kolonları olarak, `Total` ve `Unsold` de kendi kolonları olarak ayrı ayrı durur.
Gerekçe: flat tablo karışık satır taşır, tek bir slot iki farklı satır tipinde iki
farklı anlam taşıyamaz.

### Rapor çıktısı

**`REQ-F-007`** — Excel ve PDF'in `Services` sayfası **flat görünümün kolon setini**
(`REQ-F-006`), aynı sırayla ve **ekrandaki başlıklarla** üretir. Ham anahtar adı
(`crm_sold_fmt`) başlık olarak kullanılmaz.

**`REQ-F-008`** — Ham alanlar kaybolmaz; ayrı bir sayfada korunur. Böylece analiz
için ham sayı (`total`, `crm_sold_qty`, `potential_tl`) erişilebilir kalır.

**`REQ-F-009`** — Aktif filtre / arama davranışı **korunur**: rapor bugünkü gibi
ekrandaki filtreyi yansıtır (`_build_inventory_export_sheets`, `filter_mode`).

### Hata düzeltmesi

**`REQ-F-010`** (`BUG-001`) — `prepare_service_row`, `delta_fmt` anahtarını üretir.
Tanım: `Δ Used vs CRM = used_qty − crm_sold_qty`, işaretli, `display_unit` ile.
Veri eksikse `—`. Bugün üretici olmadığı için `comparison_only` profilindeki her
satırda kolon boş render oluyor.

## 5. Non-functional requirements

**`REQ-NF-001`** — Backend, API veya veri hesabı **değişmez**. İş tamamen sunum
katmanında: `crm_inventory_report.py` (kolon listeleri) ve
`crm_inventory_overview.py` (export sheet üretimi). `prepare_service_row`'a tek
ekleme `REQ-F-010`.

**`REQ-NF-002`** — Migration yok, şema değişikliği yok.

**`REQ-NF-003`** — `INVENTORY_REPORT_SCHEMA_VERSION` (`crm_inventory_report.py:101`,
bugün `inventory-final-polish-v5`) artırılır. Bu sabit DataTable `id`'lerine gömülü;
artırılmazsa tarayıcıda eski tablo state'i yeni kolon setine yapışabilir.

**`REQ-NF-004`** — RBAC'a **alt düğüm eklenmez**. `page:dashboard_crm_inventory`
alt düğümsüz tek bir `view` node'u (`src/auth/permission_catalog.py:506`); kolon
bazlı yetki bugün yok, bu iş onu getirmez.

**`REQ-NF-005`** — PDF çıktısı okunabilir olmalı. `dataframes_to_pdf_bytes`
(`src/utils/export_helpers.py:194`) landscape A4 kullanıyor ve
`col_width = min(40, max(190, pdf.w - 24) / len(cols))` ile genişliği kolon sayısına
bölüyor. 19 kolonda ≈14,4 mm/kolon. Bugünkü çıktı 60+ kolon ürettiği için zaten
okunamaz durumda — bu değişiklik PDF'i iyileştiriyor, ama 19 kolonun görsel
doğrulaması yapılmalı.

**`REQ-NF-006`** — Performans regresyonu yok: kolon eklemek satır sayısını
değiştirmiyor, `prepare_service_row` zaten tüm anahtarları üretiyor. Flat tabloda
sayfa boyutu 25 satır olarak kalır.

## 6. Scope

- `src/components/crm_inventory_report.py` — kolon sabitleri, `columns_for_family()`,
  `build_flat_view`, `prepare_service_row` (`delta_fmt` eklemesi), şema sürümü
- `src/pages/crm_inventory_overview.py` — `_build_inventory_export_sheets`
- İlgili testler (`tests/test_crm_inventory_*.py`)

## 7. Out of scope

- Backend / `datacenter-api` / `customer-api` tarafı
- `_PRODUCT_MATCHING_COLUMNS` (15 kolon) ve `_UNMAPPED_COLUMNS` (4 kolon) — bunlar
  hizmet tablosu değil, ayrı amaçlı listeler; omurga onlara uygulanmaz
- KPI kartları, filtre/arama davranışı, accordion yapısı
- Kolon bazlı RBAC
- `sellable` hesap mantığı, fiyatlandırma, birim çevrimi
- Grouped görünümdeki accordion başlık rozetleri (`_header_money_badges`)

## 8. Kısıtlar

- **`ASSUMPTION`** — Task metninde somut alan listesi verilmedi. Hermes'te yorum yok,
  aktivite yalnız "created" + "in progress" (2026-08-07'de doğrulandı). "Flat table'da
  mevcut olan tüm alanların eklenmesi" ifadesi, **flat tablonun eksik taraf olduğu**
  şeklinde okundu; kanıt bunu destekliyor (flat 11 kolon, grouped'da 8 kolon fazla).
  Sonradan somut liste çıkarsa `REQ-F-006` genişler.
- 58 mevcut test bu alanı çevreliyor; kolon sırası değişince bir kısmı kırılacak.
  Kırılan testler **düzeltilir**, silinmez.
- Yarına teslim: iş tek oturumda bitecek büyüklükte tutulmalı.

## 9. Acceptance criteria

**`AC-001`** — Dokuz profilin hepsinde ilk 8 kolon (flat'te 0-7, grouped'da 1-7)
kanonik omurga sırasındadır; hiçbir profilde omurga kolonu atlanmamıştır.

**`AC-002`** — `Birim Fiyat` dokuz profilin hepsinde son kolondur.

**`AC-003`** — Gruba özel kolonlar yalnız slot 7 ile Birim Fiyat arasında bulunur;
hiçbir gruba özel kolon omurga slotlarının arasına girmez.

**`AC-004`** — Flat görünüm `REQ-F-006`'daki 19 kolonu, o sırayla gösterir.

**`AC-005`** — Excel `Services` sayfasının kolonları ve sırası flat görünümle
birebir aynıdır; başlıklar ekrandaki başlıklardır; `panel_key`, `sellable_profile`,
`has_infra_source`, `inventory_free_mode`, `data_quality`, `used_is_allocation`
alanları bu sayfada **yer almaz**.

**`AC-006`** — Ham alanlar ayrı bir sayfada erişilebilir durumdadır.

**`AC-007`** — `comparison_only` profilindeki bir satırda `Δ Used vs CRM` kolonu
sayı gösterir, boş değildir.

**`AC-008`** — `INVENTORY_REPORT_SCHEMA_VERSION` artırılmıştır.

**`AC-009`** — Tüm test paketi yeşildir; kırılan testler yeni kolon sözleşmesine
göre güncellenmiştir, silinmemiştir.

## 10. Blocking unknown

**Yok.** Planın uygulanmasını durduran açık soru bulunmuyor.

Blocking olmayan açık uçlar:

- **`OPEN QUESTION`** — Canlıda `comparison_only` profilinde satır var mı? Profil
  backend payload'ından geliyor, local'de doğrulanamadı. `AC-007`'nin canlı
  doğrulaması buna bağlı; test ortamında sentetik satırla doğrulanabilir.
- **`OPEN QUESTION`** — `comparison_only` profiline `Free`/`Unsold` omurga kolonları
  eklenince anlamlı değer mi çıkacak? `prepare_service_row` bu satırlar için de
  hesaplıyor. Değer anlamsız çıkarsa düzeltme yeri kolon listesi değil,
  `prepare_service_row`'dur — ve bu ayrı bir iştir.

## 11. Başarı nasıl ölçülecek

1. `AC-001`–`AC-009` karşılanır (bkz. `testing-plan.md`).
2. Ekranda dokuz grubun tablosu yan yana karşılaştırıldığında ortak kolonlar aynı
   indekste görünür — tarayıcıda görsel doğrulama.
3. Excel çıktısı açıldığında `Services` sayfası ekrandaki tabloyla birebir örtüşür.
4. PDF çıktısı 19 kolonla okunabilir (`REQ-NF-005`).
