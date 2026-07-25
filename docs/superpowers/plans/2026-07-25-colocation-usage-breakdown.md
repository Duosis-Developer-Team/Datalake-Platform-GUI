# Colocation Usage Breakdown — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show where a DC's used rack-U goes (External customers / Internal / Untagged) as a stacked bar + tiles in the DC Colocation tab and the Floor Map, with English labels.

**Architecture:** A shared, de-fanned SQL+Python partition (`used_u_breakdown`) classifies each occupied front-face U-slot into exactly one group (priority External > Internal > Untagged) so the three sum to `used_u`. Both service payloads (customer-api `get_colocation.aggregate`, datacenter-api `get_dc_racks_occupancy.summary`) carry the split. One reusable Dash component (`build_colocation_summary`) renders it in both the DC Colocation tab and the Floor Map.

**Tech Stack:** Python 3.11, psycopg2, FastAPI (services), Dash + dash-mantine-components (GUI).

## Global Constraints

- English UI text only for colocation: `Colocation`, `Dedicated Customers`, `Total U` / `Used U` / `Free U` / `Racks`, `External` / `Internal` / `Untagged`, `Used U (own)`, `Device tenant → CRM match`.
- Partition invariant: `external_u + internal_u + untagged_u == used_u` (de-duplicated).
- Reuse the shipped de-fan discipline: dedupe rack by `(rack_name, site_name)`; front-face only (`face_value IN ('front','')`); `COUNT(DISTINCT u)`; cap `u BETWEEN 1 AND capacity_u`. Never reintroduce the rack-table fan-out.
- Internal classification via existing `shared.colocation.occupancy.is_internal_tenant`; blank/NULL tenant = Untagged.
- No new endpoints. No NetBox writes. No globe/global-view changes.
- Run tests with the repo `.venv` (Python 3.11). GUI/shared: `PYTHONPATH=. .venv/bin/python -m pytest <file>`. Services: `cd services/<svc> && PYTHONPATH=<repo-root> ../../.venv/bin/python -m pytest tests/<file>`.
- Repo root: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI`.

## File Structure

- `shared/colocation/occupancy.py` — add `USED_U_BREAKDOWN_SQL`, `_classify_slots`, `used_u_breakdown`.
- `services/customer-api/app/services/colocation_matching_service.py` — merge split into `aggregate`.
- `services/datacenter-api/app/services/dc_service.py` — merge split into `get_dc_racks_occupancy` summary.
- `src/components/colocation_summary.py` — NEW reusable `build_colocation_summary`.
- `src/pages/dc_view.py` — English relabel + use summary in `build_colocation_tab`; tab label.
- `src/pages/floor_map.py` — full-width summary strip in `build_floor_map_layout`.
- Tests: `tests/test_colocation_occupancy.py`, `services/customer-api/tests/test_colocation_matching_service.py`, `services/datacenter-api/tests/test_colocation_occupancy_service.py`, `tests/test_colocation_summary_component.py` (NEW), `tests/test_dc_view_colocation_tab.py`, `tests/test_floor_map_occupancy_fetch.py`.

---

### Task 1: `_classify_slots` — pure slot-priority partition

**Files:**
- Modify: `shared/colocation/occupancy.py` (append after `tenant_occupancy_rows`)
- Test: `tests/test_colocation_occupancy.py`

**Interfaces:**
- Consumes: `is_internal_tenant` (same module).
- Produces: `_classify_slots(rows) -> dict` where `rows` is an iterable of `(rack_name, site_name, u, tenant_name)`; returns `{"external_u":int,"internal_u":int,"untagged_u":int,"external_customer_count":int}`. Each distinct `(rack_name, site_name, u)` slot counts once, classified by the highest-priority tenant on it (external > internal > untagged).

- [ ] **Step 1: Write the failing test**

```python
def test_classify_slots_partitions_by_priority():
    # slot (R,IST,10): external Boyner + internal -> external wins
    # slot (R,IST,11): only internal
    # slot (R,IST,12): blank tenant -> untagged
    rows = [
        ("R", "IST", 10, "Boyner"),
        ("R", "IST", 10, "Bulutistan - Linux TEAM"),
        ("R", "IST", 11, "Bulutistan - Virtualization"),
        ("R", "IST", 12, ""),
        ("R", "IST", 12, None),
        ("R", "IST", 13, "AytemizBank"),
    ]
    out = occ._classify_slots(rows)
    assert out == {
        "external_u": 2,        # slots 10, 13
        "internal_u": 1,        # slot 11
        "untagged_u": 1,        # slot 12
        "external_customer_count": 2,   # Boyner, AytemizBank
    }
    assert out["external_u"] + out["internal_u"] + out["untagged_u"] == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_colocation_occupancy.py::test_classify_slots_partitions_by_priority -v`
Expected: FAIL — `AttributeError: module 'shared.colocation.occupancy' has no attribute '_classify_slots'`

- [ ] **Step 3: Write minimal implementation**

Append to `shared/colocation/occupancy.py`:

```python
def _classify_slots(rows) -> dict:
    """Partition occupied front-face U-slots into external/internal/untagged.

    rows: iterable of (rack_name, site_name, u, tenant_name). Each distinct
    (rack_name, site_name, u) slot is counted once and assigned to the
    highest-priority tenant occupying it: external (2) > internal (1) >
    untagged (0). Returns U counts per group + distinct external tenant count.
    """
    best: dict[tuple, int] = {}
    external_names: set[str] = set()
    for rack_name, site_name, u, tenant in rows:
        key = (rack_name, site_name or "", u)
        t = (tenant or "").strip()
        if not t:
            rank = 0
        elif is_internal_tenant(t):
            rank = 1
        else:
            rank = 2
            external_names.add(t)
        if key not in best or rank > best[key]:
            best[key] = rank
    return {
        "external_u": sum(1 for r in best.values() if r == 2),
        "internal_u": sum(1 for r in best.values() if r == 1),
        "untagged_u": sum(1 for r in best.values() if r == 0),
        "external_customer_count": len(external_names),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_colocation_occupancy.py::test_classify_slots_partitions_by_priority -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shared/colocation/occupancy.py tests/test_colocation_occupancy.py
git commit -m "feat(colocation): _classify_slots priority partition of used-U"
```

---

### Task 2: `USED_U_BREAKDOWN_SQL` + `used_u_breakdown`

**Files:**
- Modify: `shared/colocation/occupancy.py`
- Test: `tests/test_colocation_occupancy.py`

**Interfaces:**
- Consumes: `_classify_slots` (Task 1).
- Produces: `used_u_breakdown(cursor, dc_pattern: str | None = None) -> dict` — executes `USED_U_BREAKDOWN_SQL` (returns `(rack_name, site_name, u, tenant_name)` per occupied front-face slot, DC-filtered + capacity-capped, de-fanned) and returns the `_classify_slots` dict.

- [ ] **Step 1: Write the failing test**

```python
def test_used_u_breakdown_executes_and_classifies():
    cur = _FakeCursor([
        ("102", "IST", 10, "Boyner"),
        ("102", "IST", 11, "Bulutistan - Linux TEAM"),
        ("102", "IST", 12, None),
    ])
    out = occ.used_u_breakdown(cur, dc_pattern="%DC13%")
    assert cur.executed[1] == {"dc_pattern": "%DC13%"}
    assert out == {"external_u": 1, "internal_u": 1, "untagged_u": 1, "external_customer_count": 1}


def test_used_u_breakdown_sql_is_defanned_and_current_tables():
    sql = occ.USED_U_BREAKDOWN_SQL.lower()
    assert "discovery_netbox_inventory_device" in sql
    assert "loki_device_types" in sql
    assert "discovery_loki_rack" in sql
    assert "in ('front', '')" in sql
    assert "s.u between 1 and rc.capacity_u" in sql
    # de-fan: rack side collapsed to one row per (name, site) before the join
    assert "max(capacity_u)" in sql
    assert "group by rack_name, site_name" in sql
    assert "loki_devices" not in sql
    assert "discovery_loki_racks" not in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_colocation_occupancy.py::test_used_u_breakdown_executes_and_classifies tests/test_colocation_occupancy.py::test_used_u_breakdown_sql_is_defanned_and_current_tables -v`
Expected: FAIL — `AttributeError: ... has no attribute 'USED_U_BREAKDOWN_SQL'` / `used_u_breakdown`

- [ ] **Step 3: Write minimal implementation**

Append to `shared/colocation/occupancy.py`:

```python
# Per-slot classification source: one row per occupied front-face U-slot
# (rack_name, site_name, u, tenant_name), DC-filtered + capacity-capped. Joins
# to a de-duplicated rack (one row per name+site) so the non-unique rack table
# cannot fan out a device's U. Fed to _classify_slots (external>internal>untagged).
USED_U_BREAKDOWN_SQL = """
WITH dev_slots AS (
    SELECT d.rack_name,
           d.site_name,
           generate_series(
               floor(d.position)::int,
               floor(d.position)::int
                   + GREATEST(COALESCE(NULLIF(dt.u_height, 0), 1), 1)::int - 1
           ) AS u,
           d.tenant_name
    FROM discovery_netbox_inventory_device d
    JOIN loki_device_types dt ON dt.id = d.device_type_id
    WHERE d.position IS NOT NULL
      AND lower(coalesce(d.face_value, 'front')) IN ('front', '')
),
rack_cap AS (
    SELECT rack_name,
           site_name,
           MAX(capacity_u) AS capacity_u,
           MIN(dc)         AS dc
    FROM (
        SELECT r.name          AS rack_name,
               l.site_name     AS site_name,
               r.u_height::int AS capacity_u,
               COALESCE(l.parent_name, l.name) AS dc
        FROM discovery_loki_rack r
        LEFT JOIN discovery_loki_location l ON l.id::varchar = r.location_id
    ) x
    GROUP BY rack_name, site_name
)
SELECT s.rack_name, s.site_name, s.u, s.tenant_name
FROM dev_slots s
JOIN rack_cap rc
    ON rc.rack_name = s.rack_name
   AND COALESCE(rc.site_name, '') = COALESCE(s.site_name, '')
WHERE (%(dc_pattern)s IS NULL OR COALESCE(rc.dc, '') ILIKE %(dc_pattern)s)
  AND s.u BETWEEN 1 AND rc.capacity_u
"""


def used_u_breakdown(cursor, dc_pattern: str | None = None) -> dict:
    """Execute USED_U_BREAKDOWN_SQL and return the external/internal/untagged
    used-U split (sums to the de-duplicated used_u) + external customer count."""
    cursor.execute(USED_U_BREAKDOWN_SQL, {"dc_pattern": dc_pattern})
    return _classify_slots(cursor.fetchall() or [])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_colocation_occupancy.py -k "used_u_breakdown" -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add shared/colocation/occupancy.py tests/test_colocation_occupancy.py
git commit -m "feat(colocation): used_u_breakdown de-fanned SQL + fetch"
```

---

### Task 3: customer-api — merge split into `get_colocation.aggregate`

**Files:**
- Modify: `services/customer-api/app/services/colocation_matching_service.py`
- Test: `services/customer-api/tests/test_colocation_matching_service.py`

**Interfaces:**
- Consumes: `used_u_breakdown` (Task 2).
- Produces: `get_colocation(dc_code)["aggregate"]` gains `external_u`, `internal_u`, `untagged_u`, `external_customer_count`.

- [ ] **Step 1: Write the failing test** (add to the existing test file)

```python
def test_get_colocation_aggregate_includes_used_u_breakdown():
    customer = MagicMock()
    webui = MagicMock(); webui.is_available = False
    svc = ColocationMatchingService(customer_service=customer, webui=webui)
    conn = MagicMock(); conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = MagicMock()
    customer._get_connection.return_value = conn
    with patch("app.services.colocation_matching_service.occupancy_rows", return_value=_rows()), \
         patch("app.services.colocation_matching_service.tenant_occupancy_rows", return_value=_tenant_rows()), \
         patch("app.services.colocation_matching_service.used_u_breakdown",
               return_value={"external_u": 149, "internal_u": 481, "untagged_u": 648, "external_customer_count": 5}):
        out = svc.get_colocation("DC13")
    agg = out["aggregate"]
    assert agg["external_u"] == 149
    assert agg["internal_u"] == 481
    assert agg["untagged_u"] == 648
    assert agg["external_customer_count"] == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/customer-api && PYTHONPATH=/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI ../../.venv/bin/python -m pytest tests/test_colocation_matching_service.py::test_get_colocation_aggregate_includes_used_u_breakdown -v`
Expected: FAIL — `ImportError`/`AttributeError` on `used_u_breakdown` patch target, or missing keys.

- [ ] **Step 3: Write minimal implementation**

In the import block, add `used_u_breakdown`:

```python
from shared.colocation.occupancy import (
    occupancy_rows,
    aggregate_by_dc,
    tenant_occupancy_rows,
    used_u_breakdown,
)
```

In `get_colocation`, fetch the breakdown inside the connection block and merge it into `aggregate`:

```python
        rows: list = []
        tenant_rows: list = []
        breakdown: dict = {}
        try:
            with self._svc._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = occupancy_rows(cur, dc_pattern=pattern)
                    tenant_rows = tenant_occupancy_rows(cur, dc_pattern=pattern)
                    breakdown = used_u_breakdown(cur, dc_pattern=pattern)
        except Exception as exc:  # noqa: BLE001
            logger.error("colocation occupancy query failed for %s: %s", dc_code, exc)
            rows = []
            tenant_rows = []
            breakdown = {}
        agg_by_dc = aggregate_by_dc(rows)
        aggregate = {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0}
        for a in agg_by_dc.values():
            for k in aggregate:
                aggregate[k] += a[k]
        aggregate.update({
            "external_u": int(breakdown.get("external_u") or 0),
            "internal_u": int(breakdown.get("internal_u") or 0),
            "untagged_u": int(breakdown.get("untagged_u") or 0),
            "external_customer_count": int(breakdown.get("external_customer_count") or 0),
        })
        customers = build_customer_footprint(tenant_rows, self._alias_index())
        return {"aggregate": aggregate, "customers": customers, "racks": rows}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/customer-api && PYTHONPATH=/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI ../../.venv/bin/python -m pytest tests/test_colocation_matching_service.py -v`
Expected: PASS (all tests in file)

- [ ] **Step 5: Commit**

```bash
git add services/customer-api/app/services/colocation_matching_service.py services/customer-api/tests/test_colocation_matching_service.py
git commit -m "feat(colocation): customer-api aggregate carries used-U split"
```

---

### Task 4: datacenter-api — merge split into `get_dc_racks_occupancy.summary`

**Files:**
- Modify: `services/datacenter-api/app/services/dc_service.py` (`get_dc_racks_occupancy`, ~7546-7562)
- Test: `services/datacenter-api/tests/test_colocation_occupancy_service.py`

**Interfaces:**
- Consumes: `coloc_occ.used_u_breakdown` (Task 2).
- Produces: `get_dc_racks_occupancy(dc)["summary"]` gains `external_u`, `internal_u`, `untagged_u`, `external_customer_count`.

- [ ] **Step 1: Write the failing test** (add to that test file; follow its existing mocking style)

```python
def test_dc_racks_occupancy_summary_includes_used_u_breakdown(monkeypatch):
    from app.services import dc_service as m
    svc = m.DatabaseService.__new__(m.DatabaseService)
    # bypass cache: call the inner fetch via monkeypatched occupancy + breakdown
    monkeypatch.setattr(m.coloc_occ, "occupancy_rows", lambda cur, dc_pattern=None: [
        {"dc": "DC13", "capacity_u": 47, "used_u": 30, "free_u": 17},
    ])
    monkeypatch.setattr(m.coloc_occ, "aggregate_by_dc", lambda rows: {"DC13": {"total_u": 47, "used_u": 30, "free_u": 17, "rack_count": 1}})
    monkeypatch.setattr(m.coloc_occ, "used_u_breakdown", lambda cur, dc_pattern=None: {"external_u": 12, "internal_u": 10, "untagged_u": 8, "external_customer_count": 3})

    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return _Cur()
    monkeypatch.setattr(svc, "_get_connection", lambda: _Conn())
    # no cache hit
    monkeypatch.setattr(m.cache, "get", lambda k: None)
    monkeypatch.setattr(m.cache, "run_singleflight", lambda key, fn, ttl=None: fn())

    out = svc.get_dc_racks_occupancy("DC13")
    s = out["summary"]
    assert s["external_u"] == 12 and s["internal_u"] == 10 and s["untagged_u"] == 8
    assert s["external_customer_count"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/datacenter-api && PYTHONPATH=/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI ../../.venv/bin/python -m pytest tests/test_colocation_occupancy_service.py::test_dc_racks_occupancy_summary_includes_used_u_breakdown -v`
Expected: FAIL — summary missing the four keys.

- [ ] **Step 3: Write minimal implementation**

In `get_dc_racks_occupancy._fetch`, after building `total`, add the breakdown:

```python
        def _fetch():
            pattern = f"%{code}%"
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = coloc_occ.occupancy_rows(cur, dc_pattern=pattern)
                    breakdown = coloc_occ.used_u_breakdown(cur, dc_pattern=pattern)
            agg = coloc_occ.aggregate_by_dc(rows)
            total = {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0}
            for dc_agg in agg.values():
                for k in total:
                    total[k] += dc_agg[k]
            total.update({
                "external_u": int(breakdown.get("external_u") or 0),
                "internal_u": int(breakdown.get("internal_u") or 0),
                "untagged_u": int(breakdown.get("untagged_u") or 0),
                "external_customer_count": int(breakdown.get("external_customer_count") or 0),
            })
            return {"racks": rows, "summary": total}
```

Also update the `empty` summary at the top of the method to include the four keys as 0:

```python
        empty = {"racks": [], "summary": {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0,
                                          "external_u": 0, "internal_u": 0, "untagged_u": 0,
                                          "external_customer_count": 0}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/datacenter-api && PYTHONPATH=/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI ../../.venv/bin/python -m pytest tests/test_colocation_occupancy_service.py -v`
Expected: PASS (all tests in file)

- [ ] **Step 5: Commit**

```bash
git add services/datacenter-api/app/services/dc_service.py services/datacenter-api/tests/test_colocation_occupancy_service.py
git commit -m "feat(colocation): datacenter-api rack-occupancy summary carries used-U split"
```

---

### Task 5: `build_colocation_summary` reusable component

**Files:**
- Create: `src/components/colocation_summary.py`
- Test: `tests/test_colocation_summary_component.py`

**Interfaces:**
- Produces: `build_colocation_summary(aggregate: dict, customer_count: int | None = None) -> dash component`. Reads `total_u/used_u/free_u/rack_count/external_u/internal_u/untagged_u/external_customer_count` (all optional). If `customer_count` is given it overrides `aggregate["external_customer_count"]`.

- [ ] **Step 1: Write the failing test**

```python
from src.components.colocation_summary import build_colocation_summary


def test_summary_renders_tiles_bar_and_split_labels():
    agg = {"total_u": 1000, "used_u": 600, "free_u": 400, "rack_count": 10,
           "external_u": 149, "internal_u": 300, "untagged_u": 151,
           "external_customer_count": 5}
    text = str(build_colocation_summary(agg))
    assert "Total U" in text and "600" in text and "Racks" in text
    assert "External 149U (5 customers)" in text
    assert "Internal 300U" in text
    assert "Untagged 151U" in text


def test_summary_hides_bar_when_split_absent():
    text = str(build_colocation_summary({"total_u": 5, "used_u": 0, "free_u": 5, "rack_count": 1}))
    assert "Total U" in text            # tiles still render
    assert "where it goes" not in text  # no bar when split is all zero
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_colocation_summary_component.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.components.colocation_summary'`

- [ ] **Step 3: Write minimal implementation**

Create `src/components/colocation_summary.py`:

```python
"""Reusable colocation usage summary: KPI tiles + a 100% stacked bar showing
where a DC's used rack-U goes (External / Internal / Untagged). Used by the DC
Colocation tab and the Floor Map. English labels only."""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import html

_EXT_COLOR = "#F79009"  # orange — external customers
_INT_COLOR = "#528BFF"  # blue — Bulutistan internal
_UNT_COLOR = "#D0D5DD"  # grey — untagged / unattributable


def _tile(label: str, value: str):
    return dmc.Paper(radius="lg", p="md", withBorder=True, children=[
        dmc.Text(label, size="xs", c="#667085", fw=600),
        dmc.Text(value, size="xl", fw=800, c="#101828"),
    ])


def _swatch_label(color: str, text: str):
    return dmc.Group(gap=6, align="center", children=[
        html.Span(style={"width": "10px", "height": "10px", "borderRadius": "3px",
                         "background": color, "display": "inline-block"}),
        dmc.Text(text, size="xs", c="#475467"),
    ])


def build_colocation_summary(aggregate: dict, customer_count: int | None = None):
    agg = aggregate or {}
    total_u = int(agg.get("total_u") or 0)
    used_u = int(agg.get("used_u") or 0)
    free_u = int(agg.get("free_u") or 0)
    racks = int(agg.get("rack_count") or 0)
    ext = int(agg.get("external_u") or 0)
    intn = int(agg.get("internal_u") or 0)
    unt = int(agg.get("untagged_u") or 0)
    ncust = int(customer_count if customer_count is not None
                else (agg.get("external_customer_count") or 0))
    base = ext + intn + unt

    tiles = dmc.SimpleGrid(cols=4, spacing="md", children=[
        _tile("Total U", f"{total_u:,}"),
        _tile("Used U", f"{used_u:,}"),
        _tile("Free U", f"{free_u:,}"),
        _tile("Racks", f"{racks:,}"),
    ])

    children = [tiles]
    if base > 0:
        segments = []
        for u, color in ((ext, _EXT_COLOR), (intn, _INT_COLOR), (unt, _UNT_COLOR)):
            if u > 0:
                segments.append(html.Div(style={
                    "width": f"{u / base * 100:.2f}%", "background": color, "height": "100%",
                }))
        bar = html.Div(style={
            "display": "flex", "width": "100%", "height": "14px",
            "borderRadius": "7px", "overflow": "hidden", "background": "#F2F4F7",
        }, children=segments)
        labels = dmc.Group(gap="lg", mt="xs", children=[
            _swatch_label(_EXT_COLOR, f"External {ext:,}U ({ncust} customers)"),
            _swatch_label(_INT_COLOR, f"Internal {intn:,}U"),
            _swatch_label(_UNT_COLOR, f"Untagged {unt:,}U"),
        ])
        children += [
            dmc.Text("Used U — where it goes", size="xs", c="#667085", fw=600, mt="md"),
            bar,
            labels,
        ]

    return dmc.Stack(gap="xs", children=children)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_colocation_summary_component.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/components/colocation_summary.py tests/test_colocation_summary_component.py
git commit -m "feat(colocation): build_colocation_summary component (tiles + split bar)"
```

---

### Task 6: DC View Colocation tab — English relabel + summary

**Files:**
- Modify: `src/pages/dc_view.py` (`build_colocation_tab` ~2536-2585; tab label ~5891)
- Test: `tests/test_dc_view_colocation_tab.py`

**Interfaces:**
- Consumes: `build_colocation_summary` (Task 5).

- [ ] **Step 1: Write the failing test** (add to existing file)

```python
def test_colocation_tab_english_labels_and_summary():
    payload = {
        "aggregate": {"total_u": 1000, "used_u": 600, "free_u": 400, "rack_count": 10,
                      "external_u": 149, "internal_u": 300, "untagged_u": 151,
                      "external_customer_count": 1},
        "customers": [
            {"tenant": "AytemizBank", "crm_account_name": "Aytemiz", "match_status": "matched",
             "racks": ["209"], "used_u": 29, "crm_accountid": "A-1"},
        ],
        "racks": [],
    }
    text = str(build_colocation_tab(payload))
    assert "Dedicated Customers" in text
    assert "Used U (own)" in text
    assert "CRM Account" in text
    assert "Kolokasyon" not in text and "Müşteri" not in text and "Dedike" not in text
    assert "External 149U" in text        # summary component embedded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_dc_view_colocation_tab.py::test_colocation_tab_english_labels_and_summary -v`
Expected: FAIL — Turkish labels still present / summary absent.

- [ ] **Step 3: Write minimal implementation**

At the top of `src/pages/dc_view.py`, add the import (near other component imports):

```python
from src.components.colocation_summary import build_colocation_summary
```

Replace the body of `build_colocation_tab` KPI block + table so it uses the summary and English labels. The function becomes:

```python
def build_colocation_tab(coloc: dict):
    """Colocation tab: DC used-U breakdown summary + dedicated-customer footprint."""
    agg = (coloc or {}).get("aggregate", {}) or {}
    customers = (coloc or {}).get("customers", []) or []

    summary = build_colocation_summary(agg)

    if customers:
        header = html.Tr(children=[html.Th(h) for h in
                                   ("Customer", "CRM Account", "Match", "Rack", "Used U (own)")])
        body = []
        for c in customers:
            badge_color = "green" if c.get("match_status") == "matched" else "orange"
            body.append(html.Tr(children=[
                html.Td(c.get("tenant", "")),
                html.Td(c.get("crm_account_name") or "—"),
                html.Td(dmc.Badge(c.get("match_status", ""), color=badge_color, variant="light", size="sm")),
                html.Td(", ".join(c.get("racks", []) or [])),
                html.Td(f"{int(c.get('used_u') or 0):,}"),
            ]))
        table = dmc.Table(children=[html.Thead(header), html.Tbody(body)],
                          striped=True, highlightOnHover=True)
    else:
        table = dmc.Text("No dedicated (external customer) colocation devices found in this DC.",
                         size="sm", c="#98A2B3")

    return dmc.Stack(gap="lg", children=[
        html.Div(className="nexus-card", style={"padding": "20px"}, children=[
            _section_title("Colocation", "Rack U occupancy and dedicated customers"),
            summary,
        ]),
        html.Div(className="nexus-card", style={"padding": "20px"}, children=[
            _section_title("Dedicated Customers", "Device tenant → CRM match"),
            html.Div(style={"overflowX": "auto"}, children=table),
        ]),
    ])
```

Change the tab label (search for `dmc.TabsTab("Kolokasyon"`):

```python
        dmc.TabsTab("Colocation", value="colo") if _sec("sec:dc_view:colocation") else None,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_dc_view_colocation_tab.py -v`
Expected: PASS (all tests; the existing `test_build_colocation_tab_renders_kpis_and_customers` still passes — it only checks free-U value and the customer name, both still present via the summary/table).

- [ ] **Step 5: Commit**

```bash
git add src/pages/dc_view.py tests/test_dc_view_colocation_tab.py
git commit -m "feat(colocation): DC tab uses summary component + English labels"
```

---

### Task 7: Floor Map — full-width colocation summary strip

**Files:**
- Modify: `src/pages/floor_map.py` (`build_floor_map_layout` ~557; imports)
- Test: `tests/test_floor_map_occupancy_fetch.py`

**Interfaces:**
- Consumes: `build_colocation_summary` (Task 5); `api.get_dc_racks_occupancy` (existing).

- [ ] **Step 1: Write the failing test** (add to existing file)

```python
def test_floor_map_layout_has_colocation_summary_strip(monkeypatch):
    from src.pages import floor_map as fm
    monkeypatch.setattr(fm.api, "get_dc_racks_occupancy", lambda dc: {
        "racks": [],
        "summary": {"total_u": 100, "used_u": 60, "free_u": 40, "rack_count": 3,
                    "external_u": 20, "internal_u": 25, "untagged_u": 15,
                    "external_customer_count": 2},
    })
    layout = fm.build_floor_map_layout("DC13", "DC13", racks=[])
    text = str(layout)
    assert "External 20U (2 customers)" in text
    assert "Used U" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_floor_map_occupancy_fetch.py::test_floor_map_layout_has_colocation_summary_strip -v`
Expected: FAIL — strip absent.

- [ ] **Step 3: Write minimal implementation**

Add import near the top of `src/pages/floor_map.py`:

```python
from src.components.colocation_summary import build_colocation_summary
```

In `build_floor_map_layout`, after `fig = build_floor_map_figure(...)`, fetch the summary defensively:

```python
    try:
        _coloc = (api.get_dc_racks_occupancy(dc_id) or {}).get("summary") or {}
    except Exception:  # noqa: BLE001
        _coloc = {}
    coloc_strip = build_colocation_summary(_coloc)
```

Then insert the strip into the returned `html.Div(...children=[...])`, immediately after the header `html.Div(className="floor-map-header", ...)` block and before the `dmc.Grid(...)` body — as a full-width card:

```python
            # ── Colocation summary (full-width strip)
            html.Div(className="nexus-card", style={"padding": "16px", "marginTop": "12px"},
                     children=[coloc_strip]),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_floor_map_occupancy_fetch.py -v`
Expected: PASS (all tests in file)

- [ ] **Step 5: Commit**

```bash
git add src/pages/floor_map.py tests/test_floor_map_occupancy_fetch.py
git commit -m "feat(colocation): floor map full-width colocation summary strip"
```

---

### Task 8: Full-suite regression + live verify + rebuild

**Files:** none (verification)

- [ ] **Step 1: Run all colocation-touching tests**

```bash
cd /Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI
PYTHONPATH=. .venv/bin/python -m pytest tests/test_colocation_occupancy.py tests/test_colocation_matching.py tests/test_colocation_summary_component.py tests/test_dc_view_colocation_tab.py tests/test_floor_map_occupancy_fetch.py tests/test_globe_colocation_ring.py -q
cd services/customer-api && PYTHONPATH=/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI ../../.venv/bin/python -m pytest tests/ -k "coloc" -q; cd ../..
cd services/datacenter-api && PYTHONPATH=/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI ../../.venv/bin/python -m pytest tests/ -k "coloc or occupancy" -q; cd ../..
```
Expected: all PASS.

- [ ] **Step 2: Live-verify the partition sums to used_u** (against bulutlake via hmdl-api container)

Confirm `external_u + internal_u + untagged_u == used_u` for DC13 through the customer-api endpoint after rebuild (Step 3).

- [ ] **Step 3: Rebuild + recreate affected services, warm caches**

```bash
docker compose --profile microservice up -d --build datacenter-api customer-api app
# clear stale colocation/summary caches, then WARM out-of-band to avoid GUI 45s cold-timeout:
docker exec bulutistan-redis redis-cli --scan --pattern 'colocation_aggregate:*' | xargs -r docker exec -i bulutistan-redis redis-cli DEL
docker exec bulutistan-redis redis-cli --scan --pattern 'dc_racks_occupancy:*' | xargs -r docker exec -i bulutistan-redis redis-cli DEL
docker exec bulutistan-redis redis-cli --scan --pattern 'all_dc_summary:*' | xargs -r docker exec -i bulutistan-redis redis-cli DEL
docker exec bulutistan-redis redis-cli --scan --pattern 'global_dashboard:*' | xargs -r docker exec -i bulutistan-redis redis-cli DEL
curl -s -o /dev/null -w "summary %{http_code} %{time_total}s\n" --max-time 240 "http://localhost:8000/api/v1/datacenters/summary?preset=7d"
curl -s -o /dev/null -w "overview %{http_code} %{time_total}s\n" --max-time 240 "http://localhost:8000/api/v1/dashboard/overview?preset=7d"
```

- [ ] **Step 4: Browser check** — DC13 Colocation tab (bar + tiles + English table) and Floor Map (full-width strip). Hand to user for visual confirmation.

- [ ] **Step 5: Commit** (nothing to commit if all prior tasks committed; otherwise finalize).
