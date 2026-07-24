# Colocation Plan B — CRM Matching & Sellable Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the colocation `dc_hosting_u` panel to real occupancy (so the CRM inventory report shows sold-U vs used-U vs free-U + TL), and resolve rack-installed devices to CRM customers to produce a per-customer colocation footprint.

**Architecture:** `sellable_service._query_total_allocated` gains a per-panel compute path for `dc_hosting_u` (mirroring the existing `backup_netbackup_storage` / `raw_ibm_storage_system` branches) that runs `shared/colocation/occupancy.py` and returns `(Σ capacity_u, Σ used_u)`. A `007` seed row makes the panel `has_infra_source`. A new `ColocationMatchingService` groups the occupancy rows' device tenants (excluding Bulutistan-internal) and resolves them to CRM accounts via the existing `gui_crm_customer_alias` table.

**Tech Stack:** Python 3.11, psycopg2, FastAPI, pytest. Depends on **Plan A** (`shared/colocation/occupancy.py`).

## Global Constraints

- **Working directory is the worktree** `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.claude/worktrees/task-62-colocation-viz`. Do all work and commits here; never cd to the main checkout. (Subagents default to the MAIN checkout — always use absolute paths.)
- Python interpreter for tests: `.venv/bin/python` (symlink to the main checkout's venv, Python 3.11.15). System `python3` is 3.9 and breaks the suite.
- **customer-api test command** (from the service dir; NO PYTHONPATH needed — its `tests/conftest.py` appends the repo root to `sys.path`):
  `cd services/customer-api && ../../.venv/bin/python -m pytest tests/ -v --tb=short -p no:cacheprovider`
- **Shared-module tests** (e.g. `tests/test_colocation_matching.py`) run from the worktree root: `.venv/bin/python -m pytest tests/test_colocation_matching.py -v`.
- **Baseline (pre-existing, NOT yours):** the customer-api suite has **1 pre-existing failure** — `tests/test_sellable_service.py::test_recompute_family_constraints_global_host_fallback_uses_star_compute`. It is in the same file this plan touches, but it fails before any change. Do NOT try to fix it; just don't INCREASE the failure count (baseline: 464 passed / 1 failed).
- **Plan A is DONE and available:** `shared/colocation/occupancy.py` exports `OCCUPANCY_SQL`, `occupancy_rows(cursor, dc_pattern=None)`, `aggregate_by_dc(rows)`, `row_to_dict`, `is_internal_tenant(name)`, `INTERNAL_TENANT_PREFIXES`. Per-rack dict keys: `rack_id, rack_name, dc, hall, capacity_u, used_u, free_u, tenants[]`. Reuse these — never reimplement occupancy math.
- **No DDL against bulutlake.** Occupancy math is the shared module; the sellable path calls it via `self._svc._get_connection()` (the CustomerService bulutlake connection).
- `dc_hosting_u`: `family='dc_hosting'`, `resource_kind='other'` (never ratio-bound), `display_unit='U'`. Threshold 80% (the `DEFAULT_THRESHOLD_PCT`). Sellable formula: `sellable = max(capacity_u × 0.80 − used_u, 0)`.
- The panel definition already exists (`006_seed_panel_definitions.sql:106`). Only the infra-source row + compute path + (optional) price are new.
- Seed-migration numbering: the next unused `NNN_*.sql` in `services/customer-api/migrations/webui/` (028 is the last; use **029**). Wrap in `BEGIN;`/`COMMIT;`; register nothing else (the docker runner tracks by filename).

---

### Task 1: Colocation customer-footprint matching (pure function)

**Files:**
- Create: `shared/colocation/matching.py`
- Test: `tests/test_colocation_matching.py`

**Interfaces:**
- Consumes: `shared.colocation.occupancy.is_internal_tenant`.
- Produces:
  - `build_customer_footprint(occupancy_rows: Sequence[dict], alias_by_key: dict[str, dict]) -> list[dict]`
    — groups EXTERNAL device tenants across racks into per-customer entries:
    `{"tenant": str, "crm_accountid": str|None, "crm_account_name": str|None, "match_status": "matched"|"unmatched", "racks": [rack_name...], "used_u": int, "dc": str|None}`.
    `alias_by_key` maps a lowercased tenant string → `{"crm_accountid", "crm_account_name"}`.
    `used_u` per customer = sum of `capacity_u - free_u` on racks where the tenant appears (a rack shared by N tenants counts its used-U once per tenant present — acceptable for a footprint overview; documented).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_colocation_matching.py
"""Group rack occupancy by external device-tenant into per-customer footprints,
resolving to CRM accounts via the alias map; Bulutistan-internal excluded."""
from shared.colocation import matching as m


def _rows():
    return [
        {"rack_name": "116", "dc": "DC13", "capacity_u": 47, "used_u": 35, "free_u": 12,
         "tenants": ["Boyner", "Bulutistan - Linux TEAM"]},
        {"rack_name": "209", "dc": "DC13", "capacity_u": 47, "used_u": 27, "free_u": 20,
         "tenants": ["AytemizBank"]},
        {"rack_name": "300", "dc": "DC14", "capacity_u": 45, "used_u": 10, "free_u": 35,
         "tenants": ["Bulutistan - Virtualization"]},  # internal only -> no customer entry
    ]


def test_footprint_groups_external_tenants_and_excludes_internal():
    alias = {"boyner": {"crm_accountid": "A-1", "crm_account_name": "Boyner A.Ş."}}
    out = {f["tenant"]: f for f in m.build_customer_footprint(_rows(), alias)}
    assert set(out) == {"Boyner", "AytemizBank"}          # internal excluded
    assert out["Boyner"]["crm_accountid"] == "A-1"
    assert out["Boyner"]["match_status"] == "matched"
    assert out["Boyner"]["racks"] == ["116"]
    assert out["Boyner"]["used_u"] == 35                  # 47 - 12
    assert out["AytemizBank"]["match_status"] == "unmatched"
    assert out["AytemizBank"]["crm_accountid"] is None


def test_footprint_sums_used_u_across_racks():
    rows = [
        {"rack_name": "1", "dc": "DC13", "capacity_u": 47, "used_u": 10, "free_u": 37, "tenants": ["Paycore"]},
        {"rack_name": "2", "dc": "DC13", "capacity_u": 47, "used_u": 20, "free_u": 27, "tenants": ["Paycore"]},
    ]
    out = m.build_customer_footprint(rows, {})
    assert out[0]["tenant"] == "Paycore"
    assert sorted(out[0]["racks"]) == ["1", "2"]
    assert out[0]["used_u"] == 10 + 20


def test_footprint_empty_when_no_external_tenants():
    rows = [{"rack_name": "9", "dc": "DC13", "capacity_u": 47, "used_u": 5, "free_u": 42,
             "tenants": ["Bulutistan - Network & Security"]}]
    assert m.build_customer_footprint(rows, {}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_colocation_matching.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shared.colocation.matching'`.

- [ ] **Step 3: Write the module**

```python
# shared/colocation/matching.py
"""Resolve rack-installed device tenants to CRM customers → per-customer
colocation footprint. Device tenant_name is the only reliable physical→customer
signal (rack.tenant_name is ~4% populated); Bulutistan-internal tenants are
excluded via occupancy.is_internal_tenant."""
from __future__ import annotations

from typing import Any, Sequence

from shared.colocation.occupancy import is_internal_tenant


def build_customer_footprint(
    occupancy_rows: Sequence[dict],
    alias_by_key: dict,
) -> list[dict]:
    """Group external device tenants across racks into per-customer footprints.

    alias_by_key: {lowercased tenant string -> {crm_accountid, crm_account_name}}.
    """
    by_tenant: dict[str, dict] = {}
    for rack in occupancy_rows or []:
        rack_name = rack.get("rack_name")
        dc = rack.get("dc")
        used = int(rack.get("capacity_u") or 0) - int(rack.get("free_u") or 0)
        for tenant in rack.get("tenants") or []:
            if not tenant or is_internal_tenant(tenant):
                continue
            entry = by_tenant.get(tenant)
            if entry is None:
                alias = alias_by_key.get(tenant.strip().lower()) or {}
                entry = {
                    "tenant": tenant,
                    "crm_accountid": alias.get("crm_accountid"),
                    "crm_account_name": alias.get("crm_account_name"),
                    "match_status": "matched" if alias.get("crm_accountid") else "unmatched",
                    "racks": [],
                    "used_u": 0,
                    "dc": dc,
                }
                by_tenant[tenant] = entry
            if rack_name and rack_name not in entry["racks"]:
                entry["racks"].append(rack_name)
            entry["used_u"] += max(used, 0)
    return sorted(by_tenant.values(), key=lambda e: (-e["used_u"], e["tenant"]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_colocation_matching.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add shared/colocation/matching.py tests/test_colocation_matching.py
git commit -m "feat(colocation): per-customer footprint matching (device tenant -> CRM account)"
```

---

### Task 2: `dc_hosting_u` per-panel sellable compute path

**Files:**
- Modify: `services/customer-api/app/services/sellable_service.py` (add `_query_colocation_totals`; add a branch in `_query_total_allocated`)
- Test: `services/customer-api/tests/test_colocation_sellable_totals.py`

**Interfaces:**
- Consumes: `shared.colocation.occupancy.occupancy_rows`; `self._svc._get_connection()`; `self._dc_pattern(dc_code)`.
- Produces: `_query_colocation_totals(self, src, dc_code) -> tuple[float, float]` = `(Σ capacity_u, Σ used_u)` for the DC pattern.

- [ ] **Step 1: Write the failing test**

```python
# services/customer-api/tests/test_colocation_sellable_totals.py
"""dc_hosting_u total/allocated come from the shared occupancy module, summed
over the DC pattern. total=Σ capacity_u, allocated=Σ used_u."""
from unittest.mock import MagicMock, patch

from app.services.sellable_service import SellableService
from shared.sellable.models import InfraSource


def _service():
    svc = SellableService(
        customer_service=MagicMock(),
        webui=MagicMock(),
        config_service=MagicMock(),
        currency_service=MagicMock(),
        tagging_service=MagicMock(),
    )
    return svc


def test_query_total_allocated_routes_dc_hosting_u_to_colocation():
    svc = _service()
    src = InfraSource(
        panel_key="dc_hosting_u", dc_code="*",
        source_table="__colocation_occupancy__", total_column="capacity_u",
        allocated_table="__colocation_occupancy__", allocated_column="used_u",
    )
    with patch.object(svc, "_query_colocation_totals", return_value=(3616.0, 1817.0)) as q:
        total, alloc = svc._query_total_allocated(src, "DC13")
    q.assert_called_once_with(src, "DC13")
    assert (total, alloc) == (3616.0, 1817.0)


def test_query_colocation_totals_sums_occupancy_rows():
    svc = _service()
    src = InfraSource(panel_key="dc_hosting_u", dc_code="*")
    rows = [
        {"capacity_u": 47, "used_u": 35, "free_u": 12},
        {"capacity_u": 47, "used_u": 20, "free_u": 27},
    ]
    # _get_connection() is a context manager yielding a conn with .cursor()
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = MagicMock()
    svc._svc._get_connection.return_value = conn
    svc._dc_pattern = lambda dc: "%DC13%"
    with patch("app.services.sellable_service.coloc_occ.occupancy_rows", return_value=rows):
        total, alloc = svc._query_colocation_totals(src, "DC13")
    assert total == 94.0     # 47 + 47
    assert alloc == 55.0     # 35 + 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/customer-api && ../../.venv/bin/python -m pytest tests/test_colocation_sellable_totals.py -v`
Expected: FAIL — no `_query_colocation_totals`; `coloc_occ` not importable.

- [ ] **Step 3: Add the import, method, and branch**

Add near the top imports of `sellable_service.py` (with the other `from shared...` imports):

```python
from shared.colocation import occupancy as coloc_occ
```

Add the method to the class (near `_query_netbackup_storage_totals`):

```python
    def _query_colocation_totals(self, src, dc_code: str) -> tuple[float, float]:
        """dc_hosting_u total/allocated from the shared occupancy module.

        total = Σ capacity_u, allocated = Σ used_u over the DC pattern.
        """
        pattern = self._dc_pattern(dc_code)
        # '%' (global default) -> None so occupancy returns all racks.
        dc_pattern = None if pattern in (None, "%", "%%") else pattern
        try:
            with self._svc._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = coloc_occ.occupancy_rows(cur, dc_pattern=dc_pattern)
        except Exception as exc:  # noqa: BLE001
            logger.warning("colocation totals query failed for %s: %s", dc_code, exc)
            return 0.0, 0.0
        total = float(sum(int(r.get("capacity_u") or 0) for r in rows))
        allocated = float(sum(int(r.get("used_u") or 0) for r in rows))
        return total, allocated
```

In `_query_total_allocated`, add the branch immediately after the existing `backup_netbackup_storage` line:

```python
        if src.panel_key == "backup_netbackup_storage":
            return self._query_netbackup_storage_totals(src, dc_code)
        if src.panel_key == "dc_hosting_u":                     # <-- ADD
            return self._query_colocation_totals(src, dc_code)  # <-- ADD
```

(Confirm `logger` is the module logger already used in `sellable_service.py`; it is.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/customer-api && ../../.venv/bin/python -m pytest tests/test_colocation_sellable_totals.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/app/services/sellable_service.py services/customer-api/tests/test_colocation_sellable_totals.py
git commit -m "feat(customer-api): dc_hosting_u sellable compute path via shared occupancy"
```

---

### Task 3: `029` seed — `dc_hosting_u` infra-source row

**Files:**
- Create: `services/customer-api/migrations/webui/029_seed_dc_hosting_u_infra_source.sql`
- Test: `services/customer-api/tests/test_colocation_migration_029.py`

**Interfaces:**
- Produces: a `gui_panel_infra_source` row for `dc_hosting_u` with a sentinel `source_table` so `has_infra_source` becomes true (the actual math is the Task-2 code path, keyed on `panel_key`).

- [ ] **Step 1: Write the failing test**

```python
# services/customer-api/tests/test_colocation_migration_029.py
"""The 029 migration seeds a dc_hosting_u infra-source row with the sentinel
source_table and U units, wrapped in a transaction with ON CONFLICT upsert."""
import os

_MIG = os.path.join(
    os.path.dirname(__file__), "..", "migrations", "webui",
    "029_seed_dc_hosting_u_infra_source.sql",
)


def test_migration_file_exists_and_is_transactional():
    with open(_MIG, encoding="utf-8") as fh:
        sql = fh.read()
    assert "BEGIN;" in sql and "COMMIT;" in sql
    assert "INSERT INTO gui_panel_infra_source" in sql
    assert "'dc_hosting_u'" in sql
    assert "__colocation_occupancy__" in sql          # sentinel source_table
    assert "'capacity_u'" in sql and "'used_u'" in sql
    assert "'U'" in sql                                # units
    assert "ON CONFLICT (panel_key, dc_code) DO UPDATE" in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/customer-api && ../../.venv/bin/python -m pytest tests/test_colocation_migration_029.py -v`
Expected: FAIL — `FileNotFoundError`.

- [ ] **Step 3: Write the migration**

```sql
-- services/customer-api/migrations/webui/029_seed_dc_hosting_u_infra_source.sql
-- Colocation (TASK-62): make dc_hosting_u a computed sellable panel.
-- The occupancy math lives in code (SellableService._query_colocation_totals ->
-- shared/colocation/occupancy.py), keyed on panel_key. This row only needs to
-- make has_infra_source true; source_table is a documented sentinel, never
-- executed as SQL for this panel.
BEGIN;

INSERT INTO gui_panel_infra_source
    (panel_key, dc_code, source_table, total_column, total_unit,
     allocated_table, allocated_column, allocated_unit, filter_clause, notes, updated_by)
VALUES
    ('dc_hosting_u', '*',
        '__colocation_occupancy__', 'capacity_u', 'U',
        '__colocation_occupancy__', 'used_u',    'U',
        NULL,
        'Colocation free-U sellable. Totals computed in code via shared/colocation/occupancy.py (SellableService._query_colocation_totals); source_table is a sentinel, not a real relation.',
        'seed')
ON CONFLICT (panel_key, dc_code) DO UPDATE SET
    source_table     = EXCLUDED.source_table,
    total_column     = EXCLUDED.total_column,
    total_unit       = EXCLUDED.total_unit,
    allocated_table  = EXCLUDED.allocated_table,
    allocated_column = EXCLUDED.allocated_column,
    allocated_unit   = EXCLUDED.allocated_unit,
    filter_clause    = EXCLUDED.filter_clause,
    notes            = COALESCE(NULLIF(EXCLUDED.notes,''), gui_panel_infra_source.notes),
    updated_by       = 'seed',
    updated_at       = NOW();

COMMIT;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/customer-api && ../../.venv/bin/python -m pytest tests/test_colocation_migration_029.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/migrations/webui/029_seed_dc_hosting_u_infra_source.sql services/customer-api/tests/test_colocation_migration_029.py
git commit -m "feat(customer-api): 029 seed dc_hosting_u infra-source row"
```

---

### Task 4: End-to-end sellable result for `dc_hosting_u`

**Files:**
- Test: `services/customer-api/tests/test_colocation_panel_result.py`

**Interfaces:**
- Consumes: `SellableService.compute_panel` (or `compute_all_panels`) with the Task-2 path + a `PanelDefinition` for `dc_hosting_u`.
- Produces: verification that `sellable_raw = max(total*0.80 - allocated, 0)` and the panel is not ratio-bound.

- [ ] **Step 1: Write the test (behavioral, no new source)**

```python
# services/customer-api/tests/test_colocation_panel_result.py
"""dc_hosting_u yields sellable = max(capacity*0.80 - used, 0), unit U, not
ratio-bound (resource_kind='other'). Uses the canned-total fixture pattern."""
from unittest.mock import MagicMock, patch

from app.services.sellable_service import SellableService
from shared.sellable.models import InfraSource, PanelDefinition
from shared.sellable.computation import apply_threshold


def _service():
    return SellableService(
        customer_service=MagicMock(), webui=MagicMock(),
        config_service=MagicMock(), currency_service=MagicMock(), tagging_service=MagicMock(),
    )


def test_dc_hosting_u_sellable_formula():
    svc = _service()
    panel = PanelDefinition(
        panel_key="dc_hosting_u", label="DC Barındırma — U", family="dc_hosting",
        resource_kind="other", display_unit="U",
    )
    infra = InfraSource(
        panel_key="dc_hosting_u", dc_code="*",
        source_table="__colocation_occupancy__", total_column="capacity_u",
        allocated_table="__colocation_occupancy__", allocated_column="used_u",
    )
    svc.list_panel_defs = lambda: [panel]
    svc.list_unit_conversions = lambda: []
    svc.list_ratios = lambda: []
    svc.get_threshold = lambda pk, kind, dc: 80.0
    svc.get_unit_price_tl = lambda pk: (0.0, False)
    svc.get_infra_source = lambda pk, dc="*": infra
    svc._query_total_allocated = lambda src, dc: (3616.0, 1817.0)  # DC13 verified aggregate

    result = {p.panel_key: p for p in svc.compute_all_panels(dc_code="DC13")}["dc_hosting_u"]

    expected = apply_threshold(3616.0, 1817.0, 80.0)  # 3616*0.8 - 1817 = 1075.8
    assert round(result.sellable_raw, 1) == round(expected, 1)
    assert result.sellable_constrained == result.sellable_raw  # not ratio-bound
    assert result.display_unit == "U"
    assert result.has_infra_source is True
```

(If `compute_all_panels`'s stubs need more loaders patched — mirror `_build_service()` in `tests/test_sellable_service.py`. Adjust the stub set until the panel computes.)

- [ ] **Step 2: Run test to verify it fails, then passes**

Run: `cd services/customer-api && ../../.venv/bin/python -m pytest tests/test_colocation_panel_result.py -v`
Expected: initially may need loader-stub adjustments; iterate until PASS (1 passed). This test asserts existing behavior wired end-to-end, so no product code changes beyond Tasks 2-3.

- [ ] **Step 3: Commit**

```bash
git add services/customer-api/tests/test_colocation_panel_result.py
git commit -m "test(customer-api): dc_hosting_u end-to-end sellable formula"
```

---

### Task 5: Colocation matching service + endpoint (for the DC tab)

**Files:**
- Create: `services/customer-api/app/services/colocation_matching_service.py`
- Modify: `services/crm-engine/app/routers/inventory.py` OR create a customer-api router — add `GET /crm/colocation/{dc_code}` returning `{aggregate, customers[]}`
- Test: `services/customer-api/tests/test_colocation_matching_service.py`

**Interfaces:**
- Consumes: `shared.colocation.occupancy.occupancy_rows`, `shared.colocation.matching.build_customer_footprint`; `gui_crm_customer_alias` via webui (`GET_ALL_ALIASES` from `app/db/queries/service_mapping.py`).
- Produces:
  - `ColocationMatchingService.get_colocation(dc_code: str) -> dict` →
    `{"aggregate": {total_u, used_u, free_u, rack_count}, "customers": [footprint...], "racks": [occupancy rows...]}`.
  - `GET /api/v1/crm/colocation/{dc_code}` returning that payload (consumed by Plan C's DC tab).

- [ ] **Step 1: Write the failing test**

```python
# services/customer-api/tests/test_colocation_matching_service.py
"""ColocationMatchingService stitches bulutlake occupancy + webui alias table
into {aggregate, customers, racks}. Alias index is built from GET_ALL_ALIASES
rows keyed by netbox_musteri_value and crm_account_name (lowercased)."""
from unittest.mock import MagicMock, patch

from app.services.colocation_matching_service import ColocationMatchingService


def _rows():
    return [
        {"rack_name": "116", "dc": "DC13", "capacity_u": 47, "used_u": 35, "free_u": 12,
         "tenants": ["Boyner", "Bulutistan - Linux TEAM"]},
        {"rack_name": "209", "dc": "DC13", "capacity_u": 47, "used_u": 27, "free_u": 20,
         "tenants": ["AytemizBank"]},
    ]


def test_get_colocation_assembles_payload():
    customer = MagicMock()
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.return_value = [
        {"crm_accountid": "A-1", "crm_account_name": "Boyner A.Ş.",
         "canonical_customer_key": "boyner", "netbox_musteri_value": "Boyner"},
    ]
    svc = ColocationMatchingService(customer_service=customer, webui=webui)

    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = MagicMock()
    customer._get_connection.return_value = conn

    with patch("app.services.colocation_matching_service.occupancy_rows", return_value=_rows()):
        out = svc.get_colocation("DC13")

    assert out["aggregate"]["total_u"] == 94
    assert out["aggregate"]["free_u"] == 32
    names = {c["tenant"]: c for c in out["customers"]}
    assert names["Boyner"]["crm_accountid"] == "A-1"
    assert names["Boyner"]["match_status"] == "matched"
    assert names["AytemizBank"]["match_status"] == "unmatched"
    assert len(out["racks"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/customer-api && ../../.venv/bin/python -m pytest tests/test_colocation_matching_service.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write the service**

```python
# services/customer-api/app/services/colocation_matching_service.py
"""Assemble the colocation payload for the DC 'Kolokasyon' tab: per-DC U
aggregate + per-customer footprint (device tenant -> CRM account)."""
from __future__ import annotations

import logging

from shared.colocation.occupancy import occupancy_rows, aggregate_by_dc
from shared.colocation.matching import build_customer_footprint
from app.db.queries import service_mapping as sm

logger = logging.getLogger(__name__)


class ColocationMatchingService:
    def __init__(self, customer_service, webui):
        self._svc = customer_service
        self._webui = webui

    def _alias_index(self) -> dict:
        """{lowercased tenant string -> {crm_accountid, crm_account_name}} from
        gui_crm_customer_alias, indexed by netbox_musteri_value AND account name."""
        index: dict = {}
        if self._webui is None or not getattr(self._webui, "is_available", False):
            return index
        try:
            rows = self._webui.run_rows(sm.GET_ALL_ALIASES, ())
        except Exception as exc:  # noqa: BLE001
            logger.warning("alias index load failed: %s", exc)
            return index
        for r in rows or []:
            payload = {
                "crm_accountid": r.get("crm_accountid"),
                "crm_account_name": r.get("crm_account_name"),
            }
            for key in (r.get("netbox_musteri_value"), r.get("crm_account_name"),
                        r.get("canonical_customer_key")):
                if key and str(key).strip():
                    index.setdefault(str(key).strip().lower(), payload)
        return index

    def get_colocation(self, dc_code: str) -> dict:
        pattern = None if not dc_code or dc_code == "*" else f"%{dc_code.strip()}%"
        try:
            with self._svc._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = occupancy_rows(cur, dc_pattern=pattern)
        except Exception as exc:  # noqa: BLE001
            logger.error("colocation occupancy query failed for %s: %s", dc_code, exc)
            rows = []
        agg_by_dc = aggregate_by_dc(rows)
        aggregate = {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0}
        for a in agg_by_dc.values():
            for k in aggregate:
                aggregate[k] += a[k]
        customers = build_customer_footprint(rows, self._alias_index())
        return {"aggregate": aggregate, "customers": customers, "racks": rows}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/customer-api && ../../.venv/bin/python -m pytest tests/test_colocation_matching_service.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Wire the endpoint**

Add a route that constructs `ColocationMatchingService` from the app's existing customer + webui services and returns `get_colocation(dc_code)`. Prefer the customer-api app (it owns both connections). Mirror an existing customer-api router's DI pattern. Route: `@router.get("/crm/colocation/{dc_code}")` → `{"aggregate", "customers", "racks"}`. Add a delegation test in the router's test module (set the service's `get_colocation` to a canned dict, GET `/api/v1/crm/colocation/DC13`, assert the JSON).

- [ ] **Step 6: Run the full customer-api suite**

Run: `cd services/customer-api && ../../.venv/bin/python -m pytest tests/ -v --tb=short`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add services/customer-api/app/services/colocation_matching_service.py services/customer-api/tests/test_colocation_matching_service.py
git add -A services/customer-api services/crm-engine
git commit -m "feat: colocation matching service + /crm/colocation endpoint"
```

---

### Task 6: Optional price seed (flagged) — TL/U

**Files:** none by default (config action).

**Context:** With no `gui_crm_price_override` for `dc_hosting_u`, the panel reports `sellable_u` correctly but `potential_tl = 0` (`has_price=False`). This is acceptable and honest until an admin enters the real TL/U via the existing price-override UI. Do NOT hardcode a fabricated price.

- [ ] **Step 1:** Confirm with the product owner the TL/U figure (or leave unset). If provided, seed it via the existing price-override mechanism (same table the UI writes) — a one-line `gui_crm_price_override` upsert for `panel_key='dc_hosting_u'` — else document that TL stays 0 until configured.

---

## Self-Review

- **Spec coverage:** §6.2 tenant→customer resolver → Tasks 1, 5. §6.2 `dc_hosting_u` sellable wiring → Tasks 2, 3, 4. TL price (§10.2) → Task 6. crm-engine publication is automatic once the panel computes (verified via Task 4 + Task 5 endpoint). ✓
- **Type consistency:** `_query_colocation_totals(src, dc_code) -> (float, float)` used identically in Task 2 branch + test. `build_customer_footprint(rows, alias_by_key)` signature identical across Tasks 1 & 5. `get_colocation(dc_code) -> {aggregate, customers, racks}` consumed by Plan C. ✓
- **Placeholders:** Task 5 Step 5 (endpoint DI) references "an existing router's DI pattern" rather than verbatim code — unavoidable without the specific router chosen; the route shape and payload are fully specified. Task 4/6 depend on confirming stub sets / a business figure. All flagged. ✓
