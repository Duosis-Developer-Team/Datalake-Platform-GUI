# Implementation Plan — TASK-99 CRM Inventory kolon standardizasyonu

**Plan paketi:** `docs/plans/task-99-crm-inventory-columns-plan/`
**Durum:** bkz. `status.md`
**Spec:** `spec.md` (requirement ID'leri oradan referanslanır)

> Bu bölüm (Current state) 2026-08-07'de dosyalar okunarak doğrulandı.
> Etiketler: `FACT` = dosya okundu · `INFERENCE` = kanıttan çıkarım ·
> `UNKNOWN` = doğrulanmadı.

---

## 1. Current state

### 1.1 Entry point'ler ve veri akışı

`FACT` — Sayfa iki fazlı yükleniyor:

| Katman | Dosya | Rol |
|---|---|---|
| Sayfa / callback | `src/pages/crm_inventory_overview.py` (310 satır) | Route `/crm/inventory-overview`, payload fetch, filtre callback'leri, Excel/PDF export |
| Shell / kontroller | `src/components/crm_inventory_shell.py` (227 satır) | KPI kartları, filtre, arama, `grouped`/`flat` view toggle |
| Tablo üretimi | `src/components/crm_inventory_report.py` (1505 satır) | **Tüm kolon tanımları ve satır formatlama burada** |
| Skeleton | `src/components/crm_inventory_loading.py` (104 satır) | Faz A iskeleti |

Akış: `_fill_crm_inventory_content` (`crm_inventory_overview.py:123`) →
`api.get_crm_inventory_overview("*")` → `build_layout_content` →
`build_report_body` (`crm_inventory_report.py:1400`) → grouped ise
`build_family_accordion`, flat ise `build_flat_view` → her ikisi de
`build_report_table` (`crm_inventory_report.py:766`) →
`columns_for_family` (`crm_inventory_report.py:194`).

`FACT` — Kolon seçimi **tamamen GUI tarafında**. Backend payload'ı satır alanlarını
verir, kolon listesini vermez. Yani bu iş için backend/API değişikliği gerekmiyor.

`FACT` — View toggle iki değerli: `grouped` | `flat`
(`crm_inventory_shell.py:31` `_VIEW_OPTIONS`).

### 1.2 Kolon setleri — bugünkü hâli

`FACT` — `crm_inventory_report.py` içinde 12 ayrı kolon sabiti var:

| Sabit | Satır | Kolon sırası |
|---|---|---|
| `_BASE_COLUMNS` | 15 | Service · Unit · CRM Sold · Total · **Used** · Free · Unsold |
| `_REPLICATION_COLUMNS` | 25 | Service · Unit · CRM Sold · Total · **Allocated** · Free · Unsold · Sellable(Alloc) · Sellable(Max util) · Sellable(Ort.) |
| `_VIRT_BASE_COLUMNS` | 38 | Service · Unit · CRM Sold · Total · Free · Unsold *(Used yok)* |
| `_NETBACKUP_COLUMNS` | 56 | Service · Unit · CRM Sold · Total · Used · Transfer (Pre) · PostDedup (Cost) · Dedup Savings % · Free · Unsold · **Birim Fiyat** |
| `_DUAL_TRACK_COLUMNS` | 85 | Sellable(Alloc) · Sellable(Max util) · Sellable(Ort.) |
| `_ALLOC_ONLY_COLUMNS` | 91 | Sellable(Alloc) |
| `_UNIT_PRICE_COLUMN` | 95 | Birim Fiyat |
| `_FLAT_EXTRA_COLUMN` | 97 | Family |
| `_UNMAPPED_COLUMNS` | 123 | Product · Unit · CRM Sold · Amount TL |
| `_PRODUCT_MATCHING_COLUMNS` | 130 | 15 kolon (SKU … Notes) |
| `_COMPARISON_ONLY_COLUMNS` | 169 | Service · Unit · CRM Sold · Total · Used · Δ Used vs CRM |
| `_OS_LICENCE_COLUMNS` | 178 | Service · Unit · Tespit Edilen · CRM Sold · Lisanslanmalı · **Birim Fiyat** · Lisanslanmalı TL |

`columns_for_family()` bunları profile göre birleştirip döndürüyor
(`crm_inventory_report.py:194-226`). Ortaya çıkan efektif setler:

| Profil | Kolon sayısı | Birleşim |
|---|---|---|
| `standard` | 8 | `_BASE_COLUMNS` + Birim Fiyat |
| `dual_track` / flat view | 10 | `_VIRT_BASE_COLUMNS` + Sellable×3 + Birim Fiyat |
| `allocation_only` | 8 | `_VIRT_BASE_COLUMNS` + Sellable(Alloc) + Birim Fiyat |
| `virt_*` (4 aile) | 7 | `_VIRT_BASE_COLUMNS` + Birim Fiyat |
| `replication` (+veeam/zerto) | 11 | `_REPLICATION_COLUMNS` + Birim Fiyat |
| `backup_netbackup` | 11 | `_NETBACKUP_COLUMNS` (Birim Fiyat gömülü, **ayrıca eklenmez**) |
| `storage_s3` | 8 | `standard`'a düşürülür (`_PHYSICAL_FREE_FAMILIES`, satır 213) |
| `comparison_only` | 7 | `_COMPARISON_ONLY_COLUMNS` + Birim Fiyat |
| `os_licence` | 7 | `_OS_LICENCE_COLUMNS` (Birim Fiyat gömülü, **ayrıca eklenmez**) |

### 1.3 Doğrulanmış tutarsızlıklar

`FACT` **T-1 — 5. kolon her grupta başka şey.** `id` aynı (`used_fmt`) ama başlık ve
konum değişiyor: `standard`'da index 4 "Used", `replication`'da index 4 "Allocated",
`virt_*`'ta o kolon hiç yok (yerine Free geliyor).

`FACT` **T-2 — Free / Unsold konumu kayıyor.** `_BASE_COLUMNS`'ta 5-6,
`_VIRT_BASE_COLUMNS`'ta 4-5, `_NETBACKUP_COLUMNS`'ta 8-9, `comparison_only`'de hiç yok.

`FACT` **T-3 — Birim Fiyat bir grup hariç son kolon.** `_OS_LICENCE_COLUMNS`'ta
6/7. sırada; arkasında "Lisanslanmalı TL" var. Diğer sekiz profilde en sonda.

`FACT` **T-4 — Flat view superset değil.** `build_flat_view`
(`crm_inventory_report.py:1105`) sabit `sellable_profile="dual_track"` kullanıyor
(`_FLAT_VIEW_FAMILY`, satır 99) → 11 kolon (Family + 6 virt base + Sellable×3 +
Birim Fiyat). Grouped görünümde olup flat'te **olmayan** kolonlar:
`Used`, `Transfer (Pre)`, `PostDedup (Cost)`, `Dedup Savings %`, `Tespit Edilen`,
`Lisanslanmalı`, `Lisanslanmalı TL`, `Δ Used vs CRM`.

`FACT` — Ama veri zaten hazır: `prepare_service_row`
(`crm_inventory_report.py:476-677`) **her satır için bu anahtarların hepsini**
döndürüyor, ilgisiz olduğunda `"—"` / `"—\n—"` ile dolduruyor. Yani flat tabloya
eksik kolonları eklemek **saf sunum katmanı işi**; backend/hesap değişikliği yok.

`FACT` **T-5 — Rapor çıktısı ekrandaki tabloyla ilgisiz.**
`_build_inventory_export_sheets` (`crm_inventory_overview.py:204-246`) şunu yapıyor:

```python
export_rows = [{**p, **prepare_service_row(p)} for p in filtered]
...
"Services": records_to_dataframe(export_rows),
```

ve `records_to_dataframe` (`src/utils/export_helpers.py:258`) sadece
`pd.DataFrame(records)`. Sonuç:

- Kolon sırası = ham payload dict anahtar sırası (API'ye bağlı, **belirsiz**).
- Ham + formatlanmış **çift kolon**: `total` ve `total_fmt`, `crm_sold_qty` ve
  `crm_sold_fmt`, `potential_tl` ve `sellable_*_fmt` yan yana.
- İç alanlar sızıyor: `panel_key`, `sellable_profile`, `has_infra_source`,
  `inventory_free_mode`, `used_is_allocation`, `data_quality`.
- Türkçe/İngilizce başlık yok — Excel başlıkları ham alan adları (`crm_sold_fmt`),
  ekrandaki başlıklar değil (`CRM Sold`).

Aynısı PDF için de geçerli (`_export_inventory_pdf`, satır 290 — aynı sheet dict'i).

### 1.4 Yan bulgu — canlı hata

`FACT` **BUG-001 — `Δ Used vs CRM` kolonunun üreticisi yok.**
`_COMPARISON_ONLY_COLUMNS` (satır 175) `id: "delta_fmt"` kolonunu tanımlıyor, ama
`delta_fmt` anahtarı repoda **başka hiçbir yerde geçmiyor**:

```
$ grep -rn "delta_fmt" src/ tests/ --include="*.py"
src/components/crm_inventory_report.py:175:    {"name": "Δ Used vs CRM", "id": "delta_fmt"},
```

`prepare_service_row` bu anahtarı döndürmüyor → `comparison_only` profilindeki her
satırda bu kolon **boş** render oluyor.

`UNKNOWN` — Canlıda `comparison_only` profilinde satır var mı? Profil backend
payload'ından geliyor (`sellable_profile`), local'de doğrulanamadı. Kolon boş
görünüyorsa bu hata müşteriye görünür durumda demektir.

### 1.5 Mevcut test kapsamı

`FACT` — Kolon davranışını kilitleyen testler:

| Dosya | Test sayısı |
|---|---|
| `tests/test_crm_inventory_report.py` | 37 |
| `tests/test_crm_inventory_replication_columns.py` | 7 |
| `tests/test_crm_inventory_overview_page.py` | 6 |
| `tests/test_crm_inventory_os_licence_columns.py` | 5 |
| `tests/test_crm_inventory_export.py` | 3 |

Toplam **58 test** bu alanı çevreliyor. Kolon sırası değişirse bunların bir kısmı
kırılır — bu iyi haber, regresyon ağı mevcut.

`FACT` — `INVENTORY_REPORT_SCHEMA_VERSION = "inventory-final-polish-v5"`
(`crm_inventory_report.py:101`) tablo `id`'lerine gömülü; kolon şeması değişince
bu sürüm artırılmalı yoksa tarayıcı tarafında eski DataTable state'i yapışabilir.

### 1.6 Repo durumu

`FACT` — `Datalake-Platform-GUI`, branch `main`, son commit `1276b540`
(TASK-94 teslim dokümanı). Çalışma alanında takipli değişiklik: `.env` (M) —
bu dosya repoda takipli, **secret buraya yazılmaz** (`.env.local` kullanılır).

---

## 2. Değişiklik noktaları

Karar dayanağı: `decisions.md` `ADR-001`. Requirement'lar: `spec.md`.

### `src/components/crm_inventory_report.py`

| # | Ne değişecek | Neden |
|---|---|---|
| D-1 | `delta_fmt` üretimi `prepare_service_row`'a eklenir (satır 622-677 dönüş dict'i) | `REQ-F-010` / `BUG-001` — kolon tanımlı, üreticisi yok |
| D-2 | `_NUMERIC_COLS`'a (satır 107) `delta_fmt` eklenir | Sağa hizalama + genişlik kuralı bu sete bakıyor |
| D-3 | Yeni sabitler: `_SPINE`, `_SPINE_OVERRIDES`, `_GROUP_BLOCKS` | `REQ-F-001`, `REQ-F-002`, `REQ-F-005` — omurga tek kaynak olur |
| D-4 | `columns_for_family()` (satır 194-226) omurgadan türetir hale gelir | `REQ-F-001`–`REQ-F-004`; bugün 9 dallı `if` zinciri |
| D-5 | Eski kolon sabitleri kaldırılır / bloklara dönüşür: `_BASE_COLUMNS`, `_VIRT_BASE_COLUMNS`, `_REPLICATION_COLUMNS`, `_NETBACKUP_COLUMNS`, `_COMPARISON_ONLY_COLUMNS`, `_OS_LICENCE_COLUMNS`, `_DUAL_TRACK_COLUMNS`, `_ALLOC_ONLY_COLUMNS` | Aynı bilgi iki yerde yaşamasın |
| D-6 | `hide_used` semantiği değişir: **kolon düşürme → hücre boşaltma** (`build_report_table`, satır 782-806) | `REQ-F-004`; ayrıntı aşağıda **D-6 notu** |
| D-7 | Yeni `flat_columns()`; `build_flat_view` (satır 1105) bunu kullanır | `REQ-F-006` — flat superset |
| D-8 | `INVENTORY_REPORT_SCHEMA_VERSION` (satır 101) `v5` → `v6` | `REQ-NF-003`, `AC-008` |

**D-6 notu — sessiz regresyon tuzağı.** Bugün `virt_*` aileleri için
`build_family_accordion` (satır 1086) `hide_used=True` geçiyor ve
`columns_for_family` kolonu **listeden siliyor**. Yeni kuralda kolon silinmediği
için, `hide_used` hiçbir şey yapmazsa `Used` kolonu bu ailelerde **gerçek değerle
görünmeye başlar**. `prepare_service_row` hücreyi yalnız satırın kendi
`inventory_hide_used` bayrağı varsa boşaltıyor (satır 611-620) — çağıran tarafın
geçtiği argümana bakmıyor. Bu yüzden `build_report_table`, `row_hide_used` doğruyken
hazırlanmış satırların `used_fmt` değerini `"—\n—"` ile ezmelidir. Aksi hâlde
sanallaştırma tablolarında bilinçli olarak gizlenmiş bir sayı geri gelir.

### `src/pages/crm_inventory_overview.py`

| # | Ne değişecek | Neden |
|---|---|---|
| D-9 | `_build_inventory_export_sheets` (satır 204-246) `Services` sayfasını `flat_columns()` sırası ve başlıklarıyla üretir | `REQ-F-007`, `AC-005` |
| D-10 | Ham satırlar `Services_raw` sayfasına taşınır | `REQ-F-008`, `AC-006` |
| D-11 | Export hücrelerindeki satır sonu (`\n`) ` · ` ile düzleştirilir | Ekranda `whiteSpace: pre-line` ile iki satır görünen blok (`50 TB\n500 TL`), Excel'de hücre içi kırılma, PDF'te `cell()` ile bozuk render veriyor |

`REQ-F-009` gereği filtre/arama davranışı korunur — `filter_mode` ve `search`
akışına dokunulmaz.

### Dokunulmayacaklar

`_UNMAPPED_COLUMNS`, `_PRODUCT_MATCHING_COLUMNS`, KPI kartları, accordion rozetleri
(`_header_money_badges`), `src/services/api_client.py`, backend. Bkz. `spec.md` §7.

---

## 3. Adımlar

Sıra bağımlılığa göre. Her adımın kendi doğrulaması var; bir adım yeşil olmadan
sonrakine geçilmez.

### Adım 1 — `delta_fmt` üretimi (`BUG-001`)

`prepare_service_row` dönüş dict'ine `delta_fmt` eklenir:
`used_qty − crm_sold_qty`, işaretli, `display_unit` ile; iki değerden biri yoksa `—`.
`_NUMERIC_COLS`'a `delta_fmt` eklenir (D-2).

*Doğrulama:* `comparison_only` profilli sentetik satırla yeni test — kolon sayı
gösteriyor, boş değil (`AC-007`). Mevcut 58 test yeşil kalmalı (bu adım hiçbir
kolon listesine dokunmuyor).

*Neden önce:* bağımsız, küçük, geri kalanı bloklamıyor; ayrıca tek başına da
değerli bir düzeltme — sonraki adımlar takılırsa bu commit yine de gider.

### Adım 2 — Omurga sabitleri

`_SPINE`, `_SPINE_OVERRIDES`, `_GROUP_BLOCKS` yazılır (D-3). `columns_for_family()`
henüz değişmez; sabitler eklenip mevcut davranış korunur.

*Doğrulama:* `_SPINE_OVERRIDES` ve `_GROUP_BLOCKS` içindeki her `id`'nin
`prepare_service_row` çıktısında karşılığı olduğunu doğrulayan test. Bu test
`BUG-001`'in tekrarını önler — ölü kolon bir daha eklenemez.

### Adım 3 — `columns_for_family()` yeniden yazımı

Dokuz dallı `if` zinciri omurga + override + blok + `Birim Fiyat` birleşimine
dönüşür (D-4). Eski sabitler kaldırılır (D-5).

*Doğrulama:* `AC-001`, `AC-002`, `AC-003`. Test elle yazılmış beklenti listesiyle
değil, **`_SPINE` sabitinin kendisiyle** karşılaştırır — aksi hâlde test sözleşmenin
kopyası olur ve sözleşme bozulunca da beraber bozulur.

### Adım 4 — `hide_used` semantiği

`build_report_table` içinde kolon düşürme kaldırılır, `row_hide_used` doğruyken
hazırlanan satırların `used_fmt` değeri `"—\n—"` ile ezilir (D-6).

*Doğrulama:* `virt_*` ailesinden bir satırla test — `Used` kolonu **listede var**
ve hücre `—`. Bu adım atlanırsa gizlenmiş sayı geri gelir; test bunu yakalar.

### Adım 5 — Flat superset

`flat_columns()` yazılır, `build_flat_view` ona bağlanır (D-7).

*Doğrulama:* `AC-004` — 19 kolon, `spec.md` `REQ-F-006`'daki sırayla. Flat'te slot
yeniden kullanımının **uygulanmadığı** ayrıca doğrulanır (`Total` ve `Tespit Edilen`
ayrı kolonlar).

### Adım 6 — Şema sürümü

`INVENTORY_REPORT_SCHEMA_VERSION` → `inventory-column-spine-v6` (D-8).

*Doğrulama:* `AC-008`; sabitin `v5` olmadığını kontrol eden test.

### Adım 7 — Rapor çıktısı

`_build_inventory_export_sheets` `Services` sayfasını `flat_columns()`'tan üretir,
ham satırlar `Services_raw`'a taşınır, satır sonları düzleştirilir (D-9, D-10, D-11).

*Doğrulama:* `AC-005`, `AC-006` — `Services` sayfasının kolon listesi
`flat_columns()` başlıklarıyla birebir; `panel_key`, `sellable_profile`,
`has_infra_source`, `inventory_free_mode`, `data_quality`, `used_is_allocation`
bu sayfada yok. Mevcut `tests/test_crm_inventory_export.py` (3 test) güncellenir.

### Adım 8 — Test paketi ve tarayıcı doğrulaması

Kırılan testler yeni sözleşmeye göre güncellenir, silinmez (`AC-009`).

```bash
.venv/bin/python -m pytest tests/ -q      # tüm paket
.venv/bin/python app.py                   # → localhost:8050/crm/inventory-overview
```

Ardından dokuz grubun accordion'u açılır; ortak kolonların aynı indekste olduğu ve
PDF'in 19 kolonla okunabilir olduğu görsel olarak doğrulanır (`REQ-NF-005`).
Local'de backend ayakta değilse tarayıcı doğrulaması koşulamaz — `testing-plan.md`
§5 `RISK-004` üç kademeli çıkış yolunu tanımlıyor; hiçbiri işlemezse `TEST-A-*`
**"yapılmadı"** diye raporlanır, "geçti" denmez.

*Doğrulama:* `testing-plan.md` §4 ve §5. Yeni testlerin hangi dosyaya gideceği
`testing-plan.md` başındaki tabloda.

---

## 4. Interfaces

Yeni ve değişen imzalar. Kod değil, sözleşme.

```python
# --- Yeni sabitler (crm_inventory_report.py) ---

# Slot sırası. Index = konum. Family yalnız flat view'da eklenir.
_SPINE: list[dict[str, str]]
# örn. [{"name": "Service", "id": "service_label"}, ..., {"name": "Unsold", "id": "unsold_fmt"}]

# Profil bazlı slot yeniden kullanımı. Kapalı liste (REQ-F-005).
# Anahtar: profil adı. Değer: {slot_index: {"name": ..., "id": ...}}
_SPINE_OVERRIDES: dict[str, dict[int, dict[str, str]]]

# Slot 7 ile Birim Fiyat arasına giren, gruba özel kolonlar.
_GROUP_BLOCKS: dict[str, list[dict[str, str]]]


# --- Değişen / yeni fonksiyonlar ---

def columns_for_family(
    family: str | None,
    *,
    hide_used: bool = False,
) -> list[dict[str, str]]:
    """İmza korunur. Davranış: omurga + override + gruba özel blok + Birim Fiyat.
    `hide_used` artık kolon DÜŞÜRMEZ — hücre boşaltma build_report_table'da yapılır.
    Parametre geriye dönük uyumluluk için durur ve kolon setini etkilemez."""


def flat_columns() -> list[dict[str, str]]:
    """Flat view'ın 19 kolonu: Family + omurga + tüm gruba özel blokların
    birleşimi + Birim Fiyat. Slot yeniden kullanımı UYGULANMAZ (REQ-F-006).
    Sıra sabittir; export bu listeden türer."""
```

**Veri şekli — `prepare_service_row` dönüşüne eklenen tek anahtar:**

```python
"delta_fmt": str   # "+12 vCPU" | "-3 TB" | "—"
```

**Export sayfa sözleşmesi (`_build_inventory_export_sheets` dönüşü):**

| Sayfa | İçerik | Değişiklik |
|---|---|---|
| `Summary` | özet + export filtre bilgisi | değişmiyor |
| `Services` | `flat_columns()` kolonları, o sırayla, ekran başlıklarıyla | **değişiyor** |
| `Services_raw` | ham panel alanları + formatlanmış alanlar | **yeni** |
| `CRM_only` | CRM-only satırlar | değişmiyor |
| `Unmapped` | eşleşmeyen ürünler | değişmiyor |
| `Families_summary` | aile bazlı özet | değişmiyor |
| `Product_Matching` | ürün eşleştirme | değişmiyor |

**Not — `AC-005` inceliği:** "birebir aynı" kolon listesi, sırası ve başlıkları için
geçerlidir. Hücre **içeriği** düzleştirilir: ekranda iki satır görünen
`50 TB\n500 TL` bloğu export'ta `50 TB · 500 TL` olur (D-11). Bu bilinçli bir
sapmadır; `\n` Excel'de hücre kırıyor, PDF'te `cell()` ile bozuk render veriyor.
