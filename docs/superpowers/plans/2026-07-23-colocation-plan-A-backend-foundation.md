# Colocation Plan A — Backend Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the canonical colocation rack-occupancy computation as a shared module and expose it from datacenter-api (bulk per-rack endpoint + per-DC aggregate), so every downstream layer reads correct, identical used/free-U numbers.

**Architecture:** A single shared SQL module `shared/colocation/occupancy.py` holds the prod-verified occupancy query (front-face distinct U-slots over the current `discovery_*` tables). datacenter-api's `DatabaseService` gains `get_dc_racks_occupancy(dc_code)` (6h singleflight-cached, mirroring `get_dc_racks`) and a `get_colocation_aggregate()` for per-DC rollups, surfaced via a new bulk endpoint and folded into the DC summary payload.

**Tech Stack:** Python 3.11, psycopg2, FastAPI, pytest. bulutlake Postgres (host `10.134.16.6:5000`, read-only role — no DDL).

## Global Constraints

- **Working directory is the worktree** `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.claude/worktrees/task-62-colocation-viz`. Do all work and commits here; never cd to the main checkout.
- Python interpreter for all tests: `.venv/bin/python` (a symlink to the main checkout's venv, Python 3.11.15). System `python3` is 3.9 and breaks the suite. Let `WT` = the worktree root above.
- **datacenter-api test command** (run from the service dir, `shared/` needs the repo root on PYTHONPATH):
  `cd services/datacenter-api && PYTHONPATH="$WT" ../../.venv/bin/python -m pytest tests/ -v --tb=short -p no:cacheprovider`
  (or a single file: `... -m pytest tests/test_xyz.py -v`). The trailing atexit "I/O operation on closed file" logging line is harmless scheduler-shutdown noise, not a failure.
- **Shared-module unit tests** run from the worktree root: `.venv/bin/python -m pytest tests/test_colocation_occupancy.py -v`.
- **Baseline (pre-existing, NOT yours):** the datacenter-api suite has **2 pre-existing failures unrelated to colocation** — `test_dc_service_host_rows_slice.py::test_classic_host_rows_single_sql_for_cluster_subsets` and `test_host_rows.py::test_datastore_metrics_excludes_backup_datastores` (host-rows/datastore, present before any change). Do not try to fix them; just don't INCREASE the failure count. Full-suite success criterion for this plan = `254 passed` minus those 2 = your new tests pass and nothing else regresses.
- **No DDL.** The app connects to bulutlake read-only; never emit `CREATE`/`ALTER`. Occupancy lives in Python, not a DB view.
- **Current tables only:** `discovery_loki_rack`, `discovery_netbox_inventory_device`, `loki_device_types`, `discovery_loki_location`. Never use `loki_devices`/`loki_racks`/`discovery_loki_racks`/`discovery_netbox_inventory_device_type` (stale or nonexistent).
- Occupancy correctness invariant: `used_u` MUST never exceed `capacity_u` for any rack (verified over_cap=0).
- Rack endpoints carry NO `TimeFilter` (racks aren't time-scoped). Router is mounted under `/api/v1`. Handlers are sync `def` with `db: DatabaseService = Depends(get_db)`.
- Cache pattern for rack service methods: `cache.get(key)` then `cache.run_singleflight(key, _fetch, ttl=21600)` (6h); `OperationalError` → return the empty shape.

---

### Task 1: Shared canonical occupancy module

**Files:**
- Create: `shared/colocation/__init__.py`
- Create: `shared/colocation/occupancy.py`
- Test: `tests/test_colocation_occupancy.py`

**Interfaces:**
- Produces:
  - `OCCUPANCY_SQL: str` — named param `%(dc_pattern)s` (str glob like `%DC13%`, or `None` for all racks).
  - `OCCUPANCY_COLUMNS: tuple[str, ...]` = `("rack_id","rack_name","dc","hall","capacity_u","used_u","free_u","tenants")`.
  - `row_to_dict(row: Sequence[Any]) -> dict`
  - `occupancy_rows(cursor, dc_pattern: str | None = None) -> list[dict]`
  - `aggregate_by_dc(rows: Sequence[dict]) -> dict[str, dict]` → per-DC `{total_u, used_u, free_u, rack_count}`.
  - `is_internal_tenant(name: str) -> bool` (Bulutistan-own infra vs external customer).
  - `INTERNAL_TENANT_PREFIXES: tuple[str, ...]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_colocation_occupancy.py
"""Canonical colocation occupancy module — the single source of truth for
used/free rack-U. Verified against prod (over_capacity=0) on 2026-07-23."""
from shared.colocation import occupancy as occ


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = None

    def execute(self, sql, params=None):
        self.executed = (sql, params)

    def fetchall(self):
        return self._rows


def test_sql_uses_current_tables_only():
    sql = occ.OCCUPANCY_SQL.lower()
    assert "discovery_netbox_inventory_device" in sql
    assert "loki_device_types" in sql
    assert "discovery_loki_rack" in sql
    assert "discovery_loki_location" in sql
    # The stale / nonexistent tables must never appear.
    assert "loki_devices" not in sql
    assert "discovery_loki_racks" not in sql
    assert "discovery_netbox_inventory_device_type" not in sql


def test_sql_scopes_by_name_and_site_and_front_face():
    sql = occ.OCCUPANCY_SQL.lower()
    assert "s.rack_name = r.rack_name" in sql
    assert "coalesce(s.site_name, '') = coalesce(r.site_name, '')" in sql
    assert "in ('front', '')" in sql
    assert "coalesce(l.parent_name, l.name)" in sql  # DC label


def test_row_to_dict_maps_and_coerces():
    row = ("R1", "116", "DC13", "DH1", 47, 35, 12, ["Boyner", "Bulutistan - Linux TEAM"])
    d = occ.row_to_dict(row)
    assert d == {
        "rack_id": "R1", "rack_name": "116", "dc": "DC13", "hall": "DH1",
        "capacity_u": 47, "used_u": 35, "free_u": 12,
        "tenants": ["Boyner", "Bulutistan - Linux TEAM"],
    }


def test_row_to_dict_handles_nulls():
    d = occ.row_to_dict(("R2", "117", "DC13", None, 47, None, None, None))
    assert d["used_u"] == 0 and d["free_u"] == 0 and d["tenants"] == []


def test_occupancy_rows_executes_with_dc_pattern():
    cur = _FakeCursor([("R1", "116", "DC13", "DH1", 47, 35, 12, ["Boyner"])])
    rows = occ.occupancy_rows(cur, dc_pattern="%DC13%")
    assert cur.executed[1] == {"dc_pattern": "%DC13%"}
    assert rows[0]["rack_name"] == "116" and rows[0]["free_u"] == 12


def test_aggregate_by_dc_rolls_up():
    rows = [
        {"dc": "DC13", "capacity_u": 47, "used_u": 35, "free_u": 12},
        {"dc": "DC13", "capacity_u": 47, "used_u": 20, "free_u": 27},
        {"dc": "DC14", "capacity_u": 45, "used_u": 10, "free_u": 35},
    ]
    agg = occ.aggregate_by_dc(rows)
    assert agg["DC13"] == {"total_u": 94, "used_u": 55, "free_u": 39, "rack_count": 2}
    assert agg["DC14"] == {"total_u": 45, "used_u": 10, "free_u": 35, "rack_count": 1}


def test_is_internal_tenant():
    assert occ.is_internal_tenant("Bulutistan - Virtualization")
    assert occ.is_internal_tenant("Bulut Broker")
    assert occ.is_internal_tenant("CPE-Tenant")
    assert not occ.is_internal_tenant("AytemizBank")
    assert not occ.is_internal_tenant("Boyner")
    assert not occ.is_internal_tenant("")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_colocation_occupancy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shared.colocation'`.

- [ ] **Step 3: Write the module**

```python
# shared/colocation/__init__.py
```
(empty file)

```python
# shared/colocation/occupancy.py
"""Canonical colocation rack-occupancy computation — the single source of truth.

Imported by datacenter-api (endpoints) and customer-api (dc_hosting_u sellable)
so "used vs free U" can never diverge.

Verified read-only against bulutlake 2026-07-23: over_capacity = 0 across 234
racks (total 10,745 U / used 3,998 / free 6,747).

Data model (see the TASK-62 spec §5):
  * CURRENT tables only. The legacy loki_devices/loki_racks timeseries are stale
    (last collected 2026-04-12); discovery_* is the live snapshot.
  * device->rack scoped by (rack_name, site_name): rack names are non-unique
    (182 names / 234 racks) and the two NetBox snapshots use disjoint rack_id
    spaces (0 matches), so neither rack_id nor rack_name-alone is a safe key.
  * used_u = count of distinct FRONT-face U-slots occupied. A device at U=p with
    height h occupies [p .. p+h-1]; COUNT(DISTINCT u) over generate_series caps
    at capacity and absorbs chassis-child overlaps.
"""
from __future__ import annotations

from typing import Any, Sequence

# One row per rack. %(dc_pattern)s: a str glob (e.g. '%DC13%') or None for all.
OCCUPANCY_SQL = """
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
rack AS (
    SELECT r.id            AS rack_id,
           r.name          AS rack_name,
           r.u_height::int AS capacity_u,
           l.site_name     AS site_name,
           l.name          AS hall,
           COALESCE(l.parent_name, l.name) AS dc
    FROM discovery_loki_rack r
    LEFT JOIN discovery_loki_location l ON l.id::varchar = r.location_id
)
SELECT r.rack_id,
       r.rack_name,
       r.dc,
       r.hall,
       r.capacity_u,
       COUNT(DISTINCT s.u) FILTER (WHERE s.u BETWEEN 1 AND r.capacity_u) AS used_u,
       GREATEST(
           r.capacity_u
           - COUNT(DISTINCT s.u) FILTER (WHERE s.u BETWEEN 1 AND r.capacity_u),
           0
       ) AS free_u,
       ARRAY_AGG(DISTINCT s.tenant_name)
           FILTER (WHERE s.tenant_name IS NOT NULL AND btrim(s.tenant_name) <> '') AS tenants
FROM rack r
LEFT JOIN dev_slots s
    ON s.rack_name = r.rack_name
   AND COALESCE(s.site_name, '') = COALESCE(r.site_name, '')
WHERE (%(dc_pattern)s IS NULL OR COALESCE(r.dc, '') ILIKE %(dc_pattern)s)
GROUP BY r.rack_id, r.rack_name, r.dc, r.hall, r.capacity_u
ORDER BY r.dc, r.rack_name
"""

OCCUPANCY_COLUMNS = (
    "rack_id", "rack_name", "dc", "hall", "capacity_u", "used_u", "free_u", "tenants",
)

# Tenants that are Bulutistan's own infrastructure, not external colocation
# customers. Matched case-insensitively as a prefix. (Verified prod tenants:
# the "Bulutistan - *" buckets, "Bulut Broker", "CPE-Tenant", switch fabrics.)
INTERNAL_TENANT_PREFIXES = (
    "bulutistan", "bulut broker", "cpe-tenant", "dc11 arista",
)


def row_to_dict(row: Sequence[Any]) -> dict:
    """Map one OCCUPANCY_SQL row tuple to a dict with coerced numeric fields."""
    d = {col: (row[i] if i < len(row) else None) for i, col in enumerate(OCCUPANCY_COLUMNS)}
    d["capacity_u"] = int(d.get("capacity_u") or 0)
    d["used_u"] = int(d.get("used_u") or 0)
    d["free_u"] = int(d.get("free_u") or 0)
    d["tenants"] = list(d.get("tenants") or [])
    return d


def occupancy_rows(cursor, dc_pattern: str | None = None) -> list[dict]:
    """Execute OCCUPANCY_SQL on an open cursor and return per-rack dicts."""
    cursor.execute(OCCUPANCY_SQL, {"dc_pattern": dc_pattern})
    return [row_to_dict(r) for r in (cursor.fetchall() or [])]


def aggregate_by_dc(rows: Sequence[dict]) -> dict:
    """Roll per-rack rows up to per-DC totals."""
    out: dict = {}
    for r in rows:
        dc = r.get("dc") or "UNKNOWN"
        agg = out.setdefault(dc, {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0})
        agg["total_u"] += int(r.get("capacity_u") or 0)
        agg["used_u"] += int(r.get("used_u") or 0)
        agg["free_u"] += int(r.get("free_u") or 0)
        agg["rack_count"] += 1
    return out


def is_internal_tenant(name: str) -> bool:
    """True when the tenant is Bulutistan-internal (excluded from the customer view)."""
    key = (name or "").strip().lower()
    return any(key.startswith(p) for p in INTERNAL_TENANT_PREFIXES)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_colocation_occupancy.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add shared/colocation/__init__.py shared/colocation/occupancy.py tests/test_colocation_occupancy.py
git commit -m "feat(colocation): canonical rack-occupancy SQL module (single source of truth)"
```

---

### Task 2: datacenter-api `get_dc_racks_occupancy` service method

**Files:**
- Modify: `services/datacenter-api/app/services/dc_service.py` (add method on `DatabaseService`, near `get_dc_racks` ~7475)
- Test: `services/datacenter-api/tests/test_colocation_occupancy_service.py`

**Interfaces:**
- Consumes: `shared.colocation.occupancy.occupancy_rows`, `aggregate_by_dc`; `cache.get`/`cache.run_singleflight`; `self._get_connection`.
- Produces: `DatabaseService.get_dc_racks_occupancy(dc_code: str) -> dict` →
  `{"racks": [ {rack_id, rack_name, dc, hall, capacity_u, used_u, free_u, tenants[]} ], "summary": {total_u, used_u, free_u, rack_count}}`.

- [ ] **Step 1: Write the failing test**

```python
# services/datacenter-api/tests/test_colocation_occupancy_service.py
"""get_dc_racks_occupancy: 6h singleflight cache; delegates the math to the
shared colocation module; DB-down returns the empty shape."""
from unittest.mock import patch

from psycopg2 import OperationalError

from app.services.dc_service import DatabaseService


def _svc_no_db():
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool",
               side_effect=OperationalError("no db")):
        return DatabaseService()


def test_occupancy_cache_miss_uses_singleflight_6h_ttl():
    svc = _svc_no_db()
    fake = {"racks": [], "summary": {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0}}
    with patch("app.services.dc_service.cache.get", return_value=None), \
         patch("app.services.dc_service.cache.run_singleflight", return_value=fake) as sf:
        result = svc.get_dc_racks_occupancy("DC13")
    assert result == fake
    assert sf.call_count == 1
    assert sf.call_args[1].get("ttl") == 21600


def test_occupancy_cache_hit_short_circuits():
    svc = _svc_no_db()
    cached = {"racks": [{"rack_name": "116"}], "summary": {}}
    with patch("app.services.dc_service.cache.get", return_value=cached), \
         patch("app.services.dc_service.cache.run_singleflight") as sf:
        result = svc.get_dc_racks_occupancy("DC13")
    assert result == cached
    sf.assert_not_called()


def test_occupancy_blank_dc_returns_empty():
    svc = _svc_no_db()
    result = svc.get_dc_racks_occupancy("   ")
    assert result == {"racks": [], "summary": {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/datacenter-api && ../../.venv/bin/python -m pytest tests/test_colocation_occupancy_service.py -v`
Expected: FAIL with `AttributeError: 'DatabaseService' object has no attribute 'get_dc_racks_occupancy'`.

- [ ] **Step 3: Add the method**

Add near the top of `dc_service.py` imports (with the other `from shared...` imports, e.g. after line 22 `from app.db.queries import discovery_rack as drq`):

```python
from shared.colocation import occupancy as coloc_occ
```

Add the method to `DatabaseService` (place it right after `get_dc_racks`, ~line 7523):

```python
    def get_dc_racks_occupancy(self, dc_code: str) -> dict:
        """Per-rack colocation occupancy for a DC via the shared canonical SQL.

        Returns {"racks": [...], "summary": {total_u, used_u, free_u, rack_count}}.
        Each rack: rack_id, rack_name, dc, hall, capacity_u, used_u, free_u, tenants[].
        """
        empty = {"racks": [], "summary": {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0}}
        if not dc_code or not dc_code.strip():
            return empty
        code = dc_code.strip()
        cache_key = f"dc_racks_occupancy:{code}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        def _fetch():
            pattern = f"%{code}%"
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = coloc_occ.occupancy_rows(cur, dc_pattern=pattern)
            agg = coloc_occ.aggregate_by_dc(rows)
            total = {"total_u": 0, "used_u": 0, "free_u": 0, "rack_count": 0}
            for dc_agg in agg.values():
                for k in total:
                    total[k] += dc_agg[k]
            return {"racks": rows, "summary": total}

        try:
            return cache.run_singleflight(cache_key, _fetch, ttl=21600)
        except OperationalError as exc:
            logger.error("DB unavailable for get_dc_racks_occupancy(%s): %s", code, exc)
            return empty
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/datacenter-api && ../../.venv/bin/python -m pytest tests/test_colocation_occupancy_service.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add services/datacenter-api/app/services/dc_service.py services/datacenter-api/tests/test_colocation_occupancy_service.py
git commit -m "feat(datacenter-api): get_dc_racks_occupancy service method"
```

---

### Task 3: datacenter-api bulk occupancy endpoint

**Files:**
- Modify: `services/datacenter-api/app/routers/datacenters.py` (add route next to the existing rack routes ~339-346)
- Test: `services/datacenter-api/tests/test_colocation_occupancy_endpoint.py`

**Interfaces:**
- Consumes: `DatabaseService.get_dc_racks_occupancy` (Task 2).
- Produces: `GET /api/v1/datacenters/{dc_code}/racks/occupancy` → the Task-2 dict.

- [ ] **Step 1: Write the failing test**

```python
# services/datacenter-api/tests/test_colocation_occupancy_endpoint.py
"""Bulk occupancy endpoint delegates to DatabaseService.get_dc_racks_occupancy."""


def test_occupancy_endpoint_delegates(client, mock_db):
    payload = {
        "racks": [{"rack_name": "116", "capacity_u": 47, "used_u": 35, "free_u": 12, "tenants": ["Boyner"]}],
        "summary": {"total_u": 47, "used_u": 35, "free_u": 12, "rack_count": 1},
    }
    mock_db.get_dc_racks_occupancy.return_value = payload
    r = client.get("/api/v1/datacenters/DC13/racks/occupancy")
    assert r.status_code == 200
    assert r.json() == payload
    mock_db.get_dc_racks_occupancy.assert_called_once_with("DC13")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/datacenter-api && ../../.venv/bin/python -m pytest tests/test_colocation_occupancy_endpoint.py -v`
Expected: FAIL — 404 (route missing) or `AttributeError` on the mock.

- [ ] **Step 3: Add the route**

In `datacenters.py`, immediately after the `rack_devices` handler (~line 346), add:

```python
@router.get("/datacenters/{dc_code}/racks/occupancy", response_model=dict[str, Any])
def dc_racks_occupancy(dc_code: str, db: DatabaseService = Depends(get_db)):
    """Bulk per-rack colocation occupancy (capacity/used/free U + tenants) for a DC."""
    return db.get_dc_racks_occupancy(dc_code)
```

Note: FastAPI matches the more specific literal `/racks/occupancy` before the `/racks/{rack_name}/devices` param route regardless of declaration order, but declaring it adjacent keeps them together.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/datacenter-api && ../../.venv/bin/python -m pytest tests/test_colocation_occupancy_endpoint.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add services/datacenter-api/app/routers/datacenters.py services/datacenter-api/tests/test_colocation_occupancy_endpoint.py
git commit -m "feat(datacenter-api): bulk /racks/occupancy endpoint"
```

---

### Task 4: Per-DC colocation aggregate helper + summary enrichment

**Files:**
- Modify: `services/datacenter-api/app/services/dc_service.py` (add `get_colocation_aggregate`; enrich `get_all_datacenters_summary`)
- Test: `services/datacenter-api/tests/test_colocation_aggregate.py`

**Interfaces:**
- Consumes: `shared.colocation.occupancy.occupancy_rows`, `aggregate_by_dc`.
- Produces:
  - `DatabaseService.get_colocation_aggregate() -> dict[str, dict]` — `{dc: {total_u, used_u, free_u, rack_count}}`, all DCs in one query, 6h cached.
  - `get_all_datacenters_summary(...)` each DC dict gains `coloc_total_u`, `coloc_used_u`, `coloc_free_u` (0 when the DC has no colocation racks).

**Interface note for Plan C:** the summary DC key used to match aggregate is the DC's `id` (e.g. `"DC13"`); aggregate keys come from `COALESCE(location.parent_name, location.name)`. Match case-insensitively and treat a missing key as zeros.

- [ ] **Step 1: Write the failing test**

```python
# services/datacenter-api/tests/test_colocation_aggregate.py
"""get_colocation_aggregate rolls the shared occupancy rows up per DC (all DCs
in one query); summary enrichment merges coloc_* fields onto each DC dict."""
from unittest.mock import patch

from psycopg2 import OperationalError

from app.services.dc_service import DatabaseService


def _svc_no_db():
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool",
               side_effect=OperationalError("no db")):
        return DatabaseService()


def test_colocation_aggregate_cached_singleflight():
    svc = _svc_no_db()
    fake = {"DC13": {"total_u": 94, "used_u": 55, "free_u": 39, "rack_count": 2}}
    with patch("app.services.dc_service.cache.get", return_value=None), \
         patch("app.services.dc_service.cache.run_singleflight", return_value=fake) as sf:
        out = svc.get_colocation_aggregate()
    assert out == fake
    assert sf.call_args[1].get("ttl") == 21600


def test_enrich_summary_merges_coloc_fields():
    svc = _svc_no_db()
    summaries = [{"id": "DC13", "site_name": "IST"}, {"id": "DC99", "site_name": "X"}]
    agg = {"DC13": {"total_u": 94, "used_u": 55, "free_u": 39, "rack_count": 2}}
    out = svc._merge_colocation_into_summaries(summaries, agg)
    dc13 = next(d for d in out if d["id"] == "DC13")
    dc99 = next(d for d in out if d["id"] == "DC99")
    assert dc13["coloc_total_u"] == 94 and dc13["coloc_used_u"] == 55 and dc13["coloc_free_u"] == 39
    assert dc99["coloc_total_u"] == 0 and dc99["coloc_free_u"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/datacenter-api && ../../.venv/bin/python -m pytest tests/test_colocation_aggregate.py -v`
Expected: FAIL — `AttributeError` (`get_colocation_aggregate` / `_merge_colocation_into_summaries` missing).

- [ ] **Step 3: Add the methods**

Add to `DatabaseService` (after `get_dc_racks_occupancy` from Task 2):

```python
    def get_colocation_aggregate(self) -> dict:
        """Per-DC colocation U rollup for ALL DCs in one query. 6h cached.

        Returns {dc_label: {total_u, used_u, free_u, rack_count}} keyed by
        COALESCE(location.parent_name, location.name).
        """
        cache_key = "colocation_aggregate:all"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        def _fetch():
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = coloc_occ.occupancy_rows(cur, dc_pattern=None)
            return coloc_occ.aggregate_by_dc(rows)

        try:
            return cache.run_singleflight(cache_key, _fetch, ttl=21600)
        except OperationalError as exc:
            logger.error("DB unavailable for get_colocation_aggregate: %s", exc)
            return {}

    @staticmethod
    def _merge_colocation_into_summaries(summaries: list, agg: dict) -> list:
        """Attach coloc_total_u/used_u/free_u to each DC summary dict (0 if absent)."""
        by_upper = {str(k).upper(): v for k, v in (agg or {}).items()}
        for dc in summaries or []:
            key = str(dc.get("id") or "").upper()
            a = by_upper.get(key) or {}
            dc["coloc_total_u"] = int(a.get("total_u") or 0)
            dc["coloc_used_u"] = int(a.get("used_u") or 0)
            dc["coloc_free_u"] = int(a.get("free_u") or 0)
        return summaries
```

Then, in `get_all_datacenters_summary`, immediately before the `return` of the assembled `summaries` list, insert:

```python
            try:
                summaries = self._merge_colocation_into_summaries(
                    summaries, self.get_colocation_aggregate()
                )
            except Exception as exc:  # never let colocation break the summary
                logger.warning("colocation summary enrichment skipped: %s", exc)
```

(If `get_all_datacenters_summary` returns via a cached inner `_fetch`, place this inside that `_fetch` just before its `return`, so the enriched value is cached with the summary. Locate the actual return during implementation and confirm `summaries` is the list variable name.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/datacenter-api && ../../.venv/bin/python -m pytest tests/test_colocation_aggregate.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add services/datacenter-api/app/services/dc_service.py services/datacenter-api/tests/test_colocation_aggregate.py
git commit -m "feat(datacenter-api): per-DC colocation aggregate + summary enrichment"
```

---

### Task 5: Data-contract guard + retire the broken `crm_potential.py` rack path

**Files:**
- Modify: `services/datacenter-api/app/db/queries/crm_potential.py` (fix or remove the broken `discovery_loki_racks` / `discovery_netbox_inventory_device_type` references in the rack CTEs)
- Test: `services/datacenter-api/tests/test_colocation_schema_contract.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: a static guard test ensuring no query string in the colocation path references the stale/nonexistent tables.

**Context:** `crm_potential.py` `DC_SALES_POTENTIAL` (~lines 110-182) references `discovery_loki_racks` (plural, nonexistent) and `discovery_netbox_inventory_device_type` (nonexistent). Since Plan A supersedes rack capacity/used math with the shared module, this dead rack path must not be relied on. Minimal action: delete the `dc_rack_capacity` / `dc_capacity` rack CTEs (and the `total_rack_u`/`used_rack_u`/`free_rack_u` columns) from `DC_SALES_POTENTIAL` if they are unused downstream, OR repoint them at the shared occupancy if used. During implementation, grep for consumers first.

- [ ] **Step 1: Write the failing test**

```python
# services/datacenter-api/tests/test_colocation_schema_contract.py
"""Guard: the colocation/rack SQL must not reference stale or nonexistent tables."""
from app.db.queries import crm_potential
from shared.colocation import occupancy as occ

_FORBIDDEN = ("discovery_loki_racks", "discovery_netbox_inventory_device_type", "loki_devices")


def test_shared_occupancy_sql_has_no_forbidden_tables():
    sql = occ.OCCUPANCY_SQL.lower()
    for bad in _FORBIDDEN:
        assert bad not in sql, f"occupancy SQL references forbidden table {bad}"


def test_crm_potential_has_no_forbidden_rack_tables():
    # Concatenate every module-level SQL string constant and scan it.
    blob = " ".join(
        v for v in vars(crm_potential).values() if isinstance(v, str)
    ).lower()
    for bad in _FORBIDDEN:
        assert bad not in blob, f"crm_potential still references forbidden table {bad}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/datacenter-api && ../../.venv/bin/python -m pytest tests/test_colocation_schema_contract.py -v`
Expected: FAIL — `test_crm_potential_has_no_forbidden_rack_tables` fails (the plural/nonexistent tables are still referenced).

- [ ] **Step 3: Remove the broken rack CTEs**

Grep first: `grep -rn "total_rack_u\|used_rack_u\|free_rack_u\|dc_rack_capacity\|DC_SALES_POTENTIAL" services/datacenter-api services/customer-api src`. If unused downstream (expected — the sellable path is being rebuilt in Plan B), delete the `dc_capacity` and `dc_rack_capacity` CTEs and the three rack columns from `DC_SALES_POTENTIAL` in `crm_potential.py`. If a consumer exists, repoint it to `DatabaseService.get_colocation_aggregate()` instead. Do NOT leave references to `discovery_loki_racks` / `discovery_netbox_inventory_device_type`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/datacenter-api && ../../.venv/bin/python -m pytest tests/test_colocation_schema_contract.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full datacenter-api suite (no regressions)**

Run: `cd services/datacenter-api && ../../.venv/bin/python -m pytest tests/ -v --tb=short`
Expected: all pass (baseline count + the new colocation tests).

- [ ] **Step 6: Commit**

```bash
git add services/datacenter-api/app/db/queries/crm_potential.py services/datacenter-api/tests/test_colocation_schema_contract.py
git commit -m "fix(datacenter-api): retire broken rack CTEs; add colocation schema guard"
```

---

### Task 6: Live SQL smoke check (manual, gated on DB access)

**Files:** none (verification only).

**Purpose:** Confirm `OCCUPANCY_SQL` still returns `over_capacity = 0` against live prod, since the tables are collector-populated and could drift.

- [ ] **Step 1: Run the shared SQL against bulutlake**

```bash
cd /Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI
set -a; . ./.env; set +a
.venv/bin/python - <<'PY'
import os, psycopg2
from shared.colocation.occupancy import occupancy_rows, aggregate_by_dc
conn = psycopg2.connect(host=os.environ["DB_HOST"], port=os.environ["DB_PORT"],
    dbname=os.environ["DB_NAME"], user=os.environ["DB_USER"], password=os.environ["DB_PASS"], connect_timeout=8)
rows = occupancy_rows(conn.cursor())
over = [r for r in rows if r["used_u"] > r["capacity_u"]]
print("racks:", len(rows), "over_capacity:", len(over))
agg = aggregate_by_dc(rows)
for dc, a in sorted(agg.items(), key=lambda kv: -(kv[1]["total_u"]))[:8]:
    print(f"  {dc}: total={a['total_u']} used={a['used_u']} free={a['free_u']} racks={a['rack_count']}")
PY
```

Expected: `over_capacity: 0`; DC13 ≈ total 3616 / free 1799 (values may drift with collectors). If `over_capacity > 0`, STOP — the data model changed; re-investigate before proceeding.

---

## Self-Review

- **Spec coverage:** §5 shared module → Task 1. §6.1 endpoint + aggregate → Tasks 2-4. §3b schema drift → Task 5. §8 data-contract + occupancy math tests → Tasks 1, 5. Live verification → Task 6. ✓
- **Type consistency:** `get_dc_racks_occupancy`/`get_colocation_aggregate` names used identically in service + endpoint + Plan-C interface note. `OCCUPANCY_COLUMNS` order matches `row_to_dict`. ✓
- **Placeholders:** none — every step has runnable code or an exact command. Task 4 Step 3 and Task 5 Step 3 require a grep-confirm of an existing insertion point (unavoidable — the target function body is 300KB away); the code to insert is fully specified. ✓
