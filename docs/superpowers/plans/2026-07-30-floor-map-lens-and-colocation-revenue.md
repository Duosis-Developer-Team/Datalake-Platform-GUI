# Floor Map Lens + Colocation Revenue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Floor Map a Colocation/Load lens switch and fill its empty right panel with rack-level CRM customer allocation and potential-revenue tables, with click-to-highlight linking customers to their racks.

**Architecture:** A new `datacenter-api` endpoint joins NetBox rack devices to VMware/Nutanix/IBM host metrics by name and returns per-rack load. The Floor Map keeps one figure builder and swaps only its colour function and legend per lens. The right panel reuses the colocation payload DC View already renders, so both screens report identical numbers.

**Tech Stack:** Python 3.11, Dash + dash-mantine-components, Plotly (shapes-based floor map), FastAPI (datacenter-api), psycopg, pytest.

**Design doc:** `docs/superpowers/specs/2026-07-30-floor-map-lens-and-colocation-revenue-design.md`

## Global Constraints

- **Python 3.11 only.** Run everything with the main checkout's venv:
  `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python`. System `python3` is 3.9 and fails on `|` type unions.
- **All user-facing strings in English.** No Turkish in new or touched UI copy.
- **A missing/unknown value renders `—`, never `0`.** Zero reads as "worth nothing"; unknown is not zero (ADR-0028 §7).
- **Rack load aggregation is MAX, never average.** One saturated host in a rack makes the rack hot.
- **No price literals in code.** Prices come from the colocation payload's `aggregate["unit_price_tl"]`.
- **Money labels say "Potential", never "revenue"/"billed"** and always name their basis: `Potential (TL) — Allocated` / `Potential (TL) — Used` (ADR-0028 §4).
- **RBAC unchanged.** `sec:dc_view:colocation` is the sole gate for colocation data. Do not add permission nodes (ADR-0028 Consequences).
- **Per-DC data comes from per-DC endpoints**, never derived from the all-DC aggregate (ADR-0028 §6).
- Baseline: 1678 passed / 25 pre-existing failures / 2 pre-existing collection errors, identical on `main`. Do not chase these; do not let the count grow.

## File Structure

| File | Responsibility |
|---|---|
| `services/datacenter-api/app/db/queries/rack_load.py` (new) | SQL: rack devices by rack-name list; latest per-host metrics for VMware / Nutanix / IBM |
| `services/datacenter-api/app/services/rack_load.py` (new) | Pure aggregation: metric rows + device rows → per-rack load dicts. No DB, no I/O |
| `services/datacenter-api/app/services/dc_service.py` (modify) | `get_dc_racks_load(dc_code)` — connection, cache, wiring |
| `services/datacenter-api/app/routers/datacenters.py` (modify) | `GET /datacenters/{dc_code}/racks/load` |
| `src/services/api_client.py` (modify) | `get_dc_racks_load(dc_code)` |
| `src/pages/floor_map.py` (modify) | `LOAD_PALETTE`, `_color_by_load`, lens-aware figure builder, legend builder, customer panel |
| `app.py` (modify) | Lens + highlight callbacks |
| `src/pages/global_view.py` (modify) | Health→Load rename, dead-code removal |
| `dash_globe_component/src/lib/components/DashGlobe.react.js` (modify) | Read `load` key |

---

### Task 1: Per-rack load aggregation (pure functions)

**Files:**
- Create: `services/datacenter-api/app/services/rack_load.py`
- Test: `services/datacenter-api/tests/test_rack_load_aggregate.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `build_metric_index(vmware_rows, nutanix_rows, ibm_rows) -> dict[str, dict]` — key is `lower(host_name)`, value `{"cpu_pct": float|None, "ram_pct": float|None, "source": str}`.
  - `aggregate_rack_load(device_rows, metric_index) -> list[dict]` — `device_rows` are `(rack_name, device_name)` tuples; returns one dict per rack with keys `rack_name`, `load_pct`, `cpu_pct`, `ram_pct`, `monitored_devices`, `total_devices`, `hottest_device`.

- [ ] **Step 1: Write the failing test**

```python
# services/datacenter-api/tests/test_rack_load_aggregate.py
from app.services.rack_load import aggregate_rack_load, build_metric_index


def test_build_metric_index_lowercases_and_computes_percentages():
    index = build_metric_index(
        vmware_rows=[("ESX-13-01", 40.0, 100.0, 32.0, 64.0)],
        nutanix_rows=[],
        ibm_rows=[],
    )
    assert index["esx-13-01"]["cpu_pct"] == 40.0
    assert index["esx-13-01"]["ram_pct"] == 50.0
    assert index["esx-13-01"]["source"] == "vmware"


def test_rack_load_takes_the_worst_device_not_the_average():
    # One saturated host among three idle ones: a rack you cannot place work in.
    index = build_metric_index(
        vmware_rows=[
            ("h1", 5.0, 100.0, 5.0, 100.0),
            ("h2", 5.0, 100.0, 5.0, 100.0),
            ("h3", 5.0, 100.0, 5.0, 100.0),
            ("h4", 95.0, 100.0, 10.0, 100.0),
        ],
        nutanix_rows=[], ibm_rows=[],
    )
    rows = aggregate_rack_load(
        [("104", "h1"), ("104", "h2"), ("104", "h3"), ("104", "h4")], index
    )
    assert len(rows) == 1
    assert rows[0]["load_pct"] == 95.0          # MAX, not 27.5
    assert rows[0]["hottest_device"] == "h4"
    assert rows[0]["monitored_devices"] == 4
    assert rows[0]["total_devices"] == 4


def test_device_load_is_max_of_cpu_and_ram():
    index = build_metric_index([("h1", 10.0, 100.0, 90.0, 100.0)], [], [])
    rows = aggregate_rack_load([("104", "h1")], index)
    assert rows[0]["load_pct"] == 90.0
    assert rows[0]["cpu_pct"] == 10.0
    assert rows[0]["ram_pct"] == 90.0


def test_rack_with_devices_but_no_metrics_is_null_not_zero():
    # The tempting bug: unmonitored rendering as a healthy 0%.
    rows = aggregate_rack_load([("104", "switch-1"), ("104", "pdu-1")], {})
    assert rows[0]["load_pct"] is None
    assert rows[0]["monitored_devices"] == 0
    assert rows[0]["total_devices"] == 2


def test_name_matching_is_case_insensitive():
    index = build_metric_index([("ESX-13-01", 70.0, 100.0, 10.0, 100.0)], [], [])
    rows = aggregate_rack_load([("104", "esx-13-01")], index)
    assert rows[0]["load_pct"] == 70.0


def test_zero_capacity_never_divides_by_zero():
    index = build_metric_index([("h1", 5.0, 0.0, 5.0, 0.0)], [], [])
    assert index["h1"]["cpu_pct"] is None
    assert index["h1"]["ram_pct"] is None
    rows = aggregate_rack_load([("104", "h1")], index)
    assert rows[0]["load_pct"] is None


def test_ibm_memory_is_derived_from_available_not_used():
    # IBM reports available memory; used = total - available.
    index = build_metric_index([], [], [("pwr-1", 4.0, 10.0, 200.0, 50.0)])
    assert index["pwr-1"]["cpu_pct"] == 40.0
    assert index["pwr-1"]["ram_pct"] == 75.0
    assert index["pwr-1"]["source"] == "ibm"


def test_racks_are_returned_sorted_by_name():
    rows = aggregate_rack_load([("110", "a"), ("104", "b")], {})
    assert [r["rack_name"] for r in rows] == ["104", "110"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/datacenter-api && /Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_rack_load_aggregate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.rack_load'`

- [ ] **Step 3: Write the implementation**

```python
# services/datacenter-api/app/services/rack_load.py
"""Per-rack workload from NetBox rack membership + hypervisor host metrics.

"Load" is the platform's existing (CPU/RAM utilisation) quantity pushed down to
rack level -- deliberately NOT called "health", which ADR-0027 already assigns to
data freshness / automation health.

A rack's load is the MAX over its monitored devices, never the average: one
saturated host among twenty idle ones is a rack you cannot place work in, and an
average hides exactly that. A rack whose devices have no metrics at all reports
load_pct=None (rendered "Not monitored"), never 0 -- zero reads as idle capacity.
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence


def _pct(used: Any, capacity: Any) -> float | None:
    """used/capacity as a percentage, or None when capacity is absent/zero."""
    try:
        cap = float(capacity or 0)
        if cap <= 0:
            return None
        return round(float(used or 0) / cap * 100, 1)
    except (TypeError, ValueError):
        return None


def build_metric_index(
    vmware_rows: Sequence[Sequence[Any]] = (),
    nutanix_rows: Sequence[Sequence[Any]] = (),
    ibm_rows: Sequence[Sequence[Any]] = (),
) -> dict[str, dict]:
    """{lower(host name) -> {cpu_pct, ram_pct, source}} from the three host families.

    Row shapes (all "latest per host", produced by queries/rack_load.py):
      vmware_rows:  (vmhost, cpu_used_ghz, cpu_cap_ghz, mem_used_gb, mem_cap_gb)
      nutanix_rows: (host_name, cpu_used_hz, cpu_cap_hz, mem_used_bytes, mem_cap_bytes)
      ibm_rows:     (server_name, proc_used, proc_total, mem_total, mem_available)

    Keys are lowercased because NetBox device names and hypervisor host names agree
    on spelling but not always on case -- the same lower(name) idiom
    shared/licensing/os_sql.py uses for the VM-side join.
    """
    index: dict[str, dict] = {}

    def _put(name: Any, cpu_pct: float | None, ram_pct: float | None, source: str) -> None:
        key = str(name or "").strip().lower()
        if not key:
            return
        index[key] = {"cpu_pct": cpu_pct, "ram_pct": ram_pct, "source": source}

    for r in vmware_rows or ():
        _put(r[0], _pct(r[1], r[2]), _pct(r[3], r[4]), "vmware")
    for r in nutanix_rows or ():
        _put(r[0], _pct(r[1], r[2]), _pct(r[3], r[4]), "nutanix")
    for r in ibm_rows or ():
        # IBM reports AVAILABLE memory, not used -- used = total - available.
        total_mem = float(r[3] or 0)
        available = float(r[4] or 0)
        _put(r[0], _pct(r[1], r[2]), _pct(total_mem - available, total_mem), "ibm")

    return index


def aggregate_rack_load(
    device_rows: Iterable[Sequence[Any]],
    metric_index: dict[str, dict],
) -> list[dict]:
    """(rack_name, device_name) rows + metric index -> one load dict per rack.

    Every rack that has devices appears in the output, including racks where
    nothing is monitored -- the caller needs to tell "no metrics" apart from
    "rack absent from this DC".
    """
    racks: dict[str, dict] = {}

    for row in device_rows or ():
        rack_name = str(row[0] or "").strip()
        device_name = str(row[1] or "").strip()
        if not rack_name:
            continue
        entry = racks.setdefault(rack_name, {
            "rack_name": rack_name, "load_pct": None, "cpu_pct": None,
            "ram_pct": None, "monitored_devices": 0, "total_devices": 0,
            "hottest_device": None,
        })
        entry["total_devices"] += 1

        metrics = metric_index.get(device_name.lower()) if device_name else None
        if not metrics:
            continue
        cpu, ram = metrics.get("cpu_pct"), metrics.get("ram_pct")
        candidates = [v for v in (cpu, ram) if v is not None]
        if not candidates:
            continue

        entry["monitored_devices"] += 1
        device_load = max(candidates)
        if entry["load_pct"] is None or device_load > entry["load_pct"]:
            entry["load_pct"] = device_load
            entry["cpu_pct"] = cpu
            entry["ram_pct"] = ram
            entry["hottest_device"] = device_name

    return [racks[k] for k in sorted(racks)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/datacenter-api && /Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_rack_load_aggregate.py -v`
Expected: PASS — 8 tests

- [ ] **Step 5: Commit**

```bash
git add services/datacenter-api/app/services/rack_load.py services/datacenter-api/tests/test_rack_load_aggregate.py
git commit -m "feat(rack-load): per-rack load aggregation (MAX over monitored devices)"
```

---

### Task 2: Load SQL + service method + endpoint

**Files:**
- Create: `services/datacenter-api/app/db/queries/rack_load.py`
- Modify: `services/datacenter-api/app/services/dc_service.py` (add method next to `get_dc_racks_occupancy`, ~line 7757)
- Modify: `services/datacenter-api/app/routers/datacenters.py` (after `dc_racks_occupancy`, ~line 372)
- Test: `services/datacenter-api/tests/test_rack_load_endpoint.py`

**Interfaces:**
- Consumes: `app.services.rack_load.build_metric_index`, `aggregate_rack_load` (Task 1).
- Produces: `DatabaseService.get_dc_racks_load(dc_code: str) -> dict` returning `{"racks": [...], "summary": {"monitored_racks": int, "total_racks": int}}`; HTTP `GET /api/v1/datacenters/{dc_code}/racks/load`.

- [ ] **Step 1: Write the failing test**

```python
# services/datacenter-api/tests/test_rack_load_endpoint.py
from app.db.queries import rack_load as q


def test_device_query_filters_by_rack_name_array_and_active_status():
    sql = q.DEVICES_BY_RACK_NAMES
    assert "rack_name = ANY(%s::text[])" in sql
    assert "status_value = 'active'" in sql
    # DISTINCT ON keeps one row per device: the collector writes a new snapshot
    # every run, so without it a device is counted many times.
    assert "DISTINCT ON" in sql


def test_host_metric_queries_take_latest_row_per_host():
    for sql in (q.VMWARE_HOST_LATEST, q.NUTANIX_HOST_LATEST, q.IBM_SERVER_LATEST):
        assert "DISTINCT ON" in sql


def test_endpoint_returns_racks_and_summary(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.routers.datacenters import get_db

    class FakeDB:
        def get_dc_racks_load(self, dc_code):
            return {
                "racks": [{"rack_name": "104", "load_pct": 73.2, "cpu_pct": 73.2,
                           "ram_pct": 61.0, "monitored_devices": 4,
                           "total_devices": 11, "hottest_device": "esx-13-04"}],
                "summary": {"monitored_racks": 1, "total_racks": 1},
            }

    app.dependency_overrides[get_db] = lambda: FakeDB()
    try:
        resp = TestClient(app).get("/api/v1/datacenters/DC13/racks/load")
        assert resp.status_code == 200
        body = resp.json()
        assert body["racks"][0]["rack_name"] == "104"
        assert body["summary"]["monitored_racks"] == 1
    finally:
        app.dependency_overrides.clear()


def test_blank_dc_code_returns_empty_without_touching_the_db():
    from app.services.dc_service import DatabaseService

    svc = DatabaseService.__new__(DatabaseService)
    assert svc.get_dc_racks_load("  ") == {
        "racks": [], "summary": {"monitored_racks": 0, "total_racks": 0}
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/datacenter-api && /Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_rack_load_endpoint.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.db.queries.rack_load'`

- [ ] **Step 3a: Write the SQL module**

```python
# services/datacenter-api/app/db/queries/rack_load.py
"""SQL for per-rack load: NetBox rack membership joined to host metrics by name.

The rack list is supplied by the caller (from the same canonical per-DC rack query
the floor map and occupancy endpoint use) rather than re-derived here. A second,
independently-written DC-scoping rule is how two screens end up disagreeing about
one datacenter -- see ADR-0028 section 6.
"""
from __future__ import annotations

# Params: (rack_names: list[str],)
DEVICES_BY_RACK_NAMES = """
SELECT DISTINCT ON (d.rack_name, lower(d.name))
    d.rack_name,
    d.name
FROM public.discovery_netbox_inventory_device d
WHERE d.rack_name = ANY(%s::text[])
  AND d.status_value = 'active'
  AND d.name IS NOT NULL
ORDER BY d.rack_name, lower(d.name), d.collection_time DESC NULLS LAST
"""

# Params: (start_ts, end_ts)
VMWARE_HOST_LATEST = """
SELECT DISTINCT ON (vmhost)
    vmhost,
    COALESCE(cpu_ghz_used, 0),
    COALESCE(cpu_ghz_capacity, 0),
    COALESCE(memory_used_gb, 0),
    COALESCE(memory_capacity_gb, 0)
FROM public.vmhost_metrics
WHERE "timestamp" BETWEEN %s AND %s
ORDER BY vmhost, "timestamp" DESC
"""

# Params: (start_ts, end_ts)
NUTANIX_HOST_LATEST = """
SELECT DISTINCT ON (h.host_name)
    h.host_name,
    COALESCE(h.cpu_usage_avg, 0),
    COALESCE(h.total_cpu_capacity, 0),
    COALESCE(h.memory_usage_avg, 0),
    COALESCE(h.total_memory_capacity, 0)
FROM public.nutanix_host_metrics h
WHERE h.collectiontime BETWEEN %s AND %s
ORDER BY h.host_name, h.collectiontime DESC
"""

# Params: (start_ts, end_ts)
# IBM reports AVAILABLE memory; the "used" side is derived in Python.
IBM_SERVER_LATEST = """
SELECT DISTINCT ON (server_details_servername)
    server_details_servername,
    COALESCE(server_processor_utilizedprocunits, 0),
    COALESCE(server_processor_totalprocunits, 0),
    COALESCE(server_memory_totalmem, 0),
    COALESCE(server_memory_availablemem, 0)
FROM public.ibm_server_general
WHERE "timestamp" BETWEEN %s AND %s
ORDER BY server_details_servername, "timestamp" DESC
"""
```

- [ ] **Step 3b: Add the service method**

Insert into `services/datacenter-api/app/services/dc_service.py` immediately after `get_dc_racks_occupancy` ends (before `def get_colocation_aggregate`). Add `from app.db.queries import rack_load as rl_q` and `from app.services.rack_load import aggregate_rack_load, build_metric_index` to the module's imports.

```python
    def get_dc_racks_load(self, dc_code: str) -> dict:
        """Per-rack workload (max CPU/RAM utilisation of the rack's monitored
        devices) for a DC. Mirrors get_dc_racks_occupancy's shape and its 6h
        singleflight cache.

        Racks whose devices carry no metrics are returned with load_pct=None so
        the UI can render "Not monitored" rather than a misleading 0%.
        """
        empty = {"racks": [], "summary": {"monitored_racks": 0, "total_racks": 0}}
        if not dc_code or not dc_code.strip():
            return empty
        code = dc_code.strip()
        cache_key = f"dc_racks_load:{code}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        def _fetch():
            racks = (self.get_dc_racks(code) or {}).get("racks", [])
            rack_names = [str(r.get("name") or "").strip() for r in racks]
            rack_names = [n for n in rack_names if n]
            if not rack_names:
                return empty
            tr = default_time_range()
            start_ts, end_ts = tr["start"], tr["end"]
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    device_rows = self._run_rows(
                        cur, rl_q.DEVICES_BY_RACK_NAMES, (rack_names,))
                    vmware_rows = self._run_rows(
                        cur, rl_q.VMWARE_HOST_LATEST, (start_ts, end_ts))
                    nutanix_rows = self._run_rows(
                        cur, rl_q.NUTANIX_HOST_LATEST, (start_ts, end_ts))
                    ibm_rows = self._run_rows(
                        cur, rl_q.IBM_SERVER_LATEST, (start_ts, end_ts))
            index = build_metric_index(vmware_rows, nutanix_rows, ibm_rows)
            rows = aggregate_rack_load(device_rows, index)
            monitored = sum(1 for r in rows if r["monitored_devices"] > 0)
            logger.info(
                "rack load dc=%s racks=%d monitored=%d devices=%d metrics=%d",
                code, len(rows), monitored, len(device_rows or []), len(index),
            )
            return {"racks": rows,
                    "summary": {"monitored_racks": monitored,
                                "total_racks": len(rows)}}

        try:
            return cache.run_singleflight(cache_key, _fetch, ttl=21600)
        except OperationalError as exc:
            logger.error("DB unavailable for get_dc_racks_load(%s): %s", code, exc)
            return empty
```

- [ ] **Step 3c: Add the route**

Insert into `services/datacenter-api/app/routers/datacenters.py` directly after `dc_racks_occupancy`:

```python
@router.get("/datacenters/{dc_code}/racks/load", response_model=dict[str, Any])
def dc_racks_load(dc_code: str, db: DatabaseService = Depends(get_db)):
    """Bulk per-rack workload (max CPU/RAM of the rack's monitored devices)."""
    return db.get_dc_racks_load(dc_code)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/datacenter-api && /Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_rack_load_endpoint.py tests/test_rack_load_aggregate.py -v`
Expected: PASS — 12 tests

- [ ] **Step 5: Commit**

```bash
git add services/datacenter-api/app/db/queries/rack_load.py services/datacenter-api/app/services/dc_service.py services/datacenter-api/app/routers/datacenters.py services/datacenter-api/tests/test_rack_load_endpoint.py
git commit -m "feat(rack-load): /racks/load endpoint joining NetBox racks to host metrics"
```

---

### Task 3: GUI api_client accessor

**Files:**
- Modify: `src/services/api_client.py` (after `get_dc_racks_occupancy`, ~line 1970)
- Test: `tests/test_api_client_rack_load.py`

**Interfaces:**
- Consumes: HTTP `GET /api/v1/datacenters/{dc}/racks/load` (Task 2).
- Produces: `api_client.get_dc_racks_load(dc_code: str) -> dict` — `{"racks": [...], "summary": {...}}`, empty dict shape on failure.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_client_rack_load.py
from unittest.mock import patch

from src.services import api_client as api


def test_get_dc_racks_load_calls_the_load_path():
    with patch.object(api, "_get_json", return_value={"racks": [], "summary": {}}) as gj:
        api.get_dc_racks_load("DC13")
    assert gj.call_args[0][1] == "/api/v1/datacenters/DC13/racks/load"


def test_get_dc_racks_load_url_encodes_the_dc_code():
    with patch.object(api, "_get_json", return_value={"racks": []}) as gj:
        api.get_dc_racks_load("Vadi Ofis")
    assert "Vadi%20Ofis" in gj.call_args[0][1]


def test_get_dc_racks_load_returns_empty_shape_when_the_call_fails():
    with patch.object(api, "_get_json", side_effect=RuntimeError("down")):
        result = api.get_dc_racks_load("DC13")
    assert result == {"racks": [], "summary": {}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_api_client_rack_load.py -v`
Expected: FAIL — `AttributeError: module 'src.services.api_client' has no attribute 'get_dc_racks_load'`

- [ ] **Step 3: Write the implementation**

```python
def get_dc_racks_load(dc_code: str) -> dict:
    """Per-rack workload for the Floor Map's Load lens. Mirrors
    get_dc_racks_occupancy: same cache-with-stale wrapper, same empty shape."""
    enc = quote(dc_code, safe="")
    empty = {"racks": [], "summary": {}}
    ck = f"api:dc_racks_load:{enc}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/racks/load")
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_api_client_rack_load.py -v`
Expected: PASS — 3 tests

- [ ] **Step 5: Commit**

```bash
git add src/services/api_client.py tests/test_api_client_rack_load.py
git commit -m "feat(api-client): get_dc_racks_load accessor"
```

---

### Task 4: Load palette, colour function, and both legends

**Files:**
- Modify: `src/pages/floor_map.py` (after `_color_by_fill`, ~line 133)
- Test: `tests/test_floor_map_load_lens.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `LOAD_PALETTE: dict[str, tuple[str, str]]` with keys `green`, `orange`, `red`, `closed`, `unmonitored`.
  - `_color_by_load(status, load_pct) -> tuple[str, str]`.
  - `build_lens_legend(lens: str) -> dmc.Group` where `lens` is `"coloc"` or `"load"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_floor_map_load_lens.py
from src.pages import floor_map as fm


def test_unmonitored_rack_is_not_coloured_as_idle():
    # A rack with no metrics must never read as prime free capacity.
    assert fm._color_by_load("active", None) == fm.LOAD_PALETTE["unmonitored"]


def test_load_thresholds_match_the_colocation_lens_steps():
    assert fm._color_by_load("active", 10.0) == fm.LOAD_PALETTE["green"]
    assert fm._color_by_load("active", 49.9) == fm.LOAD_PALETTE["green"]
    assert fm._color_by_load("active", 50.0) == fm.LOAD_PALETTE["orange"]
    assert fm._color_by_load("active", 80.0) == fm.LOAD_PALETTE["orange"]
    assert fm._color_by_load("active", 80.1) == fm.LOAD_PALETTE["red"]


def test_closed_beats_load():
    # Mirrors _color_by_fill's closed-before-empty ordering.
    for status in ("inactive", "planned", "closed"):
        assert fm._color_by_load(status, 95.0) == fm.LOAD_PALETTE["closed"]


def test_load_palette_has_no_turquoise_idle_step():
    # A 0% reading is far more often a silent collector than idle hardware.
    assert "empty" not in fm.LOAD_PALETTE
    assert fm._color_by_load("active", 0.0) == fm.LOAD_PALETTE["green"]


def test_legends_are_english_and_lens_specific():
    coloc = str(fm.build_lens_legend("coloc"))
    load = str(fm.build_lens_legend("load"))
    assert "Fully free (sellable)" in coloc
    assert "Closed / inactive" in coloc
    assert "Not monitored" in load
    assert "Heavy load" in load
    assert "Fully free (sellable)" not in load
    for text in (coloc, load):
        for turkish in ("Tamamen boş", "Çok dolu", "Bilinmiyor", "Kapalı"):
            assert turkish not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_floor_map_load_lens.py -v`
Expected: FAIL — `AttributeError: module 'src.pages.floor_map' has no attribute '_color_by_load'`

- [ ] **Step 3: Write the implementation**

Add after `_color_by_fill` in `src/pages/floor_map.py`:

```python
# ── Load palette (colour by CPU/RAM utilisation of the rack's hosts) ────────
# Same 50/80 steps as FILL_PALETTE so a colour learned in one lens reads the
# same way in the other. No turquoise "idle" step on purpose: a 0% reading is
# far more often a silent collector than genuinely idle hardware, and painting
# that as prime capacity would invent good news.
LOAD_PALETTE = {
    "green":       ("#17B26A", "#027A48"),   # light load (<50%)
    "orange":      ("#F79009", "#B54708"),   # moderate (50-80%)
    "red":         ("#F04438", "#B42318"),   # heavy (>80%)
    "closed":      ("#475467", "#344054"),   # non-active / closed
    "unmonitored": ("#F2F4F7", "#D0D5DD"),   # no device in this rack has metrics
}

_COLOC_LEGEND = (
    ("empty",   "Fully free (sellable)"),
    ("green",   "Space available"),
    ("orange",  "Moderate"),
    ("red",     "Nearly full"),
    ("closed",  "Closed / inactive"),
    ("unknown", "Unknown"),
)

_LOAD_LEGEND = (
    ("green",       "Light load"),
    ("orange",      "Moderate load"),
    ("red",         "Heavy load"),
    ("closed",      "Closed / inactive"),
    ("unmonitored", "Not monitored"),
)


def _color_by_load(status, load_pct):
    """(fill, dark) for the Load lens. Closed is checked before load so a closed
    rack with a hot host is gray, mirroring _color_by_fill's ordering. A None
    load is "not monitored" -- never rendered as a healthy 0%."""
    if (status or "").lower() in _NON_ACTIVE_STATUSES:
        return LOAD_PALETTE["closed"]
    if load_pct is None:
        return LOAD_PALETTE["unmonitored"]
    if load_pct > 80:
        return LOAD_PALETTE["red"]
    if load_pct >= 50:
        return LOAD_PALETTE["orange"]
    return LOAD_PALETTE["green"]


def build_lens_legend(lens: str):
    """Swatch legend for the active lens. Each lens ships its own labels: the
    shared 50/80 steps mean different things (U occupancy vs CPU/RAM)."""
    palette = LOAD_PALETTE if lens == "load" else FILL_PALETTE
    entries = _LOAD_LEGEND if lens == "load" else _COLOC_LEGEND
    return dmc.Group(gap="lg", px="sm", children=[
        *[
            dmc.Group(gap=6, align="center", children=[
                html.Div(className="fm-legend-swatch",
                         style={"backgroundColor": palette[key][0]}),
                dmc.Text(label, size="xs", c="#667085"),
            ])
            for key, label in entries
        ],
        dmc.Text("Scroll to zoom · Drag to pan · Click rack to inspect",
                 size="xs", c="#98A2B3", ml="auto"),
    ])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_floor_map_load_lens.py -v`
Expected: PASS — 5 tests

- [ ] **Step 5: Commit**

```bash
git add src/pages/floor_map.py tests/test_floor_map_load_lens.py
git commit -m "feat(floor-map): Load palette, colour rule, and per-lens English legends"
```

---

### Task 5: Lens-aware figure builder + switch wiring

**Files:**
- Modify: `src/pages/floor_map.py` — `_collect_rack` (~line 260), `_collect_hall_zone` (~line 311), `build_floor_map_figure` (~line 398), `build_recolored_floor_map_figure` (~line 547), `build_floor_map_layout` (~line 562)
- Modify: `app.py` — `recolor_floor_map_by_fill` (~line 1952)
- Test: `tests/test_floor_map_lens_switch.py`

**Interfaces:**
- Consumes: `_color_by_load`, `build_lens_legend`, `LOAD_PALETTE` (Task 4); `api.get_dc_racks_load` (Task 3).
- Produces:
  - `_fetch_rack_load(dc_id, racks) -> dict[str, dict]` — `{rack_name: {"load_pct", "cpu_pct", "ram_pct", "monitored_devices", "total_devices", "hottest_device"}}`.
  - `build_floor_map_figure(racks, dc_id="", occupancy=None, load=None, lens="coloc", highlight=None)`.
  - `build_recolored_floor_map_figure(dc_id, lens="coloc", highlight=None)`.
  - Component ids: `floor-map-lens` (SegmentedControl, values `coloc`/`load`), `floor-map-legend` (Div).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_floor_map_lens_switch.py
from unittest.mock import patch

from src.pages import floor_map as fm

RACKS = [
    {"id": "R1", "name": "104", "status": "active", "u_height": 47, "hall_name": "DH7"},
    {"id": "R2", "name": "105", "status": "active", "u_height": 47, "hall_name": "DH7"},
]


def _fills(fig):
    return {s["fillcolor"] for s in fig.layout.shapes if s.get("fillcolor")}


def test_load_lens_paints_racks_with_the_load_palette():
    load = {"104": {"load_pct": 92.0, "monitored_devices": 2, "total_devices": 3},
            "105": {"load_pct": 12.0, "monitored_devices": 1, "total_devices": 4}}
    fig = fm.build_floor_map_figure(RACKS, dc_id="DC13", load=load, lens="load")
    fills = _fills(fig)
    assert fm.LOAD_PALETTE["red"][0] in fills
    assert fm.LOAD_PALETTE["green"][0] in fills


def test_load_lens_renders_unmonitored_racks_as_unmonitored_not_green():
    load = {"104": {"load_pct": None, "monitored_devices": 0, "total_devices": 5}}
    fig = fm.build_floor_map_figure(RACKS[:1], dc_id="DC13", load=load, lens="load")
    assert fm.LOAD_PALETTE["unmonitored"][0] in _fills(fig)
    assert fm.LOAD_PALETTE["green"][0] not in _fills(fig)


def test_colocation_lens_is_unchanged_by_the_lens_parameter():
    occ = {"104": 47, "105": 0}
    before = fm.build_floor_map_figure(RACKS, dc_id="DC13", occupancy=occ)
    after = fm.build_floor_map_figure(RACKS, dc_id="DC13", occupancy=occ, lens="coloc")
    assert _fills(before) == _fills(after)


def test_figure_cache_does_not_serve_one_lens_for_the_other():
    occ = {"104": 47, "105": 0}
    load = {"104": {"load_pct": 5.0, "monitored_devices": 1, "total_devices": 1},
            "105": {"load_pct": 5.0, "monitored_devices": 1, "total_devices": 1}}
    coloc_fig = fm.build_floor_map_figure(RACKS, dc_id="DC13", occupancy=occ, lens="coloc")
    load_fig = fm.build_floor_map_figure(RACKS, dc_id="DC13", load=load, lens="load")
    assert _fills(coloc_fig) != _fills(load_fig)


def test_layout_has_a_lens_switch_with_both_options():
    with patch.object(fm, "_fetch_rack_occupancy", return_value={}):
        layout = str(fm.build_floor_map_layout("DC13", "DC13", RACKS))
    assert "floor-map-lens" in layout
    assert "Colocation" in layout
    assert "Load" in layout


def test_fetch_rack_load_degrades_to_empty_when_the_api_fails():
    with patch("src.services.api_client.get_dc_racks_load", side_effect=RuntimeError):
        assert fm._fetch_rack_load("DC13", RACKS) == {}


def test_fetch_rack_load_keeps_only_requested_racks():
    payload = {"racks": [{"rack_name": "104", "load_pct": 50.0},
                         {"rack_name": "999", "load_pct": 90.0}]}
    with patch("src.services.api_client.get_dc_racks_load", return_value=payload):
        result = fm._fetch_rack_load("DC13", RACKS)
    assert set(result) == {"104"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_floor_map_lens_switch.py -v`
Expected: FAIL — `TypeError: build_floor_map_figure() got an unexpected keyword argument 'load'`

- [ ] **Step 3a: Add the load fetcher**

Add after `_fetch_rack_occupancy` in `src/pages/floor_map.py`:

```python
def _fetch_rack_load(dc_id, racks):
    """{rack_name -> load row} from the bulk load endpoint, restricted to the
    racks this floor map draws. Degrades to {} (every rack "not monitored") if
    the call fails, matching _fetch_rack_occupancy's guarded shape."""
    from src.services import api_client as api

    wanted = {str(r.get("name") or "").strip() for r in racks if str(r.get("name") or "").strip()}
    if not wanted:
        return {}
    try:
        payload = api.get_dc_racks_load(dc_id or "") or {}
    except Exception:
        _logger.warning("_fetch_rack_load: bulk load call failed for dc_id=%s", dc_id, exc_info=True)
        return {}
    out = {}
    for row in payload.get("racks", []) or []:
        name = str(row.get("rack_name") or "").strip()
        if name in wanted:
            out[name] = row
    return out
```

- [ ] **Step 3b: Thread lens through the collectors**

In `_collect_rack`, replace the signature and the colour block:

```python
def _collect_rack(shapes, hover_x, hover_y, hover_text, hover_cd,
                  rx, ry, status, name, rack_data, dc_id="", occupancy=None,
                  load=None, lens="coloc", highlight=None):
```

```python
    # Phase 1 (no data yet) keeps the status color; phase 2 colors by the lens.
    load_row = (load or {}).get(name) or {}
    load_pct = load_row.get("load_pct")
    if lens == "load":
        occupied_u = occupancy.get(name) if occupancy else None
        if load is None:
            fill, dark = _color(status)
        else:
            fill, dark = _color_by_load(status, load_pct)
    elif occupancy is None:
        fill, dark = _color(status)
        occupied_u = None
    else:
        occupied_u = occupancy.get(name)
        fill, dark = _color_by_fill(status, occupied_u, u)
```

Then, immediately after the rack body shape is appended, add the highlight outline:

```python
    if highlight and name in highlight:
        shapes.append(dict(
            type="rect", x0=rx-1.5, y0=ry-1.5, x1=rx+RACK_W+1.5, y1=ry+RACK_H+1.5,
            fillcolor="rgba(0,0,0,0)",
            line=dict(color="#4318FF", width=2.5)))
```

Extend the hover customdata with the load columns (append after `info["label"]`):

```python
    if load_pct is None:
        load_str = "Not monitored" if load is not None else "—"
    else:
        load_str = (f"{load_pct:.0f}% "
                    f"({load_row.get('monitored_devices', 0)}/"
                    f"{load_row.get('total_devices', 0)} devices)")
    hover_cd.append([rid, name, status, u, pwr, rh, rack_type, serial, dc_id,
                     doluluk_str, free_str, info["label"], load_str])
```

Widen `_collect_hall_zone` the same way — add `load=None, lens="coloc", highlight=None` to its signature and pass them straight through to every `_collect_rack` call.

- [ ] **Step 3c: Make the figure builder lens-aware**

In `build_floor_map_figure`, replace the signature and fingerprint:

```python
def build_floor_map_figure(racks, dc_id="", occupancy=None, load=None,
                           lens="coloc", highlight=None):
    # occupancy/load/lens/highlight are all part of the fingerprint: a figure
    # built for one lens must never be served for the other.
    occ_fp = "|".join(f"{k}:{v}" for k, v in sorted(occupancy.items())) if occupancy else ""
    load_fp = "|".join(f"{k}:{(v or {}).get('load_pct')}"
                       for k, v in sorted((load or {}).items())) if load else ""
    hl_fp = ",".join(sorted(highlight)) if highlight else ""
    fp = (_rack_fingerprint(dc_id, racks) + "::" + occ_fp
          + "::" + load_fp + "::" + lens + "::" + hl_fp)
```

Pass the new arguments through the `_collect_hall_zone` call:

```python
        _collect_hall_zone(shapes, annotations, hover_x, hover_y, hover_text, hover_cd,
                           hx, hy, hall_name, dims, dc_id=dc_id, occupancy=occupancy,
                           load=load, lens=lens, highlight=highlight)
```

Replace the hovertemplate with the English, lens-aware version:

```python
            hovertemplate=(
                "<b>%{customdata[1]}</b><br>"
                "Hall: %{customdata[5]}<br>"
                "Status: %{customdata[2]}<br>"
                "Occupancy: %{customdata[9]}<br>"
                "Free (sellable): %{customdata[10]}<br>"
                "Load: %{customdata[12]}<br>"
                "Power: %{customdata[4]}<br>"
                "Type: %{customdata[6]}"
                "<extra></extra>"
            ),
```

Replace `build_recolored_floor_map_figure`:

```python
def build_recolored_floor_map_figure(dc_id, lens="coloc", highlight=None):
    """Phase 2 / lens switch: fetch racks plus whichever payload the active lens
    needs, and return the recoloured figure. Returns None if the DC has no racks."""
    from src.services import api_client as api

    racks = (api.get_dc_racks(dc_id or "") or {}).get("racks", [])
    if not racks:
        return None
    if lens == "load":
        return build_floor_map_figure(racks, dc_id=dc_id,
                                      load=_fetch_rack_load(dc_id, racks),
                                      lens="load", highlight=highlight)
    occupancy = _fetch_rack_occupancy(dc_id, racks)
    return build_floor_map_figure(racks, dc_id=dc_id, occupancy=occupancy,
                                  lens="coloc", highlight=highlight)
```

- [ ] **Step 3d: Put the switch in the layout**

In `build_floor_map_layout`, replace the inline legend `dmc.Group(...)` (the block starting `# Legend — fill-based (color by U-occupancy)`) with:

```python
                            html.Div(id="floor-map-legend", children=[
                                build_lens_legend("coloc")], style={"marginTop": "8px"}),
```

and insert the switch directly above the `dmc.Paper` holding the graph:

```python
                            dmc.Group(justify="space-between", align="center", mb="xs",
                                      children=[
                                dmc.SegmentedControl(
                                    id="floor-map-lens",
                                    value="coloc",
                                    data=[{"label": "Colocation", "value": "coloc"},
                                          {"label": "Load", "value": "load"}],
                                    size="xs", radius="md",
                                ),
                                dmc.Text(
                                    "Colocation — rack space by U · Load — CPU/RAM of the "
                                    "rack's monitored hosts",
                                    size="xs", c="#98A2B3",
                                ),
                            ]),
```

Add `dcc.Store(id="fm-selected-customer", data=None)` to the layout's top-level children (it is read in Task 7).

- [ ] **Step 3e: Rewire the recolor callback**

In `app.py`, replace the `recolor_floor_map_by_fill` callback:

```python
@app.callback(
    dash.Output("floor-map-graph", "figure"),
    dash.Output("floor-map-legend", "children"),
    dash.Input("floor-map-occupancy-interval", "n_intervals"),
    dash.Input("floor-map-lens", "value"),
    dash.Input("fm-selected-customer", "data"),
    dash.State("selected-building-dc-store", "data"),
    prevent_initial_call=True,
)
def recolor_floor_map(n_intervals, lens, selected_customer, dc_store):
    """Phase-2 recolor and lens switching share one callback: two callbacks
    writing the same figure would race and the loser's colours would win."""
    dc_id = (dc_store or {}).get("dc_id", "")
    if not dc_id:
        return dash.no_update, dash.no_update

    from src.pages.floor_map import build_lens_legend, build_recolored_floor_map_figure

    lens = lens or "coloc"
    highlight = set((selected_customer or {}).get("racks") or [])
    fig = build_recolored_floor_map_figure(dc_id, lens=lens, highlight=highlight)
    legend = build_lens_legend(lens)
    return (fig if fig is not None else dash.no_update), legend
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_floor_map_lens_switch.py tests/test_floor_map_load_lens.py -v`
Expected: PASS — 12 tests

- [ ] **Step 5: Commit**

```bash
git add src/pages/floor_map.py app.py tests/test_floor_map_lens_switch.py
git commit -m "feat(floor-map): Colocation/Load lens switch with per-lens legend and hover"
```

---

### Task 6: Colocation customer panel in the empty right column

**Files:**
- Modify: `src/pages/floor_map.py` — `build_floor_map_layout`
- Test: `tests/test_floor_map_customer_panel.py`

**Interfaces:**
- Consumes: `api.get_colocation(dc_id)` — `{"aggregate": {...}, "allocation": [...], "internal": [...]}`.
- Produces: `build_colocation_customer_panel(coloc: dict) -> html.Div` rendered into the `floor-map-rack-detail` column by default; component id `fm-coloc-panel`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_floor_map_customer_panel.py
from src.pages import floor_map as fm

COLOC = {
    "aggregate": {"total_u": 2629, "used_u": 1169, "free_u": 1460,
                  "rack_count": 214, "unit_price_tl": 10430.84,
                  "free_u_potential_tl": 1000000.0, "price_source": "crm"},
    "allocation": [
        {"customer": "BOYNER", "rack_count": 7, "allocated_u": 312,
         "used_u": 222, "racks": ["104", "105"]},
        {"customer": "Unattributed", "rack_count": 4, "allocated_u": 188,
         "used_u": 90, "racks": ["112", "114"]},
    ],
    "internal": [{"tenant": "BULUTISTAN", "racks": ["201"], "used_u": 40,
                  "potential_tl": 417233.6}],
}


def test_panel_lists_dedicated_customers_with_allocated_u():
    txt = str(fm.build_colocation_customer_panel(COLOC))
    assert "BOYNER" in txt
    assert "312" in txt


def test_money_columns_name_their_basis_like_dc_view():
    # Two same-named "Potential (TL)" columns in one screen is the misread
    # ADR-0028 section 4 exists to prevent.
    txt = str(fm.build_colocation_customer_panel(COLOC))
    assert "Potential (TL) — Allocated" in txt
    assert "Potential (TL) — Used" in txt


def test_unresolved_price_renders_a_dash_not_zero():
    payload = dict(COLOC)
    payload["aggregate"] = dict(COLOC["aggregate"], unit_price_tl=None)
    txt = str(fm.build_colocation_customer_panel(payload))
    assert "—" in txt
    assert "0,00 TL" not in txt


def test_unattributed_carries_the_ambiguity_tooltip():
    txt = str(fm.build_colocation_customer_panel(COLOC))
    assert "Ownership ambiguous in NetBox" in txt


def test_empty_payload_renders_an_explanatory_state_not_a_crash():
    txt = str(fm.build_colocation_customer_panel({}))
    assert "No dedicated" in txt


def test_panel_never_claims_billed_revenue():
    txt = str(fm.build_colocation_customer_panel(COLOC))
    assert "not billed revenue" in txt
    for banned in ("Revenue (TL)", "Billed"):
        assert banned not in txt


def test_internal_resources_are_listed_separately():
    txt = str(fm.build_colocation_customer_panel(COLOC))
    assert "Internal Resources" in txt
    assert "BULUTISTAN" in txt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_floor_map_customer_panel.py -v`
Expected: FAIL — `AttributeError: module 'src.pages.floor_map' has no attribute 'build_colocation_customer_panel'`

- [ ] **Step 3: Write the implementation**

Add to `src/pages/floor_map.py` (imports: `from src.utils.format_units import fmt_tl`, `from shared.colocation.allocation import UNATTRIBUTED`, `from dash_iconify import DashIconify`):

```python
def build_colocation_customer_panel(coloc: dict):
    """Rack-level CRM allocation + potential, rendered in the floor map's right
    column when no rack is selected.

    Column semantics, header wording and the potential-not-billed framing are
    taken verbatim from dc_view.build_colocation_tab: the two screens read the
    same payload, and two labels for one number is how they drift apart.
    """
    agg = (coloc or {}).get("aggregate", {}) or {}
    allocation = (coloc or {}).get("allocation", []) or []
    internal = (coloc or {}).get("internal", []) or []
    unit_price = agg.get("unit_price_tl")

    def _potential(u):
        # An unresolved price propagates as None (renders "—"), never prices
        # allocated space at 0.
        if unit_price is None:
            return None
        return float(u or 0) * float(unit_price)

    if allocation:
        rows = []
        for c in allocation:
            name = c.get("customer", "")
            if name == UNATTRIBUTED:
                name_cell = dmc.Tooltip(
                    label=("Ownership ambiguous in NetBox: some racks have no "
                           "resolvable tenant/tag/description; others carry two "
                           "colocation rows naming different customers. Real "
                           "customer footprint, not free space."),
                    position="top", withArrow=True, multiline=True, w=260,
                    children=dmc.Group(gap=4, wrap="nowrap", children=[
                        dmc.Text(name, size="xs"),
                        DashIconify(icon="solar:info-circle-bold-duotone",
                                    width=13, style={"color": "#F79009"}),
                    ]),
                )
            else:
                name_cell = dmc.Text(name, size="xs")
            rows.append(html.Tr(
                id={"type": "fm-coloc-customer-row", "index": name},
                n_clicks=0,
                style={"cursor": "pointer"},
                children=[
                    html.Td(name_cell),
                    html.Td(f"{int(c.get('rack_count') or 0):,}"),
                    html.Td(f"{int(c.get('allocated_u') or 0):,}"),
                    html.Td(fmt_tl(_potential(c.get("allocated_u")))),
                    html.Td(f"{int(c.get('used_u') or 0):,}"),
                ]))
        alloc_table = dmc.Table(
            striped=True, highlightOnHover=True, verticalSpacing=4,
            children=[
                html.Thead(html.Tr([html.Th(h) for h in (
                    "Customer", "Racks", "Allocated U",
                    "Potential (TL) — Allocated", "Used U")])),
                html.Tbody(rows),
            ])
    else:
        alloc_table = dmc.Text(
            "No dedicated (external customer) colocation racks in this DC.",
            size="xs", c="#98A2B3")

    if internal:
        int_rows = [
            html.Tr([
                html.Td(dmc.Text(r.get("tenant", ""), size="xs")),
                html.Td(", ".join(r.get("racks", []) or [])),
                html.Td(f"{int(r.get('used_u') or 0):,}"),
                html.Td(fmt_tl(r.get("potential_tl"))),
            ])
            for r in internal
        ]
        int_table = dmc.Table(
            striped=True, highlightOnHover=True, verticalSpacing=4,
            children=[
                html.Thead(html.Tr([html.Th(h) for h in (
                    "Resource", "Rack", "Used U", "Potential (TL) — Used")])),
                html.Tbody(int_rows),
            ])
    else:
        int_table = dmc.Text("No internal (Bulutistan) colocation racks in this DC.",
                             size="xs", c="#98A2B3")

    return html.Div(id="fm-coloc-panel", children=[
        dmc.Stack(gap="lg", children=[
            html.Div([
                dmc.Text("Dedicated Customers", fw=700, size="sm", c="#101828"),
                dmc.Text("Rack allocation (NetBox role + tenant/tag/description) · "
                         "Potential at list price for Allocated U, not billed revenue",
                         size="xs", c="#667085", mb="xs"),
                dmc.Text("Select a customer to highlight their racks on the map.",
                         size="xs", c="#98A2B3", mb="xs"),
                html.Div(style={"overflowX": "auto"}, children=alloc_table),
            ]),
            html.Div([
                dmc.Text("Internal Resources", fw=700, size="sm", c="#101828"),
                dmc.Text("Bulutistan-owned rack footprint · Potential at list price, "
                         "not billed revenue — opportunity cost of self-occupied U",
                         size="xs", c="#667085", mb="xs"),
                html.Div(style={"overflowX": "auto"}, children=int_table),
            ]),
        ]),
    ])
```

In `build_floor_map_layout`, fetch the payload beside the existing occupancy fetch:

```python
    try:
        _coloc = api.get_colocation(dc_id) or {}
    except Exception:  # noqa: BLE001
        _logger.warning("build_floor_map_layout: get_colocation failed for %s", dc_id,
                        exc_info=True)
        _coloc = {}
```

and replace the right column's empty-state `children=[...]` with
`children=[build_colocation_customer_panel(_coloc)]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_floor_map_customer_panel.py -v`
Expected: PASS — 7 tests

- [ ] **Step 5: Commit**

```bash
git add src/pages/floor_map.py tests/test_floor_map_customer_panel.py
git commit -m "feat(floor-map): rack-level CRM allocation + potential panel in the right column"
```

---

### Task 7: Customer → rack highlighting, and back-to-list from rack detail

**Files:**
- Modify: `app.py` — customer-row callback (new), `show_rack_detail` (~line 1969)
- Test: `tests/test_floor_map_highlight.py`

**Interfaces:**
- Consumes: `fm-selected-customer` store and `{"type": "fm-coloc-customer-row", "index": name}` ids (Tasks 5, 6); `build_colocation_customer_panel` (Task 6).
- Produces: `resolve_customer_highlight(customer, allocation) -> dict | None` in `src/pages/floor_map.py` — `{"customer": str, "racks": [str]}` or `None` when re-selecting the same customer (toggle off).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_floor_map_highlight.py
from src.pages import floor_map as fm

ALLOCATION = [
    {"customer": "BOYNER", "rack_count": 2, "allocated_u": 94,
     "used_u": 60, "racks": ["104", "105"]},
    {"customer": "AKSIGORTA", "rack_count": 1, "allocated_u": 47,
     "used_u": 12, "racks": ["210"]},
]


def test_selecting_a_customer_returns_exactly_their_racks():
    result = fm.resolve_customer_highlight("BOYNER", ALLOCATION, current=None)
    assert result == {"customer": "BOYNER", "racks": ["104", "105"]}


def test_reselecting_the_same_customer_clears_the_highlight():
    current = {"customer": "BOYNER", "racks": ["104", "105"]}
    assert fm.resolve_customer_highlight("BOYNER", ALLOCATION, current=current) is None


def test_switching_customers_replaces_rather_than_merges():
    current = {"customer": "BOYNER", "racks": ["104", "105"]}
    result = fm.resolve_customer_highlight("AKSIGORTA", ALLOCATION, current=current)
    assert result == {"customer": "AKSIGORTA", "racks": ["210"]}


def test_unknown_customer_clears_rather_than_highlighting_everything():
    assert fm.resolve_customer_highlight("NOBODY", ALLOCATION, current=None) is None


def test_customer_with_no_racks_clears():
    alloc = [{"customer": "GHOST", "rack_count": 0, "allocated_u": 0,
              "used_u": 0, "racks": []}]
    assert fm.resolve_customer_highlight("GHOST", alloc, current=None) is None


def test_highlighted_racks_get_an_outline_on_the_figure():
    racks = [{"id": "R1", "name": "104", "status": "active",
              "u_height": 47, "hall_name": "DH7"}]
    fig = fm.build_floor_map_figure(racks, dc_id="DC13", occupancy={"104": 20},
                                    highlight={"104"})
    outlines = [s for s in fig.layout.shapes
                if s.get("line") and s["line"].get("color") == "#4318FF"]
    assert len(outlines) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_floor_map_highlight.py -v`
Expected: FAIL — `AttributeError: module 'src.pages.floor_map' has no attribute 'resolve_customer_highlight'`

- [ ] **Step 3a: Add the resolver**

Add to `src/pages/floor_map.py`:

```python
def resolve_customer_highlight(customer, allocation, current=None):
    """Which racks to outline when a customer row is clicked.

    Returns None -- clear -- when the same customer is clicked again (toggle
    off), when the name is unknown, or when the customer holds no racks.
    Selecting a second customer replaces the first rather than merging: two
    highlighted customers cannot be told apart by a single outline colour.
    """
    if not customer:
        return None
    if (current or {}).get("customer") == customer:
        return None
    for row in allocation or []:
        if row.get("customer") == customer:
            racks = [r for r in (row.get("racks") or []) if r]
            return {"customer": customer, "racks": racks} if racks else None
    return None
```

- [ ] **Step 3b: Wire the click callback**

Add to `app.py`:

```python
@app.callback(
    dash.Output("fm-selected-customer", "data"),
    dash.Input({"type": "fm-coloc-customer-row", "index": ALL}, "n_clicks"),
    dash.State("fm-selected-customer", "data"),
    dash.State("selected-building-dc-store", "data"),
    prevent_initial_call=True,
)
def select_colocation_customer(n_clicks_list, current, dc_store):
    if not any(n_clicks_list or []):
        return dash.no_update
    triggered = dash.callback_context.triggered_id
    if not triggered:
        return dash.no_update
    customer = triggered.get("index")
    dc_id = (dc_store or {}).get("dc_id", "")

    from src.pages.floor_map import resolve_customer_highlight

    allocation = (api.get_colocation(dc_id) or {}).get("allocation", []) or []
    return resolve_customer_highlight(customer, allocation, current=current)
```

- [ ] **Step 3c: Give rack detail a way back**

In `show_rack_detail`, prepend a back button to the returned `html.Div`'s children:

```python
            dmc.Button(
                "Back to customers",
                id="fm-back-to-customers",
                variant="subtle", color="gray", size="xs", mb="xs",
                leftSection=DashIconify(icon="solar:arrow-left-linear", width=14),
            ),
```

and add the callback that restores the default panel:

```python
@app.callback(
    dash.Output("floor-map-rack-detail", "children", allow_duplicate=True),
    dash.Input("fm-back-to-customers", "n_clicks"),
    dash.State("selected-building-dc-store", "data"),
    prevent_initial_call=True,
)
def back_to_colocation_panel(n_clicks, dc_store):
    if not n_clicks:
        return dash.no_update
    from src.pages.floor_map import build_colocation_customer_panel

    dc_id = (dc_store or {}).get("dc_id", "")
    return build_colocation_customer_panel(api.get_colocation(dc_id) or {})
```

Add `allow_duplicate=True` to the existing `show_rack_detail` Output as well, since two callbacks now write that target.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_floor_map_highlight.py -v`
Expected: PASS — 6 tests

- [ ] **Step 5: Commit**

```bash
git add src/pages/floor_map.py app.py tests/test_floor_map_highlight.py
git commit -m "feat(floor-map): highlight a customer's racks from the allocation table"
```

---

### Task 8: Finish the English relabel and repair the stale legend test

**Files:**
- Modify: `src/pages/floor_map.py` — `_rack_fill_info` (~line 172), header subtitle
- Modify: `app.py` — `show_rack_detail` "Dedike:" badge (~line 2020)
- Modify: `tests/test_floor_map_legend.py`
- Test: `tests/test_floor_map_legend.py` (repaired), `tests/test_floor_map_english_copy.py` (new)

**Interfaces:**
- Consumes: `build_lens_legend` (Task 4).
- Produces: no new symbols; `_rack_fill_info` returns English `label` values (`Unknown`, `Fully free`, `Nearly full`, `Moderate`, `Space available`).

- [ ] **Step 1: Write the failing tests**

Replace the body of `tests/test_floor_map_legend.py`:

```python
# tests/test_floor_map_legend.py
from unittest.mock import patch

from src.pages import floor_map as fm


def test_legend_uses_fill_based_labels():
    racks = [{"id": "R1", "name": "104", "status": "active",
              "u_height": 47, "hall_name": "DH7"}]
    with patch.object(fm, "_fetch_rack_occupancy", return_value={}):
        layout = str(fm.build_floor_map_layout("DC13", "DC13", racks))
    for label in ("Fully free (sellable)", "Space available", "Moderate",
                  "Nearly full", "Closed / inactive", "Unknown"):
        assert label in layout
```

And add:

```python
# tests/test_floor_map_english_copy.py
from unittest.mock import patch

from src.pages import floor_map as fm

TURKISH = ("Tamamen boş", "Satılabilir alan var", "Çok dolu", "Kapalı / Pasif",
           "Bilinmiyor", "Doluluk", "Dedike", "boş", "Orta")


def test_rack_fill_info_labels_are_english():
    assert fm._rack_fill_info(None, 47)["label"] == "Unknown"
    assert fm._rack_fill_info(0, 47)["label"] == "Fully free"
    assert fm._rack_fill_info(46, 47)["label"] == "Nearly full"
    assert fm._rack_fill_info(30, 47)["label"] == "Moderate"
    assert fm._rack_fill_info(5, 47)["label"] == "Space available"


def test_floor_map_layout_carries_no_turkish_copy():
    racks = [{"id": "R1", "name": "104", "status": "active",
              "u_height": 47, "hall_name": "DH7"}]
    with patch.object(fm, "_fetch_rack_occupancy", return_value={}):
        layout = str(fm.build_floor_map_layout("DC13", "DC13", racks))
    for word in TURKISH:
        assert word not in layout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_floor_map_legend.py tests/test_floor_map_english_copy.py -v`
Expected: FAIL — `assert 'Unknown' == 'Bilinmiyor'`

- [ ] **Step 3: Translate the strings**

In `_rack_fill_info`, replace the label values:

```python
    if occupied_u is None:
        return {"occupied": None, "total": total, "free": None, "pct": None,
                "label": "Unknown"}
    ...
    if occ == 0:
        label = "Fully free"
    elif pct > 80:
        label = "Nearly full"
    elif pct >= 50:
        label = "Moderate"
    else:
        label = "Space available"
```

In `app.py`'s `show_rack_detail`, replace the badge label:

```python
            dmc.Text("Dedicated:", size="xs", c="#667085", fw=600),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_floor_map_legend.py tests/test_floor_map_english_copy.py -v`
Expected: PASS — 3 tests

- [ ] **Step 5: Commit**

```bash
git add src/pages/floor_map.py app.py tests/test_floor_map_legend.py tests/test_floor_map_english_copy.py
git commit -m "fix(floor-map): finish the English relabel, repair the stale legend test"
```

---

### Task 9: Globe — Health→Load rename and dead-code removal

**Files:**
- Modify: `src/pages/global_view.py` — lines 261-281, 312-505 (delete), 516-535, 630-665, 1143-1229
- Modify: `dash_globe_component/src/lib/components/DashGlobe.react.js` (~line 66)
- Test: `tests/test_globe_load_rename.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `_build_globe_data` emits `load` instead of `health`; `_create_map_figure`, `_health_colors` and the `plotly.graph_objects`/`random` imports are gone.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_globe_load_rename.py
import inspect

from src.pages import global_view as gv

SUMMARIES = [{"id": "DC13", "site_name": "ISTANBUL", "name": "DC13",
              "stats": {"used_cpu_pct": 60.0, "used_ram_pct": 80.0},
              "vm_count": 100, "host_count": 10}]


def test_globe_points_carry_load_not_health():
    point = gv._build_globe_data(SUMMARIES)[0]
    assert point["load"] == 70.0
    assert "health" not in point


def test_dead_plotly_globe_and_its_fabricated_ping_are_gone():
    # _create_map_figure has been unreachable since the MapLibre migration
    # (3eb55fe8) and generated random "Ping: N ms" values for a hover popup.
    assert not hasattr(gv, "_create_map_figure")
    assert not hasattr(gv, "_health_colors")
    source = inspect.getsource(gv)
    assert "random" not in source
    assert "Ping" not in source


def test_badges_say_load_not_health():
    source = inspect.getsource(gv)
    assert "% Health" not in source
    assert "% Load" in source


def test_globe_free_u_label_is_english():
    source = inspect.getsource(gv)
    assert "U boş" not in source
    assert "U free" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_globe_load_rename.py -v`
Expected: FAIL — `KeyError: 'load'`

- [ ] **Step 3: Apply the rename and deletion**

1. In `_build_globe_data`: rename the local `health` to `load` and emit `"load": round(load, 1)` in place of `"health"`.
2. Delete `_health_colors` (lines 286-311) and `_create_map_figure` (lines 312-505) entirely. Remove the now-unused `import plotly.graph_objects as go` and `import random` from the module header.
3. In `_build_region_menu` (~line 523) rename `region_health` / `avg_health` to `region_load` / `avg_load`.
4. In `build_region_detail_panel` (~line 630) and `build_dc_info_card` (~line 1143): rename `health_val`/`health_color` to `load_val`/`load_color`, and change both badge texts from `f"{health_val:.0f}% Health"` to `f"{load_val:.0f}% Load"`.
5. At line 1229 change `f"{coloc_free}U boş"` to `f"{coloc_free}U free"`.
6. In `DashGlobe.react.js`, change `const health = d.health != null ? ... : '—';` to read `d.load`, keeping the popup's existing "Avg Load" label.

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/test_globe_load_rename.py tests/test_globe_colocation_ring.py tests/test_global_view_prefetch.py -v`
Expected: PASS — all green

- [ ] **Step 5: Commit**

```bash
git add src/pages/global_view.py dash_globe_component/src/lib/components/DashGlobe.react.js tests/test_globe_load_rename.py
git commit -m "refactor(globe): rename Health to Load, delete the dead Plotly globe and its fake ping"
```

---

### Task 10: Full-suite verification

**Files:** none modified.

- [ ] **Step 1: Run the whole GUI suite**

Run:
```bash
/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/ -q -p no:randomly \
  --ignore=tests/test_backup_sidebar_helpers.py \
  --ignore=tests/test_zabbix_query_deduplication.py
```
Expected: **25 failures, no more.** The two ignored files and the 25 failures are pre-existing on `main`. Any new name in the failure list is yours — fix it before proceeding.

- [ ] **Step 2: Run the datacenter-api suite**

Run: `cd services/datacenter-api && /Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python -m pytest tests/ -q`
Expected: PASS, with the 12 new rack-load tests included.

- [ ] **Step 3: Record the load-coverage measurement**

The design's one unmeasured assumption is the NetBox `device.name` ↔ host-name hit rate (Docker was down at design time). Once the stack is up:

```bash
curl -s localhost:8002/api/v1/datacenters/DC13/racks/load | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d['summary'])"
```

Record `monitored_racks / total_racks` in the KB. If monitored is near zero, the Load lens is honest but useless — report the number rather than shipping quietly.

- [ ] **Step 4: Commit any fixes and report**

```bash
git add -A && git commit -m "test(task-63): full-suite verification"
```

---

## Self-Review

**Spec coverage:** §2 rename → Task 9. §3 lens switch → Tasks 4, 5. §4 load data → Tasks 1, 2, 3. §5 right panel → Task 6; highlighting → Task 7. §6 globe alignment → Task 9. §1 gaps 4 (Turkish) → Task 8; gap 5 (dead code) → Task 9; gap 6 (stale test) → Task 8. §8 coverage measurement → Task 10 Step 3. §9 test strategy → assertions distributed across Tasks 1, 4, 5, 6, 7.

**Type consistency:** `build_floor_map_figure(racks, dc_id, occupancy, load, lens, highlight)` is used with the same keywords in Tasks 5 and 7. `_fetch_rack_load` returns `{rack_name: row}` (Task 5) and `_collect_rack` reads `.get("load_pct")` off that row. `resolve_customer_highlight` returns `{"customer", "racks"}`, which the Task 5 callback reads as `(selected_customer or {}).get("racks")`. The endpoint's `load_pct`/`monitored_devices`/`total_devices` keys are produced in Task 1 and consumed unchanged in Tasks 2, 5.

**Known ordering constraint:** Task 5 introduces `fm-selected-customer`; Task 7 populates it. Executing 7 before 5 leaves a dangling store id.
