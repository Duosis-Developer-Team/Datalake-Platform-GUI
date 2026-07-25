# HMDL Freshness Framework — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Platform-wide data-freshness + automation health for TASK-69: hybrid auto-discovery + curated config over ~167 collected tables, grouped by family, served from a background-refreshed in-process snapshot; automations use the same registry; sidebar/banner reflect data-freshness.

**Architecture:** A pure `freshness_registry` (discovery columns, EXCLUDE, family map, overrides, thresholds). `db/queries/freshness.py` discovers tables from `information_schema` and computes per-table age via `pool.fetch_one`. A background daemon thread (`freshness_snapshot`) recomputes every N minutes into an in-process cache (hmdl-api has no Redis); the endpoint serves the cached snapshot. Automations are refactored to an `AUTOMATION_SPECS` list. GUI shows family rollup cards + drill-down; the sidebar badge/banner add `data_counts.alert`.

**Tech Stack:** Python 3.11, FastAPI, psycopg2 (hmdl-api); Dash + dmc (GUI).

## Global Constraints

- hmdl-api has **no Redis** — cache = in-process module snapshot + daemon thread started in `app/main.py` lifespan.
- Freshness compute must **never run on the request path** (maxing ~120 tables > HTTP timeout). Endpoint serves the snapshot; cold = `data_status:"computing"`.
- Reuse `app.services.automation_health.classify` / `build_data_source_row` / `overall_status_counts`.
- Age computed in SQL (`EXTRACT(EPOCH FROM (now()-max(col)::timestamptz))/3600`), clamp negatives to 0.
- Seed EXCLUDE with known-legacy tables; config is team-refinable via env. Never let curation drop real data — only noise.
- Run tests: hmdl-api `cd services/hmdl-api && PYTHONPATH=<root> ../../.venv/bin/python -m pytest tests/<f>`; GUI `PYTHONPATH=. .venv/bin/python -m pytest tests/<f>`.
- Repo root: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI`.

## File Structure

- `services/hmdl-api/app/services/freshness_registry.py` — NEW pure config + resolve/exclude/family.
- `services/hmdl-api/app/db/queries/freshness.py` — NEW discover_specs + compute_freshness.
- `services/hmdl-api/app/services/freshness_snapshot.py` — NEW in-process snapshot + background refresher.
- `services/hmdl-api/app/config.py` — freshness thresholds + refresh interval + exclude override.
- `services/hmdl-api/app/main.py` — start refresher in lifespan.
- `services/hmdl-api/app/routers/collectors.py` — endpoint serves snapshot (data_families/data_counts/data_status).
- `services/hmdl-api/app/models/schemas.py` — DataFamily + response fields.
- `services/hmdl-api/app/db/queries/automation_health.py` — refactor to AUTOMATION_SPECS.
- `src/pages/settings/integrations/hmdl_automation_health.py` — family rollup cards + drill-down + computing state.
- `src/utils/hmdl_sync_ui.py` + callers — banner/badge include data alert.
- `src/services/api_client.py` — empty fallback gains data_families/data_status.

---

## Phase 1 — Backend

### Task 1: `freshness_registry.py` (pure config + resolve)

**Files:** Create `services/hmdl-api/app/services/freshness_registry.py`; Test `services/hmdl-api/tests/test_freshness_registry.py`

**Interfaces — Produces:**
- `FRESHNESS_COLUMNS: list[str]`
- `is_excluded(table: str) -> bool`
- `family_of(table: str) -> str`
- `resolve(table: str, columns: list[str], *, default_warn: float, default_dead: float) -> dict | None` → `{table,label,family,column,warn_hours,dead_hours}` or None if excluded / no freshness column.

- [ ] **Step 1: Write the failing test**

```python
from app.services import freshness_registry as fr


def test_is_excluded_drops_legacy_loki():
    assert fr.is_excluded("loki_devices")
    assert fr.is_excluded("loki_platforms")
    assert fr.is_excluded("nutanix_snapshot_schedule")
    assert not fr.is_excluded("cluster_metrics")
    assert not fr.is_excluded("discovery_loki_rack")  # discovery_* is live, not legacy


def test_family_of_maps_by_prefix():
    assert fr.family_of("raw_vmware_datastore_metrics_agg") == "VMware"
    assert fr.family_of("nutanix_cluster_metrics") == "Nutanix"
    assert fr.family_of("ibm_lpar_general") == "IBM"
    assert fr.family_of("zabbix_storage_pool_metrics") == "Zabbix"
    assert fr.family_of("discovery_netbox_inventory_device") == "NetBox"
    assert fr.family_of("raw_panduit_pdu_inventory") == "Panduit"
    assert fr.family_of("something_else") == "Other"


def test_resolve_picks_preferred_column_and_defaults():
    spec = fr.resolve("cluster_metrics", ["id", "collection_time", "timestamp"],
                      default_warn=26, default_dead=50)
    assert spec["column"] == "collection_time"      # preferred over timestamp
    assert spec["family"] == "VMware"
    assert spec["warn_hours"] == 26 and spec["dead_hours"] == 50
    assert spec["label"]                             # some human label


def test_resolve_none_when_excluded_or_no_column():
    assert fr.resolve("loki_devices", ["collection_time"], default_warn=26, default_dead=50) is None
    assert fr.resolve("t", ["id", "name"], default_warn=26, default_dead=50) is None


def test_resolve_applies_override():
    spec = fr.resolve("raw_vmware_datastore_metrics_agg",
                      ["collection_timestamp"], default_warn=26, default_dead=50)
    assert spec["label"] == "VMware Datastore Metrics"   # from OVERRIDES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/hmdl-api && PYTHONPATH=/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI ../../.venv/bin/python -m pytest tests/test_freshness_registry.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

Create `services/hmdl-api/app/services/freshness_registry.py`:

```python
"""Hybrid freshness registry: auto-discovery rules + curated overrides.

Pure (no DB). Discovery finds public tables with a freshness column; this module
decides which to monitor (EXCLUDE deprecated/legacy), what family + label they
belong to, and their thresholds. Curation is seeded from what we know and is
meant to be refined by the team over time.
"""
from __future__ import annotations

# Preference order for a table's freshness timestamp column.
FRESHNESS_COLUMNS = [
    "collection_time", "collection_timestamp", "checked_at", "processed_at",
    "finished_at", "check_time", "last_seen_at", "last_observed", "timestamp",
    "time", "last_updated",
]

# Deprecated / superseded / non-monitored tables (seed — team refines).
# The legacy loki_* timeseries are replaced by discovery_* (live snapshot).
_EXCLUDE_EXACT = {
    "loki_platforms", "loki_device_types", "loki_devices", "loki_locations",
    "loki_racks", "nutanix_snapshot_schedule",
    "raw_ibm_storage_ports", "raw_ibm_storage_vdisk_dumps",
}

# name-prefix -> friendly family
_FAMILY_PREFIXES = [
    ("discovery_netbox", "NetBox"),
    ("discovery_loki", "Loki"),
    ("discovery_ibm", "IBM"),
    ("discovery_vmware", "VMware"),
    ("discovery", "NetBox"),
    ("raw_vmware", "VMware"),
    ("raw_ibm", "IBM"),
    ("raw_panduit", "Panduit"),
    ("raw_veeam", "Backup"),
    ("vmware", "VMware"),
    ("nutanix", "Nutanix"),
    ("ibm", "IBM"),
    ("zabbix", "Zabbix"),
    ("loki", "Loki"),
    ("cluster_metrics", "VMware"),
    ("datacenter_metrics", "VMware"),
    ("vmhost", "VMware"),
    ("vm_", "VMware"),
]

# per-table overrides: label / family / warn_hours / dead_hours
OVERRIDES: dict[str, dict] = {
    "raw_vmware_datastore_metrics_agg": {"label": "VMware Datastore Metrics"},
    "raw_vmware_datastore_host_mount": {"label": "VMware Datastore Mounts"},
    "cluster_metrics": {"label": "VMware Clusters"},
    "nutanix_cluster_metrics": {"label": "Nutanix Clusters"},
    "datacenter_metrics": {"label": "VMware Datacenter"},
    "ibm_lpar_general": {"label": "IBM LPARs"},
}


def is_excluded(table: str) -> bool:
    return table in _EXCLUDE_EXACT


def family_of(table: str) -> str:
    t = table.lower()
    for prefix, fam in _FAMILY_PREFIXES:
        if t.startswith(prefix):
            return fam
    return "Other"


def _label_for(table: str) -> str:
    ov = OVERRIDES.get(table, {})
    if ov.get("label"):
        return ov["label"]
    return table.replace("_", " ").title()


def resolve(table: str, columns: list[str], *, default_warn: float, default_dead: float) -> dict | None:
    if is_excluded(table):
        return None
    col = next((c for c in FRESHNESS_COLUMNS if c in columns), None)
    if not col:
        return None
    ov = OVERRIDES.get(table, {})
    return {
        "table": table,
        "column": col,
        "label": _label_for(table),
        "family": ov.get("family") or family_of(table),
        "warn_hours": float(ov.get("warn_hours", default_warn)),
        "dead_hours": float(ov.get("dead_hours", default_dead)),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: same pytest command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/hmdl-api/app/services/freshness_registry.py services/hmdl-api/tests/test_freshness_registry.py
git commit -m "feat(hmdl): freshness registry (discovery cols, exclude, family, overrides)"
```

---

### Task 2: `db/queries/freshness.py` (discover + compute)

**Files:** Create `services/hmdl-api/app/db/queries/freshness.py`; Test `services/hmdl-api/tests/test_freshness_queries.py`

**Interfaces:**
- Consumes: `freshness_registry` (Task 1), `automation_health.build_data_source_row` + `overall_status_counts`, `app.db.pool`, `app.config.settings`.
- Produces: `discover_specs() -> list[dict]`; `compute_freshness() -> {"families": [...], "counts": {...}}` where each family = `{"family": str, "counts": {...}, "sources": [row,...]}`.

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import patch
from app.db.queries import freshness as fq


def test_discover_specs_filters_excluded_and_resolves():
    info_rows = [
        {"table_name": "cluster_metrics", "cols": ["collection_time"]},
        {"table_name": "loki_devices", "cols": ["collection_time"]},   # excluded
        {"table_name": "some_lookup", "cols": ["id", "name"]},          # no freshness col
    ]
    with patch.object(fq.pool, "fetch_all", return_value=info_rows):
        specs = fq.discover_specs()
    tables = {s["table"] for s in specs}
    assert tables == {"cluster_metrics"}


def test_compute_freshness_groups_by_family_and_counts():
    specs = [
        {"table": "cluster_metrics", "column": "collection_time", "label": "VMware Clusters",
         "family": "VMware", "warn_hours": 26, "dead_hours": 50},
        {"table": "raw_vmware_datastore_metrics_agg", "column": "collection_timestamp",
         "label": "VMware Datastore Metrics", "family": "VMware", "warn_hours": 26, "dead_hours": 50},
        {"table": "nutanix_cluster_metrics", "column": "collection_time", "label": "Nutanix Clusters",
         "family": "Nutanix", "warn_hours": 26, "dead_hours": 50},
    ]
    # age per table (in call order): fresh, dead, fresh
    ages = [{"age_hours": 1.0}, {"age_hours": 240.0}, {"age_hours": 0.5}]
    with patch.object(fq, "discover_specs", return_value=specs), \
         patch.object(fq.pool, "fetch_one", side_effect=ages):
        out = fq.compute_freshness()
    fams = {f["family"]: f for f in out["families"]}
    assert set(fams) == {"VMware", "Nutanix"}
    assert fams["VMware"]["counts"]["dead"] == 1
    assert fams["VMware"]["counts"]["fresh"] == 1
    assert fams["Nutanix"]["counts"]["fresh"] == 1
    assert out["counts"]["dead"] == 1
    assert out["counts"]["alert"] == 1


def test_compute_freshness_clamps_negative_age():
    specs = [{"table": "cluster_metrics", "column": "collection_time", "label": "L",
              "family": "VMware", "warn_hours": 26, "dead_hours": 50}]
    with patch.object(fq, "discover_specs", return_value=specs), \
         patch.object(fq.pool, "fetch_one", return_value={"age_hours": -3.0}):
        out = fq.compute_freshness()
    assert out["families"][0]["sources"][0]["age_hours"] == 0.0
    assert out["families"][0]["sources"][0]["status"] == "fresh"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/hmdl-api && PYTHONPATH=<root> ../../.venv/bin/python -m pytest tests/test_freshness_queries.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

Create `services/hmdl-api/app/db/queries/freshness.py`:

```python
"""Discover collected data tables and compute their freshness, grouped by family.

Expensive (max() over ~120 tables) — call ONLY from the background refresher,
never on the request path.
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.db import pool
from app.services import automation_health as ah
from app.services import freshness_registry as reg


def discover_specs() -> list[dict[str, Any]]:
    rows = pool.fetch_all(
        """
        SELECT c.table_name, array_agg(c.column_name::text) AS cols
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
         AND t.table_type = 'BASE TABLE'
        WHERE c.table_schema = 'public'
          AND c.column_name = ANY(%s)
        GROUP BY c.table_name
        ORDER BY c.table_name
        """,
        (reg.FRESHNESS_COLUMNS,),
    )
    specs: list[dict[str, Any]] = []
    for r in rows or []:
        spec = reg.resolve(
            r["table_name"], list(r.get("cols") or []),
            default_warn=settings.ah_data_warn_hours,
            default_dead=settings.ah_data_dead_hours,
        )
        if spec:
            specs.append(spec)
    return specs


def _age_hours(table: str, col: str) -> float | None:
    r = pool.fetch_one(
        f"SELECT EXTRACT(EPOCH FROM (now() - max({col}::timestamptz)))/3600.0 AS age_hours "
        f"FROM public.{table}"
    )
    if not r or r.get("age_hours") is None:
        return None
    age = float(r["age_hours"])
    return 0.0 if age < 0 else age


def compute_freshness() -> dict[str, Any]:
    families: dict[str, list[dict]] = {}
    for spec in discover_specs():
        try:
            age = _age_hours(spec["table"], spec["column"])
        except Exception:  # noqa: BLE001 — a bad table never breaks the whole sweep
            age = None
        row = ah.build_data_source_row(
            key=spec["table"], label=spec["label"], table=spec["table"],
            last_data_at=None, age_hours=age,
            warn_hours=spec["warn_hours"], dead_hours=spec["dead_hours"],
        )
        families.setdefault(spec["family"], []).append(row)

    fam_list = []
    all_statuses: list[str] = []
    for fam in sorted(families):
        sources = families[fam]
        statuses = [s["status"] for s in sources]
        all_statuses.extend(statuses)
        fam_list.append({
            "family": fam,
            "counts": ah.overall_status_counts(statuses),
            "sources": sources,
        })
    return {"families": fam_list, "counts": ah.overall_status_counts(all_statuses)}
```

- [ ] **Step 4: Run test to verify it passes** — same command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/hmdl-api/app/db/queries/freshness.py services/hmdl-api/tests/test_freshness_queries.py
git commit -m "feat(hmdl): freshness discovery + family-grouped compute"
```

---

### Task 3: config thresholds + refresh interval

**Files:** Modify `services/hmdl-api/app/config.py`

- [ ] **Step 1** (no new test — covered by Task 4). Add after `ah_data_dead_hours`:

```python
    ah_freshness_refresh_min: float = float(_env("HMDL_FRESHNESS_REFRESH_MIN", default="30"))
```

- [ ] **Step 2: Commit** (fold into Task 4 commit).

---

### Task 4: in-process snapshot + background refresher

**Files:** Create `services/hmdl-api/app/services/freshness_snapshot.py`; Test `services/hmdl-api/tests/test_freshness_snapshot.py`

**Interfaces — Produces:** `get_snapshot() -> dict` (returns `{"families":[],"counts":{...zeros...,"alert":0},"generated_at":None,"status":"computing"}` until first compute, else the stored snapshot with `status:"ok"`); `refresh_now()` (compute + store, used by the loop + tests); `start_refresher()` (daemon thread).

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import patch
from app.services import freshness_snapshot as snap


def test_snapshot_is_computing_before_first_refresh():
    snap._reset_for_test()
    s = snap.get_snapshot()
    assert s["status"] == "computing"
    assert s["families"] == []
    assert s["counts"]["alert"] == 0


def test_refresh_now_stores_ok_snapshot():
    snap._reset_for_test()
    computed = {"families": [{"family": "VMware", "counts": {"dead": 1}, "sources": []}],
                "counts": {"fresh": 0, "stale": 0, "dead": 1, "unknown": 0, "alert": 1}}
    with patch("app.services.freshness_snapshot.compute_freshness", return_value=computed):
        snap.refresh_now()
    s = snap.get_snapshot()
    assert s["status"] == "ok"
    assert s["counts"]["alert"] == 1
    assert s["generated_at"] is not None
```

- [ ] **Step 2: Run test to verify it fails** — Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

Create `services/hmdl-api/app/services/freshness_snapshot.py`:

```python
"""In-process freshness snapshot + background refresher (hmdl-api has no Redis).

The endpoint serves the last snapshot instantly; a daemon thread recomputes it
every ah_freshness_refresh_min minutes so the expensive ~120-table sweep never
runs on the request path.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from app.config import settings
from app.db.queries.freshness import compute_freshness

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_snapshot: dict | None = None
_stop = threading.Event()
_thread: threading.Thread | None = None

_EMPTY_COUNTS = {"fresh": 0, "stale": 0, "dead": 0, "unknown": 0, "alert": 0}


def _reset_for_test() -> None:
    global _snapshot
    with _lock:
        _snapshot = None


def get_snapshot() -> dict:
    with _lock:
        if _snapshot is None:
            return {"families": [], "counts": dict(_EMPTY_COUNTS),
                    "generated_at": None, "status": "computing"}
        return _snapshot


def refresh_now() -> None:
    result = compute_freshness()
    result["generated_at"] = datetime.now(timezone.utc)
    result["status"] = "ok"
    global _snapshot
    with _lock:
        _snapshot = result


def _loop(interval_s: float) -> None:
    while not _stop.is_set():
        try:
            refresh_now()
        except Exception:  # noqa: BLE001
            logger.exception("freshness snapshot refresh failed")
        _stop.wait(interval_s)


def start_refresher() -> threading.Thread:
    global _thread
    _stop.clear()
    _thread = threading.Thread(
        target=_loop, args=(settings.ah_freshness_refresh_min * 60.0,),
        name="freshness-refresher", daemon=True,
    )
    _thread.start()
    return _thread
```

- [ ] **Step 4: Run test to verify it passes** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/hmdl-api/app/config.py services/hmdl-api/app/services/freshness_snapshot.py services/hmdl-api/tests/test_freshness_snapshot.py
git commit -m "feat(hmdl): in-process freshness snapshot + background refresher"
```

---

### Task 5: wire snapshot into lifespan + endpoint + schema

**Files:** Modify `app/main.py` (lifespan start_refresher), `app/db/queries/automation_health.py` (attach snapshot to response), `app/models/schemas.py` (DataFamily + fields), `app/routers/collectors.py` (unchanged if it returns build_automation_health()). Test `services/hmdl-api/tests/test_automation_health_api.py`.

**Interfaces:** `build_automation_health()` return dict gains `data_families`, `data_counts`, `data_status`, `data_snapshot_at` from `freshness_snapshot.get_snapshot()`.

- [ ] **Step 1: Write the failing test** (extend the api test)

```python
def test_automation_health_includes_data_families_from_snapshot(monkeypatch):
    from app.db.queries import automation_health as q
    from app.services import freshness_snapshot as snap
    monkeypatch.setattr(snap, "get_snapshot", lambda: {
        "families": [{"family": "VMware", "counts": {"fresh": 1, "stale": 0, "dead": 1,
                     "unknown": 0, "alert": 1}, "sources": []}],
        "counts": {"fresh": 1, "stale": 0, "dead": 1, "unknown": 0, "alert": 1},
        "generated_at": None, "status": "ok"})
    # stub the DB-backed parts so only the merge is exercised
    monkeypatch.setattr(q, "_now", lambda: None)
    monkeypatch.setattr(q, "_max_ts", lambda sql: None)
    monkeypatch.setattr(q, "_collector_extra", lambda: {})
    monkeypatch.setattr(q, "_proxy_health", lambda now: ([], {"total": 0, "fresh": 0, "stale": 0, "dead": 0}))
    monkeypatch.setattr(q, "_data_gaps", lambda: {"cluster_missing": 0, "ibm_missing": 0, "by_source": {}})
    out = q.build_automation_health()
    assert out["data_status"] == "ok"
    assert out["data_counts"]["alert"] == 1
    assert out["data_families"][0]["family"] == "VMware"
```

- [ ] **Step 2: Run test to verify it fails** — Expected: FAIL (keys missing).

- [ ] **Step 3: Write minimal implementation**

In `automation_health.py`, replace the old `_data_sources()` call/return with the snapshot:

```python
from app.services import freshness_snapshot as fsnap
```
and in `build_automation_health()` return:
```python
    snap = fsnap.get_snapshot()
    return {
        "generated_at": now,
        "automations": automations,
        "counts": counts,
        "proxies": proxies,
        "proxy_summary": proxy_summary,
        "data_gaps": _data_gaps(),
        "data_families": snap.get("families", []),
        "data_counts": snap.get("counts", {}),
        "data_status": snap.get("status", "computing"),
        "data_snapshot_at": snap.get("generated_at"),
    }
```
Remove the earlier flat `_data_sources`/`_DATA_SOURCES` block (superseded by the registry). 

In `app/main.py` lifespan startup, add:
```python
    from app.services import freshness_snapshot
    freshness_snapshot.start_refresher()
```

In `schemas.py`, add and wire into `AutomationHealthResponse`:
```python
class DataFamily(BaseModel):
    family: str
    counts: AutomationCounts = Field(default_factory=AutomationCounts)
    sources: list[AutomationRow] = Field(default_factory=list)
```
```python
    data_families: list[DataFamily] = Field(default_factory=list)
    data_counts: AutomationCounts = Field(default_factory=AutomationCounts)
    data_status: str = "computing"
    data_snapshot_at: datetime | None = None
```
(Remove the flat `data_sources: list[AutomationRow]` field added in the first cut.)

- [ ] **Step 4: Run test** — `pytest tests/test_automation_health_api.py tests/test_automation_health_data_sources.py -q`. Delete `test_automation_health_data_sources.py` if it tested the removed flat `_data_sources` (its coverage moves to Task 2). Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/hmdl-api/app -A && git add services/hmdl-api/tests -A
git commit -m "feat(hmdl): serve freshness snapshot (data_families) from automation-health"
```

---

### Task 6: refactor automations to AUTOMATION_SPECS

**Files:** Modify `services/hmdl-api/app/services/freshness_registry.py` (add `AUTOMATION_SPECS`), `app/db/queries/automation_health.py` (iterate specs). Test `services/hmdl-api/tests/test_automation_health.py`.

- [ ] **Step 1: Write the failing test**

```python
def test_automation_specs_cover_the_four_hmdl_automations():
    from app.services.freshness_registry import AUTOMATION_SPECS
    keys = {s["key"] for s in AUTOMATION_SPECS}
    assert keys == {"zabbix_sync", "collector_sync", "reachability_checks", "vm_reconciliation"}
    for s in AUTOMATION_SPECS:
        assert s["schema"] and s["table"] and s["column"] and s["label"]
```

- [ ] **Step 2: Run** — FAIL (AUTOMATION_SPECS missing).

- [ ] **Step 3: Implement** — add to `freshness_registry.py`:

```python
# HMDL automation log tables (hmdl schema). warn/dead keys reference config settings.
AUTOMATION_SPECS = [
    {"key": "zabbix_sync", "label": "NetBox → Zabbix Sync", "cadence": "~8 saatte bir",
     "schema": "hmdl", "table": "zabbix_sync_log", "column": "processed_at",
     "warn": "ah_zabbix_warn_hours", "dead": "ah_zabbix_dead_hours", "where": "dry_run = FALSE"},
    {"key": "collector_sync", "label": "Datalake Collector Sync", "cadence": "günlük 02:00",
     "schema": "hmdl", "table": "collector_sync_log", "column": "finished_at",
     "warn": "ah_collector_warn_hours", "dead": "ah_collector_dead_hours", "where": "dry_run = FALSE",
     "extra": "collector"},
    {"key": "reachability_checks", "label": "Collector Reachability Checks", "cadence": "collector sync ile",
     "schema": "hmdl", "table": "collector_check_log", "column": "checked_at",
     "warn": "ah_checks_warn_hours", "dead": "ah_checks_dead_hours", "where": None},
    {"key": "vm_reconciliation", "label": "VM Envanter Reconciliation", "cadence": "günlük",
     "schema": "hmdl", "table": "hmdl_datalake_monitoring_clusters", "column": "check_time",
     "warn": "ah_recon_warn_hours", "dead": "ah_recon_dead_hours", "where": None},
]
```

In `automation_health.py`, replace the 4 hand-built rows with a loop:

```python
    from app.services import freshness_registry as reg
    automations = []
    for s in reg.AUTOMATION_SPECS:
        where = f" WHERE {s['where']}" if s.get("where") else ""
        last = _max_ts(f"SELECT max({s['column']}) AS ts FROM {settings.hmdl_schema}.{s['table']}{where}")
        automations.append(ah.build_automation_row(
            key=s["key"], label=s["label"], cadence=s["cadence"],
            last_run_at=last, now=now,
            warn_hours=getattr(settings, s["warn"]), dead_hours=getattr(settings, s["dead"]),
            extra=_collector_extra() if s.get("extra") == "collector" else None,
        ))
```

- [ ] **Step 4: Run** — `pytest tests/test_automation_health.py tests/test_automation_health_api.py -q`. Expected: PASS (same 4 automations).

- [ ] **Step 5: Commit**

```bash
git add services/hmdl-api -A
git commit -m "refactor(hmdl): automations driven by AUTOMATION_SPECS registry"
```

---

## Phase 2 — GUI

### Task 7: family rollup cards + drill-down + computing state

**Files:** Modify `src/pages/settings/integrations/hmdl_automation_health.py`; `src/services/api_client.py` (empty fallback gains data_families/data_counts/data_status). Test `tests/test_hmdl_automation_health_page.py`.

- [ ] **Step 1: Write the failing test**

```python
@patch("src.pages.settings.integrations.hmdl_automation_health.api.get_hmdl_automation_health")
def test_page_renders_family_rollups(mock_ah):
    data = dict(MOCK_AH)
    data["data_status"] = "ok"
    data["data_counts"] = {"fresh": 3, "stale": 0, "dead": 2, "unknown": 0, "alert": 2}
    data["data_families"] = [
        {"family": "VMware", "counts": {"fresh": 1, "stale": 0, "dead": 2, "unknown": 0, "alert": 2},
         "sources": [{"key": "raw_vmware_datastore_metrics_agg", "label": "VMware Datastore Metrics",
                      "cadence": "public.raw_vmware_datastore_metrics_agg", "last_run_at": None,
                      "age_hours": 240.0, "status": "dead", "warn_hours": 26, "dead_hours": 50, "extra": {}}]},
        {"family": "Nutanix", "counts": {"fresh": 2, "stale": 0, "dead": 0, "unknown": 0, "alert": 0},
         "sources": []},
    ]
    mock_ah.return_value = data
    text = str(page.build_layout())
    assert "Data Collection Freshness" in text
    assert "VMware" in text and "Nutanix" in text
    assert "VMware Datastore Metrics" in text


@patch("src.pages.settings.integrations.hmdl_automation_health.api.get_hmdl_automation_health")
def test_page_shows_computing_state(mock_ah):
    data = dict(MOCK_AH)
    data["data_status"] = "computing"
    data["data_families"] = []
    data["data_counts"] = {"fresh": 0, "stale": 0, "dead": 0, "unknown": 0, "alert": 0}
    mock_ah.return_value = data
    assert "hesaplan" in str(page.build_layout()).lower()
```

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Implement** — in `build_layout`, replace the flat data-sources section with family rollups:

```python
    data_families = data.get("data_families") or []
    data_counts = data.get("data_counts") or {}
    data_status = data.get("data_status") or "computing"

    def _family_card(fam):
        c = fam.get("counts") or {}
        dead, stale, fresh = int(c.get("dead") or 0), int(c.get("stale") or 0), int(c.get("fresh") or 0)
        color = "red" if dead else ("orange" if stale else "green")
        return dmc.Paper(
            p="md", withBorder=True, radius="md",
            children=[
                dmc.Group(justify="space-between", children=[
                    dmc.Text(fam.get("family") or "—", fw=700),
                    dmc.Badge(f"{dead} ölü · {stale} bayat · {fresh} taze", color=color, variant="light"),
                ]),
                dmc.Stack(gap=4, mt="xs", children=[
                    _automation_card(s) for s in (fam.get("sources") or []) if s.get("status") in ("dead", "stale")
                ] or [dmc.Text("Tümü taze.", size="xs", c="dimmed")]),
            ],
        )

    if data_status == "computing":
        data_body = dmc.Text("Veri tazeliği hesaplanıyor… birazdan yenileyin.", size="sm", c="dimmed")
    else:
        data_body = dmc.SimpleGrid(cols={"base": 1, "md": 2, "lg": 3}, spacing="md",
                                   children=[_family_card(f) for f in data_families]
                                   or [dmc.Text("Veri kaynağı yok.", size="sm", c="dimmed")])

    data_sources_section = dmc.Paper(
        p="lg", withBorder=True, radius="md", mb="lg",
        children=[
            section_header("Data Collection Freshness",
                           "Toplanan verinin tazeliği — aile bazında (yalnız sorunlular listelenir).",
                           icon="solar:database-bold-duotone"),
            data_body,
        ],
    )
```
Keep `alert = int(counts.get("alert") or 0) + int(data_counts.get("alert") or 0)` and insert `data_sources_section` after `automations_section` (already wired). In `api_client._EMPTY_HMDL_AUTOMATION_HEALTH`, replace flat `data_sources` with `"data_families": [], "data_counts": {...zeros...}, "data_status": "computing"`.

- [ ] **Step 4: Run** — `PYTHONPATH=. .venv/bin/python -m pytest tests/test_hmdl_automation_health_page.py -q`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pages/settings/integrations/hmdl_automation_health.py src/services/api_client.py tests/test_hmdl_automation_health_page.py
git commit -m "feat(hmdl gui): family rollup cards + computing state for data freshness"
```

---

### Task 8: sidebar badge + banner include data alert

**Files:** Modify `src/utils/hmdl_sync_ui.py` (or its callers) so the staleness banner/badge count = automations alert + data alert. Test `tests/test_hmdl_sub_nav_badge.py`.

- [ ] **Step 1: Write the failing test** — assert that when `counts.alert=0` but `data_counts.alert=2`, the badge/banner still shows an alert. (Follow the existing test's call convention; if the badge helper takes a single `counts`, add a small combiner and pass the merged count.)

```python
def test_badge_reflects_data_freshness_alert():
    from src.utils.hmdl_sync_ui import combined_alert_count
    assert combined_alert_count({"alert": 0}, {"alert": 2}) == 2
    assert combined_alert_count({"alert": 1}, {"alert": 2}) == 3
```

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Implement** — add helper in `hmdl_sync_ui.py`:

```python
def combined_alert_count(counts: dict | None, data_counts: dict | None) -> int:
    return int((counts or {}).get("alert") or 0) + int((data_counts or {}).get("alert") or 0)
```
Update the sub-nav badge + `hmdl_overview` banner call sites to compute the count with `combined_alert_count(data.get("counts"), data.get("data_counts"))` and pass a `{"alert": combined, ...}`-shaped dict (or the raw int) to `staleness_alert_banner` / the badge.

- [ ] **Step 4: Run** — `PYTHONPATH=. .venv/bin/python -m pytest tests/test_hmdl_sub_nav_badge.py -q`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/utils/hmdl_sync_ui.py tests/test_hmdl_sub_nav_badge.py src/pages -A
git commit -m "feat(hmdl gui): sidebar badge + banner include data-freshness alerts"
```

---

## Phase 3 — Verify + deploy

### Task 9: full regression + rebuild + live verify

- [ ] **Step 1:** `cd services/hmdl-api && PYTHONPATH=<root> ../../.venv/bin/python -m pytest tests/ -q` — all pass.
- [ ] **Step 2:** `PYTHONPATH=. .venv/bin/python -m pytest tests/test_hmdl_automation_health_page.py tests/test_hmdl_sub_nav_badge.py -q` — all pass.
- [ ] **Step 3:** `docker compose --profile microservice up -d --build hmdl-api app`.
- [ ] **Step 4:** wait ~1–2 min for the first background snapshot, then
  `curl -s localhost:8007/api/v1/collectors/automation-health | python3 -m json.tool | head` — verify `data_status:"ok"`, `data_families` populated, VMware family shows the 2 dead datastore tables + ~60d perf pipelines etc.
- [ ] **Step 5:** Browser: Automation Health page shows family rollups; datastore + perf dead surfaced; sidebar badge red. Hand to user.

## Self-Review notes

- Spec coverage: registry (T1) ✓, discovery+compute (T2) ✓, thresholds (T3) ✓, snapshot+background (T4) ✓, endpoint+schema (T5) ✓, automations registry (T6) ✓, GUI rollup+computing (T7) ✓, sidebar/banner (T8) ✓, verify (T9) ✓.
- The first-cut flat `data_sources` (registry-less) is intentionally removed in T5/T7 — superseded by `data_families`. Its test file is removed once T2 covers the logic.
- Curation seed is minimal-but-safe; excludes only known-legacy; team refines OVERRIDES/EXCLUDE via config.
