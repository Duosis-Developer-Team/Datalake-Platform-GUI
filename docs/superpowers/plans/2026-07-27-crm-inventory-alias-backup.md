# CRM Inventory temizliği + Alias ekleme + Backup eşleşmeyen veriler — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CRM Inventory sayfasından Power tablosunu ve üç Product Matching kolonunu kaldır; Eşleşmeyen Veriler sayfasına tek tıkla alias ekleyen bir işlem kolonu ve NetBackup policy'leri için Backup sekmesi ekle.

**Architecture:** Dört bağımsız iş kolu. Power filtresi ve payload zenginleştirmesi `customer-api` servis katmanında (tablo ile KPI tek kaynaktan gelsin diye); eşleştirme mantığı `shared/customer/` altındaki saf modüllerde (SQL yolu ile bellek yolu birbirinden kaymasın diye); arayüz Dash `DataTable` + `active_cell` kalıbıyla.

**Tech Stack:** Python 3.11, Dash + dash-mantine-components, FastAPI (customer-api), PostgreSQL (psycopg2), pytest, openpyxl.

**Spec:** `docs/superpowers/specs/2026-07-27-crm-inventory-alias-backup-design.md`

## Global Constraints

- **Python yorumlayıcısı:** her komutta repo kökündeki `./.venv/bin/python` kullanılır. Sistemdeki `python3` 3.9'dur ve bu kod tabanını `|` tip birleşimi hatasıyla kırar.
- **Test komutu:** `./.venv/bin/python -m pytest <path> -q` — repo kökünden çalıştırılır. GUI testleri `tests/`, servis testleri `services/customer-api/tests/` altında, ikisi de aynı venv ile koşar.
- **Türkçe katlama tek yerden gelir:** `shared/customer/unmapped_classifier.norm()`. Yeni normalizasyon fonksiyonu yazılmaz.
- **Eşleştirme semantiği tek yerden gelir:** `shared/customer/match.py`. `prefix`/`contains`/`suffix`/`exact` davranışı orada tanımlı, yeniden türetilmez.
- **`PUT /crm/aliases/{id}/source-mappings` bir hesabın TÜM mapping'lerini değiştirir.** Her yazma işlemi önce mevcutları okuyup birleşimi göndermek zorundadır.
- **Mapping girdisi şeması** (`CustomerSourceMappingEntry`): `data_source: str`, `match_method: str`, `match_value: str`, `display_label: str|None`, `priority: int = 100`, `enabled: bool = True`, `notes: str|None`.
- **Geriye dönük uyumluluk:** `tests/test_unmapped_classifier.py` içinde 22 test var ve `account_keys_from_names()` / `guess_owner()` imzalarına dayanıyor. Bu iki fonksiyonun mevcut imzası korunur.
- **Commit mesajları** İngilizce, `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` satırıyla biter.

## File Structure

| Dosya | Sorumluluk | Görev |
|---|---|---|
| `services/customer-api/app/services/inventory_overview_service.py` | Gizli family filtresi | 1 |
| `src/components/crm_inventory_report.py` | Product Matching kolonları | 2 |
| `shared/customer/unmapped_classifier.py` | Sahiplik sınıflandırma + alias önerisi | 3, 7 |
| `services/customer-api/app/db/queries/unmapped.py` | Ham veri SQL'leri | 3, 7 |
| `services/customer-api/app/services/customer_service.py` | Payload birleştirme | 3, 7 |
| `src/services/api_client.py` | GUI cache invalidasyonu | 4 |
| `src/utils/crm_source_mapping_ui.py` | Mapping birleştirme (saf) | 4 |
| `src/pages/unmapped_resources.py` | Sayfa düzeni, tablolar, sekmeler | 5, 8 |
| `src/pages/unmapped_resources_callbacks.py` | İşlem kolonu callback'i | 5 |
| `shared/customer/backup_policy.py` | NetBackup adlandırma standardı (saf) | 6 |
| `scripts/seed_backup_policy_aliases.py` | Excel seed + rapor | 9 |

---

## Task 1: CRM Inventory'de Power family'sini gizle

**Files:**
- Modify: `services/customer-api/app/services/inventory_overview_service.py:66-73` (sabit ekleme), `:1156` (filtre)
- Test: `services/customer-api/tests/test_inventory_overview_service.py`

**Interfaces:**
- Consumes: yok (ilk görev)
- Produces: `_INVENTORY_HIDDEN_FAMILIES: frozenset[str]` — modül seviyesinde sabit

**Neden burada:** `panel_rows` listesi hem `families_map`'i (satır 1159) hem `summary`'yi (satır 1184-1200) hem de payload'daki `"panels"` alanını (satır 1217) besliyor. Sıralamadan hemen önce filtrelersek üçü birden tutarlı olur. Arayüzde filtrelemek tabloyu boşaltır ama KPI'ları Power'ı saymaya devam ettirir.

- [ ] **Step 1: Write the failing test**

`services/customer-api/tests/test_inventory_overview_service.py` dosyasının sonuna ekle:

```python
def test_hidden_families_constant_excludes_power_but_not_power_hana():
    """Power ve Power HANA aynı IBM altyapısını paylaşır; sayfada yalnızca HANA görünür."""
    from app.services.inventory_overview_service import _INVENTORY_HIDDEN_FAMILIES

    assert "virt_power" in _INVENTORY_HIDDEN_FAMILIES
    assert "virt_power_hana" not in _INVENTORY_HIDDEN_FAMILIES


def test_hidden_family_rows_are_dropped_before_families_and_summary():
    """Filtre panel listesinde uygulanır, böylece tablo ve KPI aynı kaynaktan beslenir."""
    from app.services.inventory_overview_service import _drop_hidden_families

    rows = [
        {"family": "virt_power", "crm_sold_tl": 100.0, "service_label": "Power CPU"},
        {"family": "virt_power_hana", "crm_sold_tl": 50.0, "service_label": "HANA CPU"},
        {"family": "virt_classic", "crm_sold_tl": 25.0, "service_label": "KM CPU"},
    ]
    kept = _drop_hidden_families(rows)

    assert [r["family"] for r in kept] == ["virt_power_hana", "virt_classic"]
    assert sum(float(r["crm_sold_tl"]) for r in kept) == 75.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest services/customer-api/tests/test_inventory_overview_service.py -q -k hidden`
Expected: FAIL — `ImportError: cannot import name '_INVENTORY_HIDDEN_FAMILIES'`

- [ ] **Step 3: Add the constant and helper**

`inventory_overview_service.py` içinde, `_INVENTORY_CRM_VISIBLE_FAMILIES` tanımının (satır 69-73) hemen ardına ekle:

```python
# Families rendered nowhere on /crm/inventory-overview. virt_power shares the
# same IBM Power infrastructure as virt_power_hana (see sellable_service:261),
# so showing both reads the underlying capacity twice. Filtered from the panel
# list before families AND summary are built, so the table and the KPI cards
# can never disagree about what is on the page.
_INVENTORY_HIDDEN_FAMILIES: frozenset[str] = frozenset({"virt_power"})


def _drop_hidden_families(panel_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        r for r in panel_rows
        if str(r.get("family") or "") not in _INVENTORY_HIDDEN_FAMILIES
    ]
```

- [ ] **Step 4: Apply the filter**

`inventory_overview_service.py:1156`, `panel_rows.sort(...)` satırının **hemen öncesine** ekle:

```python
        panel_rows = _drop_hidden_families(panel_rows)
```

Sonuç şöyle görünmeli:

```python
            panel_rows.append(row)

        panel_rows = _drop_hidden_families(panel_rows)
        panel_rows.sort(key=lambda r: (-float(r.get("crm_sold_tl") or 0), r.get("service_label") or ""))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest services/customer-api/tests/test_inventory_overview_service.py -q`
Expected: PASS, mevcut testler dahil hepsi yeşil

- [ ] **Step 6: Verify the page-level tests still pass**

Run: `./.venv/bin/python -m pytest tests/test_crm_inventory_overview_page.py tests/test_crm_inventory_report.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add services/customer-api/app/services/inventory_overview_service.py services/customer-api/tests/test_inventory_overview_service.py
git commit -m "$(cat <<'EOF'
feat(crm-inventory): hide the Power family from the inventory page

virt_power and virt_power_hana share the same IBM Power infrastructure,
so rendering both reads the underlying capacity twice. Drop virt_power
from the panel list before families and summary are computed, so the
table and the KPI cards cannot disagree.

Only /crm/inventory-overview consumes this payload; DC View and Sellable
Potential read Power through separate paths and are unaffected.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Product Matching tablosundan üç kolonu kaldır

**Files:**
- Modify: `src/components/crm_inventory_report.py:82-94` (kolon listesi), `:732-741` (satır hazırlama), `:753-762` (arama)
- Test: `tests/test_crm_inventory_product_matching.py`, `tests/test_crm_inventory_export.py`

**Interfaces:**
- Consumes: yok
- Produces: `prepare_product_matching_row()` artık `usage_source`, `infra_total_fmt`, `infra_used_fmt` anahtarlarını üretmez

**Dikkat:** Ekran ve Excel export ayrı yollardan besleniyor. Yalnızca kolon listesini düzenlemek export'u değiştirmez — bu yüzden `prepare_product_matching_row()` de düzenlenir.

- [ ] **Step 1: Write the failing test**

`tests/test_crm_inventory_product_matching.py` dosyasının sonuna ekle:

```python
def test_dropped_columns_are_absent_from_screen_and_export():
    """Usage Source / Infra Total / Infra Used ekrandan da Excel'den de kalktı.

    Ekran kolonları ve export alanları ayrı yollardan beslenir, bu yüzden ikisi
    de ayrıca kontrol edilir: yalnızca kolon listesini düzenlemek export'ta
    alanları bırakırdı.
    """
    from src.components.crm_inventory_report import _PRODUCT_MATCHING_COLUMNS

    dropped = {"usage_source", "infra_total_fmt", "infra_used_fmt"}

    screen_ids = {c["id"] for c in _PRODUCT_MATCHING_COLUMNS}
    assert not (screen_ids & dropped)
    assert "infra_tables_fmt" in screen_ids  # Tables kolonu kalıyor

    prepared = prepare_product_matching_row({
        "productnumber": "000BLT-46",
        "product_name": "HC CPU",
        "crm_sold_qty": 10,
        "crm_sold_tl": 100,
        "usage_source": "Loki",
        "infra_total": 20,
        "infra_used": 5,
        "infra_tables": ["nutanix_vm_metrics"],
    })
    assert not (set(prepared) & dropped)


def test_search_no_longer_probes_the_dropped_usage_source_field():
    """usage_source üretilmiyorsa onda arama yapmak sessiz ölü koddur."""
    rows = [{
        "productnumber": "000BLT-46",
        "product_name": "HC CPU",
        "usage_source": "Loki",
        "matching_rule": "cpu total",
    }]
    assert filter_product_matching_rows(rows, "all", "loki") == []
    assert filter_product_matching_rows(rows, "all", "cpu total") == rows
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_crm_inventory_product_matching.py -q -k "dropped or probes"`
Expected: FAIL — `assert not ({'usage_source', ...} & {...})` üç kolon hâlâ mevcut

- [ ] **Step 3: Remove the three screen columns**

`src/components/crm_inventory_report.py:82`, `_PRODUCT_MATCHING_COLUMNS` şu hale gelir:

```python
_PRODUCT_MATCHING_COLUMNS = [
    {"name": "SKU", "id": "productnumber"},
    {"name": "Product", "id": "product_name"},
    {"name": "Unit", "id": "resource_unit"},
    {"name": "CRM Sold", "id": "crm_sold_fmt"},
    {"name": "Status", "id": "match_status"},
    {"name": "Matching Rule", "id": "matching_rule"},
    {"name": "Panel", "id": "panel_key"},
    {"name": "Tables", "id": "infra_tables_fmt"},
]
```

- [ ] **Step 4: Remove the three fields from the export path**

`src/components/crm_inventory_report.py:712`, `prepare_product_matching_row()` şu hale gelir:

```python
def prepare_product_matching_row(row: dict[str, Any]) -> dict[str, Any]:
    """Format product matching registry row for DataTable / export."""
    sold_qty = row.get("crm_sold_qty")
    sold_tl = row.get("crm_sold_tl")
    try:
        sold_fmt = f"{float(sold_qty or 0):,.1f}"
        if sold_tl is not None:
            sold_fmt = f"{sold_fmt}\n({float(sold_tl):,.0f} TL)"
    except (TypeError, ValueError):
        sold_fmt = str(sold_qty or "")

    tables = row.get("infra_tables") or []
    return {
        **row,
        "crm_sold_fmt": sold_fmt,
        "infra_tables_fmt": ", ".join(str(t) for t in tables) if tables else "—",
        "panel_key": row.get("panel_key") or "—",
        "matching_rule": row.get("matching_rule") or "—",
    }
```

`_num()` iç fonksiyonu tamamen silinir — tek kullanıcısı kaldırılan iki alandı.

**Not:** `**row` yayılımı ham `usage_source` / `infra_total` / `infra_used` alanlarını geçirmeye devam eder. Bunları da düşürmek gerekir:

```python
    tables = row.get("infra_tables") or []
    out = {
        **row,
        "crm_sold_fmt": sold_fmt,
        "infra_tables_fmt": ", ".join(str(t) for t in tables) if tables else "—",
        "panel_key": row.get("panel_key") or "—",
        "matching_rule": row.get("matching_rule") or "—",
    }
    # Screen and export are both fed from this dict; dropping them here is what
    # keeps them out of the downloaded workbook, not the column list above.
    for key in ("usage_source", "infra_total", "infra_used"):
        out.pop(key, None)
    return out
```

- [ ] **Step 5: Remove the dead search probe**

`src/components/crm_inventory_report.py:760`, `filter_product_matching_rows()` içindeki şu satırı sil:

```python
            or q in str(r.get("usage_source") or "").casefold()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_crm_inventory_product_matching.py tests/test_crm_inventory_export.py -q`
Expected: PASS

Mevcut `test_prepare_and_filter_product_matching_rows` testi `infra_total`/`infra_used` alanlarını fixture'da tutuyor ama sonucu kontrol etmiyor — kırılmamalı. Kırılırsa fixture'ı değil, yalnızca kaldırılan alanlara dair iddiaları düzelt.

- [ ] **Step 7: Commit**

```bash
git add src/components/crm_inventory_report.py tests/test_crm_inventory_product_matching.py tests/test_crm_inventory_export.py
git commit -m "$(cat <<'EOF'
feat(crm-inventory): drop Usage Source / Infra Total / Infra Used columns

Removed from the Product Matching table and from the Excel export. The
two are fed by separate paths (_PRODUCT_MATCHING_COLUMNS vs
prepare_product_matching_row), so editing only the column list would
have left the fields in the downloaded workbook.

Also drops the now-dead usage_source probe from the search filter.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Unmapped payload'a hesap kimliği ve alias önerisi ekle

**Files:**
- Modify: `shared/customer/unmapped_classifier.py:80-111` (`guess_owner`), `:68-73` (`UnmappedRow`), `:153-160` (`account_keys_from_names`), `:163-227` (payload/classify)
- Modify: `services/customer-api/app/db/queries/unmapped.py:27-31` (`CRM_ACCOUNT_NAMES`)
- Modify: `services/customer-api/app/services/customer_service.py:545-576` (`_load_unmapped_resources`)
- Test: `tests/test_unmapped_classifier.py`

**Interfaces:**
- Consumes: yok
- Produces:
  - `guess_owner_key(name: str, account_keys: Mapping[str, str]) -> str | None` — eşleşen **anahtarı** döndürür (görünen adı değil)
  - `alias_suggestion(name: str) -> str` — VM adının ilk `-` öncesi
  - `account_ids_from_rows(rows: Iterable[Mapping[str, object]]) -> dict[str, str]` — `norm(name) -> accountid`
  - `build_unmapped_payload(..., account_ids: Mapping[str, str] | None = None)` — satırlar `guessed_owner_id`, `suggested_alias`, `suggested_method` alanlarını kazanır
  - `classify_unmapped(..., account_ids: Mapping[str, str] | None = None)`

**Geriye dönük uyumluluk:** `guess_owner()` ve `account_keys_from_names()` mevcut imzalarıyla kalır; 22 test onlara dayanıyor. `guess_owner()` artık `guess_owner_key()` üzerinden çalışır.

- [ ] **Step 1: Write the failing test**

`tests/test_unmapped_classifier.py` dosyasının sonuna ekle:

```python
def test_guess_owner_key_returns_the_matching_key_not_the_display_name():
    """Hesap kimliğini bulabilmek için eşleşen anahtar gerekir, görünen ad yetmez."""
    from shared.customer.unmapped_classifier import guess_owner, guess_owner_key

    keys = {"abrakenerjielektrikuretimanonimsirketi": "ABRAK ENERJİ ELEKTRİK ÜRETİM ANONİM ŞİRKETİ"}

    assert guess_owner_key("Abrak_Enerji-Sophos", keys) == "abrakenerjielektrikuretimanonimsirketi"
    assert guess_owner("Abrak_Enerji-Sophos", keys) == "ABRAK ENERJİ ELEKTRİK ÜRETİM ANONİM ŞİRKETİ"
    assert guess_owner_key("123host", keys) is None


def test_alias_suggestion_is_the_prefix_before_the_first_dash():
    """Buton, ekranda görünen satır grubunu bağlar — daha genişini değil."""
    from shared.customer.unmapped_classifier import alias_suggestion

    assert alias_suggestion("Ada_Gross_Cloud-Appsrv_Restored_20_05_2026") == "Ada_Gross_Cloud"
    assert alias_suggestion("Abrak_Enerji-Sophos") == "Abrak_Enerji"
    # Tiresiz ad: prefix tüm addır, kural tek makineyi bağlar. Uydurulmuş bir
    # kesme noktasıyla bilinmeyen sayıda makine bağlamaktan iyidir.
    assert alias_suggestion("Deneme_Kredi_LOG_Server") == "Deneme_Kredi_LOG_Server"
    assert alias_suggestion("  Padded-Vm  ") == "Padded"


def test_payload_rows_carry_account_id_and_alias_suggestion():
    from shared.customer.unmapped_classifier import (
        account_ids_from_rows,
        account_keys_from_names,
        build_unmapped_payload,
    )

    accounts = [{"name": "ADA GROSS", "accountid": "acc-ada-1"}]
    keys = account_keys_from_names([a["name"] for a in accounts])
    ids = account_ids_from_rows(accounts)

    payload = build_unmapped_payload(
        [("Ada_Gross_Cloud-Oracledb", "vmware"), ("123host", "vmware")],
        owners=[],
        account_keys=keys,
        account_ids=ids,
    )
    by_name = {r["name"]: r for r in payload["rows"]}

    gap = by_name["Ada_Gross_Cloud-Oracledb"]
    assert gap["reason"] == "alias_gap"
    assert gap["guessed_owner"] == "ADA GROSS"
    assert gap["guessed_owner_id"] == "acc-ada-1"
    assert gap["suggested_alias"] == "Ada_Gross_Cloud"
    assert gap["suggested_method"] == "prefix"

    orphan = by_name["123host"]
    assert orphan["reason"] == "orphan"
    assert orphan["guessed_owner_id"] is None
    assert orphan["suggested_alias"] is None


def test_account_ids_are_optional_so_existing_callers_keep_working():
    from shared.customer.unmapped_classifier import account_keys_from_names, build_unmapped_payload

    payload = build_unmapped_payload(
        [("Ada_Gross-Db", "vmware")],
        owners=[],
        account_keys=account_keys_from_names(["ADA GROSS"]),
    )
    row = payload["rows"][0]
    assert row["guessed_owner"] == "ADA GROSS"
    assert row["guessed_owner_id"] is None
    assert row["suggested_alias"] == "Ada_Gross"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_unmapped_classifier.py -q -k "guess_owner_key or alias_suggestion or account_id"`
Expected: FAIL — `ImportError: cannot import name 'guess_owner_key'`

- [ ] **Step 3: Refactor guess_owner into a key-returning core**

`shared/customer/unmapped_classifier.py:80`, mevcut `guess_owner()` fonksiyonunu şununla değiştir:

```python
def guess_owner_key(name: str, account_keys: Mapping[str, str]) -> str | None:
    """Best-effort *account key* for an unmatched name.

    1. Exact key match on the prefix before the first '-' (strong: the
       ``<Customer>-<VMname>`` convention).
    2. Fallback for dash-less names: the longest account key that the folded
       full name starts with (handles ``Deneme_Kredi_LOG_Server``).

    Returns the folded key, or ``None``. The *key* is returned rather than the
    display name because callers need it to look up the CRM account id too;
    guess_owner() below is the display-name view of the same answer.
    """
    raw = (name or "").strip()
    if not raw:
        return None

    prefix = raw.split("-", 1)[0] if "-" in raw else raw
    pkey = norm(prefix)
    full = norm(raw)
    if not pkey and not full:
        return None
    if pkey and pkey in account_keys:  # strong: exact <Customer>-... convention
        return pkey

    # Fuzzy, longest-key-wins, in both directions:
    #   dir A: account key sits at the start of the VM name  (Deneme_Kredi_LOG_Server)
    #   dir B: VM prefix is a short form of a longer legal name (Deneme_Ltd -> DENEME LTD SAN. VE TİC. A.Ş.)
    best_key = ""
    pkey_usable = len(pkey) >= _MIN_STARTSWITH_KEY
    for k in account_keys:
        if len(k) < _MIN_STARTSWITH_KEY or len(k) <= len(best_key):
            continue
        if full.startswith(k) or (pkey_usable and k.startswith(pkey)):
            best_key = k
    return best_key or None


def guess_owner(name: str, account_keys: Mapping[str, str]) -> str | None:
    """Display name for an unmatched name's best-effort owner, or None."""
    key = guess_owner_key(name, account_keys)
    return account_keys[key] if key else None


def alias_suggestion(name: str) -> str | None:
    """The alias value the one-click action writes: the prefix before the first '-'.

    Deliberately narrow. Widening it to the *matched account key* would bind
    machines the operator cannot see on screen; widening a rule later from the
    aliases page is cheaper than discovering an over-claiming one.

    A dash-less name yields the whole name, so the rule binds exactly that one
    machine — better than inventing a cut point.
    """
    raw = (name or "").strip()
    if not raw:
        return None
    return raw.split("-", 1)[0] if "-" in raw else raw
```

- [ ] **Step 4: Add the account-id index**

`shared/customer/unmapped_classifier.py`, `account_keys_from_names()` (satır 153) fonksiyonunun hemen ardına ekle:

```python
def account_ids_from_rows(rows: Iterable[Mapping[str, object]]) -> dict[str, str]:
    """norm(account_name) -> crm accountid, first-writer-wins.

    Kept parallel to account_keys_from_names() rather than merged into it: the
    22 existing classifier tests build key maps from bare name lists, and the
    SQL path has callers that never select accountid.
    """
    ids: dict[str, str] = {}
    for row in rows:
        name = str(row.get("name") or "").strip()
        accountid = str(row.get("accountid") or "").strip()
        if not name or not accountid:
            continue
        k = norm(name)
        if k and k not in ids:
            ids[k] = accountid
    return ids
```

- [ ] **Step 5: Thread the new fields through UnmappedRow, classify and payload**

`UnmappedRow` (satır 68) şu hale gelir:

```python
@dataclass(frozen=True)
class UnmappedRow:
    name: str
    guessed_owner: str | None
    reason: str  # 'alias_gap' | 'orphan'
    guessed_owner_id: str | None = None
    suggested_alias: str | None = None
```

`classify_unmapped()` (satır 202) şu hale gelir:

```python
def classify_unmapped(
    names: Iterable[str],
    owners: Sequence[OwnerMatcher],
    account_keys: Mapping[str, str],
    system_prefixes: Sequence[str] = DEFAULT_SYSTEM_PREFIXES,
    account_ids: Mapping[str, str] | None = None,
) -> list[UnmappedRow]:
    """Return one row per name owned by nobody (system VMs excluded, not returned).

    Order preserved; duplicates preserved (caller de-dupes names upstream).
    """
    ids = account_ids or {}
    rows: list[UnmappedRow] = []
    for name in names:
        if not name or not name.strip() or not norm(name):
            continue  # skip empties and punctuation-only junk ('-', '---')
        if is_system_vm(name, system_prefixes):
            continue
        name_lower = name.strip().lower()
        if any(m.matches(name_lower) for m in owners):
            continue
        key = guess_owner_key(name, account_keys)
        rows.append(UnmappedRow(
            name=name,
            guessed_owner=account_keys[key] if key else None,
            reason="alias_gap" if key else "orphan",
            guessed_owner_id=ids.get(key) if key else None,
            suggested_alias=alias_suggestion(name) if key else None,
        ))
    return rows
```

`build_unmapped_payload()` (satır 163) şu hale gelir:

```python
def build_unmapped_payload(
    names_with_platform: Iterable[tuple[str, str]],
    owners: Sequence[OwnerMatcher],
    account_keys: Mapping[str, str],
    system_prefixes: Sequence[str] = DEFAULT_SYSTEM_PREFIXES,
    account_ids: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Full response payload: sorted rows (+platform) and reason counts.

    alias_gap rows sort first (they are the actionable worklist), then by guessed
    owner, then name.
    """
    name_platform: dict[str, str] = {}
    for name, platform in names_with_platform:
        if name and name not in name_platform:
            name_platform[name] = platform or ""

    classified = classify_unmapped(
        name_platform.keys(), owners, account_keys, system_prefixes, account_ids
    )
    rows = [
        {
            "name": r.name,
            "platform": name_platform.get(r.name, ""),
            "guessed_owner": r.guessed_owner,
            "guessed_owner_id": r.guessed_owner_id,
            "suggested_alias": r.suggested_alias,
            "suggested_method": "prefix" if r.suggested_alias else None,
            "reason": r.reason,
            "kind": "vm",
        }
        for r in classified
    ]
    rows.sort(key=lambda d: (
        d["reason"] != "alias_gap",
        (d["guessed_owner"] or "").casefold(),
        d["name"].casefold(),
    ))
    return {
        "rows": rows,
        "total": len(rows),
        "alias_gap_count": sum(1 for d in rows if d["reason"] == "alias_gap"),
        "orphan_count": sum(1 for d in rows if d["reason"] == "orphan"),
    }
```

`"kind": "vm"` alanı şimdiden eklenir — Görev 7 backup satırlarını aynı listeye koyacak ve arayüz sekmeleri bu alanla ayıracak.

- [ ] **Step 6: Run classifier tests**

Run: `./.venv/bin/python -m pytest tests/test_unmapped_classifier.py -q`
Expected: PASS — yeni 4 test dahil, mevcut 22 test kırılmadan

- [ ] **Step 7: Select accountid in the SQL**

`services/customer-api/app/db/queries/unmapped.py:27`, `CRM_ACCOUNT_NAMES` şu hale gelir:

```python
# All CRM accounts (for fuzzy alias-gap owner guessing + the one-click alias
# action, which needs the accountid to address the save endpoint).
CRM_ACCOUNT_NAMES = """
SELECT DISTINCT name, accountid
FROM public.discovery_crm_accounts
WHERE name IS NOT NULL AND btrim(name) <> ''
"""
```

- [ ] **Step 8: Wire it in the service**

`services/customer-api/app/services/customer_service.py:545`, `_load_unmapped_resources()` şu hale gelir:

```python
    def _load_unmapped_resources(self, start, end) -> dict:
        from app.db.queries import unmapped as uq
        from shared.customer.unmapped_classifier import (
            account_ids_from_rows,
            account_keys_from_names,
            build_unmapped_payload,
            owner_matchers_from_mappings,
        )

        names_with_platform: list[tuple[str, str]] = []
        for sql, platform in (
            (uq.UNMAPPED_VMWARE_NAMES, "vmware"),
            (uq.UNMAPPED_NUTANIX_NAMES, "nutanix"),
        ):
            for row in self._run_query(sql, (start, end)):
                name = str(row.get("name") or "").strip()
                if name:
                    names_with_platform.append((name, platform))

        account_rows = [r for r in self._run_query(uq.CRM_ACCOUNT_NAMES, ()) if r.get("name")]
        account_names = [str(r.get("name") or "").strip() for r in account_rows]
        account_keys = account_keys_from_names(account_names)
        account_ids = account_ids_from_rows(account_rows)

        # Ownership = every VM mapping rule (flattened from the per-account index)
        # unioned with each customer's display-name fallback (safe over-claim).
        mapping_index = self._load_source_mapping_index()
        mapping_rows = [row for rows in mapping_index.values() for row in rows]
        owners = owner_matchers_from_mappings(mapping_rows, display_names=account_names)

        return build_unmapped_payload(
            names_with_platform, owners, account_keys, account_ids=account_ids
        )
```

- [ ] **Step 9: Run the full affected suites**

Run: `./.venv/bin/python -m pytest tests/test_unmapped_classifier.py tests/test_unmapped_page.py services/customer-api/tests/ -q`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add shared/customer/unmapped_classifier.py services/customer-api/app/db/queries/unmapped.py services/customer-api/app/services/customer_service.py tests/test_unmapped_classifier.py
git commit -m "$(cat <<'EOF'
feat(unmapped): carry CRM account id and alias suggestion on each row

The one-click alias action needs the accountid to address the save
endpoint, and the alias value it would write. Both are produced where
the owner guess already happens, so the UI never re-derives a prefix of
its own — that drift is what match.py was written to prevent.

guess_owner() is refactored onto guess_owner_key(), which returns the
matched key rather than the display name; the 22 existing classifier
tests keep their signatures.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Mapping birleştirme yardımcısı + GUI cache invalidasyonu

**Files:**
- Modify: `src/utils/crm_source_mapping_ui.py` (saf yardımcı ekleme)
- Modify: `src/services/api_client.py:2467-2477` (`_invalidate_customer_views_cache`)
- Test: `tests/test_crm_source_mapping_ui.py` (yoksa oluştur), `tests/test_api_client_cache_invalidation.py` (oluştur)

**Interfaces:**
- Consumes: yok
- Produces: `merge_source_mapping(existing: list[dict], entry: dict) -> tuple[list[dict], bool]` — `(birleşmiş liste, yazma gerekli mi)`

**İki ayrı hata bu görevde kapanıyor:**
1. `PUT` tüm mapping'leri değiştirdiği için birleştirme şart — yoksa müşterinin diğer alias'ları silinir.
2. GUI cache'i `api:unmapped_resources:*` anahtarını temizlemiyor — buton kaydetse bile sayfa bayat listeyi gösterir ve satır ekranda kalır.

- [ ] **Step 1: Write the failing test**

Yeni dosya `tests/test_crm_source_mapping_merge.py`:

```python
"""PUT /crm/aliases/{id}/source-mappings replaces ALL mappings for an account,
so every write path must send the union of old + new. These pin that.
"""
from src.utils.crm_source_mapping_ui import merge_source_mapping

_NEW = {
    "data_source": "virtualization",
    "match_method": "prefix",
    "match_value": "Ada_Gross_Cloud",
    "enabled": True,
    "priority": 100,
}


def test_merge_appends_without_dropping_existing_mappings():
    existing = [
        {"data_source": "virtualization", "match_method": "contains", "match_value": "Ada Gross"},
        {"data_source": "backup_netbackup", "match_method": "prefix", "match_value": "ada-gros"},
    ]
    merged, changed = merge_source_mapping(existing, _NEW)

    assert changed is True
    assert len(merged) == 3
    assert existing[0] in merged and existing[1] in merged
    assert merged[-1]["match_value"] == "Ada_Gross_Cloud"


def test_merge_is_idempotent_on_an_identical_rule():
    existing = [dict(_NEW)]
    merged, changed = merge_source_mapping(existing, _NEW)

    assert changed is False
    assert merged == existing


def test_merge_compares_value_case_insensitively_like_ilike_does():
    """Match values resolve through ILIKE, so 'ADA_GROSS_CLOUD' is the same rule."""
    existing = [{**_NEW, "match_value": "ADA_GROSS_CLOUD"}]
    _, changed = merge_source_mapping(existing, _NEW)

    assert changed is False


def test_merge_treats_a_different_method_as_a_different_rule():
    existing = [{**_NEW, "match_method": "contains"}]
    merged, changed = merge_source_mapping(existing, _NEW)

    assert changed is True
    assert len(merged) == 2


def test_merge_does_not_mutate_the_caller_list():
    existing = [{"data_source": "virtualization", "match_method": "contains", "match_value": "x"}]
    merge_source_mapping(existing, _NEW)

    assert len(existing) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_crm_source_mapping_merge.py -q`
Expected: FAIL — `ImportError: cannot import name 'merge_source_mapping'`

- [ ] **Step 3: Implement the merge helper**

`src/utils/crm_source_mapping_ui.py` sonuna ekle:

```python
def _rule_identity(mapping: dict) -> tuple[str, str, str]:
    """The triple that makes two mappings the same rule.

    match_value is lowercased because values resolve through ILIKE (see
    shared.customer.match.sql_pattern) — 'ADA_GROSS' and 'Ada_Gross' claim
    exactly the same rows, so writing both would be a silent duplicate.
    """
    return (
        str(mapping.get("data_source") or "").strip(),
        str(mapping.get("match_method") or "").strip().lower(),
        str(mapping.get("match_value") or "").strip().lower(),
    )


def merge_source_mapping(existing: list[dict], entry: dict) -> tuple[list[dict], bool]:
    """Union `entry` into `existing`. Returns (merged, needs_write).

    The save endpoint replaces every mapping an account has, so callers must
    send old + new together; appending is not optional. Returns needs_write
    False when the rule is already present, so the caller can skip the PUT
    entirely rather than rewrite an unchanged set.
    """
    merged = [dict(m) for m in (existing or [])]
    identity = _rule_identity(entry)
    if any(_rule_identity(m) == identity for m in merged):
        return merged, False
    merged.append(dict(entry))
    return merged, True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_crm_source_mapping_merge.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Write the failing cache test**

Yeni dosya `tests/test_unmapped_cache_invalidation.py`:

```python
"""The unmapped view is the complement of every mapping, so a mapping write
must drop it. customer-api already does this server-side
(customer_service.apply_mapping_invalidation); the GUI response cache did not,
which left the just-fixed row on screen after a successful save.
"""


def test_mapping_write_drops_the_gui_unmapped_response_cache():
    from src.services import api_client

    ck = "api:unmapped_resources:preset=7d"
    api_client._api_response_cache.set(ck, {"rows": [], "total": 0})
    assert api_client._api_response_cache.get(ck) is not None

    api_client._invalidate_customer_views_cache()

    assert api_client._api_response_cache.get(ck) is None
```

- [ ] **Step 6: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_unmapped_cache_invalidation.py -q`
Expected: FAIL — `assert <dict> is None`, anahtar hâlâ cache'te

- [ ] **Step 7: Add the missing prefix**

`src/services/api_client.py:2473`, `_invalidate_customer_views_cache()` şu hale gelir:

```python
    _api_response_cache.delete_prefix("api:customer_resources:")
    # The unmapped view is the complement of every mapping, so any mapping
    # write changes it. customer-api drops its own copy already; without this
    # line the GUI kept serving the stale list and the row the operator just
    # fixed stayed on screen.
    _api_response_cache.delete_prefix("api:unmapped_resources:")
    _api_response_cache.delete("api:crm_aliases")
    _api_response_cache.delete("api:customer_catalog")
    _api_response_cache.delete("api:customer_overview")
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_unmapped_cache_invalidation.py tests/test_crm_source_mapping_merge.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/utils/crm_source_mapping_ui.py src/services/api_client.py tests/test_crm_source_mapping_merge.py tests/test_unmapped_cache_invalidation.py
git commit -m "$(cat <<'EOF'
feat(crm-aliases): add mapping merge helper, drop stale unmapped cache

Two prerequisites for the one-click alias action:

merge_source_mapping() unions a new rule into an account's existing set.
The save endpoint replaces every mapping an account has, so appending is
not optional — writing the bare new rule would delete the rest. It also
reports whether a write is needed at all, making a repeat click a no-op.

_invalidate_customer_views_cache() now drops api:unmapped_resources:*.
customer-api already invalidated its own copy on every mapping write;
the GUI cache did not, so a successful save still rendered the stale
list and the fixed row stayed on screen.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Eşleşmeyen Veriler sayfasına işlem kolonu ve callback

**Files:**
- Modify: `src/pages/unmapped_resources.py` (tablo, sekme, düzen, link düzeltmesi)
- Create: `src/pages/unmapped_resources_callbacks.py`
- Modify: `app.py:162` civarı (callback modülünü import et)
- Test: `tests/test_unmapped_page.py`, yeni `tests/test_unmapped_alias_action.py`

**Interfaces:**
- Consumes: Görev 3'ten `guessed_owner_id` / `suggested_alias` / `suggested_method` / `kind` alanları; Görev 4'ten `merge_source_mapping()`
- Produces:
  - Tablo id'si `{"type": "unmapped-table", "kind": "vm"}` — desen eşleşmeli, Görev 8 `kind="backup"` ile ikincisini ekler
  - `ACTION_LABEL: str = "Alias ekle"`
  - `apply_alias_suggestion(row: dict) -> tuple[str, str]` — `(bildirim_türü, mesaj)`; saf olmayan, api_client çağırır

**Neden buton değil `active_cell`:** `dash_table.DataTable` hücre içinde bileşen barındıramaz. Tabloyu `html.Table`'a çevirmek kolon filtreleme ve sıralamayı kaybettirir — sayfa bunları metinle vaat ediyor (`unmapped_resources.py:132`). Hücre buton gibi biçimlendirilir, tıklama `active_cell` ile yakalanır.

- [ ] **Step 1: Write the failing test for the action column**

`tests/test_unmapped_page.py` içindeki `_PAYLOAD` sabitini genişlet:

```python
_PAYLOAD = {
    "rows": [
        {"name": "Acme_Kilit-Web01", "guessed_owner": "Örnek Kilit A.Ş.",
         "platform": "Nutanix", "reason": "alias_gap", "kind": "vm",
         "guessed_owner_id": "acc-1", "suggested_alias": "Acme_Kilit",
         "suggested_method": "prefix"},
        {"name": "123host", "guessed_owner": None, "platform": "VMware",
         "reason": "orphan", "kind": "vm",
         "guessed_owner_id": None, "suggested_alias": None,
         "suggested_method": None},
    ],
    "total": 2,
    "alias_gap_count": 1,
    "orphan_count": 1,
}
```

Dosyanın sonuna ekle:

```python
def test_alias_gap_rows_offer_an_action_and_orphans_do_not():
    """Sahipsiz satırda bağlanacak müşteri yok; işlem hücresi boş kalır."""
    from src.pages.unmapped_resources import ACTION_LABEL, _table_rows

    rows = _table_rows(_PAYLOAD["rows"])
    by_name = {r["name"]: r for r in rows}

    assert by_name["Acme_Kilit-Web01"]["action"] == ACTION_LABEL
    assert by_name["123host"]["action"] == ""


def test_table_rows_carry_a_stable_key_for_the_click_handler():
    """active_cell yalnızca satır indeksi verir; sıralama/filtre sonrası indeks kayar."""
    from src.pages.unmapped_resources import _table_rows

    rows = _table_rows(_PAYLOAD["rows"])
    assert rows[0]["row_key"] == "vm::Acme_Kilit-Web01"
    assert rows[1]["row_key"] == "vm::123host"


def test_hint_links_to_customer_aliases_not_internal_aliases():
    """İç Alias yalnızca INTERNAL rezerve hesabı içindir; müşteri alias'ı oraya yazılmaz."""
    out = _render()
    assert "/settings/integrations/crm/internal-aliases" not in out
    assert "crm-aliases" in out or "crm/aliases" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_unmapped_page.py -q`
Expected: FAIL — `ImportError: cannot import name 'ACTION_LABEL'`

- [ ] **Step 3: Add the action column and row key**

`src/pages/unmapped_resources.py` içinde `_TABLE_ID` sabitini (satır 22) şununla değiştir:

```python
ACTION_LABEL = "Alias ekle"
# Canonical route from src/pages/settings/shell.py:85 (ADMIN_PREFIX =
# "/administration"). The hint previously pointed at
# /settings/integrations/crm/internal-aliases, which is both the wrong page
# and the wrong prefix.
CUSTOMER_ALIASES_HREF = "/administration/integrations/crm/aliases"


def table_id(kind: str) -> dict[str, str]:
    """Pattern-matching id so one callback serves every source tab."""
    return {"type": "unmapped-table", "kind": kind}
```

`_TABLE_ID` kullanımlarını `table_id("vm")` ile değiştir.

`_table_rows()` (satır 48) şu hale gelir:

```python
def _table_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        kind = r.get("kind") or "vm"
        actionable = bool(r.get("reason") == "alias_gap" and r.get("guessed_owner_id")
                          and r.get("suggested_alias"))
        out.append({
            # active_cell reports a viewport row index, which moves as soon as
            # the operator sorts or filters. The click handler resolves the row
            # through this key instead.
            "row_key": f"{kind}::{r.get('name') or ''}",
            "guessed_owner": r.get("guessed_owner") or "—",
            "name": r.get("name") or "",
            "platform": _PLATFORM_LABEL.get(r.get("platform"), r.get("platform") or ""),
            "reason": _REASON_LABEL.get(r.get("reason"), r.get("reason") or ""),
            "action": ACTION_LABEL if actionable else "",
        })
    return out
```

- [ ] **Step 4: Render the column and style it like a button**

`_vm_table()` içindeki `columns=` listesine ekle ve gizli kolonu bildir:

```python
            columns=[
                {"name": "TAHMİNİ SAHİP", "id": "guessed_owner"},
                {"name": "MAKİNE ADI", "id": "name"},
                {"name": "PLATFORM", "id": "platform"},
                {"name": "NEDEN", "id": "reason"},
                {"name": "İŞLEM", "id": "action"},
            ],
            hidden_columns=["row_key"],
```

`style_data_conditional` listesine, mevcut girdilerin **önüne** ekle:

```python
                # The cell IS the button: DataTable cannot host a component, and
                # replacing the table with html.Table would cost the native
                # column filtering and sorting this page advertises above.
                {"if": {"column_id": "action", "filter_query": f"{{action}} = '{ACTION_LABEL}'"},
                 "color": "#4318FF", "fontWeight": "700", "cursor": "pointer",
                 "textDecoration": "underline"},
```

- [ ] **Step 5: Fix the hint link**

`src/pages/unmapped_resources.py:109`, `hint` içindeki `dcc.Link` şu hale gelir:

```python
            dcc.Link("Ayarlar › CRM › Müşteri Alias", href=CUSTOMER_ALIASES_HREF),
```

Ve satır 108-110'daki metin şu hale gelir:

```python
            "‘Alias eksik’ satırlar aslında gerçek bir müşterinin makineleridir; adı "
            "eşleşmediği için sahipsiz görünürler. ‘İŞLEM’ sütunundaki ‘Alias ekle’ "
            "bağlantısı kuralı tek tıkla ekler; elle düzenlemek için ",
            dcc.Link("Ayarlar › CRM › Müşteri Alias", href=CUSTOMER_ALIASES_HREF),
            " ekranını kullanın.",
```

- [ ] **Step 6: Confirm the route still resolves**

Run: `grep -n "integrations/crm/aliases" src/pages/settings/shell.py`

Expected: `/administration/integrations/crm/aliases` hem gezinme listesinde (satır 85) hem route tablosunda (satır 136) görünür. Görünmezse `CUSTOMER_ALIASES_HREF` sabitini `shell.py`'deki gerçek değere göre düzelt ve testteki iddiayı da güncelle.

- [ ] **Step 7: Run page tests**

Run: `./.venv/bin/python -m pytest tests/test_unmapped_page.py -q`
Expected: PASS

- [ ] **Step 8: Write the failing callback test**

Yeni dosya `tests/test_unmapped_alias_action.py`:

```python
"""The one-click alias action. The save endpoint replaces an account's whole
mapping set, so these pin that the union is sent — not the bare new rule.
"""
from unittest.mock import patch

_ROW = {
    "row_key": "vm::Acme_Kilit-Web01",
    "guessed_owner": "Örnek Kilit A.Ş.",
    "name": "Acme_Kilit-Web01",
    "reason": "Alias eksik",
    "action": "Alias ekle",
}

_PAYLOAD_ROW = {
    "name": "Acme_Kilit-Web01",
    "guessed_owner": "Örnek Kilit A.Ş.",
    "guessed_owner_id": "acc-1",
    "suggested_alias": "Acme_Kilit",
    "suggested_method": "prefix",
    "reason": "alias_gap",
    "kind": "vm",
    "platform": "nutanix",
}

_EXISTING_ALIAS = {
    "crm_accountid": "acc-1",
    "crm_account_name": "Örnek Kilit A.Ş.",
    "source_mappings": [
        {"data_source": "backup_netbackup", "match_method": "prefix", "match_value": "acme-kili"},
    ],
}


def test_action_sends_the_union_not_just_the_new_rule():
    from src.pages.unmapped_resources_callbacks import apply_alias_suggestion

    with patch("src.services.api_client.get_crm_aliases", return_value=[_EXISTING_ALIAS]), \
         patch("src.services.api_client.put_crm_source_mappings",
               return_value=([], None)) as put:
        status, _ = apply_alias_suggestion(_PAYLOAD_ROW)

    assert status == "saved"
    (account_id,), kwargs = put.call_args
    assert account_id == "acc-1"
    sent = kwargs["mappings"]
    assert len(sent) == 2
    assert {"backup_netbackup", "virtualization"} == {m["data_source"] for m in sent}
    new = [m for m in sent if m["data_source"] == "virtualization"][0]
    assert new["match_method"] == "prefix"
    assert new["match_value"] == "Acme_Kilit"


def test_repeat_click_writes_nothing():
    from src.pages.unmapped_resources_callbacks import apply_alias_suggestion

    already = {
        **_EXISTING_ALIAS,
        "source_mappings": [
            {"data_source": "virtualization", "match_method": "prefix", "match_value": "Acme_Kilit"},
        ],
    }
    with patch("src.services.api_client.get_crm_aliases", return_value=[already]), \
         patch("src.services.api_client.put_crm_source_mappings") as put:
        status, _ = apply_alias_suggestion(_PAYLOAD_ROW)

    assert status == "exists"
    put.assert_not_called()


def test_a_row_without_an_account_id_is_refused():
    from src.pages.unmapped_resources_callbacks import apply_alias_suggestion

    with patch("src.services.api_client.put_crm_source_mappings") as put:
        status, _ = apply_alias_suggestion({**_PAYLOAD_ROW, "guessed_owner_id": None})

    assert status == "error"
    put.assert_not_called()


def test_a_cache_warning_still_counts_as_saved():
    """The write has already committed by the time the cache drop is attempted;
    reporting failure would say 'not saved' about a saved mapping."""
    from src.pages.unmapped_resources_callbacks import apply_alias_suggestion

    with patch("src.services.api_client.get_crm_aliases", return_value=[_EXISTING_ALIAS]), \
         patch("src.services.api_client.put_crm_source_mappings",
               return_value=([], "cache not cleared")):
        status, message = apply_alias_suggestion(_PAYLOAD_ROW)

    assert status == "warning"
    assert "cache not cleared" in message


def test_a_backend_failure_is_reported_not_raised():
    from src.pages.unmapped_resources_callbacks import apply_alias_suggestion

    with patch("src.services.api_client.get_crm_aliases", side_effect=RuntimeError("api down")):
        status, message = apply_alias_suggestion(_PAYLOAD_ROW)

    assert status == "error"
    assert message
```

- [ ] **Step 9: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_unmapped_alias_action.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.pages.unmapped_resources_callbacks'`

- [ ] **Step 10: Implement the callback module**

Yeni dosya `src/pages/unmapped_resources_callbacks.py`:

```python
"""One-click alias action for Eşleşmeyen Veriler.

The cell IS the button: dash_table.DataTable cannot host a component, and
replacing the table with html.Table would cost the native column filtering and
sorting the page advertises. So the action column renders text and the click
arrives as active_cell.
"""
from __future__ import annotations

import logging

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, no_update
from dash.exceptions import PreventUpdate

from src.pages import unmapped_resources as page
from src.services import api_client as api
from src.utils.crm_source_mapping_ui import find_alias, merge_source_mapping

logger = logging.getLogger(__name__)

_STATUS_COLOR = {"saved": "teal", "exists": "blue", "warning": "yellow", "error": "red"}


def apply_alias_suggestion(row: dict) -> tuple[str, str]:
    """Write the suggested alias rule for one unmapped row.

    Returns (status, message) where status is saved | exists | warning | error.
    Never raises: this runs from a click handler, and a traceback there takes
    the whole page down rather than the one action that failed.
    """
    account_id = str(row.get("guessed_owner_id") or "").strip()
    alias_value = str(row.get("suggested_alias") or "").strip()
    method = str(row.get("suggested_method") or "prefix").strip()
    data_source = "backup_netbackup" if row.get("kind") == "backup" else "virtualization"

    if not account_id or not alias_value:
        return "error", "Bu satır için bağlanacak müşteri tahmini yok."

    entry = {
        "data_source": data_source,
        "match_method": method,
        "match_value": alias_value,
        "enabled": True,
        "priority": 100,
        "notes": "Eşleşmeyen Veriler ekranından tek tıkla eklendi.",
    }

    try:
        alias = find_alias(api.get_crm_aliases() or [], account_id)
        existing = list((alias or {}).get("source_mappings") or [])
        # The save endpoint replaces every mapping this account has, so the
        # union has to go out; sending the bare new rule would delete the rest.
        merged, needs_write = merge_source_mapping(existing, entry)
        if not needs_write:
            return "exists", f"‘{alias_value}’ kuralı bu müşteride zaten ekli."

        _, cache_warning = api.put_crm_source_mappings(
            account_id,
            crm_account_name=(alias or {}).get("crm_account_name") or row.get("guessed_owner"),
            mappings=merged,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("alias suggestion failed account=%s value=%s", account_id, alias_value)
        return "error", f"Kaydedilemedi: {exc}"

    if cache_warning:
        # The DB write committed before the cache drop was attempted, so this
        # is a warning about staleness, not a failed save.
        return "warning", f"Kaydedildi, ancak önbellek temizlenemedi: {cache_warning}"
    return "saved", f"‘{alias_value}’ kuralı {row.get('guessed_owner')} müşterisine eklendi."


def _notification(status: str, message: str) -> dmc.Alert:
    return dmc.Alert(
        message,
        color=_STATUS_COLOR.get(status, "gray"),
        variant="light",
        withCloseButton=True,
        mb="md",
    )


@callback(
    Output(page.BODY_ID, "children"),
    Output(page.TOAST_ID, "children"),
    Input({"type": "unmapped-table", "kind": ALL}, "active_cell"),
    State({"type": "unmapped-table", "kind": ALL}, "derived_viewport_data"),
    State({"type": "unmapped-table", "kind": ALL}, "id"),
    State(page.STORE_ID, "data"),
    prevent_initial_call=True,
)
def _on_action_cell(active_cells, viewport_data, table_ids, store):
    if not ctx.triggered_id:
        raise PreventUpdate

    # Resolve which table fired by id, not by scanning for the first active
    # cell in the action column: once the operator has clicked an action in
    # both tabs, both tables hold a stale active_cell there and a scan would
    # keep re-firing the first one.
    triggered_index = None
    for i, table_id_ in enumerate(table_ids or []):
        if table_id_ == ctx.triggered_id:
            triggered_index = i
            break
    if triggered_index is None:
        raise PreventUpdate

    cell = (active_cells or [])[triggered_index]
    if not cell or cell.get("column_id") != "action":
        raise PreventUpdate

    rows = (viewport_data or [])[triggered_index] or []
    row_index = cell.get("row")
    if row_index is None or row_index >= len(rows):
        raise PreventUpdate

    row_key = rows[row_index].get("row_key")
    payload_row = page.find_payload_row(store or {}, row_key)
    if not payload_row:
        raise PreventUpdate

    status, message = apply_alias_suggestion(payload_row)
    if status in ("error", "exists"):
        # Nothing changed on the server, so re-rendering the body would only
        # cost a refetch and lose the operator's sort/filter state.
        return no_update, _notification(status, message)

    return page.build_body(store.get("time_range")), _notification(status, message)
```

- [ ] **Step 11: Add the page hooks the callback depends on**

`src/pages/unmapped_resources.py` içine ekle (modül seviyesinde sabitler, `ACTION_LABEL` yanına):

```python
BODY_ID = "unmapped-body"
TOAST_ID = "unmapped-toast"
STORE_ID = "unmapped-store"


def find_payload_row(store: dict, row_key: str | None) -> dict | None:
    """Resolve a clicked table row back to its full payload row.

    Matched on row_key rather than viewport index: active_cell reports the
    index within the current page of a sorted/filtered view, which does not
    address the payload.
    """
    if not row_key:
        return None
    for r in (store or {}).get("rows") or []:
        if f"{r.get('kind') or 'vm'}::{r.get('name') or ''}" == row_key:
            return r
    return None
```

`build_layout()` (satır 60) şu hale gelir:

```python
def build_layout(tr: dict | None = None, visible_sections=None) -> html.Div:
    tr = tr or default_time_range()
    return html.Div(style={"padding": "8px 4px"}, children=[
        _header(),
        html.Div(id=TOAST_ID),
        html.Div(id=BODY_ID, children=build_body(tr)),
    ])


def build_body(tr: dict | None = None) -> list:
    """KPIs, hint and tables — re-rendered after a successful alias write."""
    tr = tr or default_time_range()
    try:
        data = api.get_unmapped_resources(tr)
    except Exception:
        data = {"rows": [], "total": 0, "alias_gap_count": 0, "orphan_count": 0}

    rows = data.get("rows") or []
    total = int(data.get("total") or 0)
    alias_gap = int(data.get("alias_gap_count") or 0)
    orphan = int(data.get("orphan_count") or 0)

    kpis = dmc.SimpleGrid(cols={"base": 1, "sm": 3}, spacing="md", mb="md", children=[
        _kpi("Toplam eşleşmeyen", total, "solar:server-square-bold-duotone", "#4318FF"),
        _kpi("Alias eksik (düzeltilebilir)", alias_gap, "solar:pen-new-square-bold-duotone", "#FFB547"),
        _kpi("Sahipsiz", orphan, "solar:ghost-bold-duotone", "#A3AED0"),
    ])

    tabs = dmc.Tabs(value="virt", children=[
        dmc.TabsList([
            dmc.TabsTab("Sanallaştırma", value="virt"),
        ]),
        dmc.TabsPanel(value="virt", pt="md",
                      children=_vm_table([r for r in rows if (r.get("kind") or "vm") == "vm"])),
    ])

    return [
        dcc.Store(id=STORE_ID, data={"rows": rows, "time_range": tr}),
        kpis,
        _hint(),
        tabs,
    ]
```

Mevcut `header` ve `hint` blokları `_header()` ve `_hint()` fonksiyonlarına taşınır — gövdesi aynen korunur, yalnızca `def _header() -> dmc.Group:` / `def _hint() -> dmc.Alert:` sarmalayıcısı eklenir.

- [ ] **Step 12: Register the callback module**

`app.py:162` civarına, mevcut kalıba uyarak ekle:

```python
from src.pages import unmapped_resources_callbacks  # noqa: F401 — unmapped one-click alias action
```

- [ ] **Step 13: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_unmapped_alias_action.py tests/test_unmapped_page.py -q`
Expected: PASS

- [ ] **Step 14: Verify the app still boots (callback ids must resolve)**

Run: `./.venv/bin/python -c "import app; print('ok')"`
Expected: `ok` — hata verirse callback Output id'si sayfada yok demektir

- [ ] **Step 15: Commit**

```bash
git add src/pages/unmapped_resources.py src/pages/unmapped_resources_callbacks.py app.py tests/test_unmapped_page.py tests/test_unmapped_alias_action.py
git commit -m "$(cat <<'EOF'
feat(unmapped): one-click alias action on the alias-gap worklist

Adds an İŞLEM column that writes the suggested prefix rule for the
guessed customer, then re-renders the page so the fixed row leaves the
list and the KPI cards follow.

The cell is the button: DataTable cannot host a component, and swapping
in an html.Table would cost the native column filtering and sorting the
page advertises. Clicks arrive as active_cell and resolve through a
hidden row_key, because the reported index belongs to the sorted and
filtered viewport, not the payload.

Also points the hint at Customer Aliases; it linked to Internal Aliases,
which only ever holds the reserved INTERNAL account.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: NetBackup policy adlandırma standardı (saf modül)

**Files:**
- Create: `shared/customer/backup_policy.py`
- Test: `tests/test_backup_policy.py`

**Interfaces:**
- Consumes: `shared.customer.unmapped_classifier.norm`
- Produces:
  - `policy_tokens_for_account(name: str) -> set[str]`
  - `build_policy_index(accounts: Iterable[Mapping[str, object]]) -> dict[str, list[tuple[str, str]]]` — token → `[(display_name, accountid)]`
  - `guess_policy_owner(policy: str, index) -> tuple[str, list[tuple[str, str]]] | None` — `(eşleşen_token, adaylar)`

**Standart (Excel'den türetildi, canlı veriyle doğrulandı):** policy adı `<ilk4(kelime1)>[-<ilk4(kelime2)>]-<workload>-<env>-<tip>`. Excel'in 233 token'ının 215'i (%92) uyuyor.

- [ ] **Step 1: Write the failing test**

Yeni dosya `tests/test_backup_policy.py`:

```python
"""NetBackup policy naming standard, derived from backup-musteri-isim.xlsx and
validated against 1,294 live policy names.

Standard: <first4(word1)>[-<first4(word2)>]-<workload>-<env>-<type>, Turkish-folded.
"""
from shared.customer.backup_policy import (
    build_policy_index,
    guess_policy_owner,
    policy_tokens_for_account,
)


def test_tokens_follow_the_first_four_letters_of_each_word():
    assert "abc-dete" in policy_tokens_for_account("ABC Deterjan")
    assert "ayak-duny" in policy_tokens_for_account("Ayakkabı Dünyası")
    assert "cele-hold" in policy_tokens_for_account("Çelebi Holding")


def test_turkish_characters_fold_the_same_way_the_classifier_folds_them():
    assert "capa-medi" in policy_tokens_for_account("Çapa Medikal")
    assert "alki-kagi" in policy_tokens_for_account("Alkim Kağıt")
    assert "bizi-topt" in policy_tokens_for_account("Bizim Toptan")


def test_single_word_accounts_yield_the_short_and_the_full_form():
    tokens = policy_tokens_for_account("Aksular")
    assert "aksu" in tokens
    assert "aksular" in tokens


def test_legal_suffixes_are_not_treated_as_name_words():
    """'ABRAK ENERJİ ... ANONİM ŞİRKETİ' must not produce 'abra-anon'."""
    tokens = policy_tokens_for_account("ABRAK ENERJİ ELEKTRİK ÜRETİM ANONİM ŞİRKETİ")
    assert "abra-ener" in tokens
    assert not any(t.endswith("-anon") or t.endswith("-sirk") for t in tokens)


def test_two_segment_token_wins_over_one_segment():
    """abc-dete is more specific than abc; the longer match is the safer owner."""
    index = build_policy_index([
        {"name": "ABC Deterjan", "accountid": "acc-abc-dete"},
        {"name": "ABC Holding", "accountid": "acc-abc-hold"},
    ])
    token, candidates = guess_policy_owner("abc-dete-s4hana-prd-log", index)

    assert token == "abc-dete"
    assert candidates == [("ABC Deterjan", "acc-abc-dete")]


def test_an_ambiguous_token_returns_every_candidate():
    """avro matches AVROMED and AVRORA LLC. Measured on live data: 27% of
    policies land here. Callers must not pick one."""
    index = build_policy_index([
        {"name": "AVROMED", "accountid": "acc-avromed"},
        {"name": "AVRORA LLC", "accountid": "acc-avrora"},
    ])
    token, candidates = guess_policy_owner("avro-CLAVRDB01-H", index)

    assert token == "avro"
    assert len(candidates) == 2
    assert {c[0] for c in candidates} == {"AVROMED", "AVRORA LLC"}


def test_an_unknown_policy_has_no_owner():
    index = build_policy_index([{"name": "ABC Deterjan", "accountid": "acc-1"}])
    assert guess_policy_owner("visa01-vm-image", index) is None
    assert guess_policy_owner("", index) is None


def test_a_token_must_not_match_a_longer_segment_it_merely_starts():
    """'abc' must not claim 'abcdef-prd': the segment boundary is a dash."""
    index = build_policy_index([{"name": "ABC Deterjan", "accountid": "acc-1"}])
    assert guess_policy_owner("abcdef-prd-log", index) is None


def test_candidates_are_ordered_deterministically():
    """Two runs must not disagree about which candidate is listed first."""
    index = build_policy_index([
        {"name": "AVRORA LLC", "accountid": "acc-avrora"},
        {"name": "AVROMED", "accountid": "acc-avromed"},
    ])
    _, candidates = guess_policy_owner("avro-db", index)
    assert candidates == [("AVROMED", "acc-avromed"), ("AVRORA LLC", "acc-avrora")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_backup_policy.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'shared.customer.backup_policy'`

- [ ] **Step 3: Implement the module**

Yeni dosya `shared/customer/backup_policy.py`:

```python
"""NetBackup policy name → CRM account, via the naming standard (pure, no DB).

Derived from ``backup-musteri-isim.xlsx`` (sheet AD-KARŞILIĞI: 189 customers,
233 policy tokens) and validated against 1,294 live policy names:

    <first4(word1)>[-<first4(word2)>]-<workload>-<env>-<type>

Turkish-folded, lowercase. 215 of the sheet's 233 tokens (92%) follow it;
the rest are consonant squeezes (``trkn`` ← Turkon) or unrelated codes
(``visa01``), which no rule derives — the spreadsheet is the authority there
and is loaded separately as a seed.

The standard alone is NOT sufficient to assign an owner: matching all 1,294
live policies against 2,668 CRM accounts leaves 27% matching more than one
account (``avro`` → AVROMED and AVRORA LLC). guess_policy_owner() therefore
returns *every* candidate and refuses to choose; callers surface the ambiguity
rather than guessing.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable, Mapping

from shared.customer.unmapped_classifier import norm

# Legal-form and generic words that are not part of the trading name and never
# contribute a policy token. Folded (norm()) before comparison.
_NAME_STOPWORDS: frozenset[str] = frozenset({
    "anonim", "sirketi", "sirket", "limited", "ltd", "sti",
    "as", "ve", "tic", "ticaret", "san", "sanayi", "holding",
})

_WORD_SPLIT = re.compile(r"[^0-9A-Za-zçğıöşüÇĞİÖŞÜ]+")

# Token length the standard uses per word.
_TOKEN_LEN = 4

# Shortest token trusted on its own. Below this a token claims far too much.
_MIN_TOKEN = 3


def _name_words(name: str) -> list[str]:
    """Folded, stopword-free words of an account name, in order."""
    words = [norm(w) for w in _WORD_SPLIT.split(name or "")]
    return [w for w in words if w and w not in _NAME_STOPWORDS]


def policy_tokens_for_account(name: str) -> set[str]:
    """Every policy prefix this account plausibly owns under the standard."""
    words = _name_words(name)
    if not words:
        return set()

    tokens: set[str] = set()
    head = words[0][:_TOKEN_LEN]

    if len(words) > 1:
        tail = words[1][:_TOKEN_LEN]
        if len(head) >= _MIN_TOKEN and tail:
            tokens.add(f"{head}-{tail}")
    if len(head) >= _TOKEN_LEN:
        tokens.add(head)
    # 'Aksular' appears in live data both as 'aksu' and in full.
    if len(words[0]) > _TOKEN_LEN:
        tokens.add(words[0])
    return tokens


def build_policy_index(
    accounts: Iterable[Mapping[str, object]],
) -> dict[str, list[tuple[str, str]]]:
    """token -> [(display_name, accountid)], each list sorted by display name.

    Sorted so an ambiguous match reports its candidates in the same order on
    every run; dict iteration order would otherwise leak into the UI.
    """
    index: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in accounts:
        name = str(row.get("name") or "").strip()
        accountid = str(row.get("accountid") or "").strip()
        if not name or not accountid:
            continue
        for token in policy_tokens_for_account(name):
            index[token].add((name, accountid))
    return {t: sorted(v) for t, v in index.items()}


def guess_policy_owner(
    policy: str,
    index: Mapping[str, list[tuple[str, str]]],
) -> tuple[str, list[tuple[str, str]]] | None:
    """(matched_token, candidates) for a policy name, or None.

    Tries the two-segment token first (``abc-dete``), then the single segment
    (``avro``): the longer prefix is the more specific claim. Matching is on
    whole dash-separated segments, so ``abc`` never claims ``abcdef-prd``.

    Returns every candidate for the winning token. A caller that picks one
    when there are several will bind backup capacity to the wrong customer,
    which reaches billing — the ambiguity is surfaced instead.
    """
    cleaned = (policy or "").strip().lower()
    if not cleaned:
        return None

    segments = cleaned.split("-")
    candidates_by_length = []
    if len(segments) >= 2:
        candidates_by_length.append("-".join(segments[:2]))
    candidates_by_length.append(segments[0])

    for token in candidates_by_length:
        owners = index.get(token)
        if owners:
            return token, list(owners)
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_backup_policy.py -q`
Expected: PASS (9 tests)

- [ ] **Step 5: Validate the standard against the real spreadsheet**

`tests/test_backup_policy.py` sonuna ekle:

```python
def test_the_standard_reproduces_the_spreadsheets_own_tokens():
    """The sheet is ground truth. If a change to the standard stops
    reproducing its documented tokens, that is a regression, not an
    improvement. These pairs are copied verbatim from AD-KARŞILIĞI.
    """
    documented = {
        "ABC Deterjan": "abc-dete",
        "Akasya Maden": "akas-made",
        "Alkim Kağıt": "alki-kagi",
        "Ayakkabı Dünyası": "ayak-duny",
        "Bizim Toptan": "bizi-topt",
        "Bony Çorap": "bony-cora",
        "Çapa Medikal": "capa-medi",
        "Çelebi Holding": "cele-hold",
        "Azer": "azer",
        "Boyner": "boyner",
    }
    for account, token in documented.items():
        assert token in policy_tokens_for_account(account), f"{account} -> {token}"
```

`Azer` (4 harf) `head` yolundan, `Boyner` (6 harf) tam-kelime yolundan gelir. İkisi de geçmezse `policy_tokens_for_account` tek-kelime dallarını düzelt.

- [ ] **Step 6: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_backup_policy.py -q`
Expected: PASS (10 tests)

- [ ] **Step 7: Commit**

```bash
git add shared/customer/backup_policy.py tests/test_backup_policy.py
git commit -m "$(cat <<'EOF'
feat(backup): NetBackup policy naming standard as a pure module

Derived from backup-musteri-isim.xlsx and validated against 1,294 live
policy names: <first4(word1)>[-<first4(word2)>]-<workload>-<env>-<type>,
Turkish-folded. 215 of the sheet's 233 tokens follow it.

guess_policy_owner returns every candidate for the winning token rather
than picking one. Matching all live policies against 2,668 CRM accounts
leaves 27% ambiguous (avro -> AVROMED and AVRORA LLC); choosing there
would bind backup capacity to the wrong customer and reach billing.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Backup satırlarını unmapped payload'a ekle

**Files:**
- Modify: `services/customer-api/app/db/queries/unmapped.py` (yeni sorgu)
- Modify: `shared/customer/unmapped_classifier.py` (backup sınıflandırma)
- Modify: `services/customer-api/app/services/customer_service.py:545-576`
- Test: `tests/test_unmapped_classifier.py`

**Interfaces:**
- Consumes: Görev 6'dan `build_policy_index()`, `guess_policy_owner()`; Görev 3'ten `owner_matchers_from_mappings()`
- Produces:
  - `BACKUP_OWNER_SOURCES: tuple[str, ...] = ("backup_netbackup", "backup_veeam", "backup_zerto")`
  - `classify_unmapped_policies(policies, owners, policy_index) -> list[dict]`
  - Payload: `rows` listesi backup satırlarını da taşır (`kind="backup"`), `ambiguous_count` alanı eklenir

- [ ] **Step 1: Write the failing test**

`tests/test_unmapped_classifier.py` sonuna ekle:

```python
def test_backup_policies_classify_into_gap_ambiguous_and_orphan():
    from shared.customer.backup_policy import build_policy_index
    from shared.customer.unmapped_classifier import classify_unmapped_policies

    index = build_policy_index([
        {"name": "ABC Deterjan", "accountid": "acc-abc"},
        {"name": "AVROMED", "accountid": "acc-avromed"},
        {"name": "AVRORA LLC", "accountid": "acc-avrora"},
    ])
    rows = classify_unmapped_policies(
        ["abc-dete-s4hana-prd-log", "avro-CLAVRDB01-H", "visa01-vm-image"],
        owners=[],
        policy_index=index,
    )
    by_name = {r["name"]: r for r in rows}

    gap = by_name["abc-dete-s4hana-prd-log"]
    assert gap["reason"] == "alias_gap"
    assert gap["guessed_owner"] == "ABC Deterjan"
    assert gap["guessed_owner_id"] == "acc-abc"
    assert gap["suggested_alias"] == "abc-dete"
    assert gap["suggested_method"] == "prefix"
    assert gap["kind"] == "backup"
    assert gap["platform"] == "netbackup"

    amb = by_name["avro-CLAVRDB01-H"]
    assert amb["reason"] == "ambiguous"
    assert amb["candidate_count"] == 2
    # No single owner is claimed and no action is offered: binding backup
    # capacity to the wrong customer reaches billing.
    assert amb["guessed_owner_id"] is None
    assert amb["suggested_alias"] is None

    assert by_name["visa01-vm-image"]["reason"] == "orphan"


def test_a_policy_already_claimed_by_a_backup_rule_is_not_reported():
    from shared.customer.backup_policy import build_policy_index
    from shared.customer.unmapped_classifier import (
        OwnerMatcher,
        classify_unmapped_policies,
    )

    index = build_policy_index([{"name": "ABC Deterjan", "accountid": "acc-abc"}])
    owners = [OwnerMatcher(owner="ABC Deterjan", kind="prefix", value="abc-dete")]

    rows = classify_unmapped_policies(["abc-dete-s4hana-prd-log"], owners, index)
    assert rows == []


def test_backup_owner_sources_cover_every_backup_data_source():
    """A policy claimed by any backup rule must not appear in the worklist,
    regardless of which backup product the rule was written for."""
    from shared.customer.unmapped_classifier import BACKUP_OWNER_SOURCES

    assert set(BACKUP_OWNER_SOURCES) == {"backup_netbackup", "backup_veeam", "backup_zerto"}


def test_payload_merges_vm_and_backup_rows_with_combined_counts():
    from shared.customer.backup_policy import build_policy_index
    from shared.customer.unmapped_classifier import (
        account_ids_from_rows,
        account_keys_from_names,
        build_unmapped_payload,
    )

    accounts = [{"name": "ADA GROSS", "accountid": "acc-ada"},
                {"name": "AVROMED", "accountid": "acc-avromed"},
                {"name": "AVRORA LLC", "accountid": "acc-avrora"}]
    payload = build_unmapped_payload(
        [("Ada_Gross_Cloud-Db", "vmware")],
        owners=[],
        account_keys=account_keys_from_names([a["name"] for a in accounts]),
        account_ids=account_ids_from_rows(accounts),
        policies=["avro-CLAVRDB01-H", "visa01-vm-image"],
        policy_index=build_policy_index(accounts),
    )

    kinds = {r["kind"] for r in payload["rows"]}
    assert kinds == {"vm", "backup"}
    assert payload["total"] == 3
    assert payload["alias_gap_count"] == 1   # the VM row
    assert payload["orphan_count"] == 1      # visa01
    assert payload["ambiguous_count"] == 1   # avro
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_unmapped_classifier.py -q -k "backup or policies or ambiguous"`
Expected: FAIL — `ImportError: cannot import name 'classify_unmapped_policies'`

- [ ] **Step 3: Implement policy classification**

`shared/customer/unmapped_classifier.py`, `VM_OWNER_SOURCES` tanımının (satır 115) ardına ekle:

```python
# data_source keys whose rules claim backup policy names. A policy claimed by
# any of them is somebody's, regardless of which backup product it was written
# for, so all three gate the worklist.
BACKUP_OWNER_SOURCES: tuple[str, ...] = (
    "backup_netbackup", "backup_veeam", "backup_zerto",
)
```

`classify_unmapped()` fonksiyonunun ardına ekle:

```python
def classify_unmapped_policies(
    policies: Iterable[str],
    owners: Sequence[OwnerMatcher],
    policy_index: Mapping[str, list[tuple[str, str]]],
) -> list[dict[str, object]]:
    """Backup policies owned by nobody, split into gap / ambiguous / orphan.

    ``ambiguous`` is a third outcome the VM path does not have: a 4-char token
    can address two customers (``avro`` → AVROMED and AVRORA LLC), and 27% of
    live policies do. Those rows name no owner and offer no action — binding
    backup capacity to the wrong customer reaches billing and capacity
    reports, which is worse than leaving the row unresolved.
    """
    from shared.customer.backup_policy import guess_policy_owner

    rows: list[dict[str, object]] = []
    for policy in policies:
        name = (policy or "").strip()
        if not name or not norm(name):
            continue
        name_lower = name.lower()
        if any(m.matches(name_lower) for m in owners):
            continue

        hit = guess_policy_owner(name, policy_index)
        token, candidates = hit if hit else (None, [])

        if len(candidates) == 1:
            owner, accountid = candidates[0]
            reason, suggested = "alias_gap", token
        elif len(candidates) > 1:
            owner, accountid = None, None
            reason, suggested = "ambiguous", None
        else:
            owner, accountid = None, None
            reason, suggested = "orphan", None

        rows.append({
            "name": name,
            "platform": "netbackup",
            "guessed_owner": owner,
            "guessed_owner_id": accountid,
            "suggested_alias": suggested,
            "suggested_method": "prefix" if suggested else None,
            "reason": reason,
            "kind": "backup",
            "candidate_count": len(candidates),
        })
    return rows
```

- [ ] **Step 4: Merge backup rows into the payload**

`build_unmapped_payload()` imzasına iki parametre ekle ve gövdesini güncelle:

```python
def build_unmapped_payload(
    names_with_platform: Iterable[tuple[str, str]],
    owners: Sequence[OwnerMatcher],
    account_keys: Mapping[str, str],
    system_prefixes: Sequence[str] = DEFAULT_SYSTEM_PREFIXES,
    account_ids: Mapping[str, str] | None = None,
    policies: Iterable[str] | None = None,
    policy_index: Mapping[str, list[tuple[str, str]]] | None = None,
    backup_owners: Sequence[OwnerMatcher] | None = None,
) -> dict[str, object]:
```

`rows` listesi kurulduktan **sonra**, `rows.sort(...)` çağrısından **önce** ekle:

```python
    if policies is not None and policy_index is not None:
        rows.extend(classify_unmapped_policies(
            policies,
            backup_owners if backup_owners is not None else owners,
            policy_index,
        ))
```

`rows.sort()` anahtarını genişlet. `alias_gap` en üstte (tek tıkla çözülür), sonra `ambiguous` (elle seçimle çözülür), en altta `orphan` (çözülecek bir şey yok). VM satırlarında `candidate_count` yok, bu yüzden her yerde `.get()` kullanılır:

```python
    _REASON_ORDER = {"alias_gap": 0, "ambiguous": 1, "orphan": 2}
    rows.sort(key=lambda d: (
        _REASON_ORDER.get(str(d["reason"]), 9),
        (d.get("guessed_owner") or "").casefold(),
        str(d["name"]).casefold(),
    ))
```

`_REASON_ORDER` modül seviyesinde tanımlanır, fonksiyon içinde değil.

Dönüş sözlüğüne yeni sayacı ekle:

```python
    return {
        "rows": rows,
        "total": len(rows),
        "alias_gap_count": sum(1 for d in rows if d["reason"] == "alias_gap"),
        "orphan_count": sum(1 for d in rows if d["reason"] == "orphan"),
        "ambiguous_count": sum(1 for d in rows if d["reason"] == "ambiguous"),
    }
```

VM satırlarına da `"candidate_count": 1 if r.guessed_owner_id else 0` eklenmez — arayüz bu alanı yalnızca backup satırlarında okur ve `.get()` ile erişir.

- [ ] **Step 5: Run classifier tests**

Run: `./.venv/bin/python -m pytest tests/test_unmapped_classifier.py -q`
Expected: PASS

- [ ] **Step 6: Add the SQL**

`services/customer-api/app/db/queries/unmapped.py` sonuna ekle:

```python
# Distinct NetBackup policy names in the window. starttime is the job's own
# clock (this table has no collection_time), so the window bounds it directly.
UNMAPPED_NETBACKUP_POLICIES = """
SELECT DISTINCT policyname AS name
FROM public.raw_netbackup_jobs_metrics
WHERE starttime BETWEEN %s AND %s
  AND policyname IS NOT NULL
  AND btrim(policyname) <> ''
"""
```

- [ ] **Step 7: Wire it in the service**

`services/customer-api/app/services/customer_service.py`, `_load_unmapped_resources()` sonundaki `return` bloğunu şununla değiştir:

```python
        # Backup: policy names, guessed through the NetBackup naming standard.
        # Ownership is gated by every backup rule, not just netbackup ones — a
        # policy claimed by a veeam or zerto rule is already somebody's.
        from shared.customer.backup_policy import build_policy_index
        from shared.customer.unmapped_classifier import BACKUP_OWNER_SOURCES

        policies = [
            str(r.get("name") or "").strip()
            for r in self._run_query(uq.UNMAPPED_NETBACKUP_POLICIES, (start, end))
            if r.get("name")
        ]
        policy_index = build_policy_index(account_rows)
        backup_owners = owner_matchers_from_mappings(
            mapping_rows, sources=BACKUP_OWNER_SOURCES
        )

        return build_unmapped_payload(
            names_with_platform,
            owners,
            account_keys,
            account_ids=account_ids,
            policies=policies,
            policy_index=policy_index,
            backup_owners=backup_owners,
        )
```

`owner_matchers_from_mappings` çağrısında `display_names` **verilmez**: müşteri unvanının policy adında geçmesi beklenmez, verilirse `contains` kuralları neredeyse hiçbir şey eşleştirmeden gürültü yaratır.

- [ ] **Step 8: Run all affected suites**

Run: `./.venv/bin/python -m pytest tests/test_unmapped_classifier.py tests/test_backup_policy.py tests/test_unmapped_page.py services/customer-api/tests/ -q`
Expected: PASS

- [ ] **Step 9: Verify the classification against live data**

Yeni kodun canlı veriyle ürettiği dağılımı ölç. Bu adım yalnızca ölçüm içindir — sayılar beklenenden saparsa görevi bloke etme, bulguyu rapor et.

```bash
cat > /tmp/verify_backup_split.py <<'PY'
import sys
sys.path.insert(0, "/app")
import psycopg2, psycopg2.extras
from collections import Counter
from shared.customer.backup_policy import build_policy_index
from shared.customer.unmapped_classifier import classify_unmapped_policies

c = psycopg2.connect(host="10.134.16.6", port=5000, dbname="bulutlake",
                     user="bulutlake", password="BulutLakePas24", connect_timeout=10)
cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cur.execute("""SELECT DISTINCT policyname AS name FROM public.raw_netbackup_jobs_metrics
               WHERE starttime > now() - interval '7 days' AND policyname IS NOT NULL""")
policies = [r["name"] for r in cur.fetchall()]
cur.execute("""SELECT DISTINCT name, accountid FROM public.discovery_crm_accounts
               WHERE name IS NOT NULL AND btrim(name) <> ''""")
accounts = [dict(r) for r in cur.fetchall()]

rows = classify_unmapped_policies(policies, [], build_policy_index(accounts))
print("policies:", len(policies), "accounts:", len(accounts))
print(Counter(r["reason"] for r in rows))
PY
docker cp /tmp/verify_backup_split.py bulutistan-customer-api:/tmp/ \
  && docker exec bulutistan-customer-api python /tmp/verify_backup_split.py
```

Expected: ~1.294 policy; `alias_gap` ≈ %59, `ambiguous` ≈ %27, `orphan` ≈ %14. Bunlar spec yazılırken aynı mantıkla ölçülen oranlar; belirgin sapma `policy_tokens_for_account` içindeki stopword listesinin veya token uzunluğunun kaymış olduğunu gösterir.

Not: konteynerdeki kod imajdan gelir, worktree'den değil. Ölçüm yeni `backup_policy.py`'yi görmüyorsa dosyayı da kopyala:
`docker cp shared/customer/backup_policy.py bulutistan-customer-api:/app/shared/customer/`

- [ ] **Step 10: Commit**

```bash
git add services/customer-api/app/db/queries/unmapped.py shared/customer/unmapped_classifier.py services/customer-api/app/services/customer_service.py tests/test_unmapped_classifier.py
git commit -m "$(cat <<'EOF'
feat(unmapped): classify unowned NetBackup policies alongside VMs

Policies join the same rows list with kind="backup", guessed through the
naming standard. Ownership is gated by every backup data source, so a
policy already claimed by a veeam or zerto rule never reaches the list.

Adds a third outcome the VM path does not have: ambiguous. A 4-char
token can address two customers and 27% of live policies do, so those
rows name no owner and carry no suggestion.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Backup sekmesini arayüze ekle

**Files:**
- Modify: `src/pages/unmapped_resources.py`
- Test: `tests/test_unmapped_page.py`

**Interfaces:**
- Consumes: Görev 5'ten `table_id()`, `ACTION_LABEL`, `build_body()`; Görev 7'den `kind="backup"` satırları ve `ambiguous_count`
- Produces: `_backup_table(rows) -> html.Div`

- [ ] **Step 1: Write the failing test**

`tests/test_unmapped_page.py` sonuna ekle:

```python
_MIXED_PAYLOAD = {
    "rows": [
        {"name": "Acme_Kilit-Web01", "guessed_owner": "Örnek Kilit A.Ş.",
         "platform": "Nutanix", "reason": "alias_gap", "kind": "vm",
         "guessed_owner_id": "acc-1", "suggested_alias": "Acme_Kilit",
         "suggested_method": "prefix"},
        {"name": "abc-dete-s4hana-prd-log", "guessed_owner": "ABC Deterjan",
         "platform": "netbackup", "reason": "alias_gap", "kind": "backup",
         "guessed_owner_id": "acc-abc", "suggested_alias": "abc-dete",
         "suggested_method": "prefix", "candidate_count": 1},
        {"name": "avro-CLAVRDB01-H", "guessed_owner": None,
         "platform": "netbackup", "reason": "ambiguous", "kind": "backup",
         "guessed_owner_id": None, "suggested_alias": None,
         "suggested_method": None, "candidate_count": 2},
    ],
    "total": 3,
    "alias_gap_count": 2,
    "orphan_count": 0,
    "ambiguous_count": 1,
}


def test_backup_tab_renders_next_to_virtualization():
    out = _render(_MIXED_PAYLOAD)
    assert "Sanallaştırma" in out
    assert "Backup" in out
    assert "abc-dete-s4hana-prd-log" in out


def test_backup_rows_do_not_leak_into_the_virtualization_table():
    """Her sekme yalnızca kendi kaynağını gösterir."""
    from src.pages.unmapped_resources import _table_rows

    vm_only = _table_rows([r for r in _MIXED_PAYLOAD["rows"] if r["kind"] == "vm"])
    assert [r["name"] for r in vm_only] == ["Acme_Kilit-Web01"]


def test_ambiguous_rows_are_labelled_and_offer_no_action():
    """Yanlış müşteriye backup bağlamak boş bırakmaktan kötüdür."""
    from src.pages.unmapped_resources import _table_rows

    rows = _table_rows([r for r in _MIXED_PAYLOAD["rows"] if r["kind"] == "backup"])
    by_name = {r["name"]: r for r in rows}

    assert by_name["avro-CLAVRDB01-H"]["reason"] == "Belirsiz (2 aday)"
    assert by_name["avro-CLAVRDB01-H"]["action"] == ""
    assert by_name["abc-dete-s4hana-prd-log"]["action"] == "Alias ekle"


def test_ambiguous_kpi_appears_only_when_there_are_ambiguous_rows():
    assert "Belirsiz" in _render(_MIXED_PAYLOAD)
    assert "Belirsiz" not in _render(_PAYLOAD)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_unmapped_page.py -q -k "backup or ambiguous"`
Expected: FAIL — `assert 'Backup' in out`

- [ ] **Step 3: Add the ambiguous reason label**

`src/pages/unmapped_resources.py:19`:

```python
_REASON_LABEL = {"alias_gap": "Alias eksik", "orphan": "Sahipsiz"}
_PLATFORM_LABEL = {"vmware": "VMware", "nutanix": "Nutanix", "netbackup": "NetBackup"}
```

`_table_rows()` içindeki `reason` hesabını şununla değiştir:

```python
        reason_key = r.get("reason") or ""
        if reason_key == "ambiguous":
            reason = f"Belirsiz ({int(r.get('candidate_count') or 0)} aday)"
        else:
            reason = _REASON_LABEL.get(reason_key, reason_key)
```

ve satır sözlüğünde `"reason": reason` kullan.

- [ ] **Step 4: Add the backup table builder**

`_vm_table()` fonksiyonunun ardına ekle:

```python
def _backup_table(rows: list[dict]) -> html.Div:
    if not rows:
        return dmc.Alert(color="teal", variant="light", title="Eşleşmeyen backup yok",
                         children="Seçili zaman aralığında sahipsiz bir yedekleme "
                                  "politikası bulunamadı.")
    return html.Div(className="nexus-card", style={"padding": "20px"}, children=[
        html.Div(style={"height": "2px", "width": "32px", "borderRadius": "2px",
                        "marginBottom": "12px",
                        "background": "linear-gradient(90deg,#4318FF,#FFB547)"}),
        dmc.Text("Policy adları ‘müşteri-workload-ortam-tip’ standardına göre "
                 "eşleştirilir. ‘Belirsiz’ satırlarda aynı önek birden fazla "
                 "müşteriye uyar; doğru müşteriyi Müşteri Alias ekranından seçin.",
                 size="xs", c="#A3AED0", mb="sm"),
        dash_table.DataTable(
            id=table_id("backup"),
            data=_table_rows(rows),
            columns=[
                {"name": "TAHMİNİ SAHİP", "id": "guessed_owner"},
                {"name": "POLICY ADI", "id": "name"},
                {"name": "KAYNAK", "id": "platform"},
                {"name": "NEDEN", "id": "reason"},
                {"name": "İŞLEM", "id": "action"},
            ],
            hidden_columns=["row_key"],
            page_size=25,
            filter_action="native",
            sort_action="native",
            sort_mode="multi",
            style_as_list_view=True,
            style_table={"overflowX": "auto"},
            style_cell={"fontSize": "12.5px", "padding": "10px 12px", "textAlign": "left",
                        "fontFamily": "DM Sans, Inter, system-ui, sans-serif",
                        "color": "#2B3674", "border": "none",
                        "borderBottom": "1px solid #eef1f4"},
            style_header={"backgroundColor": "#F4F7FE", "color": "#707EAE",
                          "fontWeight": "700", "fontSize": "10.5px",
                          "textTransform": "uppercase", "letterSpacing": "0.04em",
                          "border": "none", "padding": "10px 12px"},
            style_cell_conditional=[
                {"if": {"column_id": "name"}, "fontWeight": "600"},
                {"if": {"column_id": "guessed_owner"}, "color": "#707EAE"},
            ],
            style_data_conditional=[
                {"if": {"column_id": "action", "filter_query": f"{{action}} = '{ACTION_LABEL}'"},
                 "color": "#4318FF", "fontWeight": "700", "cursor": "pointer",
                 "textDecoration": "underline"},
                {"if": {"filter_query": "{reason} = 'Alias eksik'"},
                 "backgroundColor": "rgba(255,181,71,0.07)"},
                {"if": {"filter_query": "{reason} contains 'Belirsiz'", "column_id": "reason"},
                 "color": "#B26A00", "fontWeight": "700"},
                {"if": {"filter_query": "{reason} = 'Sahipsiz'", "column_id": "reason"},
                 "color": "#A3AED0", "fontWeight": "600"},
                {"if": {"state": "active"},
                 "backgroundColor": "rgba(67,24,255,0.06)", "border": "none"},
            ],
        ),
    ])
```

- [ ] **Step 5: Render both tabs and the ambiguous KPI**

`build_body()` içindeki `kpis` ve `tabs` bloklarını şununla değiştir:

```python
    vm_rows = [r for r in rows if (r.get("kind") or "vm") == "vm"]
    backup_rows = [r for r in rows if r.get("kind") == "backup"]
    ambiguous = int(data.get("ambiguous_count") or 0)

    kpi_cards = [
        _kpi("Toplam eşleşmeyen", total, "solar:server-square-bold-duotone", "#4318FF"),
        _kpi("Alias eksik (düzeltilebilir)", alias_gap, "solar:pen-new-square-bold-duotone", "#FFB547"),
        _kpi("Sahipsiz", orphan, "solar:ghost-bold-duotone", "#A3AED0"),
    ]
    if ambiguous:
        # Only shown when it exists: a permanent zero card would read as a
        # state the operator has to clear.
        kpi_cards.append(
            _kpi("Belirsiz (elle seçim)", ambiguous, "solar:question-circle-bold-duotone", "#B26A00")
        )
    # KPIs stay source-agnostic on purpose; per-tab counts live on the tab
    # badges, so the page never shows two different readings of "total".
    kpis = dmc.SimpleGrid(cols={"base": 1, "sm": len(kpi_cards)}, spacing="md", mb="md",
                          children=kpi_cards)

    tabs = dmc.Tabs(value="virt", children=[
        dmc.TabsList([
            dmc.TabsTab("Sanallaştırma", value="virt",
                        rightSection=dmc.Badge(str(len(vm_rows)), size="xs",
                                               variant="light", color="indigo")),
            dmc.TabsTab("Backup", value="backup",
                        rightSection=dmc.Badge(str(len(backup_rows)), size="xs",
                                               variant="light", color="indigo")),
        ]),
        dmc.TabsPanel(value="virt", pt="md", children=_vm_table(vm_rows)),
        dmc.TabsPanel(value="backup", pt="md", children=_backup_table(backup_rows)),
    ])
```

- [ ] **Step 6: Update the page subtitle**

`_header()` içindeki alt başlık artık yalnızca VM'leri anlatmıyor:

```python
                dmc.Text("Hiçbir müşteriye eşleşmeyen kaynaklar: sanal makineler ve "
                         "yedekleme politikaları.",
                         size="sm", c="dimmed"),
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_unmapped_page.py tests/test_unmapped_alias_action.py -q`
Expected: PASS

- [ ] **Step 8: Verify the app boots**

Run: `./.venv/bin/python -c "import app; print('ok')"`
Expected: `ok`

- [ ] **Step 9: Commit**

```bash
git add src/pages/unmapped_resources.py tests/test_unmapped_page.py
git commit -m "$(cat <<'EOF'
feat(unmapped): add the Backup tab beside Sanallaştırma

NetBackup policies get their own table with the same one-click action,
served by the same pattern-matched callback. Ambiguous rows render as
"Belirsiz (N aday)" with no action, so the operator resolves them by
choosing a customer rather than accepting a coin flip.

The KPI cards stay source-agnostic and count both tabs; per-tab totals
live on the tab badges, so the page never shows two readings of "total".
The Belirsiz card appears only when the count is non-zero.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Excel seed betiği

**Files:**
- Create: `scripts/seed_backup_policy_aliases.py`
- Test: `tests/test_seed_backup_policy_aliases.py`

**Interfaces:**
- Consumes: Görev 6'dan `policy_tokens_for_account()`; Görev 4'ten `merge_source_mapping()`; `unmapped_classifier.norm()`
- Produces:
  - `parse_sheet(path: str) -> list[tuple[str, list[str]]]` — `(müşteri adı, [token, ...])`
  - `resolve_accounts(sheet_rows, crm_accounts) -> SeedPlan` — dataclass: `.matched`, `.not_found`, `.ambiguous`
  - `format_report(plan: SeedPlan) -> str`

**Neden ayrı betik, migration değil:** Excel operasyonel bir belge, şema değil. Yeniden çalıştırılabilir ve rapor üreten bir betik, tek seferlik migration'dan daha kullanışlı — tablo güncellendiğinde tekrar koşulur.

- [ ] **Step 1: Write the failing test**

Yeni dosya `tests/test_seed_backup_policy_aliases.py`:

```python
"""The spreadsheet is the authority for the 27% of policies the naming standard
cannot disambiguate. Rows it cannot resolve are reported, never skipped in
silence — a silent skip looks identical to a successful seed.
"""
from scripts.seed_backup_policy_aliases import (
    format_report,
    parse_sheet_rows,
    resolve_accounts,
)


def test_multi_token_cells_split_into_separate_rules():
    rows = parse_sheet_rows([
        ("Aksular", "aksu,aksular"),
        ("Alisan lojistik", "alis, alis-logo"),
        ("Azer", "azer"),
    ])
    assert dict(rows) == {
        "Aksular": ["aksu", "aksular"],
        "Alisan lojistik": ["alis", "alis-logo"],
        "Azer": ["azer"],
    }


def test_blank_and_header_rows_are_ignored():
    rows = parse_sheet_rows([
        ("MÜŞTERİ ADI", "POLICY ADI"),
        ("", ""),
        (None, None),
        ("Azer", "azer"),
    ])
    assert dict(rows) == {"Azer": ["azer"]}


def test_short_sheet_names_resolve_to_full_legal_crm_names():
    """'Aksular' in the sheet is 'AKSULAR GIDA SANAYİ A.Ş.' in CRM."""
    plan = resolve_accounts(
        [("Aksular", ["aksu", "aksular"])],
        [{"name": "AKSULAR GIDA SANAYİ A.Ş.", "accountid": "acc-aksu"}],
    )
    assert plan.matched == [("acc-aksu", "AKSULAR GIDA SANAYİ A.Ş.", ["aksu", "aksular"])]
    assert plan.not_found == []
    assert plan.ambiguous == []


def test_a_sheet_name_with_no_crm_account_is_reported_not_skipped():
    plan = resolve_accounts(
        [("Hayali Müşteri", ["haya"])],
        [{"name": "AKSULAR GIDA SANAYİ A.Ş.", "accountid": "acc-aksu"}],
    )
    assert plan.matched == []
    assert plan.not_found == ["Hayali Müşteri"]


def test_a_sheet_name_matching_two_crm_accounts_needs_a_human():
    plan = resolve_accounts(
        [("Avrora", ["avro", "avrora"])],
        [{"name": "AVRORA LLC", "accountid": "acc-1"},
         {"name": "AVRORA ENERJİ", "accountid": "acc-2"}],
    )
    assert plan.matched == []
    assert len(plan.ambiguous) == 1
    assert plan.ambiguous[0][0] == "Avrora"
    assert sorted(plan.ambiguous[0][1]) == ["AVRORA ENERJİ", "AVRORA LLC"]


def test_report_names_every_unresolved_row():
    plan = resolve_accounts(
        [("Hayali Müşteri", ["haya"]), ("Avrora", ["avro"])],
        [{"name": "AVRORA LLC", "accountid": "acc-1"},
         {"name": "AVRORA ENERJİ", "accountid": "acc-2"}],
    )
    report = format_report(plan)
    assert "Hayali Müşteri" in report
    assert "Avrora" in report
    assert "AVRORA LLC" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_seed_backup_policy_aliases.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.seed_backup_policy_aliases'`

- [ ] **Step 3: Check whether scripts/ is importable**

Run: `ls scripts/__init__.py 2>/dev/null || echo "missing"`

`missing` çıkarsa oluştur:

```bash
touch scripts/__init__.py
```

- [ ] **Step 4: Implement the script**

Yeni dosya `scripts/seed_backup_policy_aliases.py`:

```python
"""Seed backup_netbackup alias rules from backup-musteri-isim.xlsx.

The naming standard (shared/customer/backup_policy.py) derives a customer's
policy prefix in 87% of live cases, but 27% of those match more than one CRM
account — 'avro' addresses both AVROMED and AVRORA LLC. The spreadsheet
resolves exactly those, so it is loaded as ground truth alongside the
heuristic rather than instead of it.

Idempotent: rules already present are not rewritten. Rows that cannot be
resolved to a CRM account are reported by name, never dropped in silence —
a silent skip is indistinguishable from a successful seed.

Usage:
    ./.venv/bin/python -m scripts.seed_backup_policy_aliases <xlsx> [--apply]

Without --apply it prints the plan and writes nothing.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field

from shared.customer.unmapped_classifier import norm

SHEET_NAME = "AD-KARŞILIĞI"
DATA_SOURCE = "backup_netbackup"
MATCH_METHOD = "prefix"

_HEADER_CELLS = {"musteri adi", "policy adi"}


@dataclass
class SeedPlan:
    matched: list[tuple[str, str, list[str]]] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)
    ambiguous: list[tuple[str, list[str]]] = field(default_factory=list)


def parse_sheet_rows(raw_rows) -> list[tuple[str, list[str]]]:
    """(customer, [token, ...]) per sheet row; headers and blanks dropped.

    A cell may hold several comma-separated tokens ('aksu,aksular'); each
    becomes its own rule, because they are alternative prefixes rather than
    one compound value.
    """
    out: list[tuple[str, list[str]]] = []
    for name_cell, policy_cell in raw_rows:
        name = str(name_cell or "").strip()
        policy = str(policy_cell or "").strip()
        if not name or not policy:
            continue
        if norm(name) in {norm(h) for h in _HEADER_CELLS}:
            continue
        tokens = [t.strip().lower() for t in policy.split(",") if t.strip()]
        if tokens:
            out.append((name, tokens))
    return out


def resolve_accounts(sheet_rows, crm_accounts) -> SeedPlan:
    """Match short sheet names to full CRM legal names.

    Uses the same Turkish folding as the classifier so this path and the
    runtime path cannot disagree about what two names being "the same" means.
    """
    by_key: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for acc in crm_accounts:
        name = str(acc.get("name") or "").strip()
        accountid = str(acc.get("accountid") or "").strip()
        if name and accountid:
            by_key[norm(name)].append((name, accountid))

    plan = SeedPlan()
    for sheet_name, tokens in sheet_rows:
        key = norm(sheet_name)
        exact = by_key.get(key, [])
        candidates = exact or [
            entry
            for k, entries in by_key.items()
            if k.startswith(key) and len(key) >= 4
            for entry in entries
        ]
        if not candidates:
            plan.not_found.append(sheet_name)
        elif len(candidates) > 1:
            plan.ambiguous.append((sheet_name, sorted(c[0] for c in candidates)))
        else:
            name, accountid = candidates[0]
            plan.matched.append((accountid, name, tokens))
    return plan


def format_report(plan: SeedPlan) -> str:
    lines = [
        f"Matched:    {len(plan.matched)} customers",
        f"Not found:  {len(plan.not_found)} customers",
        f"Ambiguous:  {len(plan.ambiguous)} customers",
        "",
    ]
    if plan.not_found:
        lines.append("No CRM account for these sheet names:")
        lines += [f"  - {n}" for n in plan.not_found]
        lines.append("")
    if plan.ambiguous:
        lines.append("These sheet names match more than one CRM account (pick one by hand):")
        for sheet_name, names in plan.ambiguous:
            lines.append(f"  - {sheet_name}: {', '.join(names)}")
        lines.append("")
    return "\n".join(lines)


def load_sheet(path: str) -> list[tuple[str, list[str]]]:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[SHEET_NAME]
    return parse_sheet_rows(
        (row[0], row[1]) for row in ws.iter_rows(values_only=True) if row and len(row) >= 2
    )


def apply_plan(plan: SeedPlan) -> tuple[int, int]:
    """Write the matched rules. Returns (accounts_written, rules_added)."""
    from src.services import api_client as api
    from src.utils.crm_source_mapping_ui import find_alias, merge_source_mapping

    aliases = api.get_crm_aliases() or []
    accounts_written = rules_added = 0

    for accountid, account_name, tokens in plan.matched:
        alias = find_alias(aliases, accountid)
        mappings = list((alias or {}).get("source_mappings") or [])
        added_here = 0
        for token in tokens:
            mappings, changed = merge_source_mapping(mappings, {
                "data_source": DATA_SOURCE,
                "match_method": MATCH_METHOD,
                "match_value": token,
                "enabled": True,
                "priority": 100,
                "notes": "backup-musteri-isim.xlsx seed",
            })
            added_here += int(changed)
        if not added_here:
            continue
        # The save endpoint replaces the account's whole mapping set, so the
        # union built above is what goes out.
        api.put_crm_source_mappings(
            accountid,
            crm_account_name=(alias or {}).get("crm_account_name") or account_name,
            mappings=mappings,
        )
        accounts_written += 1
        rules_added += added_here

    return accounts_written, rules_added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx", help="path to backup-musteri-isim.xlsx")
    parser.add_argument("--apply", action="store_true",
                        help="write the rules; without it, only the plan is printed")
    args = parser.parse_args(argv)

    from src.services import api_client as api

    sheet_rows = load_sheet(args.xlsx)
    crm_accounts = [
        {"name": a.get("crm_account_name"), "accountid": a.get("crm_accountid")}
        for a in (api.get_crm_aliases() or [])
    ]
    plan = resolve_accounts(sheet_rows, crm_accounts)

    print(f"Sheet rows: {len(sheet_rows)}")
    print(format_report(plan))

    if not args.apply:
        print("Dry run — nothing written. Re-run with --apply to seed.")
        return 0

    accounts_written, rules_added = apply_plan(plan)
    print(f"Wrote {rules_added} rules across {accounts_written} accounts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_seed_backup_policy_aliases.py -q`
Expected: PASS (6 tests)

- [ ] **Step 6: Dry-run against the real spreadsheet**

Run:

```bash
./.venv/bin/python -m scripts.seed_backup_policy_aliases \
  "/Users/namlisarac/Desktop/Work/Datalake/backup-musteri-isim.xlsx"
```

Expected: 189 satır okunur, eşleşen / bulunamayan / belirsiz sayıları ve isim listeleri yazdırılır, hiçbir şey yazılmaz.

Raporu kaydet — kullanıcının çözmesi gereken satırlar bu listedir:

```bash
./.venv/bin/python -m scripts.seed_backup_policy_aliases \
  "/Users/namlisarac/Desktop/Work/Datalake/backup-musteri-isim.xlsx" \
  > docs/qa/2026-07-27-backup-seed-dry-run.txt
```

- [ ] **Step 7: Commit**

```bash
git add scripts/seed_backup_policy_aliases.py tests/test_seed_backup_policy_aliases.py scripts/__init__.py docs/qa/2026-07-27-backup-seed-dry-run.txt
git commit -m "$(cat <<'EOF'
feat(backup): seed backup_netbackup aliases from the customer spreadsheet

The naming standard cannot disambiguate 27% of live policies; the sheet
resolves exactly those, so it loads as ground truth alongside the
heuristic rather than instead of it.

Idempotent, and dry-run by default. Sheet rows that resolve to no CRM
account, or to more than one, are reported by name instead of skipped —
a silent skip reads identically to a successful seed.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 8: Apply the seed (after reviewing the dry-run report with the user)**

Bu adım **kullanıcı onayı** gerektirir: canlı CRM mapping tablosuna yazar.

Run:

```bash
./.venv/bin/python -m scripts.seed_backup_policy_aliases \
  "/Users/namlisarac/Desktop/Work/Datalake/backup-musteri-isim.xlsx" --apply
```

Sonrasında Backup sekmesini yeniden yükleyip `alias_gap` + `ambiguous` sayılarının düştüğünü doğrula.

---

## Final verification

- [ ] **Run the whole suite**

Run: `./.venv/bin/python -m pytest tests/ services/customer-api/tests/ -q`
Expected: PASS — kırmızı yok

- [ ] **Boot the app**

Run: `./.venv/bin/python -c "import app; print('ok')"`
Expected: `ok`

- [ ] **Manual check against the running stack**

1. `/crm/inventory-overview` → "Power" accordion yok, "Power HANA" var; Product Matching tablosunda üç kolon yok; Export indir, Excel'de de yok.
2. `/unmapped-resources` → iki sekme; Sanallaştırma'da bir "Alias ekle" tıkla; satır kaybolsun, KPI düşsün, bildirim çıksın.
3. Administration › CRM Dynamics 365 › Customer Aliases → o müşterinin Virtualization sütununda yeni kural görünsün.
4. Backup sekmesi → "Belirsiz (N aday)" satırlarında işlem hücresi boş.
