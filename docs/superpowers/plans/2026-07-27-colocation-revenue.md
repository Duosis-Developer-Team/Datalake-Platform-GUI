# Colocation Revenue & Physical Inventory Restructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface CRM's per-rack-U colocation price as a *potential revenue* figure across the colocation card, dedicated-customer table, DC summary and DC cards, move Colocation under Physical Inventory as a sub-tab, and fix internal-tenant classification to read the Administration mappings it is assumed to reflect.

**Architecture:** Price resolution lands in customer-api (override table in webui-db → CRM price level in bulutlake → `None`) and rides out on the existing `/api/v1/crm/colocation/{dc}` payload, so every GUI surface reads one already-cached source instead of querying independently. `shared/colocation` stays database-free: internal-tenant prefixes are passed *in* rather than looked up, keeping it unit-testable. GUI changes are presentation-only.

**Tech Stack:** Python 3.11, Dash + dash-mantine-components, FastAPI (customer-api), psycopg2, pytest.

**Spec:** [`docs/superpowers/specs/2026-07-27-colocation-revenue-design.md`](../specs/2026-07-27-colocation-revenue-design.md)

## Global Constraints

- **Python 3.11.** System `python3` is 3.9 and fails these tests. Always run via `.venv/bin/python` / `.venv/bin/pytest`.
- **Never hardcode the price.** The literal `10430.84` must not appear in application code. Only fixtures and this plan may contain it.
- **Never fall back to zero price.** An unresolved price is `None` and renders `—`. Zero reads as "no opportunity"; unknown is not zero.
- **Potential ≠ Billed.** Labels say "potential", computed at list price. No UI string may imply realized revenue. This release ships potential only.
- **Colocation is never summed into the virtualization range.** It renders as its own line with a single value.
- **English UI labels** in DC View / datacenters surfaces, matching surrounding code.
- **Colocation productid:** `ee635018-5c6d-f011-b4cc-6045bd93381c` — the only CRM product priced per rack-U.
- **Currency:** TRY only (`transactioncurrency_text = 'Turkish Lira'`).
- Run the full suite with `.venv/bin/pytest tests/ -q` (GUI) and `cd services/customer-api && ../../.venv/bin/pytest tests/ -q` (API) before the final commit of each task.

## File Structure

**Create:**
- `services/customer-api/app/db/queries/colocation_price.py` — SQL for the CRM per-U price level and the webui override lookup.
- `services/customer-api/app/services/colocation_price_service.py` — resolution order + arithmetic. No Dash, no HTTP.
- `services/customer-api/tests/test_colocation_price_service.py`
- `tests/test_colocation_potential_column.py`
- `tests/test_dc_view_phys_inv_nested_tabs.py`
- `tests/test_datacenters_colocation_potential.py`

**Modify:**
- `shared/colocation/occupancy.py:162` — `is_internal_tenant` takes injectable prefixes.
- `shared/colocation/matching.py:56` — `build_internal_footprint` / `build_customer_footprint` thread prefixes through.
- `services/customer-api/app/services/colocation_matching_service.py:46` — resolve price, attach potential, source internal prefixes from Administration.
- `src/components/colocation_summary.py:45` — fifth tile.
- `src/pages/dc_view.py:2537` — potential column on both colocation tables.
- `src/pages/dc_view.py:5472,5480,5570,5746,5835` — nested Physical Inventory tabs.
- `src/auth/permission_catalog.py:141` — colocation becomes a sub-section of phys_inv.
- `src/pages/dc_summary_sellable.py` — Physical — Colocation entry.
- `src/pages/datacenters.py:216,665,1008` — separate colocation line.
- `services/customer-api/app/db/queries/crm_sales.py:141,163` — correct the stale "productpricelevels is currently empty in production" comment.

---

### Task 1: Colocation unit price resolver

Resolves the per-U price with a strict precedence and no zero fallback. Everything downstream depends on this contract.

**Files:**
- Create: `services/customer-api/app/db/queries/colocation_price.py`
- Create: `services/customer-api/app/services/colocation_price_service.py`
- Test: `services/customer-api/tests/test_colocation_price_service.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `COLOCATION_PRODUCT_ID: str`
  - `resolve_colocation_unit_price(datalake_cursor, webui) -> tuple[float | None, str]` returning `(price, source)` where `source` is one of `"override"`, `"crm"`, `"unavailable"`.
  - `potential_tl(u: int | float | None, unit_price: float | None) -> float | None`

- [ ] **Step 1: Write the failing test**

Create `services/customer-api/tests/test_colocation_price_service.py`:

```python
"""Colocation per-U price resolution: webui override wins over the CRM price
level; an unresolved price is None (never 0.0), because 0 reads as 'no
opportunity' while None reads as 'price unknown'."""
from unittest.mock import MagicMock

from app.services.colocation_price_service import (
    COLOCATION_PRODUCT_ID,
    potential_tl,
    resolve_colocation_unit_price,
)


def _webui(rows):
    w = MagicMock()
    w.is_available = True
    w.run_rows.return_value = rows
    return w


def _cursor(rows):
    cur = MagicMock()
    cur.fetchall.return_value = rows
    return cur


def test_override_wins_over_crm_price_level():
    cur = _cursor([(10430.84,)])
    webui = _webui([{"unit_price_tl": 9000.0}])

    price, source = resolve_colocation_unit_price(cur, webui)

    assert price == 9000.0
    assert source == "override"


def test_falls_back_to_crm_price_level_when_no_override():
    cur = _cursor([(10430.84,)])
    webui = _webui([])

    price, source = resolve_colocation_unit_price(cur, webui)

    assert price == 10430.84
    assert source == "crm"


def test_unresolved_price_is_none_not_zero():
    cur = _cursor([])
    webui = _webui([])

    price, source = resolve_colocation_unit_price(cur, webui)

    assert price is None
    assert source == "unavailable"


def test_webui_unavailable_falls_through_to_crm():
    cur = _cursor([(10430.84,)])
    webui = MagicMock()
    webui.is_available = False

    price, source = resolve_colocation_unit_price(cur, webui)

    assert price == 10430.84
    assert source == "crm"


def test_webui_failure_does_not_break_resolution():
    cur = _cursor([(10430.84,)])
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.side_effect = RuntimeError("webui down")

    price, source = resolve_colocation_unit_price(cur, webui)

    assert price == 10430.84
    assert source == "crm"


def test_datalake_failure_yields_unavailable():
    cur = MagicMock()
    cur.execute.side_effect = RuntimeError("datalake down")
    webui = _webui([])

    price, source = resolve_colocation_unit_price(cur, webui)

    assert price is None
    assert source == "unavailable"


def test_zero_override_is_honoured_as_zero_not_treated_as_missing():
    # A deliberate 0.0 override means "free"; it must not silently fall through.
    cur = _cursor([(10430.84,)])
    webui = _webui([{"unit_price_tl": 0.0}])

    price, source = resolve_colocation_unit_price(cur, webui)

    assert price == 0.0
    assert source == "override"


def test_product_id_is_the_per_u_colocation_product():
    assert COLOCATION_PRODUCT_ID == "ee635018-5c6d-f011-b4cc-6045bd93381c"


def test_potential_tl_multiplies_u_by_price():
    assert potential_tl(85, 10430.84) == 85 * 10430.84


def test_potential_tl_is_none_when_price_is_none():
    assert potential_tl(85, None) is None


def test_potential_tl_handles_zero_and_missing_u():
    assert potential_tl(0, 10430.84) == 0.0
    assert potential_tl(None, 10430.84) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/customer-api && ../../.venv/bin/pytest tests/test_colocation_price_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.colocation_price_service'`

- [ ] **Step 3: Write the query module**

Create `services/customer-api/app/db/queries/colocation_price.py`:

```python
"""Colocation per-rack-U unit price.

Two sources, resolved in the service layer:
  - gui_crm_price_override (webui-db) — operator-set price, wins when present.
  - discovery_crm_productpricelevels (bulutlake) — the CRM list price.

Verified 2026-07-27: productid ee635018-... ("Veri Merkezi Barindirma Hizmeti
(U)") is the ONLY CRM product priced with uomid_name = 'U'. Its TL row sits on
the "TL Fiyat Listesi" price list with statecode = 0, so the active-price-list
filter keeps it.
"""

# bulutlake — CRM list price for the per-U colocation product, TL only.
# Newest row first: CRM keeps history and we want the current price.
COLOCATION_CRM_UNIT_PRICE = """
SELECT ppl.amount::double precision
FROM   discovery_crm_productpricelevels ppl
JOIN   discovery_crm_pricelevels pl ON pl.pricelevelid = ppl.pricelevelid
WHERE  ppl.productid = %s
  AND  pl.statecode = 0
  AND  ppl.transactioncurrency_text = 'Turkish Lira'
ORDER  BY ppl.modifiedon DESC NULLS LAST
LIMIT  1;
"""

# webui-db — operator override for the same product.
COLOCATION_PRICE_OVERRIDE = """
SELECT unit_price_tl
FROM   gui_crm_price_override
WHERE  productid = %s
LIMIT  1;
"""
```

- [ ] **Step 4: Write the service module**

Create `services/customer-api/app/services/colocation_price_service.py`:

```python
"""Resolve the colocation per-rack-U unit price and derive potential TL.

Precedence: operator override (webui-db) -> CRM list price (bulutlake) -> None.

An unresolved price is None, never 0.0. Zero renders as "0 TL" and reads as
"this rack space is worth nothing"; None renders as an em dash and reads as
"we do not know the price". A deliberate 0.0 override is still honoured as 0.0.
"""
from __future__ import annotations

import logging

from app.db.queries import colocation_price as q

logger = logging.getLogger(__name__)

# "Veri Merkezi Barindirma Hizmeti (U)" — the only CRM product priced per rack-U.
COLOCATION_PRODUCT_ID = "ee635018-5c6d-f011-b4cc-6045bd93381c"


def _override_price(webui) -> float | None:
    if webui is None or not getattr(webui, "is_available", False):
        return None
    try:
        rows = webui.run_rows(q.COLOCATION_PRICE_OVERRIDE, (COLOCATION_PRODUCT_ID,))
    except Exception as exc:  # noqa: BLE001
        logger.warning("colocation price override lookup failed: %s", exc)
        return None
    for r in rows or []:
        value = r.get("unit_price_tl") if isinstance(r, dict) else r[0]
        if value is not None:
            return float(value)
    return None


def _crm_price(cursor) -> float | None:
    try:
        cursor.execute(q.COLOCATION_CRM_UNIT_PRICE, (COLOCATION_PRODUCT_ID,))
        rows = cursor.fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("colocation CRM price lookup failed: %s", exc)
        return None
    for r in rows or []:
        value = r[0] if not isinstance(r, dict) else r.get("amount")
        if value is not None:
            return float(value)
    return None


def resolve_colocation_unit_price(cursor, webui) -> tuple[float | None, str]:
    """Return (unit_price_tl, source) with source in
    {"override", "crm", "unavailable"}."""
    override = _override_price(webui)
    if override is not None:
        return override, "override"
    crm = _crm_price(cursor)
    if crm is not None:
        return crm, "crm"
    return None, "unavailable"


def potential_tl(u, unit_price: float | None) -> float | None:
    """U count x unit price. None price propagates as None (unknown), while a
    missing/zero U count is a real zero."""
    if unit_price is None:
        return None
    return float(u or 0) * float(unit_price)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd services/customer-api && ../../.venv/bin/pytest tests/test_colocation_price_service.py -q`
Expected: PASS — 11 passed

- [ ] **Step 6: Fix the stale comment in crm_sales.py**

In `services/customer-api/app/db/queries/crm_sales.py`, replace both stale claims. Line ~141-143 currently reads:

```python
# (catalog price comes from gui_crm_price_override + discovery_crm_productpricelevels
#  resolved in the service layer; productpricelevels is currently empty in production).
```

Replace with:

```python
# (catalog price comes from gui_crm_price_override + discovery_crm_productpricelevels
#  resolved in the service layer. NOTE: productpricelevels is NOT empty — verified
#  2026-07-27, it holds 12 rows across the colocation product family alone.)
```

And line ~163:

```python
# Optional fallback: catalog rows if the price-level table is populated. Service layer
# uses gui_crm_price_override first; this query is the secondary source for completeness.
```

Replace with:

```python
# Catalog rows from the price-level table (populated — verified 2026-07-27). Service
# layer uses gui_crm_price_override first; this query is the secondary source.
```

- [ ] **Step 7: Commit**

```bash
git add services/customer-api/app/db/queries/colocation_price.py \
        services/customer-api/app/services/colocation_price_service.py \
        services/customer-api/tests/test_colocation_price_service.py \
        services/customer-api/app/db/queries/crm_sales.py
git commit -m "feat(colocation): resolve per-U unit price from override then CRM price level

Unresolved price is None rather than 0.0 so the UI can distinguish 'price
unknown' from 'worth nothing'. A deliberate 0.0 override is still honoured.

Also corrects a stale comment claiming productpricelevels is empty in
production; it holds 12 rows across the colocation product family."
```

---

### Task 2: Internal tenant classification reads Administration mappings

Fixes the defect: `is_internal_tenant` matches a hardcoded tuple and never reads `gui_crm_customer_source_mapping`. `shared/colocation` must stay database-free, so prefixes are injected.

**Files:**
- Modify: `shared/colocation/occupancy.py:162`
- Modify: `shared/colocation/matching.py:20-70`
- Modify: `services/customer-api/app/services/colocation_matching_service.py:24-75`
- Test: `tests/test_colocation_occupancy.py` (extend)
- Test: `services/customer-api/tests/test_colocation_matching_service.py` (extend)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces:
  - `is_internal_tenant(name: str, prefixes: Sequence[str] | None = None) -> bool`
  - `build_customer_footprint(tenant_rows, alias_index, internal_prefixes=None) -> list[dict]`
  - `build_internal_footprint(tenant_rows, internal_prefixes=None) -> list[dict]`
  - `ColocationMatchingService._internal_prefixes() -> tuple[str, ...]`

- [ ] **Step 1: Write the failing test for injectable prefixes**

Append to `tests/test_colocation_occupancy.py`:

```python
from shared.colocation.occupancy import INTERNAL_TENANT_PREFIXES, is_internal_tenant


def test_is_internal_tenant_uses_builtin_prefixes_by_default():
    assert is_internal_tenant("Bulutistan - Linux TEAM") is True
    assert is_internal_tenant("Boyner") is False


def test_is_internal_tenant_accepts_injected_prefixes():
    injected = ("acme-internal",)
    assert is_internal_tenant("ACME-Internal Fabric", injected) is True
    # Injected prefixes REPLACE the defaults; the caller decides what to union in.
    assert is_internal_tenant("Bulutistan - Linux TEAM", injected) is False


def test_is_internal_tenant_empty_injection_matches_nothing():
    # An empty Administration table must not classify everything as internal.
    assert is_internal_tenant("Bulutistan - Linux TEAM", ()) is False


def test_builtin_prefixes_unchanged():
    assert INTERNAL_TENANT_PREFIXES == (
        "bulutistan", "bulut broker", "cpe-tenant", "dc11 arista",
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_colocation_occupancy.py -q -k injected`
Expected: FAIL — `TypeError: is_internal_tenant() takes 1 positional argument but 2 were given`

- [ ] **Step 3: Make prefixes injectable in occupancy.py**

In `shared/colocation/occupancy.py`, replace lines 162-165:

```python
def is_internal_tenant(name: str) -> bool:
    """True when the tenant is Bulutistan-internal (excluded from the customer view)."""
    key = (name or "").strip().lower()
    return any(key.startswith(p) for p in INTERNAL_TENANT_PREFIXES)
```

with:

```python
def is_internal_tenant(name: str, prefixes: Sequence[str] | None = None) -> bool:
    """True when the tenant is Bulutistan-internal (excluded from the customer view).

    `prefixes` REPLACES the built-in tuple rather than extending it — the caller
    owns the union, because the caller is the one that knows whether the
    Administration mapping table was reachable. Passing an empty sequence
    deliberately classifies nothing as internal.
    """
    active = INTERNAL_TENANT_PREFIXES if prefixes is None else prefixes
    key = (name or "").strip().lower()
    return any(key.startswith(p) for p in active)
```

`Sequence` is already imported at the top of the module (used by `row_to_dict`).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_colocation_occupancy.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing test for footprint threading**

Append to `tests/test_colocation_matching.py`:

```python
from shared.colocation.matching import build_customer_footprint, build_internal_footprint


def _rows():
    return [
        {"dc": "DC13", "rack_name": "116", "tenant_name": "Boyner", "used_u": 20},
        {"dc": "DC13", "rack_name": "116", "tenant_name": "Acme-Internal", "used_u": 15},
    ]


def test_internal_footprint_honours_injected_prefixes():
    internal = build_internal_footprint(_rows(), internal_prefixes=("acme-internal",))

    assert [r["tenant"] for r in internal] == ["Acme-Internal"]


def test_customer_footprint_excludes_injected_internal_tenants():
    customers = build_customer_footprint(_rows(), {}, internal_prefixes=("acme-internal",))

    assert [c["tenant"] for c in customers] == ["Boyner"]


def test_default_prefixes_still_apply_when_none_injected():
    rows = [{"dc": "DC13", "rack_name": "116",
             "tenant_name": "Bulutistan - Linux TEAM", "used_u": 15}]

    assert build_internal_footprint(rows) != []
    assert build_customer_footprint(rows, {}) == []
```

- [ ] **Step 6: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_colocation_matching.py -q -k injected`
Expected: FAIL — `TypeError: build_internal_footprint() got an unexpected keyword argument 'internal_prefixes'`

- [ ] **Step 7: Thread prefixes through matching.py**

In `shared/colocation/matching.py`, add the keyword parameter to both builders and pass it to every `is_internal_tenant` call. `build_customer_footprint` becomes:

```python
def build_customer_footprint(tenant_rows, alias_index, internal_prefixes=None) -> list[dict]:
```

and its guard at line ~32 becomes:

```python
        if not tenant or is_internal_tenant(tenant, internal_prefixes):
            continue
```

`build_internal_footprint` becomes:

```python
def build_internal_footprint(tenant_rows, internal_prefixes=None) -> list[dict]:
```

and its guard at line ~65 becomes:

```python
        if not tenant or not is_internal_tenant(tenant, internal_prefixes):
            continue
```

Update both docstrings to note that `internal_prefixes=None` means the built-in tuple.

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_colocation_matching.py tests/test_colocation_occupancy.py -q`
Expected: PASS

- [ ] **Step 9: Write the failing service test**

Append to `services/customer-api/tests/test_colocation_matching_service.py`:

```python
def test_internal_prefixes_union_administration_mappings_with_builtins():
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.return_value = [
        {"match_value": "Acme-Internal", "enabled": True},
        {"match_value": "Disabled-One", "enabled": False},
        {"match_value": "  Padded  ", "enabled": True},
    ]
    svc = ColocationMatchingService(customer_service=MagicMock(), webui=webui)

    prefixes = svc._internal_prefixes()

    assert "acme-internal" in prefixes
    assert "padded" in prefixes
    assert "disabled-one" not in prefixes
    # Built-ins are always retained as a seed.
    assert "bulutistan" in prefixes


def test_internal_prefixes_fall_back_to_builtins_when_webui_unavailable():
    webui = MagicMock()
    webui.is_available = False
    svc = ColocationMatchingService(customer_service=MagicMock(), webui=webui)

    assert svc._internal_prefixes() == INTERNAL_TENANT_PREFIXES


def test_internal_prefixes_fall_back_to_builtins_when_lookup_raises():
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.side_effect = RuntimeError("webui down")
    svc = ColocationMatchingService(customer_service=MagicMock(), webui=webui)

    assert svc._internal_prefixes() == INTERNAL_TENANT_PREFIXES
```

Add to that file's imports:

```python
from shared.colocation.occupancy import INTERNAL_TENANT_PREFIXES
```

- [ ] **Step 10: Run test to verify it fails**

Run: `cd services/customer-api && ../../.venv/bin/pytest tests/test_colocation_matching_service.py -q -k internal_prefixes`
Expected: FAIL — `AttributeError: 'ColocationMatchingService' object has no attribute '_internal_prefixes'`

- [ ] **Step 11: Implement `_internal_prefixes` and wire it in**

In `services/customer-api/app/services/colocation_matching_service.py`, extend the imports:

```python
from shared.colocation.occupancy import (
    INTERNAL_TENANT_PREFIXES,
    occupancy_rows,
    aggregate_by_dc,
    tenant_occupancy_rows,
    used_u_breakdown,
)
```

Add the method after `_alias_index`:

```python
    def _internal_prefixes(self) -> tuple[str, ...]:
        """Bulutistan-internal tenant prefixes: the built-in seed unioned with the
        enabled Administration -> Internal (Bulutistan) source mappings.

        Before this existed the internal/external split ignored Administration
        entirely, so operator edits had no effect on the Colocation tab. Built-ins
        stay in the union so an empty or unreachable mapping table degrades to
        today's behaviour rather than reclassifying every internal rack as an
        external customer.
        """
        prefixes = list(INTERNAL_TENANT_PREFIXES)
        if self._webui is None or not getattr(self._webui, "is_available", False):
            return tuple(prefixes)
        try:
            rows = self._webui.run_rows(
                sm.LIST_SOURCE_MAPPINGS_FOR_ACCOUNT, (INTERNAL_ACCOUNT_ID,)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("internal mapping load failed: %s", exc)
            return tuple(prefixes)
        for r in rows or []:
            if not r.get("enabled", True):
                continue
            value = (r.get("match_value") or "").strip().lower()
            if value and value not in prefixes:
                prefixes.append(value)
        return tuple(prefixes)
```

Add the module-level constant just below `logger`:

```python
# Reserved account id the Administration "Internal (Bulutistan) source mappings"
# editor writes under. Mirrors INTERNAL_ACCOUNT_ID in the GUI editor.
INTERNAL_ACCOUNT_ID = "INTERNAL"
```

Then in `get_colocation`, replace lines 73-74:

```python
        customers = build_customer_footprint(tenant_rows, self._alias_index())
        internal = build_internal_footprint(tenant_rows)
```

with:

```python
        internal_prefixes = self._internal_prefixes()
        customers = build_customer_footprint(
            tenant_rows, self._alias_index(), internal_prefixes=internal_prefixes
        )
        internal = build_internal_footprint(
            tenant_rows, internal_prefixes=internal_prefixes
        )
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `cd services/customer-api && ../../.venv/bin/pytest tests/test_colocation_matching_service.py -q`
Expected: PASS

- [ ] **Step 13: Measure the before/after split**

This change moves tenants between the External and Internal buckets. Record the shift rather than assuming it is zero.

Run:

```bash
.venv/bin/python - <<'PY'
import os, sys, psycopg2
from dotenv import load_dotenv
sys.path.insert(0, os.getcwd()); load_dotenv(".env")
from shared.colocation.occupancy import used_u_breakdown
conn = psycopg2.connect(host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT") or "5000",
    dbname=os.getenv("DB_NAME") or "bulutlake", user=os.getenv("DB_USER") or "datalakeui",
    password=os.getenv("DB_PASS"), connect_timeout=20)
conn.set_session(readonly=True, autocommit=True)
print(used_u_breakdown(conn.cursor(), None))
PY
```

Paste the output into the commit message. If external/internal U changed, say by how much and why (which Administration mapping caused it). If Administration holds no INTERNAL mappings yet, the numbers must be identical — state that.

- [ ] **Step 14: Commit**

```bash
git add shared/colocation/occupancy.py shared/colocation/matching.py \
        services/customer-api/app/services/colocation_matching_service.py \
        tests/test_colocation_occupancy.py tests/test_colocation_matching.py \
        services/customer-api/tests/test_colocation_matching_service.py
git commit -m "fix(colocation): classify internal tenants from Administration mappings

is_internal_tenant matched a hardcoded 4-entry prefix tuple and never read
gui_crm_customer_source_mapping, so the Administration > Internal (Bulutistan)
source mappings editor had no effect on the Colocation tab's internal/external
split. The service now unions the enabled INTERNAL mappings over the built-in
seed and injects them; shared/colocation stays database-free.

Built-ins are retained in the union so an empty or unreachable mapping table
degrades to previous behaviour instead of reclassifying internal racks as
external customers.

Used-U breakdown before/after: <paste Step 13 output>"
```

---

### Task 3: Attach price and potential to the colocation payload

One resolution per request, carried on the existing cached endpoint so no GUI surface queries pricing itself.

**Files:**
- Modify: `services/customer-api/app/services/colocation_matching_service.py:46-75`
- Test: `services/customer-api/tests/test_colocation_matching_service.py` (extend)

**Interfaces:**
- Consumes: `resolve_colocation_unit_price`, `potential_tl`, `COLOCATION_PRODUCT_ID` (Task 1); `_internal_prefixes` (Task 2).
- Produces: payload additions consumed by Tasks 4-8:
  - `payload["aggregate"]["unit_price_tl"]: float | None`
  - `payload["aggregate"]["price_source"]: str`
  - `payload["aggregate"]["free_u_potential_tl"]: float | None`
  - `payload["aggregate"]["used_u_potential_tl"]: float | None`
  - each row of `payload["customers"]` and `payload["internal"]` gains `"potential_tl": float | None`

- [ ] **Step 1: Write the failing test**

Append to `services/customer-api/tests/test_colocation_matching_service.py`:

```python
def _service_with_price(price):
    customer = MagicMock()
    conn = MagicMock()
    customer._get_connection.return_value.__enter__.return_value = conn
    webui = MagicMock()
    webui.is_available = False
    svc = ColocationMatchingService(customer_service=customer, webui=webui)
    return svc, price


def test_payload_carries_unit_price_and_potential():
    svc, price = _service_with_price(10430.84)

    with patch("app.services.colocation_matching_service.occupancy_rows", return_value=_rows()), \
         patch("app.services.colocation_matching_service.tenant_occupancy_rows", return_value=_tenant_rows()), \
         patch("app.services.colocation_matching_service.used_u_breakdown", return_value={}), \
         patch("app.services.colocation_matching_service.resolve_colocation_unit_price",
               return_value=(price, "crm")):
        payload = svc.get_colocation("DC13")

    agg = payload["aggregate"]
    assert agg["unit_price_tl"] == price
    assert agg["price_source"] == "crm"
    assert agg["free_u_potential_tl"] == agg["free_u"] * price
    assert agg["used_u_potential_tl"] == agg["used_u"] * price

    boyner = next(c for c in payload["customers"] if c["tenant"] == "Boyner")
    assert boyner["potential_tl"] == boyner["used_u"] * price


def test_payload_potential_is_none_when_price_unresolved():
    svc, _ = _service_with_price(None)

    with patch("app.services.colocation_matching_service.occupancy_rows", return_value=_rows()), \
         patch("app.services.colocation_matching_service.tenant_occupancy_rows", return_value=_tenant_rows()), \
         patch("app.services.colocation_matching_service.used_u_breakdown", return_value={}), \
         patch("app.services.colocation_matching_service.resolve_colocation_unit_price",
               return_value=(None, "unavailable")):
        payload = svc.get_colocation("DC13")

    agg = payload["aggregate"]
    assert agg["unit_price_tl"] is None
    assert agg["price_source"] == "unavailable"
    assert agg["free_u_potential_tl"] is None
    assert all(c["potential_tl"] is None for c in payload["customers"])
    assert all(r["potential_tl"] is None for r in payload["internal"])


def test_internal_rows_also_carry_potential():
    svc, price = _service_with_price(1000.0)

    with patch("app.services.colocation_matching_service.occupancy_rows", return_value=_rows()), \
         patch("app.services.colocation_matching_service.tenant_occupancy_rows", return_value=_tenant_rows()), \
         patch("app.services.colocation_matching_service.used_u_breakdown", return_value={}), \
         patch("app.services.colocation_matching_service.resolve_colocation_unit_price",
               return_value=(price, "override")):
        payload = svc.get_colocation("DC13")

    assert payload["internal"]
    for r in payload["internal"]:
        assert r["potential_tl"] == r["used_u"] * price
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/customer-api && ../../.venv/bin/pytest tests/test_colocation_matching_service.py -q -k potential`
Expected: FAIL — `KeyError: 'unit_price_tl'`

- [ ] **Step 3: Wire price resolution into `get_colocation`**

In `services/customer-api/app/services/colocation_matching_service.py`, extend the imports:

```python
from app.services.colocation_price_service import (
    potential_tl,
    resolve_colocation_unit_price,
)
```

Inside the `with conn.cursor() as cur:` block in `get_colocation`, after `breakdown = used_u_breakdown(...)`, add:

```python
                    unit_price, price_source = resolve_colocation_unit_price(
                        cur, self._webui
                    )
```

Initialise the pair alongside the other defaults before the `try` (so the failure path still produces a valid payload):

```python
        unit_price: float | None = None
        price_source = "unavailable"
```

and add to the `except` block:

```python
            unit_price = None
            price_source = "unavailable"
```

Then extend the aggregate update:

```python
        aggregate.update({
            "external_u": int(breakdown.get("external_u") or 0),
            "internal_u": int(breakdown.get("internal_u") or 0),
            "untagged_u": int(breakdown.get("untagged_u") or 0),
            "external_customer_count": int(breakdown.get("external_customer_count") or 0),
            "unit_price_tl": unit_price,
            "price_source": price_source,
            "free_u_potential_tl": potential_tl(aggregate["free_u"], unit_price),
            "used_u_potential_tl": potential_tl(aggregate["used_u"], unit_price),
        })
```

and stamp the rows before returning:

```python
        for row in customers:
            row["potential_tl"] = potential_tl(row.get("used_u"), unit_price)
        for row in internal:
            row["potential_tl"] = potential_tl(row.get("used_u"), unit_price)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/customer-api && ../../.venv/bin/pytest tests/test_colocation_matching_service.py tests/test_colocation_router.py tests/test_colocation_panel_result.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/app/services/colocation_matching_service.py \
        services/customer-api/tests/test_colocation_matching_service.py
git commit -m "feat(colocation): carry unit price and potential TL on the colocation payload

Resolved once per request and attached to the aggregate plus every customer and
internal row, so each GUI surface reads one already-cached source instead of
querying pricing itself. An unresolved price propagates as None through every
potential field."
```

---

### Task 4: Free U Potential tile on the colocation summary card

**Files:**
- Modify: `src/components/colocation_summary.py:45-50`
- Test: `tests/test_colocation_summary_component.py` (extend)

**Interfaces:**
- Consumes: `aggregate["free_u_potential_tl"]`, `aggregate["unit_price_tl"]`, `aggregate["price_source"]` (Task 3).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_colocation_summary_component.py`:

```python
from src.components.colocation_summary import build_colocation_summary


def _texts(component):
    """Flatten every dmc.Text/str value in a Dash component tree."""
    out = []
    stack = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            out.append(node)
            continue
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
        label = getattr(node, "label", None)
        if isinstance(label, str):
            out.append(label)
    return out


def test_free_u_potential_tile_renders_tl_value():
    agg = {"total_u": 2719, "used_u": 1169, "free_u": 1550, "rack_count": 57,
           "free_u_potential_tl": 1550 * 10430.84, "unit_price_tl": 10430.84,
           "price_source": "crm"}

    texts = _texts(build_colocation_summary(agg))

    assert "Free U Potential" in texts
    assert "16.17 Milyon TL" in texts


def test_free_u_potential_tile_renders_dash_when_price_unresolved():
    agg = {"total_u": 2719, "used_u": 1169, "free_u": 1550, "rack_count": 57,
           "free_u_potential_tl": None, "unit_price_tl": None,
           "price_source": "unavailable"}

    texts = _texts(build_colocation_summary(agg))

    assert "Free U Potential" in texts
    assert "—" in texts
    assert "0 TL" not in texts


def test_free_u_potential_tile_absent_keys_do_not_crash():
    texts = _texts(build_colocation_summary({"total_u": 10, "used_u": 4, "free_u": 6}))

    assert "Free U Potential" in texts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_colocation_summary_component.py -q -k potential`
Expected: FAIL — `assert 'Free U Potential' in [...]`

- [ ] **Step 3: Add the tile**

In `src/components/colocation_summary.py`, extend the import block:

```python
from src.utils.format_units import fmt_tl
```

Add a tooltip-capable tile helper below `_tile`:

```python
def _tile_with_tip(label: str, value: str, tip: str):
    return dmc.Tooltip(
        label=tip, position="bottom", withArrow=True, multiline=True, w=280,
        children=_tile(label, value),
    )
```

Extend `build_colocation_summary` — after the existing `unt` / `ncust` reads, add:

```python
    potential = agg.get("free_u_potential_tl")
    unit_price = agg.get("unit_price_tl")
    price_source = agg.get("price_source") or "unavailable"
    if unit_price is None:
        price_tip = ("Colocation unit price unavailable — no operator override and no "
                     "CRM price level for the per-U product. Shown as — rather than 0.")
    else:
        origin = {"override": "operator override",
                  "crm": "CRM price list"}.get(price_source, price_source)
        price_tip = (f"Free U x {unit_price:,.2f} TL per U ({origin}). "
                     "Potential at list price — not billed revenue.")
```

and replace the `tiles` block:

```python
    tiles = dmc.SimpleGrid(cols=5, spacing="md", children=[
        _tile("Total U", f"{total_u:,}"),
        _tile("Used U", f"{used_u:,}"),
        _tile("Free U", f"{free_u:,}"),
        _tile("Racks", f"{racks:,}"),
        _tile_with_tip("Free U Potential", fmt_tl(potential), price_tip),
    ])
```

`fmt_tl(None)` already returns `"—"`, which is exactly the required unresolved rendering.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_colocation_summary_component.py tests/test_floor_map_recolor.py -q`
Expected: PASS — the floor map also renders this component, so it must still build.

- [ ] **Step 5: Commit**

```bash
git add src/components/colocation_summary.py tests/test_colocation_summary_component.py
git commit -m "feat(colocation): Free U Potential tile on the summary card

Reads free_u_potential_tl from the same aggregate the Free U tile uses, so the
two can never disagree. Unresolved price renders as an em dash via fmt_tl(None)
rather than 0 TL, and the tooltip names the price source."
```

---

### Task 5: Potential column on the Dedicated Customers and Internal Resources tables

**Files:**
- Modify: `src/pages/dc_view.py:2537-2593`
- Test: `tests/test_colocation_potential_column.py` (create)

**Interfaces:**
- Consumes: `customers[].potential_tl`, `internal[].potential_tl` (Task 3).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Create `tests/test_colocation_potential_column.py`:

```python
"""The colocation tables carry a potential-TL column computed at list price.
The header must not imply billed revenue: no rack tenant currently matches a
CRM colocation contract (verified 2026-07-27)."""
from src.pages.dc_view import build_colocation_tab


def _texts(component):
    out = []
    stack = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            out.append(node)
            continue
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
        label = getattr(node, "label", None)
        if isinstance(label, str):
            out.append(label)
    return out


def _table_rows(component):
    """Every dmc.Table body row as a list of its cells' flattened text."""
    rows = []
    stack = [component]
    while stack:
        node = stack.pop()
        if node is None or isinstance(node, str):
            continue
        if type(node).__name__ == "Tr":
            cells = []
            for td in (getattr(node, "children", None) or []):
                if type(td).__name__ != "Td":
                    continue
                cells.append(" ".join(t for t in _texts(td)).strip())
            if cells:
                rows.append(cells)
            continue
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
    return rows


def _payload(potential):
    return {
        "aggregate": {"total_u": 2719, "used_u": 1169, "free_u": 1550,
                      "rack_count": 57, "unit_price_tl": 10430.84,
                      "price_source": "crm",
                      "free_u_potential_tl": 1550 * 10430.84},
        "customers": [{"tenant": "Boyner", "crm_account_name": None,
                       "match_status": "unmatched", "racks": ["122"],
                       "used_u": 85, "potential_tl": potential}],
        "internal": [{"tenant": "Bulutistan - Linux TEAM", "racks": ["116"],
                      "used_u": 15, "potential_tl": potential}],
    }


def test_customer_table_has_potential_column_header():
    texts = _texts(build_colocation_tab(_payload(85 * 10430.84)))

    assert "Potential (TL)" in texts


def test_customer_potential_value_rendered():
    # fmt_tl is the compact executive formatter: 886,621.4 -> "886.6 Bin TL".
    # Used here so an unresolved price renders "—" through the same function.
    rows = _table_rows(build_colocation_tab(_payload(85 * 10430.84)))

    boyner = next(r for r in rows if r[0] == "Boyner")
    assert boyner[-1] == "886.6 Bin TL"


def test_internal_table_has_potential_column():
    tab = build_colocation_tab(_payload(15 * 10430.84))
    texts = _texts(tab)

    assert texts.count("Potential (TL)") == 2


def test_unresolved_potential_renders_dash_not_zero():
    # Assert the potential CELL specifically, not "no '0' anywhere in the tree" —
    # the tree is full of legitimate numbers and a blanket scan would pass or fail
    # for reasons unrelated to this behaviour.
    tab = build_colocation_tab(_payload(None))
    rows = _table_rows(tab)

    boyner = next(r for r in rows if r[0] == "Boyner")
    assert boyner[-1] == "—"

    internal = next(r for r in rows if r[0] == "Bulutistan - Linux TEAM")
    assert internal[-1] == "—"


def test_header_disclaims_billed_revenue():
    texts = " ".join(_texts(build_colocation_tab(_payload(1.0))))

    assert "list price" in texts.lower()
    assert "not billed" in texts.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_colocation_potential_column.py -q`
Expected: FAIL — `assert 'Potential (TL)' in [...]`

- [ ] **Step 3: Add the column to both tables**

`src/pages/dc_view.py:26` opens a multi-name `from src.utils.format_units import (` block that does **not** include `fmt_tl`. Add `fmt_tl` to that existing parenthesised list — do not add a second import statement from the same module.

In `build_colocation_tab`, replace the customer header and body:

```python
        header = html.Tr(children=[html.Th(h) for h in
                                   ("Customer", "CRM Account", "Match", "Rack", "Used U (own)")])
```

with:

```python
        header = html.Tr(children=[html.Th(h) for h in
                                   ("Customer", "CRM Account", "Match", "Rack",
                                    "Used U (own)", "Potential (TL)")])
```

and append one cell inside the customer loop, after the `used_u` cell:

```python
                html.Td(fmt_tl(c.get("potential_tl"))),
```

Do the same for the internal table:

```python
        int_header = html.Tr(children=[html.Th(h) for h in
                                       ("Resource", "Rack", "Used U", "Potential (TL)")])
```

and inside its loop, after the `used_u` cell:

```python
                html.Td(fmt_tl(r.get("potential_tl"))),
```

Finally, change both section subtitles so the framing travels with the number. Replace:

```python
            _section_title("Dedicated Customers", "Device tenant → CRM match"),
```

with:

```python
            _section_title(
                "Dedicated Customers",
                "Device tenant → CRM match · Potential at list price, not billed revenue",
            ),
```

and:

```python
            _section_title("Internal Resources", "Bulutistan-owned rack footprint"),
```

with:

```python
            _section_title(
                "Internal Resources",
                "Bulutistan-owned rack footprint · Potential at list price, "
                "not billed revenue — opportunity cost of self-occupied U",
            ),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_colocation_potential_column.py tests/test_dc_view_colocation_tab.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pages/dc_view.py tests/test_colocation_potential_column.py
git commit -m "feat(colocation): potential TL column on both colocation tables

Computed at list price, and both section subtitles say so. No rack tenant
currently matches a CRM colocation contract, so a column implying billed
revenue would be wrong on every row."
```

---

### Task 6: Colocation becomes a Physical Inventory sub-tab

Follows the existing nested-tab pattern (Virtualization, Backup) rather than introducing a new mechanism.

**Files:**
- Modify: `src/pages/dc_view.py:5472,5480-5489,5570-5582,5746-5761,5835-5850,5897-5905`
- Modify: `src/auth/permission_catalog.py:141`
- Test: `tests/test_dc_view_phys_inv_nested_tabs.py` (create)
- Test: `tests/test_permission_catalog_colocation.py` (extend)

**Interfaces:**
- Consumes: `build_colocation_tab` (Task 5), `_build_physical_inventory_dc_tab` (existing).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing permission test**

Append to `tests/test_permission_catalog_colocation.py`:

```python
from src.auth.permission_catalog import build_default_permission_roots


def _find(nodes, code):
    """PermissionNode is a dataclass with .code / .children — not a dict."""
    for n in nodes:
        if n.code == code:
            return n
        found = _find(n.children or [], code)
        if found:
            return found
    return None


def test_colocation_is_a_child_of_physical_inventory():
    phys = _find(build_default_permission_roots(), "sec:dc_view:phys_inv")

    assert phys is not None
    child_codes = [c.code for c in (phys.children or [])]
    assert "sub:dc_view:phys_inv:colocation" in child_codes
    assert "sub:dc_view:phys_inv:overview" in child_codes


def test_legacy_colocation_section_code_is_retained_for_migration():
    # Principals granted the old section code must not lose access silently.
    assert _find(build_default_permission_roots(), "sec:dc_view:colocation") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_permission_catalog_colocation.py -q -k child_of_physical`
Expected: FAIL — `assert 'sub:dc_view:phys_inv:colocation' in [...]`

- [ ] **Step 3: Restructure the permission catalog**

In `src/auth/permission_catalog.py`, replace line 141:

```python
                    _n("sec:dc_view:phys_inv", "Physical Inventory", "section", sort_order=50),
```

with:

```python
                    _n(
                        "sec:dc_view:phys_inv",
                        "Physical Inventory",
                        "section",
                        sort_order=50,
                        children=[
                            _n("sub:dc_view:phys_inv:overview", "Overview", "sub_section"),
                            _n("sub:dc_view:phys_inv:colocation", "Colocation", "sub_section"),
                        ],
                    ),
```

Leave the existing `sec:dc_view:colocation` node in place. It is now a legacy key: no tab reads it directly, but principals already granted it keep a valid grant, and Step 5 honours it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_permission_catalog_colocation.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing nested-tab test**

Create `tests/test_dc_view_phys_inv_nested_tabs.py`:

```python
"""Colocation renders as a Physical Inventory sub-tab, not a top-level tab."""
from src.pages import dc_view


def _tab_values(component):
    """Collect every dmc.TabsTab `value` in a Dash component tree."""
    out = []
    stack = [component]
    while stack:
        node = stack.pop()
        if node is None or isinstance(node, str):
            continue
        if type(node).__name__ == "TabsTab":
            value = getattr(node, "value", None)
            if value:
                out.append(value)
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
    return out


def test_phys_inv_subtab_values():
    panel = dc_view._build_phys_inv_tab_content(
        phys_inv={}, coloc={}, show_overview=True, show_colo=True,
    )

    values = _tab_values(panel)
    assert "phys-overview" in values
    assert "phys-colo" in values


def test_colocation_subtab_hidden_without_permission():
    panel = dc_view._build_phys_inv_tab_content(
        phys_inv={}, coloc={}, show_overview=True, show_colo=False,
    )

    assert "phys-colo" not in _tab_values(panel)


def test_overview_subtab_hidden_without_permission():
    panel = dc_view._build_phys_inv_tab_content(
        phys_inv={}, coloc={}, show_overview=False, show_colo=True,
    )

    values = _tab_values(panel)
    assert "phys-overview" not in values
    assert "phys-colo" in values
```

- [ ] **Step 6: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_dc_view_phys_inv_nested_tabs.py -q`
Expected: FAIL — `AttributeError: module 'src.pages.dc_view' has no attribute '_build_phys_inv_tab_content'`

- [ ] **Step 7: Add the nested-tab builder**

In `src/pages/dc_view.py`, add immediately after `build_colocation_tab` (which ends around line 2593):

```python
def _build_phys_inv_tab_content(phys_inv, coloc, *, show_overview: bool, show_colo: bool):
    """Physical Inventory tab body: Overview + Colocation nested tabs.

    Mirrors the Virtualization / Backup nested-tab shape already used in this
    module, so no new UI mechanism is introduced.
    """
    order = [("phys-overview", show_overview), ("phys-colo", show_colo)]
    default_tab = next((t for t, ok in order if ok), "phys-overview")
    return dmc.Tabs(
        id="phys-inv-nested-tabs",
        color="violet",
        variant="outline",
        radius="md",
        value=default_tab,
        children=[
            dmc.TabsList(children=[
                dmc.TabsTab("Overview", value="phys-overview") if show_overview else None,
                dmc.TabsTab("Colocation", value="phys-colo") if show_colo else None,
            ]),
            dmc.TabsPanel(
                value="phys-overview",
                children=dmc.Stack(gap="lg", style={"paddingTop": "12px"},
                                   children=[_build_physical_inventory_dc_tab(phys_inv)]),
            ) if show_overview else None,
            dmc.TabsPanel(
                value="phys-colo",
                children=dmc.Stack(gap="lg", style={"paddingTop": "12px"},
                                   children=[build_colocation_tab(coloc)]),
            ) if show_colo else None,
        ],
    )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_dc_view_phys_inv_nested_tabs.py -q`
Expected: PASS

- [ ] **Step 9: Rewire the DC View tab list**

Still in `src/pages/dc_view.py`:

**9a.** Replace line 5472 so the legacy grant still opens the sub-tab:

```python
    show_colo = _sec("sec:dc_view:colocation")
```

with:

```python
    # Colocation moved under Physical Inventory. Accept the new sub-section key OR
    # the legacy section key, so principals granted the old key keep access.
    show_colo = _sec("sub:dc_view:phys_inv:colocation") or _sec("sec:dc_view:colocation")
    show_phys_overview = _sec("sub:dc_view:phys_inv:overview") or _sec("sec:dc_view:phys_inv")
    # The parent tab appears when either child is visible.
    show_phys = (show_phys and show_phys_overview) or show_colo
```

Place these three lines immediately after the existing `show_phys = has_phys_inv and _sec("sec:dc_view:phys_inv")` assignment and before the `if eager_tabs is not None:` block, then add inside that block:

```python
        show_phys = _sec("sec:dc_view:phys_inv") or show_colo
```

**9b.** Remove the top-level colocation entry from `tabs_order` (line 5488) — delete `("colo", show_colo),`.

**9c.** Remove the top-level tab (line 5580) — delete `dmc.TabsTab("Colocation", value="colo") if show_colo else None,`.

**9d.** Do the same at line 5904 in the second tab list — delete `dmc.TabsTab("Colocation", value="colo") if _sec("sec:dc_view:colocation") else None,`.

**9e.** Replace the Physical Inventory panel body (lines 5752-5759) so it renders the nested tabs:

```python
                        else html.Div(
                            id="dc-tab-phys-inv-root",
                            children=dmc.Stack(
                                gap="lg",
                                style={"padding": "0 30px"},
                                children=[_build_physical_inventory_dc_tab(phys_inv)],
                            ),
                        )
```

becomes:

```python
                        else html.Div(
                            id="dc-tab-phys-inv-root",
                            children=dmc.Stack(
                                gap="lg",
                                style={"padding": "0 30px"},
                                children=[_build_phys_inv_tab_content(
                                    phys_inv,
                                    api.get_colocation(dc_id) if show_colo else {},
                                    show_overview=show_phys_overview,
                                    show_colo=show_colo,
                                )],
                            ),
                        )
```

**9f.** Delete the entire top-level Colocation `dmc.TabsPanel` block (lines 5835-5850), including its `# Colocation (dedicated-customer rack footprint)` comment.

- [ ] **Step 10: Run the DC View suite**

Run: `.venv/bin/pytest tests/ -q -k "dc_view or colocation or permission"`
Expected: PASS. If a test asserts the old top-level `"colo"` tab value, update it to `"phys-colo"` — that is the intended change, not a regression.

- [ ] **Step 11: Commit**

```bash
git add src/pages/dc_view.py src/auth/permission_catalog.py \
        tests/test_dc_view_phys_inv_nested_tabs.py tests/test_permission_catalog_colocation.py
git commit -m "feat(dc-view): Colocation becomes a Physical Inventory sub-tab

Physical Inventory gains Overview + Colocation nested tabs, reusing the shape
Virtualization and Backup already use. The top-level Colocation tab is removed.

sec:dc_view:colocation is retained as a legacy key and still grants access to
the sub-tab, so principals holding only the old grant do not silently lose it."
```

---

### Task 7: Physical — Colocation entry on the DC Summary sellable tab

**Files:**
- Modify: `src/pages/dc_summary_sellable.py`
- Modify: `src/pages/dc_view.py` (pass colocation aggregate into the summary builder)
- Test: `tests/test_dc_summary_sellable_colocation.py` (create)

**Interfaces:**
- Consumes: `aggregate["free_u"]`, `aggregate["free_u_potential_tl"]` (Task 3).
- Produces: `build_colocation_sellable_entry(coloc_aggregate: dict | None) -> html.Div | None`

- [ ] **Step 1: Confirm the module's visual idiom**

Run: `grep -n "^def " src/pages/dc_summary_sellable.py`

This module has no generic per-family entry builder to reuse — it exposes `_exec_kpi`,
`build_virt_compute_block`, `build_virt_storage_block` and
`build_summary_sellable_children`. Read `_exec_kpi` (line ~55) and
`build_summary_sellable_children` (line ~438) to match the surrounding card idiom
(`nexus-card`, `_BRAND` / `_MUTED` / `_TEXT` colours), then write the new entry in that
style. Step 6 renders it from `_build_summary_tab` in `src/pages/dc_view.py`, not from
this module — this module only exports the builder.

- [ ] **Step 2: Write the failing test**

Create `tests/test_dc_summary_sellable_colocation.py`:

```python
"""DC Summary carries a Physical — Colocation entry: free rack-U and its TL
value at list price. Distinct from the virtualization families and never
summed into them."""
from src.pages.dc_summary_sellable import build_colocation_sellable_entry


def _texts(component):
    out = []
    stack = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            out.append(node)
            continue
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
    return out


def test_entry_renders_free_u_and_tl():
    entry = build_colocation_sellable_entry(
        {"free_u": 1550, "free_u_potential_tl": 1550 * 10430.84,
         "unit_price_tl": 10430.84, "price_source": "crm"}
    )

    texts = _texts(entry)
    assert any("Colocation" in t for t in texts)
    assert any("1,550" in t for t in texts)
    assert "16.17 Milyon TL" in texts


def test_entry_renders_dash_when_price_unresolved():
    entry = build_colocation_sellable_entry(
        {"free_u": 1550, "free_u_potential_tl": None,
         "unit_price_tl": None, "price_source": "unavailable"}
    )

    assert "—" in _texts(entry)


def test_entry_is_none_without_colocation_data():
    assert build_colocation_sellable_entry(None) is None
    assert build_colocation_sellable_entry({}) is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_dc_summary_sellable_colocation.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_colocation_sellable_entry'`

- [ ] **Step 4: Implement the entry**

In `src/pages/dc_summary_sellable.py`, add:

```python
def build_colocation_sellable_entry(coloc_aggregate: dict | None):
    """Physical — Colocation sellable entry: free rack-U and its TL value.

    Returns None when there is no colocation data for this DC, so the caller can
    omit the card entirely rather than render an empty one. This value is never
    summed into the virtualization total: colocation potential runs 8-28x larger
    (measured 2026-07-27) and would swamp it.
    """
    agg = coloc_aggregate or {}
    free_u = agg.get("free_u")
    if not free_u:
        return None
    potential = agg.get("free_u_potential_tl")
    unit_price = agg.get("unit_price_tl")
    if unit_price is None:
        tip = "Colocation unit price unavailable — shown as — rather than 0."
    else:
        tip = (f"{free_u:,} free U x {unit_price:,.2f} TL per U. "
               "Potential at list price — not billed revenue.")
    return dmc.Tooltip(
        label=tip, position="bottom", withArrow=True, multiline=True, w=300,
        children=html.Div(
            className="nexus-card",
            style={"padding": "16px"},
            children=[
                dmc.Text("Physical — Colocation", size="sm", fw=700, c=_TEXT),
                dmc.Text(f"{free_u:,} free U", size="xs", c=_MUTED),
                dmc.Text(fmt_tl(potential), size="xl", fw=800, c=_BRAND),
            ],
        ),
    )
```

`fmt_tl`, `dmc`, `html`, `_TEXT`, `_MUTED` and `_BRAND` are already imported in this module.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_dc_summary_sellable_colocation.py -q`
Expected: PASS

- [ ] **Step 6: Render it in the Summary tab**

In `src/pages/dc_view.py`, `_build_summary_tab` currently receives `sellable_summary`. Add a `coloc_aggregate` keyword parameter defaulting to `None`, and append the entry to the sellable section when it is not `None`:

```python
    colo_entry = build_colocation_sellable_entry(coloc_aggregate)
```

Append `colo_entry` to the children list of the sellable block, guarded by `if colo_entry is not None`. Import it at the top of `dc_view.py`:

```python
from src.pages.dc_summary_sellable import build_colocation_sellable_entry
```

At the call site (line ~5591), pass the aggregate — reusing the same cached fetch the Physical Inventory tab uses:

```python
                        children=[_build_summary_tab(
                            data, tr, dc_id=str(dc_id),
                            sellable_summary=sellable_summary if show_summary_sellable else None,
                            show_sellable=show_summary_sellable,
                            classic_clusters=classic_clusters or None,
                            hyperconv_clusters=hyperconv_clusters or None,
                            coloc_aggregate=(api.get_colocation(dc_id) or {}).get("aggregate")
                                if show_colo else None,
                        )],
```

- [ ] **Step 7: Run the summary suite**

Run: `.venv/bin/pytest tests/ -q -k "summary or sellable"`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/pages/dc_summary_sellable.py src/pages/dc_view.py \
        tests/test_dc_summary_sellable_colocation.py
git commit -m "feat(dc-summary): Physical — Colocation sellable entry

Free rack-U and its TL value at list price, rendered beside the virtualization
families but never summed into them — colocation potential measured 8-28x
larger and would swamp the virtualization signal."
```

---

### Task 8: Separate Colocation line on DC cards and the Potential Sales KPI

**Files:**
- Modify: `src/pages/datacenters.py:113-129,216-270,665-690,1008-1025`
- Test: `tests/test_datacenters_colocation_potential.py` (create)

**Interfaces:**
- Consumes: `aggregate["free_u_potential_tl"]` (Task 3).
- Produces: `_colocation_sales_line(colo_tl: float | None, *, loading: bool = False) -> html.Div | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_datacenters_colocation_potential.py`:

```python
"""Colocation potential renders as its own line, never folded into the
virtualization min-max range."""
from src.pages.datacenters import _colocation_sales_line, _dc_sellable_ribbon


def _texts(component):
    out = []
    stack = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            out.append(node)
            continue
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
        label = getattr(node, "label", None)
        if isinstance(label, str):
            out.append(label)
    return out


def test_colocation_line_renders_single_value_not_a_range():
    texts = _texts(_colocation_sales_line(16_167_802.0))

    assert "Potential Sales (Colocation)" in texts
    assert "16.17 Milyon TL" in texts
    assert not any("–" in t and "Milyon" in t for t in texts)


def test_colocation_line_absent_when_no_value():
    assert _colocation_sales_line(None) is None
    assert _colocation_sales_line(0.0) is None


def test_colocation_line_shows_loading_state():
    texts = _texts(_colocation_sales_line(None, loading=True))

    assert "Potential Sales (Colocation)" in texts
    assert "…" in texts


def test_virtualization_ribbon_label_unchanged():
    texts = _texts(_dc_sellable_ribbon(
        1_000_000.0, virt_tl_min=574_800.0, virt_tl_max=1_910_000.0,
        total_portfolio_tl=10_000_000.0,
    ))

    assert "Potential Sales (Virtualization)" in texts
    assert "Potential Sales (Colocation)" not in texts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_datacenters_colocation_potential.py -q`
Expected: FAIL — `ImportError: cannot import name '_colocation_sales_line'`

- [ ] **Step 3: Implement the line**

In `src/pages/datacenters.py`, add after `_potential_sales_display` (line ~129):

```python
def _colocation_sales_line(colo_tl: float | None, *, loading: bool = False):
    """Colocation potential as its own line — a single value, not a range.

    Free rack-U is an exact count and the unit price is a single figure, so no
    interval exists. Kept separate from the virtualization range because
    colocation potential measured 8-28x larger per DC (2026-07-27); summing them
    would erase every movement in the virtualization signal.

    Returns None when there is nothing to show, so callers can omit the row.
    """
    if loading:
        headline, tip_value = "…", "Hesaplanıyor"
    elif not colo_tl:
        return None
    else:
        headline = fmt_tl(colo_tl)
        tip_value = f"{float(colo_tl):,.0f} TL"
    return dmc.Tooltip(
        label=(f"Potential Sales (Colocation): {tip_value}\n"
               "Free rack-U x the CRM per-U colocation price. Potential at list "
               "price — not billed revenue. Not included in the virtualization range."),
        position="bottom",
        withArrow=True,
        multiline=True,
        w=320,
        children=dmc.Group(
            justify="space-between",
            gap="xs",
            mt=6,
            children=[
                dmc.Text("Potential Sales (Colocation)", size="xs", fw=600, c="#A3AED0"),
                dmc.Text(
                    headline,
                    size="xs",
                    fw=800,
                    c="#0BA5EC",
                    style={"textAlign": "right", "lineHeight": 1.2, "maxWidth": "55%"},
                ),
            ],
        ),
    )
```

`src/pages/datacenters.py:26` currently imports only `fmt_tl_range`. Change it to:

```python
from src.utils.format_units import fmt_tl, fmt_tl_range
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_datacenters_colocation_potential.py -q`
Expected: PASS

- [ ] **Step 5: Render the line on the DC card**

`_dc_sellable_ribbon` returns a single `dmc.Tooltip`. Give it a `colo_tl` keyword parameter defaulting to `None` and wrap its return so the colocation line sits beneath the existing ribbon:

```python
def _dc_sellable_ribbon(
    virt_tl: float,
    *,
    virt_tl_min: float | None = None,
    virt_tl_max: float | None = None,
    total_portfolio_tl: float,
    loading: bool = False,
    colo_tl: float | None = None,
) -> html.Div:
```

The function currently ends with a single `return dmc.Tooltip(label=tip, ... children=html.Div(...))`. Do not retype that expression. Instead:

1. Change that final statement from `return dmc.Tooltip(` to `ribbon = dmc.Tooltip(` — the body and closing paren stay byte-for-byte identical.
2. Append these four lines immediately after it, at the same indentation as `ribbon`:

```python
    colo_line = _colocation_sales_line(colo_tl, loading=loading)
    if colo_line is None:
        return ribbon
    return html.Div(children=[ribbon, colo_line])
```

Then update the single call site at line ~595 (inside `_dc_vault_card`) to pass the per-DC value:

```python
            _dc_sellable_ribbon(
                ...existing keyword arguments unchanged...,
                colo_tl=colo_potential_by_dc.get(str(dc.get("dc_code") or dc.get("code") or "")),
            ),
```

`colo_potential_by_dc` is built once in the page-level function that renders the cards — see Step 6, which creates it.

- [ ] **Step 6: Render the KPI tile at both call sites**

At lines ~672 and ~1013, add a sibling `_summary_kpi` immediately after the existing virtualization tile in each `children` list:

```python
            _summary_kpi(
                "solar:box-bold-duotone",
                "Potential Sales (Colocation)",
                fmt_tl(total_colo_potential_tl),
                "cyan",
                tooltip=(
                    f"Total colocation potential (all DCs): "
                    f"{float(total_colo_potential_tl or 0):,.0f} TL\n"
                    "Free rack-U x the CRM per-U colocation price. Potential at list "
                    "price — not billed revenue. Not summed into the virtualization "
                    "figure beside it."
                ),
                allow_wrap=True,
            ),
```

**Read this before writing the helper — an earlier draft of this plan got it wrong.**

`datacenters.py` does not currently call `get_colocation` at all. The obvious optimisation — one `get_colocation("*")` fetch, then group its `racks` rows by `dc` to get the per-DC split — produces numbers that **contradict the DC View Colocation tab**, and must not be used.

Measured 2026-07-27: 25 racks at site ISTANBUL are registered in NetBox under two DC labels at once (DC13+DH3, DC13+DH4) with conflicting `u_height` values. `_dedupe_physical_racks` keeps one row per `(rack_name, site_name)`, so the surviving capacity depends on which rows the query returned. Grouping the all-DC payload gives DC13 **1,550** free U; the per-DC call the Colocation tab makes gives **1,460**. Same datacenter, two screens, ~0.94 M TL apart.

So: the per-DC figure comes from the same per-DC call the Colocation tab uses, and the all-DC total comes from the `"*"` aggregate. They are deliberately not derived from each other, and the total is LESS than the sum of the cards because the `"*"` path deduplicates racks shared between DC labels. The KPI tooltip must say so.

Add this helper near the other module-level helpers in `src/pages/datacenters.py`:

```python
def _colocation_potential(dc_codes) -> tuple[float, dict[str, float]]:
    """(all-DC potential TL, {dc_code: potential TL}).

    The per-DC values come from per-DC get_colocation calls — the SAME path the
    DC View Colocation tab uses — because 25 ISTANBUL racks are registered under
    two DC labels with conflicting heights (measured 2026-07-27), and deriving a
    per-DC split from the all-DC payload disagrees with what the Colocation tab
    shows for the same datacenter.

    The all-DC total comes from the "*" aggregate, which de-duplicates those
    shared racks. It is therefore SMALLER than the sum of the per-DC values, by
    design. api_client caches these calls with single-flight, so the per-DC
    fetches are cheap once warm.

    Returns (0.0, {}) when the price is unresolved — the caller renders nothing
    rather than a misleading zero.
    """
    total_payload = api.get_colocation("*") or {}
    total_agg = total_payload.get("aggregate") or {}
    if total_agg.get("unit_price_tl") is None:
        return 0.0, {}
    by_dc: dict[str, float] = {}
    for code in dc_codes:
        code = str(code or "").strip()
        if not code:
            continue
        agg = (api.get_colocation(code) or {}).get("aggregate") or {}
        value = agg.get("free_u_potential_tl")
        if value:
            by_dc[code] = float(value)
    return float(total_agg.get("free_u_potential_tl") or 0.0), by_dc
```

In each of the two functions containing the KPI strips, call it once alongside the other totals, passing the DC codes that function already has in scope:

```python
    total_colo_potential_tl, colo_potential_by_dc = _colocation_potential(
        [d.get("dc_code") or d.get("code") for d in datacenters]
    )
```

Inspect how each function names its DC collection before writing this line — `datacenters` is the name used in the KPI strips around lines 665 and 1008, but confirm the per-DC code key (`dc_code` vs `code`) against the real records rather than assuming.

`colo_potential_by_dc` is what Step 5's call site consumes.

- [ ] **Step 7: Run the datacenters suite**

Run: `.venv/bin/pytest tests/ -q -k "datacenter or vault or sellable"`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/pages/datacenters.py tests/test_datacenters_colocation_potential.py
git commit -m "feat(datacenters): separate Potential Sales (Colocation) line

A single value rather than a range — free rack-U is an exact count and the unit
price is one figure. Deliberately not summed into the virtualization range:
colocation potential measured 8-28x larger per DC, so a combined figure would be
colocation-dominated and hide virtualization movement entirely."
```

---

### Task 9: Resolve the rack-capacity discrepancy

The spec forbids shipping the potential figure until this is explained. The deployed UI shows DC13 Total U 2,629 / Free U 1,460; `occupancy_rows` measured 2,719 / 1,550 on 2026-07-27. Used U (1,169) and rack count (57) match exactly, so the divergence is in `u_height`, not occupancy. 90 U is ~0.94 M TL in DC13 alone.

**Files:**
- Test: `tests/test_colocation_occupancy.py` (extend with a regression guard)
- Modify: whichever source the investigation identifies (unknown until Step 1)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Find where the 90 U differ**

Run:

```bash
.venv/bin/python - <<'PY'
import os, sys, psycopg2
from dotenv import load_dotenv
sys.path.insert(0, os.getcwd()); load_dotenv(".env")
from shared.colocation.occupancy import occupancy_rows
conn = psycopg2.connect(host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT") or "5000",
    dbname=os.getenv("DB_NAME") or "bulutlake", user=os.getenv("DB_USER") or "datalakeui",
    password=os.getenv("DB_PASS"), connect_timeout=20)
conn.set_session(readonly=True, autocommit=True)
rows = [r for r in occupancy_rows(conn.cursor(), "%DC13%")]
print(f"racks={len(rows)} total_u={sum(r['capacity_u'] for r in rows)}")
for r in sorted(rows, key=lambda r: -r["capacity_u"])[:20]:
    print(r["rack_name"], r["capacity_u"], r["used_u"], r["free_u"])
PY
```

Compare `capacity_u` per rack against `discovery_loki_rack.u_height` for DC13. Look for racks whose `u_height` is null, zero, or recently changed — `git log --oneline -- shared/colocation/occupancy.py` and the floor-map `u_height` patch history are the likely leads.

- [ ] **Step 2: Record the finding**

Write one paragraph in the commit message stating the cause: either (a) the deployed build predates a `u_height` fix, in which case no code change is needed and the discrepancy resolves on deploy, or (b) the query over-counts, in which case fix the query. Do not adjust either number to match the other.

- [ ] **Step 3: Add the regression guard**

Append to `tests/test_colocation_occupancy.py`:

```python
def test_capacity_uses_rack_u_height_not_device_span():
    """Rack capacity comes from the rack's own u_height. A rack whose devices
    span beyond its height must not inflate capacity — that was the suspected
    cause of the DC13 2,629-vs-2,719 gap measured 2026-07-27."""
    from shared.colocation.occupancy import row_to_dict, OCCUPANCY_COLUMNS

    row = [1, "116", "DC13", "Hall-A", 47, 60, 0, ["Boyner"], "ISTANBUL"]
    d = row_to_dict(row[:len(OCCUPANCY_COLUMNS)])

    assert d["capacity_u"] == 47
    assert d["free_u"] == 0
```

- [ ] **Step 4: Run the occupancy suite**

Run: `.venv/bin/pytest tests/test_colocation_occupancy.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_colocation_occupancy.py
git commit -m "test(colocation): guard rack capacity against device-span inflation

Investigation of the DC13 2,629-vs-2,719 total-U gap: <paste the Step 2 finding>.

90 U is ~0.94M TL at the current list price, so the potential figure must not
ship until the gap is explained."
```

---

### Task 10: Full-suite verification

- [ ] **Step 1: Run the GUI suite**

Run: `.venv/bin/pytest tests/ -q`
Expected: PASS, zero failures. Record the pass count.

- [ ] **Step 2: Run the customer-api suite**

Run: `cd services/customer-api && ../../.venv/bin/pytest tests/ -q`
Expected: PASS, zero failures. Record the pass count.

- [ ] **Step 3: Verify no hardcoded price leaked into application code**

Run: `grep -rn "10430\|10,430" --include='*.py' src services shared | grep -v tests`
Expected: no output. Any hit outside a test fixture violates a global constraint — remove it.

- [ ] **Step 4: Verify colocation is never summed into the virtualization range**

Run: `grep -rn "virt_tl.*colo_tl\|colo_tl.*virt_tl" --include='*.py' src`
Expected: no arithmetic combining them. Presentation-only co-location in a container is fine; addition is not.

- [ ] **Step 5: Verify the rack-dedup baseline still holds**

The `(rack_name, site_name)` fan-out guard in `shared/colocation/occupancy.py` is what keeps
free-U honest; a regression here silently multiplies every potential figure. Re-measure
against the 2026-07-27 baseline:

```bash
.venv/bin/python - <<'PY'
import os, sys, psycopg2
from dotenv import load_dotenv
sys.path.insert(0, os.getcwd()); load_dotenv(".env")
from shared.colocation.occupancy import occupancy_rows
conn = psycopg2.connect(host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT") or "5000",
    dbname=os.getenv("DB_NAME") or "bulutlake", user=os.getenv("DB_USER") or "datalakeui",
    password=os.getenv("DB_PASS"), connect_timeout=20)
conn.set_session(readonly=True, autocommit=True)
rows = occupancy_rows(conn.cursor(), None)
print(f"racks={len(rows)} (baseline 188)")
print(f"free_u={sum(r['free_u'] for r in rows)} (baseline 5892)")
print(f"total_u={sum(r['capacity_u'] for r in rows)} (baseline 8603)")
PY
```

Expected: 188 racks, 5,892 free U, 8,603 total U. A rack count above 188 means the dedupe
regressed and the figures are inflated — stop and fix before reporting. Genuine
infrastructure change is possible; if the numbers moved, say which racks appeared or
disappeared, do not just accept the new total.

- [ ] **Step 6: Report**

State the two pass counts, the Step 5 baseline result, the outcome of Task 9's
investigation, and the before/after used-U breakdown from Task 2 Step 13. Do not claim
completion without these numbers.
