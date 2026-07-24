# Colocation Plan C — Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface colocation U in both views — a per-DC free/used-U ring on the Globe, a new DC "Kolokasyon" tab (KPIs + per-customer footprint), corrected real-U occupancy on the floor map, and customer badges on the rack detail — consuming Plan A's endpoints and Plan B's `/crm/colocation`.

**Architecture:** Dash (dash-mantine-components 0.14.1 + Plotly). New `api_client` functions call Plan A/B endpoints. The floor map switches from per-rack device-count occupancy to the bulk occupancy endpoint (correct real-U). The Globe gains a 4th RingProgress in `build_dc_info_card` from the `coloc_*` summary fields Plan A added. A new lazy `"colo"` DC tab renders KPIs + a customers table.

**Tech Stack:** Python 3.11, Dash ≥2.16.1, dash-mantine-components==0.14.1, dash-iconify, Plotly. Depends on **Plan A** (endpoints, `coloc_*` summary fields) and **Plan B** (`/crm/colocation`).

## Global Constraints

- **Working directory is the worktree** `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.claude/worktrees/task-62-colocation-viz`. Do all work and commits here; never cd to the main checkout. (Subagents default to the MAIN checkout — always use absolute paths.)
- Python interpreter/tests: `.venv/bin/python` (symlink to the main venv, Python 3.11.15). GUI tests run from the **worktree root**: `.venv/bin/python -m pytest tests/<file> -v -p no:cacheprovider`.
- **Do NOT run the whole `tests/` suite** — it takes >10 minutes and aborts on pre-existing collection errors. Run only the specific test files you create/touch, plus the named regression files each task lists.
- **Pre-existing breakage (NOT yours — do not fix, do not chase):**
  - Collection errors abort a full-suite run: `tests/test_backup_sidebar_helpers.py` (`KeyError: '_compute_backup_tr'`) and `tests/test_zabbix_query_deduplication.py`.
  - `tests/test_dc_view_visibility.py` — **9 failures** from a stale test double (`AttributeError: 'FakeApi' object has no attribute 'get_dc_zerto_license'` at `src/pages/dc_view.py:5277`). This file is in Plan C's blast radius (Task 4 edits `dc_view.py`) but it fails BEFORE any change. Baseline for the targeted set = **60 passed / 9 failed**.
- **Plan A + B are DONE and available:**
  - `shared/colocation/occupancy.py`: `occupancy_rows`, `aggregate_by_dc`, `is_internal_tenant`; per-rack keys `rack_id, rack_name, dc, hall, capacity_u, used_u, free_u, tenants[]`.
  - `shared/colocation/matching.py`: `build_customer_footprint`.
  - datacenter-api: `GET /api/v1/datacenters/{dc_code}/racks/occupancy` → `{racks:[…], summary:{total_u,used_u,free_u,rack_count}}`; DC summaries now carry `coloc_total_u/coloc_used_u/coloc_free_u`.
  - customer-api: `GET /api/v1/crm/colocation/{dc_code}` → `{aggregate:{…}, customers:[…], racks:[…]}` — use the **`_get_client_cust()`** accessor in `api_client.py`.
- GUI test import convention: `from src.pages import X`; patch api at its usage module (e.g. `patch("src.services.api_client.get_rack_devices")`, or `patch.multiple("src.pages.dc_view.api", ...)`).
- dmc version is **0.14.1** — use only props valid there (the verbatim snippets below are known-good).
- Colocation ring color thresholds: reuse floor-map fill semantics — free-heavy = green (sellable), full = red. Use a **fill %** (used/total), coloring like `_pct_color` (≥80 red, ≥50 orange, else teal).
- Adding the `"colo"` lazy tab requires **four coordinated edits** (Task 4) — a missing one silently breaks tab loading.
- Floor map must keep its two-phase render (fast status paint → recolor). Only the occupancy source changes (device-count → bulk endpoint real-U).

---

### Task 1: api_client — occupancy + colocation clients

**Files:**
- Modify: `src/services/api_client.py` (add two functions near `get_dc_racks` ~1872)
- Test: `tests/test_api_client_colocation.py`

**Interfaces:**
- Consumes: `_get_client_dc`, `_get_json`, `_api_cache_get_with_stale`, `quote`.
- Produces:
  - `get_dc_racks_occupancy(dc_code: str) -> dict` → `{"racks":[...], "summary":{...}}` from `/api/v1/datacenters/{dc}/racks/occupancy`.
  - `get_colocation(dc_code: str) -> dict` → `{"aggregate":{...}, "customers":[...], "racks":[...]}` from `/api/v1/crm/colocation/{dc}` (Plan B; via the crm/customer client).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_client_colocation.py
"""api_client colocation clients call the right endpoints and cache via SWR."""
from unittest.mock import patch

from src.services import api_client as api
from src.services import cache_service


def test_get_dc_racks_occupancy_calls_endpoint():
    cache_service.clear()
    payload = {"racks": [{"rack_name": "116"}], "summary": {"free_u": 12}}
    with patch("src.services.api_client._get_json", return_value=payload) as gj:
        out = api.get_dc_racks_occupancy("DC13")
    assert out == payload
    called_path = gj.call_args[0][1]
    assert called_path == "/api/v1/datacenters/DC13/racks/occupancy"


def test_get_dc_racks_occupancy_empty_on_bad_shape():
    cache_service.clear()
    with patch("src.services.api_client._get_json", return_value="oops"):
        out = api.get_dc_racks_occupancy("DC13")
    assert out == {"racks": [], "summary": {}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_api_client_colocation.py -v`
Expected: FAIL — `AttributeError: module 'src.services.api_client' has no attribute 'get_dc_racks_occupancy'`.

- [ ] **Step 3: Add the client functions**

Add to `api_client.py` after `get_rack_devices` (~line 1894), mirroring the verbatim `get_dc_racks` pattern:

```python
def get_dc_racks_occupancy(dc_code: str) -> dict:
    enc = quote(dc_code, safe="")
    empty = {"racks": [], "summary": {}}
    ck = f"api:dc_racks_occupancy:{enc}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/racks/occupancy")
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_colocation(dc_code: str) -> dict:
    enc = quote(dc_code, safe="")
    empty = {"aggregate": {}, "customers": [], "racks": []}
    ck = f"api:colocation:{enc}"

    def fetch() -> dict:
        data = _get_json(_get_client_cust(), f"/api/v1/crm/colocation/{enc}")
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)
```

**VERIFIED (Plan B outcome):** the endpoint is hosted by **customer-api** at `/api/v1/crm/colocation/{dc_code}`, so the client accessor is **`_get_client_cust()`** (the same one `get_netbox_viz_exclusions` uses at `api_client.py:2587`) — NOT `_get_client_crm()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_api_client_colocation.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/services/api_client.py tests/test_api_client_colocation.py
git commit -m "feat(gui): api_client colocation occupancy + matching clients"
```

---

### Task 2: Floor map — correct real-U occupancy via bulk endpoint

**Files:**
- Modify: `src/pages/floor_map.py` (`_fetch_rack_occupancy` ~132; add tenant to hover)
- Test: `tests/test_floor_map_occupancy_endpoint.py`

**Interfaces:**
- Consumes: `api.get_dc_racks_occupancy` (Task 1).
- Produces: `_fetch_rack_occupancy(dc_id, racks)` returns `{rack_name -> occupied_u}` where `occupied_u` is the **real used-U** from the bulk endpoint (one call, not N device-count calls). Racks absent from the response are omitted (rendered gray/unknown), preserving current behavior.

**Rationale:** Today `_fetch_rack_occupancy` fans out `get_rack_devices` per rack and counts devices (1-U each — wrong for multi-U gear, and reads the stale `loki_devices`). The bulk endpoint returns correct real-U from the current tables in one call.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_floor_map_occupancy_endpoint.py
"""Floor map occupancy now comes from the bulk /racks/occupancy endpoint (real
used-U), one call, instead of per-rack device-count fan-out."""
from unittest.mock import patch

from src.pages import floor_map as fm


def test_fetch_rack_occupancy_uses_bulk_endpoint():
    racks = [{"name": "116"}, {"name": "209"}]
    bulk = {"racks": [
        {"rack_name": "116", "used_u": 35, "capacity_u": 47, "free_u": 12},
        {"rack_name": "209", "used_u": 27, "capacity_u": 47, "free_u": 20},
    ], "summary": {}}
    with patch("src.services.api_client.get_dc_racks_occupancy", return_value=bulk) as m:
        occ = fm._fetch_rack_occupancy("DC13", racks)
    m.assert_called_once_with("DC13")
    assert occ["116"] == 35
    assert occ["209"] == 27


def test_fetch_rack_occupancy_omits_missing_racks():
    racks = [{"name": "116"}, {"name": "999"}]
    bulk = {"racks": [{"rack_name": "116", "used_u": 35, "capacity_u": 47}], "summary": {}}
    with patch("src.services.api_client.get_dc_racks_occupancy", return_value=bulk):
        occ = fm._fetch_rack_occupancy("DC13", racks)
    assert occ["116"] == 35
    assert "999" not in occ  # unknown -> rendered gray


def test_fetch_rack_occupancy_empty_on_backend_failure():
    with patch("src.services.api_client.get_dc_racks_occupancy", return_value={"racks": [], "summary": {}}):
        occ = fm._fetch_rack_occupancy("DC13", [{"name": "116"}])
    assert occ == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_floor_map_occupancy_endpoint.py -v`
Expected: FAIL — current `_fetch_rack_occupancy` calls `get_rack_devices`, not `get_dc_racks_occupancy`.

- [ ] **Step 3: Rewrite `_fetch_rack_occupancy`**

Replace the body (lines ~132-154) with:

```python
def _fetch_rack_occupancy(dc_id, racks):
    """{rack_name -> occupied_u} for the given racks, from the bulk colocation
    occupancy endpoint (real used-U via the shared canonical SQL). One call
    instead of N. Racks absent from the response are omitted -> rendered gray."""
    from src.services import api_client as api

    wanted = {str(r.get("name") or "").strip() for r in racks if str(r.get("name") or "").strip()}
    if not wanted:
        return {}
    payload = api.get_dc_racks_occupancy(dc_id or "") or {}
    occupancy: dict = {}
    for row in payload.get("racks", []) or []:
        name = str(row.get("rack_name") or "").strip()
        if name in wanted and row.get("used_u") is not None:
            occupancy[name] = int(row.get("used_u") or 0)
    return occupancy
```

The `ThreadPoolExecutor` import at line 16 may become unused here — leave it if other functions use it; otherwise remove. Verify the existing floor-map fill tests (`tests/test_floor_map_figure_fill.py`, `tests/test_floor_map_recolor.py`) still pass — they feed `occupancy` directly to `build_floor_map_figure` and are unaffected by this fetch change.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_floor_map_occupancy_endpoint.py tests/test_floor_map_figure_fill.py tests/test_floor_map_occupancy_fetch.py -v`
Expected: the new file passes; `test_floor_map_occupancy_fetch.py` (the OLD device-count test) now FAILS because behavior changed — **delete or rewrite** `tests/test_floor_map_occupancy_fetch.py` to match the endpoint behavior (its device-count assumption is obsolete). Rewrite it to the new bulk pattern (same asserts as Step 1) and remove the stale file, then re-run.

- [ ] **Step 5: Commit**

```bash
git add src/pages/floor_map.py tests/test_floor_map_occupancy_endpoint.py tests/test_floor_map_occupancy_fetch.py
git commit -m "feat(gui): floor map real-U occupancy via bulk endpoint (was device-count)"
```

---

### Task 3: Globe — colocation ring in the DC detail card

**Files:**
- Modify: `src/pages/global_view.py` (`_build_globe_data` ~239; `build_dc_info_card` ~1107, the `SimpleGrid` ~1187)
- Test: `tests/test_globe_colocation_ring.py`

**Interfaces:**
- Consumes: `coloc_total_u`/`coloc_used_u`/`coloc_free_u` on each DC summary dict (Plan A Task 4).
- Produces: each globe point carries `coloc_free_u`, `coloc_used_u`, `coloc_total_u`; `build_dc_info_card` renders a 4th "Kolokasyon" RingProgress (fill % = used/total).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_globe_colocation_ring.py
"""Globe points carry coloc_* fields; the DC info card renders a Kolokasyon ring."""
from src.pages import global_view as gv


def test_build_globe_data_carries_coloc_fields():
    summaries = [{
        "id": "DC13", "site_name": "IST", "name": "DC13", "description": "Equinix",
        "status": "active", "vm_count": 10, "host_count": 2, "stats": {"used_cpu_pct": 40, "used_ram_pct": 50},
        "coloc_total_u": 3616, "coloc_used_u": 1817, "coloc_free_u": 1799,
    }]
    pts = gv._build_globe_data(summaries)
    assert pts and pts[0]["coloc_free_u"] == 1799
    assert pts[0]["coloc_used_u"] == 1817
    assert pts[0]["coloc_total_u"] == 3616


def test_coloc_fields_default_zero_when_absent():
    summaries = [{
        "id": "DC13", "site_name": "IST", "name": "DC13", "description": "",
        "status": "active", "vm_count": 1, "host_count": 1, "stats": {},
    }]
    pts = gv._build_globe_data(summaries)
    assert pts[0]["coloc_total_u"] == 0 and pts[0]["coloc_free_u"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_globe_colocation_ring.py -v`
Expected: FAIL — `KeyError: 'coloc_free_u'`.

- [ ] **Step 3: Add coloc fields to `_build_globe_data`**

In `_build_globe_data`, inside the `data.append({...})` dict (after `"health": round(health, 1),`), add:

```python
            "coloc_total_u": int(dc.get("coloc_total_u") or 0),
            "coloc_used_u": int(dc.get("coloc_used_u") or 0),
            "coloc_free_u": int(dc.get("coloc_free_u") or 0),
```

- [ ] **Step 4: Add the ring to `build_dc_info_card`**

The `SimpleGrid(cols=4, ...)` at ~1187 currently holds 3 rings + 1 text tile. Bump to `cols=5` (or replace the text tile) and add a 4th ring tile. First compute the fill % near the other pcts (~1118-1126), reading from `get_dc_racks_occupancy`/summary or the passed data. Since `build_dc_info_card(dc_id, tr, site_name)` doesn't currently have coloc numbers, fetch them:

```python
    # colocation summary (best-effort; 0 if unavailable)
    from src.services import api_client as api
    _coloc = (api.get_dc_racks_occupancy(dc_id) or {}).get("summary", {})
    coloc_total = int(_coloc.get("total_u") or 0)
    coloc_used = int(_coloc.get("used_u") or 0)
    coloc_pct = round(coloc_used / coloc_total * 100) if coloc_total else 0
    coloc_free = int(_coloc.get("free_u") or 0)
```

Then add this tile into the `SimpleGrid.children` list (mirroring the CPU ring pattern, using the existing `_pct_color`):

```python
                    dmc.Stack(gap=4, align="center", children=[
                        dmc.RingProgress(size=80, thickness=7, roundCaps=True,
                            sections=[{"value": coloc_pct, "color": _pct_color(coloc_pct)}],
                            label=dmc.Text(f"{coloc_pct:.0f}%", ta="center", fw=700, size="sm")),
                        dmc.Text("Kolokasyon", size="xs", fw=600, c="#A3AED0"),
                        dmc.Text(f"{coloc_free}U boş", size="xs", c="#667085"),
                    ]),
```

and change `cols=4` → `cols=5` on that `SimpleGrid`.

- [ ] **Step 5: Run test to verify it passes + smoke the card builder**

Run: `.venv/bin/python -m pytest tests/test_globe_colocation_ring.py -v`
Expected: PASS. (The card render is covered by not raising; add a minimal `build_dc_info_card` smoke test with `patch("src.services.api_client.get_dc_racks_occupancy", ...)` if the existing global_view tests don't already exercise it.)

- [ ] **Step 6: Commit**

```bash
git add src/pages/global_view.py tests/test_globe_colocation_ring.py
git commit -m "feat(gui): colocation free-U ring on the globe DC card"
```

---

### Task 4: DC "Kolokasyon" lazy tab — the four coordinated edits + builder

**Files:**
- Modify: `src/pages/dc_view.py` (`_LAZY_TAB_KEYS` ~4923; `build_dc_view` gates ~5404 + `TabsList` ~5507 + `TabsPanel` ~5683; `render_dc_loading_page` ~5803-5822; add `build_colocation_tab`)
- Modify: `src/pages/dc_view_callbacks.py` (`expand_dc_view_on_tab` Output list ~140)
- Test: `tests/test_dc_view_colocation_tab.py`

**Interfaces:**
- Consumes: `api.get_colocation(dc_id)` (Task 1).
- Produces: a lazy `"colo"` tab whose root `dc-tab-colo-root` renders `build_colocation_tab(coloc_payload)` (KPIs + customers table), gated by `sec:dc_view:colocation`.

**CRITICAL — four coordinated edits (a missing one silently breaks tab load; see the verbatim anchors):**
1. `_LAZY_TAB_KEYS` gains `"colo"`.
2. `build_dc_view`: add `show_colo` + `("colo", show_colo)` to `tabs_order`; add `dmc.TabsTab("Kolokasyon", value="colo")` to the `TabsList`; add a `dmc.TabsPanel(value="colo", ...)` mirroring phys-inv with root `id="dc-tab-colo-root"`.
3. `render_dc_loading_page` (Phase-A shell): add `("colo", _sec("sec:dc_view:colocation"))` to its `tabs_order` and `dmc.TabsTab("Kolokasyon", value="colo")` to its `tabs` list — else the lazy placeholder root never exists.
4. `dc_view_callbacks.expand_dc_view_on_tab`: insert `Output("dc-tab-colo-root", "children", allow_duplicate=True)` at the **same ordinal position** as `"colo"` in `_LAZY_TAB_KEYS` (the callback does `updates[idx] = content`, index-aligned).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dc_view_colocation_tab.py
"""build_colocation_tab renders KPIs + customer rows; the lazy 'colo' tab is
registered so build_dc_view exposes a dc-tab-colo-root."""
from unittest.mock import patch

from src.pages import dc_view
from src.pages.dc_view import _LAZY_TAB_KEYS, build_colocation_tab, _find_component_by_id


def test_colo_is_a_registered_lazy_tab():
    assert "colo" in _LAZY_TAB_KEYS


def test_build_colocation_tab_renders_kpis_and_customers():
    payload = {
        "aggregate": {"total_u": 3616, "used_u": 1817, "free_u": 1799, "rack_count": 78},
        "customers": [
            {"tenant": "AytemizBank", "crm_account_name": "Aytemiz Bank",
             "match_status": "matched", "racks": ["209"], "used_u": 52, "crm_accountid": "A-1"},
        ],
        "racks": [],
    }
    comp = build_colocation_tab(payload)
    # Renders without error and mentions the free-U and the customer.
    text = str(comp)
    assert "1799" in text or "1,799" in text
    assert "AytemizBank" in text


def test_dc_view_exposes_colo_root_when_eager():
    api_patch = {name: (lambda *a, **k: {}) for name in dir(dc_view.api) if name.startswith("get_")}
    api_patch["get_colocation"] = lambda dc: {"aggregate": {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0}, "customers": [], "racks": []}
    with patch.multiple("src.pages.dc_view.api", **api_patch):
        page = dc_view.build_dc_view("DC13", time_range={"preset": "7d"}, eager_tabs=frozenset({"colo"}))
    assert _find_component_by_id(page, "dc-tab-colo-root") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_dc_view_colocation_tab.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_colocation_tab'` and `"colo" not in _LAZY_TAB_KEYS`.

- [ ] **Step 3a: Add `build_colocation_tab` builder**

Add near `_build_physical_inventory_dc_tab` in `dc_view.py` (mirror its `dmc.Stack` / `nexus-card` / `_kpi` / `_section_title` patterns):

```python
def build_colocation_tab(coloc: dict):
    """Kolokasyon tab: DC free/used-U KPIs + dedicated-customer footprint table."""
    agg = (coloc or {}).get("aggregate", {}) or {}
    customers = (coloc or {}).get("customers", []) or []
    total_u = int(agg.get("total_u") or 0)
    used_u = int(agg.get("used_u") or 0)
    free_u = int(agg.get("free_u") or 0)
    pct = round(used_u / total_u * 100) if total_u else 0

    kpis = dmc.SimpleGrid(cols=4, spacing="lg", style={"marginTop": "12px"}, children=[
        _kpi("Toplam U", f"{total_u:,}", _DC_ICONS.get("total_devices", "solar:server-bold-duotone"), color="indigo", stagger=1),
        _kpi("Kullanılan U", f"{used_u:,}", _DC_ICONS.get("device_roles", "solar:server-bold-duotone"), color="violet", stagger=2),
        _kpi("Boş (satılabilir) U", f"{free_u:,}", _DC_ICONS.get("top_role", "solar:server-bold-duotone"), color="teal", stagger=3),
        _kpi("Doluluk", f"%{pct}", _DC_ICONS.get("manufacturers", "solar:server-bold-duotone"), color="grape", stagger=4),
    ])

    if customers:
        header = html.Tr(children=[html.Th(h) for h in
                                   ("Müşteri", "CRM Hesabı", "Eşleşme", "Rack", "Kullanılan U")])
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
        table = dmc.Text("Bu DC'de dedike (dış müşteri) kolokasyon cihazı bulunamadı.",
                         size="sm", c="#98A2B3")

    return dmc.Stack(gap="lg", children=[
        html.Div(className="nexus-card", style={"padding": "20px"}, children=[
            _section_title("Kolokasyon", "Rack U doluluğu ve dedike müşteriler"),
            kpis,
        ]),
        html.Div(className="nexus-card", style={"padding": "20px"}, children=[
            _section_title("Dedike Müşteriler", "Cihaz tenant → CRM eşleştirmesi"),
            html.Div(style={"overflowX": "auto"}, children=table),
        ]),
    ])
```

(Verify `dmc.Table` exists in dmc 0.14.1; if its API differs, fall back to a `dash_table.DataTable` or an html.Table — keep the same columns.)

- [ ] **Step 3b: The four coordinated edits**

Edit 1 — `dc_view.py:4923`:
```python
_LAZY_TAB_KEYS: tuple[str, ...] = ("virt", "backup", "storage", "phys-inv", "network", "avail", "colo")
```

Edit 2 — in `build_dc_view`: after `show_avail = ...` (~5410) add `show_colo = _sec("sec:dc_view:colocation")`; append `("colo", show_colo)` to `tabs_order` (~5426); add `dmc.TabsTab("Kolokasyon", value="colo") if show_colo else None,` to the `TabsList` children (~5518); and add this `TabsPanel` alongside the others (mirror phys-inv ~5683), computing the payload:
```python
                dmc.TabsPanel(
                    value="colo",
                    children=(
                        _tab_lazy_placeholder("colo", dc_display)
                        if not _tab_eager(eager_tabs, "colo")
                        else html.Div(
                            id="dc-tab-colo-root",
                            children=dmc.Stack(
                                gap="lg", style={"padding": "0 30px"},
                                children=[build_colocation_tab(api.get_colocation(dc_id))],
                            ),
                        )
                    ),
                ) if show_colo else None,
```

Edit 3 — in `render_dc_loading_page` (~5803-5822): add `("colo", _sec("sec:dc_view:colocation"))` to its `tabs_order`, and `dmc.TabsTab("Kolokasyon", value="colo") if _sec("sec:dc_view:colocation") else None,` to its `tabs` list.

Edit 4 — `dc_view_callbacks.py` `expand_dc_view_on_tab` decorator: append (as the 7th root Output, matching `_LAZY_TAB_KEYS.index("colo") == 6`, i.e. AFTER `dc-tab-avail-root` and BEFORE `dc-view-loaded-tabs`):
```python
    Output("dc-tab-avail-root", "children", allow_duplicate=True),
    Output("dc-tab-colo-root", "children", allow_duplicate=True),   # <-- ADD (index 6)
    Output("dc-view-loaded-tabs", "data", allow_duplicate=True),
```
Because `updates = [dash.no_update] * len(_LAZY_TAB_KEYS)` (now length 7) and `updates[idx] = content`, and `return (*updates, sorted(loaded), ready_bump)`, the ordinal alignment is automatic once the Output is at position 6. **Confirm the six existing root Outputs are in `_LAZY_TAB_KEYS` order** (virt, backup, storage, phys-inv, network, avail) — the verbatim decorator lists them in that order, so appending colo at position 6 is correct.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_dc_view_colocation_tab.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Regression — existing lazy-tab tests**

Run: `.venv/bin/python -m pytest tests/test_dc_view_lazy_tabs.py tests/test_dc_view_visibility.py -v`
Expected: PASS (adding a tab must not break existing tabs). Fix any count-based assertions that hardcoded 6 lazy tabs.

- [ ] **Step 6: Commit**

```bash
git add src/pages/dc_view.py src/pages/dc_view_callbacks.py tests/test_dc_view_colocation_tab.py
git commit -m "feat(gui): DC Kolokasyon lazy tab (KPIs + dedicated-customer footprint)"
```

---

### Task 5: Rack detail — dedicated-customer badges

**Files:**
- Modify: `app.py` (`show_rack_detail` ~1937; optionally `_build_rack_unit_diagram` ~1783)
- Test: `tests/test_rack_detail_tenants.py`

**Interfaces:**
- Consumes: `api.get_dc_racks_occupancy(dc_id)` → per-rack `tenants[]` (Plan A), filtered to external via `shared.colocation.occupancy.is_internal_tenant`.
- Produces: the rack detail panel shows external-customer badge(s) for the clicked rack when present.

**Scope note:** Per-U customer coloring inside the rack elevation needs device-level tenant+position, which `get_rack_devices` does not return today. That is deferred (a follow-up: extend the devices endpoint with `tenant_name`). This task delivers the achievable, honest version — a customer badge row from the rack's occupancy tenants.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rack_detail_tenants.py
"""Rack detail surfaces external dedicated-customer badges from occupancy tenants."""
from src.pages.floor_map import _external_rack_tenants  # helper added below


def test_external_tenants_filters_internal():
    tenants = ["Boyner", "Bulutistan - Linux TEAM", "AytemizBank", "Bulut Broker"]
    assert _external_rack_tenants(tenants) == ["Boyner", "AytemizBank"]


def test_external_tenants_empty():
    assert _external_rack_tenants(["Bulutistan - Virtualization"]) == []
    assert _external_rack_tenants([]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_rack_detail_tenants.py -v`
Expected: FAIL — `ImportError: cannot import name '_external_rack_tenants'`.

- [ ] **Step 3: Add the helper + wire the badge**

Add to `floor_map.py`:
```python
def _external_rack_tenants(tenants):
    """External (non-Bulutistan) tenants occupying a rack, order-preserved, deduped."""
    from shared.colocation.occupancy import is_internal_tenant

    seen, out = set(), []
    for t in tenants or []:
        if t and not is_internal_tenant(t) and t not in seen:
            seen.add(t)
            out.append(t)
    return out
```

In `app.py` `show_rack_detail`, after computing `devices`, fetch the rack's tenants from the bulk occupancy payload and render a badge row when non-empty. Insert before the `_build_rack_unit_diagram` call:
```python
    from src.pages.floor_map import _external_rack_tenants
    _occ = (api.get_dc_racks_occupancy(dc_id or "") or {}).get("racks", [])
    _tenants = next((r.get("tenants") for r in _occ if str(r.get("rack_name")) == str(name)), []) or []
    _ext = _external_rack_tenants(_tenants)
    tenant_badges = (
        dmc.Group(gap=6, mb="sm", children=[
            dmc.Text("Dedike:", size="xs", c="#667085", fw=600),
            *[dmc.Badge(t, color="grape", variant="light", size="sm") for t in _ext],
        ]) if _ext else None
    )
```
Then add `tenant_badges` into the returned `html.Div(children=[...])` (e.g. right after the quick-stats `SimpleGrid`).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_rack_detail_tenants.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/pages/floor_map.py app.py tests/test_rack_detail_tenants.py
git commit -m "feat(gui): dedicated-customer badges on rack detail panel"
```

---

### Task 6: Full GUI colocation suite + CRM report row check

**Files:**
- Test: `tests/test_crm_report_colocation_row.py` (light)

**Interfaces:**
- Consumes: `src/components/crm_inventory_report.py` `prepare_service_row` (or the family accordion builder) with a `dc_hosting_u` row payload (from Plan B).
- Produces: verification that a populated `dc_hosting_u` row (has_infra_source True) renders sold/used/free/sellable columns rather than the "infra telemetry pending" hint.

- [ ] **Step 1: Write the test**

```python
# tests/test_crm_report_colocation_row.py
"""When dc_hosting_u has infra data, its report row shows the U quantities, not
the 'infra telemetry pending' placeholder."""
from src.components import crm_inventory_report as rpt


def test_dc_hosting_u_row_renders_quantities():
    row = {
        "panel_key": "dc_hosting_u", "label": "DC Barındırma — U", "family": "dc_hosting",
        "display_unit": "U", "total": 3616, "used_qty": 1817, "free_qty": 1799,
        "crm_sold_qty": 2, "sellable_qty": 1075.8, "unit_price_tl": 0.0,
        "has_infra_source": True, "sellable_profile": "allocation_only",
    }
    comp = rpt.prepare_service_row(row)  # adjust to the real builder signature
    text = str(comp)
    assert "1799" in text or "1,799" in text  # free U present
    assert "telemetry pending" not in text.lower()
```

(Adjust `prepare_service_row` call to the actual builder signature in `crm_inventory_report.py`; the point is a populated colocation row renders quantities. If the builder needs a family/context arg, supply a minimal one.)

- [ ] **Step 2: Run + iterate to green**

Run: `.venv/bin/python -m pytest tests/test_crm_report_colocation_row.py -v`
Expected: PASS after matching the real builder signature. No product code change expected (Plan B populates the payload; the report already renders any panel row).

- [ ] **Step 3: Run the full GUI colocation suite**

Run: `.venv/bin/python -m pytest tests/test_colocation_occupancy.py tests/test_colocation_matching.py tests/test_api_client_colocation.py tests/test_floor_map_occupancy_endpoint.py tests/test_globe_colocation_ring.py tests/test_dc_view_colocation_tab.py tests/test_rack_detail_tenants.py tests/test_crm_report_colocation_row.py -v`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_crm_report_colocation_row.py
git commit -m "test(gui): dc_hosting_u colocation report row renders quantities"
```

---

## Self-Review

- **Spec coverage:** §6.3 Globe ring → Task 3. DC Kolokasyon tab → Task 4. Floor map correct occupancy → Task 2. Rack elevation customer → Task 5 (badges; per-U coloring deferred + flagged). CRM report row → Task 6. api_client plumbing → Task 1. ✓
- **Type consistency:** `get_dc_racks_occupancy` / `get_colocation` names match Plan A/B endpoints. `build_colocation_tab(coloc_payload)` consumes Plan B's `{aggregate, customers, racks}` shape exactly. The four-edit tab wiring aligns Output ordinal 6 with `_LAZY_TAB_KEYS.index("colo")`. ✓
- **Placeholders:** Task 3 Step 4, Task 4 Step 3a (dmc.Table availability), Task 6 (builder signature) require confirming an exact API against the running dmc/report code — flagged with fallbacks; all code shown. Per-U rack coloring explicitly deferred (needs a device-tenant endpoint), logged here rather than silently dropped. ✓
