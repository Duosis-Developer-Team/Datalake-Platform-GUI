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

> spec.md onaylandıktan sonra doldurulacak.

## 3. Adımlar

> spec.md onaylandıktan sonra doldurulacak.

## 4. Interfaces

> spec.md onaylandıktan sonra doldurulacak.
