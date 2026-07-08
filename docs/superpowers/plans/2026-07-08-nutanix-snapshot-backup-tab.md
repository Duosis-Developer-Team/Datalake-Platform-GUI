# Nutanix Snapshot Backup Tab — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Nutanix" sub-tab (rich panel + Missing Entities) under Backup & Replication in both DC view and Customer view, sourced from `nutanix_snapshot_schedule_metrics`.

**Architecture:** Follow the existing backup-vendor path exactly: pure helpers in `shared/`, SQL + fetch + cache in the `datacenter-api` microservice, HTTP wrappers in the GUI `api_client`, a panel in `backup_panel.py`, and wiring in `dc_view.py` / `customer_view.py`. DC attribution is DB-native (`nutanix_ip` → discovery inventory → DC); customer attribution is the `protection_domain_name`/`vm_names` prefix. Caching uses the rigorous single-flight + stale-TTL variant because the `DISTINCT ON (snapshot_id)` scan is expensive.

**Tech Stack:** Python, FastAPI (datacenter-api), Dash + dash-mantine-components (GUI), psycopg2, Redis-backed `cache_service`, pytest/unittest.

## Global Constraints

- **Every snapshot query MUST be `collection_time`-bounded** and scoped to a DC's IP set first — `SELECT count(*)` on the full table times out.
- **Minimum lookback = 48h:** floor `effective_start = min(start, end − 48h)` before the `DISTINCT ON (snapshot_id)` de-dup (collection is sparse; a narrow UI range must not empty the panel).
- **Caching is mandatory** (spec §9): backend `run_singleflight` + `set_with_stale` on the heavy set, in-process paging, separate long-TTL IP→DC map, refresh endpoint; GUI wrappers via `_api_cache_get_with_stale` (no-stale + cross-pod lock); warm via `api_client` inside `warm_mode`.
- **Do NOT touch the monolith `src/services/db_service.py`** — the user path is the microservice; warming goes through `api_client` like `_warm_dc_network_for_range`.
- **DC filter uses `name LIKE '%dc_code%'`** on `discovery_nutanix_inventory_cluster`, matching `queries/nutanix.py`.
- Reuse existing panel primitives (`_kpi_card`, `_gauge_card`, `smart_bytes`) and the `nexus-card` / `dc-premium-table` classes — do not restyle.
- Pattern references (mirror these verbatim for signatures/shape): `get_dc_netbackup_pools` (`api_client.py:829`), `_fetch_dc_netbackup_pools` (`dc_service.py:3619`), `get_dc_netbackup_pools` cache (`dc_service.py:3791`), `dc_netbackup` route (`routers/datacenters.py:67`), `network_interface_table` route (`routers/datacenters.py:348`), `build_netbackup_panel` (`backup_panel.py:275`), `compute_has_backup` (`dc_view.py:5027`).

---

## File Structure

- Create `shared/nutanix/__init__.py` — package marker.
- Create `shared/nutanix/snapshot_helpers.py` — pure, DB-free logic (customer parse, retention parse, IP↔uuid, aggregate). One responsibility: transform/aggregate snapshot rows.
- Create `services/datacenter-api/app/db/queries/nutanix_snapshot.py` — SQL constants (DC-IP resolution, latest-per-snapshot).
- Modify `services/datacenter-api/app/services/dc_service.py` — fetch + cache methods.
- Modify `services/datacenter-api/app/routers/datacenters.py` — endpoints.
- Modify `src/services/api_client.py` — HTTP wrappers + refresh.
- Modify `src/components/backup_panel.py` — `build_nutanix_snapshot_panel`.
- Modify `src/pages/dc_view.py` — has_nutanix_backup, eager batch, tab panel, compute_has_backup, export.
- Modify `src/pages/dc_view_callbacks.py` — table pagination callback.
- Modify `src/pages/customer_view.py` — Nutanix sub-tab in `_build_backup_tabs`.
- Modify `src/services/scheduler_service.py` — warm job.
- Tests: `tests/test_nutanix_snapshot_helpers.py`, `tests/test_nutanix_snapshot_fetch.py`, `tests/test_api_client_nutanix_snapshots.py`, `tests/test_nutanix_snapshot_panel.py`, and additions to `tests/test_dc_view_has_backup.py`.

---

## Task 1: Pure helpers — customer & retention parse

**Files:**
- Create: `shared/nutanix/__init__.py`
- Create: `shared/nutanix/snapshot_helpers.py`
- Test: `tests/test_nutanix_snapshot_helpers.py`

**Interfaces:**
- Produces: `parse_customer(protection_domain_name: str | None, vm_names: str | None = None) -> str | None`; `parse_retention(schedule_local_max_snapshots, protection_domain_name: str | None = None) -> int | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nutanix_snapshot_helpers.py
import unittest
from shared.nutanix.snapshot_helpers import parse_customer, parse_retention


class TestParseCustomer(unittest.TestCase):
    def test_clean_prefix_from_pd_name(self):
        self.assertEqual(parse_customer("Alisan_Lojistik-1Day_30RP"), "Alisan_Lojistik")

    def test_alphanumeric_customer_kept(self):
        self.assertEqual(parse_customer("12mtech-1Days_7RP"), "12mtech")

    def test_generic_schedule_returns_none(self):
        self.assertIsNone(parse_customer("1Days_10RP"))
        self.assertIsNone(parse_customer("1Day7RP"))

    def test_no_dash_falls_back_to_vm_names(self):
        # PD name is underscore-only; vm_names carries "Customer-VM".
        self.assertEqual(
            parse_customer("Capa_Medikal_1Days_7RP", "Capa_Medikal-App1, Capa_Medikal-App2"),
            "Capa_Medikal",
        )

    def test_all_unparseable_returns_none(self):
        self.assertIsNone(parse_customer("1_VC1DC13_Backup", None))


class TestParseRetention(unittest.TestCase):
    def test_prefers_max_snapshots(self):
        self.assertEqual(parse_retention(30, "X-1Day_7RP"), 30)

    def test_falls_back_to_rp_in_name(self):
        self.assertEqual(parse_retention(None, "Zorlu_Zes-1Day_7RP"), 7)

    def test_returns_none_when_unknown(self):
        self.assertIsNone(parse_retention(None, "no-retention-token"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_helpers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shared.nutanix'`

- [ ] **Step 3: Write minimal implementation**

```python
# shared/nutanix/__init__.py
```
(empty file)

```python
# shared/nutanix/snapshot_helpers.py
"""Pure, DB-free helpers for Nutanix snapshot rows (customer/retention parse,
IP↔uuid resolution, aggregation). Imported by the datacenter-api fetch layer
and unit-tested directly."""
from __future__ import annotations

import re

# Generic-schedule prefixes like "1Days_10RP", "1Day7RP", "2Hours-360RP" — a
# leading integer immediately followed by a time unit means "no customer".
_GENERIC_SCHEDULE_RE = re.compile(r"^\d+\s*(day|days|hour|hours|min|mins|week|weeks|month|months)", re.IGNORECASE)
_RP_RE = re.compile(r"(\d+)\s*RP", re.IGNORECASE)


def _looks_like_customer(prefix: str | None) -> bool:
    if not prefix:
        return False
    if _GENERIC_SCHEDULE_RE.match(prefix):
        return False
    return True


def parse_customer(protection_domain_name: str | None, vm_names: str | None = None) -> str | None:
    """Customer = token before the first '-' (customer names use '_'). Try the
    protection-domain name first, then the first vm_names entry. None if neither
    yields a plausible customer (these become 'Missing Entities')."""
    for source in (protection_domain_name, vm_names):
        if not source:
            continue
        first = str(source).split(",")[0].strip()
        if "-" not in first:
            continue
        prefix = first.split("-", 1)[0].strip()
        if _looks_like_customer(prefix):
            return prefix
    return None


def parse_retention(schedule_local_max_snapshots, protection_domain_name: str | None = None) -> int | None:
    """Retention count: prefer schedule_local_max_snapshots, else parse '<n>RP'
    from the protection-domain name (e.g. '1Day_7RP' -> 7)."""
    if schedule_local_max_snapshots not in (None, 0, ""):
        try:
            return int(schedule_local_max_snapshots)
        except (TypeError, ValueError):
            pass
    if protection_domain_name:
        m = _RP_RE.search(str(protection_domain_name))
        if m:
            return int(m.group(1))
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_helpers.py -v`
Expected: PASS (all 8 tests)

- [ ] **Step 5: Commit**

```bash
git add shared/nutanix/__init__.py shared/nutanix/snapshot_helpers.py tests/test_nutanix_snapshot_helpers.py
git commit -m "feat(nutanix-snap): pure customer/retention parse helpers"
```

---

## Task 2: Pure helpers — IP↔uuid & aggregation

**Files:**
- Modify: `shared/nutanix/snapshot_helpers.py`
- Test: `tests/test_nutanix_snapshot_helpers.py`

**Interfaces:**
- Produces: `ip_to_nutanix_uuid(ip: str | None) -> str | None`; `uuid_to_ip(nutanix_uuid: str | None) -> str | None`; `split_vms(vm_names: str | None) -> list[str]`; `aggregate_snapshots(rows: list[dict]) -> dict` returning keys `total_snapshots, total_size_bytes, protected_vms, missing_entities, schedule_type_breakdown, state_breakdown`. Each row dict uses keys: `size_in_bytes, vm_names, schedule_type, state, missing_entity`.

- [ ] **Step 1: Write the failing test (append to the same test file)**

```python
# append to tests/test_nutanix_snapshot_helpers.py
from shared.nutanix.snapshot_helpers import (
    ip_to_nutanix_uuid, uuid_to_ip, split_vms, aggregate_snapshots,
)


class TestIpUuid(unittest.TestCase):
    def test_ip_to_uuid(self):
        self.assertEqual(ip_to_nutanix_uuid("10.34.2.98"), "nutanix-10.34.2.98")

    def test_uuid_to_ip_strips_prefix(self):
        self.assertEqual(uuid_to_ip("nutanix-10.34.2.98"), "10.34.2.98")

    def test_uuid_to_ip_passthrough_without_prefix(self):
        self.assertEqual(uuid_to_ip("10.34.2.98"), "10.34.2.98")


class TestAggregate(unittest.TestCase):
    def _rows(self):
        return [
            {"size_in_bytes": 100, "vm_names": "Cust-A, Cust-B", "schedule_type": "DAILY",
             "state": "AVAILABLE", "missing_entity": None},
            {"size_in_bytes": 200, "vm_names": "Cust-B, Cust-C", "schedule_type": "DAILY",
             "state": "AVAILABLE", "missing_entity": None},
            {"size_in_bytes": 50, "vm_names": None, "schedule_type": "MONTHLY",
             "state": "AVAILABLE", "missing_entity": "Cust-Ghost"},
        ]

    def test_totals(self):
        agg = aggregate_snapshots(self._rows())
        self.assertEqual(agg["total_snapshots"], 3)
        self.assertEqual(agg["total_size_bytes"], 350)
        self.assertEqual(agg["protected_vms"], 3)  # A, B, C distinct
        self.assertEqual(agg["missing_entities"], 1)

    def test_breakdowns(self):
        agg = aggregate_snapshots(self._rows())
        self.assertEqual(agg["schedule_type_breakdown"], {"DAILY": 2, "MONTHLY": 1})
        self.assertEqual(agg["state_breakdown"], {"AVAILABLE": 3})

    def test_empty(self):
        agg = aggregate_snapshots([])
        self.assertEqual(agg["total_snapshots"], 0)
        self.assertEqual(agg["total_size_bytes"], 0)
        self.assertEqual(agg["protected_vms"], 0)
        self.assertEqual(agg["schedule_type_breakdown"], {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_helpers.py -k "IpUuid or Aggregate" -v`
Expected: FAIL — `ImportError: cannot import name 'ip_to_nutanix_uuid'`

- [ ] **Step 3: Write minimal implementation (append to `snapshot_helpers.py`)**

```python
def ip_to_nutanix_uuid(ip: str | None) -> str | None:
    return f"nutanix-{ip}" if ip else None


def uuid_to_ip(nutanix_uuid: str | None) -> str | None:
    if not nutanix_uuid:
        return None
    s = str(nutanix_uuid)
    prefix = "nutanix-"
    return s[len(prefix):] if s.startswith(prefix) else s


def split_vms(vm_names: str | None) -> list[str]:
    if not vm_names:
        return []
    return [v.strip() for v in str(vm_names).split(",") if v.strip()]


def aggregate_snapshots(rows: list[dict]) -> dict:
    """KPIs + breakdowns over already-deduped latest-per-snapshot rows."""
    total_size = 0
    vm_set: set[str] = set()
    missing = 0
    sched: dict[str, int] = {}
    state: dict[str, int] = {}
    for r in rows:
        total_size += int(r.get("size_in_bytes") or 0)
        for vm in split_vms(r.get("vm_names")):
            vm_set.add(vm)
        if r.get("missing_entity"):
            missing += 1
        st = str(r.get("schedule_type") or "Unknown")
        sched[st] = sched.get(st, 0) + 1
        stt = str(r.get("state") or "Unknown")
        state[stt] = state.get(stt, 0) + 1
    return {
        "total_snapshots": len(rows),
        "total_size_bytes": total_size,
        "protected_vms": len(vm_set),
        "missing_entities": missing,
        "schedule_type_breakdown": sched,
        "state_breakdown": state,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_helpers.py -v`
Expected: PASS (all tests, ~14)

- [ ] **Step 5: Commit**

```bash
git add shared/nutanix/snapshot_helpers.py tests/test_nutanix_snapshot_helpers.py
git commit -m "feat(nutanix-snap): IP/uuid + aggregation helpers"
```

---

## Task 3: SQL query constants (microservice)

**Files:**
- Create: `services/datacenter-api/app/db/queries/nutanix_snapshot.py`
- Test: `tests/test_nutanix_snapshot_queries.py`

**Interfaces:**
- Produces module constants `DC_NUTANIX_IPS` (params: `dc_code`) and `SNAPSHOTS_BY_IPS_LATEST` (params: `ip_list, start_ts, end_ts`). Both are `str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nutanix_snapshot_queries.py
import unittest
from app.db.queries import nutanix_snapshot as q


class TestSnapshotQueries(unittest.TestCase):
    def test_dc_ips_query_filters_by_name_like_and_is_parameterized(self):
        self.assertIn("discovery_nutanix_inventory_cluster", q.DC_NUTANIX_IPS)
        self.assertIn("LIKE", q.DC_NUTANIX_IPS.upper())
        self.assertIn("%s", q.DC_NUTANIX_IPS)

    def test_snapshots_query_is_time_bounded_and_dedups(self):
        sql = q.SNAPSHOTS_BY_IPS_LATEST
        self.assertIn("nutanix_snapshot_schedule_metrics", sql)
        self.assertIn("DISTINCT ON", sql.upper())
        self.assertIn("collection_time BETWEEN", sql)
        self.assertIn("= ANY(", sql)
        self.assertIn("to_timestamp", sql)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_queries.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.db.queries.nutanix_snapshot'`
(Note: the test suite adds `services/datacenter-api` to `sys.path`; verify `app.*` imports resolve — see `tests/conftest.py`. If `app` is not importable, prefix imports with the path used by existing microservice tests.)

- [ ] **Step 3: Write minimal implementation**

```python
# services/datacenter-api/app/db/queries/nutanix_snapshot.py
"""SQL for Nutanix snapshot metrics.

DC attribution is DB-native: snapshot.nutanix_ip -> discovery inventory
cluster (nutanix_uuid = 'nutanix-' || ip) -> cluster name carrying the DC code.
All snapshot reads are collection_time-bounded and scoped to a DC's IP set.
"""

# Resolve a DC's Nutanix IPs + their cluster name (for the table "Cluster" column).
# Param: (dc_code,)
DC_NUTANIX_IPS = """
SELECT DISTINCT
    replace(nutanix_uuid, 'nutanix-', '') AS nutanix_ip,
    name AS cluster_name
FROM public.discovery_nutanix_inventory_cluster
WHERE name LIKE ('%%' || %s || '%%')
  AND nutanix_uuid LIKE 'nutanix-%%'
"""

# Latest row per physical snapshot within the window, scoped to the DC's IPs.
# Params: (ip_list, start_ts, end_ts)
# usec epoch columns converted to timestamps here for tz-consistency with Grafana.
SNAPSHOTS_BY_IPS_LATEST = """
SELECT DISTINCT ON (snapshot_id)
    nutanix_ip,
    protection_domain_name,
    state,
    vm_names,
    missing_entities_entity_name,
    missing_entities_entity_type,
    schedule_type,
    schedule_local_max_snapshots,
    size_in_bytes,
    to_timestamp(schedule_start_times_in_usecs / 1000000.0) AS start_time,
    to_timestamp(snapshot_create_time_usecs / 1000000.0)    AS create_time,
    to_timestamp(snapshot_expiry_time_usecs / 1000000.0)    AS expiry_time,
    snapshot_id
FROM public.nutanix_snapshot_schedule_metrics
WHERE nutanix_ip = ANY(%s)
  AND collection_time BETWEEN %s AND %s
ORDER BY snapshot_id, collection_time DESC
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_queries.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/datacenter-api/app/db/queries/nutanix_snapshot.py tests/test_nutanix_snapshot_queries.py
git commit -m "feat(nutanix-snap): DC-IP + latest-per-snapshot SQL"
```

---

## Task 4: Microservice fetch (`_fetch_dc_nutanix_snapshots`)

**Files:**
- Modify: `services/datacenter-api/app/services/dc_service.py`
- Test: `tests/test_nutanix_snapshot_fetch.py`

**Interfaces:**
- Consumes: `shared.nutanix.snapshot_helpers`, `DC_NUTANIX_IPS`, `SNAPSHOTS_BY_IPS_LATEST`, and existing `self._get_connection()`, `self._run_rows(cursor, sql, params)`.
- Produces: `DatabaseService._resolve_dc_nutanix_ips(dc_code, cursor) -> dict[str, str]` (ip→cluster); `DatabaseService._fetch_dc_nutanix_snapshots(dc_code, start_ts, end_ts) -> dict` returning `{"rows": [...], "totals": {...}, "as_of": str}` where each row is a dict with keys `nutanix_ip, cluster, customer, protection_domain_name, vm_names, entity_type, schedule_type, retention, size_in_bytes, start_time, create_time, expiry_time, missing_entity, snapshot_id`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nutanix_snapshot_fetch.py
import datetime as dt
import unittest
from unittest.mock import MagicMock, patch

with patch("psycopg2.pool.ThreadedConnectionPool"):
    from app.services.dc_service import DatabaseService


def _svc():
    with patch("psycopg2.pool.ThreadedConnectionPool"):
        svc = DatabaseService()
    svc._pool = MagicMock()
    return svc


class TestFetchNutanixSnapshots(unittest.TestCase):
    def test_fetch_enriches_and_aggregates(self):
        svc = _svc()
        ip_rows = [("10.34.2.98", "DC13-G17-HYBRID")]
        snap_rows = [
            # nutanix_ip, pd_name, state, vm_names, miss_name, miss_type, sched_type,
            # max_snaps, size, start_time, create_time, expiry_time, snapshot_id
            ("10.34.2.98", "Zorlu_Zes-1Day_7RP", "AVAILABLE", "Zorlu_Zes-Terminal",
             None, None, "DAILY", 7, 4940000000,
             dt.datetime(2025, 3, 25, 5, 44), dt.datetime(2026, 7, 8, 5, 44),
             dt.datetime(2026, 7, 15, 5, 44), "snap-1"),
        ]
        # First _run_rows call = DC IPs; second = snapshots.
        with patch.object(svc, "_run_rows", side_effect=[ip_rows, snap_rows]), \
             patch.object(svc, "_get_connection"):
            out = svc._fetch_dc_nutanix_snapshots("DC13", "s", "e")
        self.assertEqual(len(out["rows"]), 1)
        row = out["rows"][0]
        self.assertEqual(row["cluster"], "DC13-G17-HYBRID")
        self.assertEqual(row["customer"], "Zorlu_Zes")
        self.assertEqual(row["retention"], 7)
        self.assertEqual(out["totals"]["total_snapshots"], 1)
        self.assertEqual(out["totals"]["protected_vms"], 1)

    def test_no_dc_ips_returns_empty(self):
        svc = _svc()
        with patch.object(svc, "_run_rows", side_effect=[[]]), \
             patch.object(svc, "_get_connection"):
            out = svc._fetch_dc_nutanix_snapshots("DCX", "s", "e")
        self.assertEqual(out["rows"], [])
        self.assertEqual(out["totals"]["total_snapshots"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_fetch.py -v`
Expected: FAIL — `AttributeError: 'DatabaseService' object has no attribute '_fetch_dc_nutanix_snapshots'`

- [ ] **Step 3: Write minimal implementation**

Add near the other backup fetchers (after `_fetch_dc_veeam_repositories`, ~`dc_service.py:3736`). Add the import at the top of the file with the other `shared.*` imports:

```python
from shared.nutanix import snapshot_helpers as nsnap
from app.db.queries import nutanix_snapshot as nsq
```

```python
    def _resolve_dc_nutanix_ips(self, dc_code: str, cursor) -> dict[str, str]:
        """{nutanix_ip: cluster_name} for a DC, from the discovery inventory."""
        rows = self._run_rows(cursor, nsq.DC_NUTANIX_IPS, (dc_code,))
        return {ip: cluster for (ip, cluster) in (rows or []) if ip}

    def _fetch_dc_nutanix_snapshots(self, dc_code: str, start_ts, end_ts) -> dict:
        """Latest-per-snapshot rows for a DC, enriched + aggregated."""
        empty = {"rows": [], "totals": nsnap.aggregate_snapshots([]), "as_of": ""}
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                ip_to_cluster = self._resolve_dc_nutanix_ips(dc_code, cur)
                if not ip_to_cluster:
                    return empty
                raw = self._run_rows(
                    cur, nsq.SNAPSHOTS_BY_IPS_LATEST,
                    (list(ip_to_cluster.keys()), start_ts, end_ts),
                )

        rows_out: list[dict] = []
        as_of = ""
        for r in raw or []:
            (ip, pd_name, state, vm_names, miss_name, miss_type, sched_type,
             max_snaps, size, start_time, create_time, expiry_time, snapshot_id) = r
            create_iso = create_time.isoformat() if create_time else ""
            if create_iso > as_of:
                as_of = create_iso
            rows_out.append({
                "nutanix_ip": ip,
                "cluster": ip_to_cluster.get(ip, ""),
                "customer": nsnap.parse_customer(pd_name, vm_names),
                "protection_domain_name": pd_name,
                "vm_names": vm_names,
                "entity_type": miss_type,
                "missing_entity": miss_name,
                "schedule_type": sched_type,
                "retention": nsnap.parse_retention(max_snaps, pd_name),
                "size_in_bytes": int(size or 0),
                "start_time": start_time.isoformat() if start_time else "",
                "create_time": create_iso,
                "expiry_time": expiry_time.isoformat() if expiry_time else "",
                "snapshot_id": snapshot_id,
            })
        return {"rows": rows_out, "totals": nsnap.aggregate_snapshots(rows_out), "as_of": as_of}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_fetch.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/datacenter-api/app/services/dc_service.py tests/test_nutanix_snapshot_fetch.py
git commit -m "feat(nutanix-snap): microservice DC snapshot fetch"
```

---

## Task 5: Microservice cache wrappers + paging + customer + refresh

**Files:**
- Modify: `services/datacenter-api/app/services/dc_service.py`
- Test: `tests/test_nutanix_snapshot_fetch.py`

**Interfaces:**
- Consumes: `_fetch_dc_nutanix_snapshots`; existing `cache` module (`run_singleflight`, `set_with_stale`, `get_with_stale`, `delete_prefix`), `default_time_range()`, `time_range_to_bounds(tr)`, `min_lookback` (implement inline).
- Produces:
  - `get_dc_nutanix_snapshots(dc_code, time_range=None) -> dict` — full cached base set (`{"rows","totals","as_of"}`).
  - `get_dc_nutanix_snapshot_table(dc_code, time_range=None, *, page=1, page_size=50, search="", schedule_type=None) -> dict` — `{"items","total","page","page_size"}`.
  - `get_dc_nutanix_missing(dc_code, time_range=None, *, page=1, page_size=50) -> dict` — same shape, missing-entity rows.
  - `get_customer_nutanix_snapshots(customer, time_range=None) -> dict`.
  - `refresh_dc_nutanix_snapshots(dc_code) -> dict`.

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/test_nutanix_snapshot_fetch.py
class TestCacheWrappers(unittest.TestCase):
    def _base(self):
        return {
            "rows": [
                {"customer": "Zorlu_Zes", "protection_domain_name": "Zorlu_Zes-1Day_7RP",
                 "schedule_type": "DAILY", "missing_entity": None, "size_in_bytes": 10,
                 "nutanix_ip": "10.34.2.98", "cluster": "DC13-G17-HYBRID", "vm_names": "Zorlu_Zes-T"},
                {"customer": "Alisan", "protection_domain_name": "Alisan-1Day_30RP",
                 "schedule_type": "DAILY", "missing_entity": "Alisan-Ghost", "size_in_bytes": 20,
                 "nutanix_ip": "10.34.2.98", "cluster": "DC13-G17-HYBRID", "vm_names": None},
            ],
            "totals": {"total_snapshots": 2}, "as_of": "2026-07-08T05:44:00",
        }

    def test_table_paginates_and_searches(self):
        svc = _svc()
        with patch.object(svc, "get_dc_nutanix_snapshots", return_value=self._base()):
            page = svc.get_dc_nutanix_snapshot_table("DC13", None, page=1, page_size=1)
            self.assertEqual(page["total"], 2)
            self.assertEqual(len(page["items"]), 1)
            hit = svc.get_dc_nutanix_snapshot_table("DC13", None, search="alisan")
            self.assertEqual(hit["total"], 1)
            self.assertEqual(hit["items"][0]["customer"], "Alisan")

    def test_missing_only(self):
        svc = _svc()
        with patch.object(svc, "get_dc_nutanix_snapshots", return_value=self._base()):
            out = svc.get_dc_nutanix_missing("DC13", None)
            self.assertEqual(out["total"], 1)
            self.assertEqual(out["items"][0]["missing_entity"], "Alisan-Ghost")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_fetch.py::TestCacheWrappers -v`
Expected: FAIL — `AttributeError: ... 'get_dc_nutanix_snapshot_table'`

- [ ] **Step 3: Write minimal implementation**

Add after the fetch method. Model the cache on `_set_compute_cached` (`dc_service.py:1039-1048`, which uses `cache.run_singleflight`/`set_with_stale`). Reuse module-level constants for TTLs if present, else literals.

```python
    _NSNAP_FRESH_TTL = 1200      # 20 min
    _NSNAP_STALE_TTL = 86400     # 24 h
    _NSNAP_MIN_LOOKBACK_SECONDS = 48 * 3600

    def _nsnap_effective_bounds(self, tr: dict):
        """Floor start to end-48h so a narrow UI range never empties the panel."""
        start_ts, end_ts = time_range_to_bounds(tr)
        floor = end_ts - dt.timedelta(seconds=self._NSNAP_MIN_LOOKBACK_SECONDS)
        return (min(start_ts, floor), end_ts)

    def get_dc_nutanix_snapshots(self, dc_code: str, time_range: dict | None = None) -> dict:
        tr = time_range or default_time_range()
        start_ts, end_ts = self._nsnap_effective_bounds(tr)
        key = f"dc_nutanix_snap:{dc_code}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val, _ = cache.get_with_stale(key)
        if cached_val is not None:
            return cached_val

        def factory():
            try:
                return self._fetch_dc_nutanix_snapshots(dc_code, start_ts, end_ts)
            except (OperationalError, PoolError) as exc:
                logger.warning("get_dc_nutanix_snapshots failed for %s: %s", dc_code, exc)
                return {"rows": [], "totals": nsnap.aggregate_snapshots([]), "as_of": ""}

        result = cache.run_singleflight(key, factory)
        cache.set_with_stale(key, result, fresh_ttl=self._NSNAP_FRESH_TTL, stale_ttl=self._NSNAP_STALE_TTL)
        return result

    @staticmethod
    def _paginate(items: list[dict], page: int, page_size: int) -> dict:
        page = max(1, int(page or 1))
        page_size = max(1, min(200, int(page_size or 50)))
        total = len(items)
        start = (page - 1) * page_size
        return {"items": items[start:start + page_size], "total": total,
                "page": page, "page_size": page_size}

    def get_dc_nutanix_snapshot_table(self, dc_code: str, time_range: dict | None = None, *,
                                      page: int = 1, page_size: int = 50,
                                      search: str = "", schedule_type: str | None = None) -> dict:
        base = self.get_dc_nutanix_snapshots(dc_code, time_range)
        rows = base.get("rows", [])
        q = (search or "").strip().lower()
        if q:
            rows = [r for r in rows if q in " ".join(str(r.get(k) or "") for k in
                    ("customer", "protection_domain_name", "vm_names", "nutanix_ip", "cluster")).lower()]
        if schedule_type:
            rows = [r for r in rows if (r.get("schedule_type") or "") == schedule_type]
        return self._paginate(rows, page, page_size)

    def get_dc_nutanix_missing(self, dc_code: str, time_range: dict | None = None, *,
                               page: int = 1, page_size: int = 50) -> dict:
        base = self.get_dc_nutanix_snapshots(dc_code, time_range)
        rows = [r for r in base.get("rows", []) if r.get("missing_entity")]
        return self._paginate(rows, page, page_size)

    def get_customer_nutanix_snapshots(self, customer: str, time_range: dict | None = None) -> dict:
        tr = time_range or default_time_range()
        start_ts, end_ts = self._nsnap_effective_bounds(tr)
        key = f"cust_nutanix_snap:{customer}:{tr.get('start','')}:{tr.get('end','')}"
        cached_val, _ = cache.get_with_stale(key)
        if cached_val is not None:
            return cached_val

        def factory():
            try:
                return self._fetch_customer_nutanix_snapshots(customer, start_ts, end_ts)
            except (OperationalError, PoolError) as exc:
                logger.warning("get_customer_nutanix_snapshots failed for %s: %s", customer, exc)
                return {"rows": [], "totals": nsnap.aggregate_snapshots([]), "as_of": ""}

        result = cache.run_singleflight(key, factory)
        cache.set_with_stale(key, result, fresh_ttl=self._NSNAP_FRESH_TTL, stale_ttl=self._NSNAP_STALE_TTL)
        return result

    def refresh_dc_nutanix_snapshots(self, dc_code: str) -> dict:
        cache.delete_prefix(f"dc_nutanix_snap:{dc_code}:")
        cache.delete_prefix(f"stale:dc_nutanix_snap:{dc_code}:")
        return {"status": "ok", "dc": dc_code}
```

Also add the customer fetch (mirrors `_fetch_dc_nutanix_snapshots` but filters by prefix; no DC-IP restriction). Add a new SQL constant `SNAPSHOTS_BY_CUSTOMER_LATEST` in `nutanix_snapshot.py` (params: `customer_prefix, start_ts, end_ts`) that adds `AND (protection_domain_name LIKE %s OR vm_names LIKE %s)` with `customer || '-%'`. Implement `_fetch_customer_nutanix_snapshots` by running that query (no inventory join; `cluster` left blank) and reusing the same enrichment loop.

```python
    def _fetch_customer_nutanix_snapshots(self, customer: str, start_ts, end_ts) -> dict:
        like = f"{customer}-%"
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                raw = self._run_rows(cur, nsq.SNAPSHOTS_BY_CUSTOMER_LATEST,
                                     (like, like, start_ts, end_ts))
        rows_out: list[dict] = []
        as_of = ""
        for r in raw or []:
            (ip, pd_name, state, vm_names, miss_name, miss_type, sched_type,
             max_snaps, size, start_time, create_time, expiry_time, snapshot_id) = r
            create_iso = create_time.isoformat() if create_time else ""
            if create_iso > as_of:
                as_of = create_iso
            rows_out.append({
                "nutanix_ip": ip, "cluster": "",
                "customer": nsnap.parse_customer(pd_name, vm_names),
                "protection_domain_name": pd_name, "vm_names": vm_names,
                "entity_type": miss_type, "missing_entity": miss_name,
                "schedule_type": sched_type,
                "retention": nsnap.parse_retention(max_snaps, pd_name),
                "size_in_bytes": int(size or 0),
                "start_time": start_time.isoformat() if start_time else "",
                "create_time": create_iso,
                "expiry_time": expiry_time.isoformat() if expiry_time else "",
                "snapshot_id": snapshot_id,
            })
        return {"rows": rows_out, "totals": nsnap.aggregate_snapshots(rows_out), "as_of": as_of}
```

`SNAPSHOTS_BY_CUSTOMER_LATEST` (add to `nutanix_snapshot.py`, same SELECT list/order as `SNAPSHOTS_BY_IPS_LATEST` but):
```sql
WHERE (protection_domain_name LIKE %s OR vm_names LIKE %s)
  AND collection_time BETWEEN %s AND %s
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_fetch.py -v`
Expected: PASS (fetch + cache-wrapper tests)

- [ ] **Step 5: Commit**

```bash
git add services/datacenter-api/app/services/dc_service.py services/datacenter-api/app/db/queries/nutanix_snapshot.py tests/test_nutanix_snapshot_fetch.py
git commit -m "feat(nutanix-snap): cached base set, paging, customer, refresh"
```

---

## Task 6: Router endpoints (microservice)

**Files:**
- Modify: `services/datacenter-api/app/routers/datacenters.py`
- Test: `tests/test_nutanix_snapshot_router.py`

**Interfaces:**
- Consumes: the Task-5 `DatabaseService` methods; existing `TimeFilter`, `get_db`, `Query`, `router`.
- Produces routes: `GET /datacenters/{dc_code}/backup/nutanix`, `GET …/backup/nutanix/table`, `GET …/backup/nutanix/missing`, `POST …/backup/nutanix/refresh`, `GET /customers/{customer}/backup/nutanix`.

- [ ] **Step 1: Write the failing test** (use the existing microservice TestClient pattern — check an existing router test for how `app` and `get_db` are overridden; mirror it)

```python
# tests/test_nutanix_snapshot_router.py
import unittest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app          # adjust to the actual FastAPI app import used by other router tests
from app.routers.datacenters import get_db


class TestNutanixRoutes(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_nutanix_summary(self):
        self.db.get_dc_nutanix_snapshots.return_value = {"rows": [], "totals": {"total_snapshots": 0}, "as_of": ""}
        resp = self.client.get("/api/v1/datacenters/DC13/backup/nutanix")
        self.assertEqual(resp.status_code, 200)
        self.db.get_dc_nutanix_snapshots.assert_called_once()

    def test_nutanix_table_passes_paging(self):
        self.db.get_dc_nutanix_snapshot_table.return_value = {"items": [], "total": 0, "page": 2, "page_size": 25}
        resp = self.client.get("/api/v1/datacenters/DC13/backup/nutanix/table?page=2&page_size=25&search=zorlu")
        self.assertEqual(resp.status_code, 200)
        _, kwargs = self.db.get_dc_nutanix_snapshot_table.call_args
        self.assertEqual(kwargs["page"], 2)
        self.assertEqual(kwargs["search"], "zorlu")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_router.py -v`
Expected: FAIL — 404 (routes not registered)

- [ ] **Step 3: Write minimal implementation** (add after the `dc_veeam` block, ~`routers/datacenters.py:79`; mirror `network_interface_table` for the paged one)

```python
@router.get("/datacenters/{dc_code}/backup/nutanix", response_model=dict[str, Any])
def dc_nutanix_snapshots(dc_code: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_dc_nutanix_snapshots(dc_code, tf.to_dict())


@router.get("/datacenters/{dc_code}/backup/nutanix/table", response_model=dict[str, Any])
def dc_nutanix_snapshot_table(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(""),
    schedule_type: Optional[str] = Query(None),
):
    return db.get_dc_nutanix_snapshot_table(
        dc_code, tf.to_dict(), page=page, page_size=page_size,
        search=search, schedule_type=schedule_type,
    )


@router.get("/datacenters/{dc_code}/backup/nutanix/missing", response_model=dict[str, Any])
def dc_nutanix_missing(
    dc_code: str,
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    return db.get_dc_nutanix_missing(dc_code, tf.to_dict(), page=page, page_size=page_size)


@router.post("/datacenters/{dc_code}/backup/nutanix/refresh")
def dc_nutanix_refresh(dc_code: str, db: DatabaseService = Depends(get_db)):
    return db.refresh_dc_nutanix_snapshots(dc_code)


@router.get("/customers/{customer}/backup/nutanix", response_model=dict[str, Any])
def customer_nutanix_snapshots(customer: str, tf: TimeFilter = Depends(), db: DatabaseService = Depends(get_db)):
    return db.get_customer_nutanix_snapshots(customer, tf.to_dict())
```

(If the customer routes live in a different router file than `datacenters.py`, put the `/customers/...` route there, next to the existing customer backup routes.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/datacenter-api/app/routers/datacenters.py tests/test_nutanix_snapshot_router.py
git commit -m "feat(nutanix-snap): router endpoints"
```

---

## Task 7: GUI `api_client` wrappers + refresh

**Files:**
- Modify: `src/services/api_client.py`
- Test: `tests/test_api_client_nutanix_snapshots.py`

**Interfaces:**
- Consumes: existing `_get_client_dc`, `_get_client_cust`, `_get_json`, `_build_time_params`, `_serialize_tr_cache_key`, `_api_cache_get_with_stale`, `quote`.
- Produces: `get_dc_nutanix_snapshots(dc_code, tr) -> dict`; `get_dc_nutanix_snapshot_table(dc_code, tr, page=1, page_size=50, search="", schedule_type=None) -> dict`; `get_dc_nutanix_missing(dc_code, tr, page=1, page_size=50) -> dict`; `get_customer_nutanix_snapshots(customer, tr) -> dict`; `refresh_dc_nutanix_snapshots_cache(dc_code) -> dict`.

- [ ] **Step 1: Write the failing test** (mirror `tests/test_api_client_backup_jobs.py`)

```python
# tests/test_api_client_nutanix_snapshots.py
import unittest
from unittest.mock import patch

from src.services import api_client as api
from src.services import cache_service as cs


class TestNutanixApiClient(unittest.TestCase):
    def setUp(self):
        cs.clear()

    def test_get_dc_nutanix_snapshots_hits_endpoint_and_caches(self):
        payload = {"rows": [{"customer": "Zorlu_Zes"}], "totals": {"total_snapshots": 1}, "as_of": ""}
        with patch("src.services.api_client._get_json", return_value=payload) as mock_json:
            out1 = api.get_dc_nutanix_snapshots("DC13", {"start": "a", "end": "b"})
            out2 = api.get_dc_nutanix_snapshots("DC13", {"start": "a", "end": "b"})
        self.assertEqual(out1["totals"]["total_snapshots"], 1)
        self.assertEqual(out2, out1)
        self.assertEqual(mock_json.call_count, 1)  # second call served from cache

    def test_table_wrapper_passes_params(self):
        with patch("src.services.api_client._get_json", return_value={"items": [], "total": 0}) as mock_json:
            api.get_dc_nutanix_snapshot_table("DC13", {"start": "a", "end": "b"}, page=3, search="x")
        _, kwargs = mock_json.call_args
        self.assertEqual(kwargs["params"]["page"], 3)
        self.assertEqual(kwargs["params"]["search"], "x")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_api_client_nutanix_snapshots.py -v`
Expected: FAIL — `AttributeError: module 'src.services.api_client' has no attribute 'get_dc_nutanix_snapshots'`

- [ ] **Step 3: Write minimal implementation** (add after `get_dc_veeam_repos`, ~`api_client.py:862`; mirror it exactly)

```python
def get_dc_nutanix_snapshots(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    empty = {"rows": [], "totals": {}, "as_of": ""}
    ck = f"api:dc_nutanix_snap:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/backup/nutanix", params=_build_time_params(tr))
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_dc_nutanix_snapshot_table(dc_code: str, tr: Optional[dict], page: int = 1,
                                  page_size: int = 50, search: str = "",
                                  schedule_type: Optional[str] = None) -> dict:
    enc = quote(dc_code, safe="")
    empty = {"items": [], "total": 0, "page": page, "page_size": page_size}
    ck = f"api:dc_nutanix_snap_tbl:{enc}:{_serialize_tr_cache_key(tr)}:p{page}:ps{page_size}:q{search}:st{schedule_type or ''}"

    def fetch() -> dict:
        params = {**_build_time_params(tr), "page": page, "page_size": page_size, "search": search or ""}
        if schedule_type:
            params["schedule_type"] = schedule_type
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/backup/nutanix/table", params=params)
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_dc_nutanix_missing(dc_code: str, tr: Optional[dict], page: int = 1, page_size: int = 50) -> dict:
    enc = quote(dc_code, safe="")
    empty = {"items": [], "total": 0, "page": page, "page_size": page_size}
    ck = f"api:dc_nutanix_miss:{enc}:{_serialize_tr_cache_key(tr)}:p{page}:ps{page_size}"

    def fetch() -> dict:
        params = {**_build_time_params(tr), "page": page, "page_size": page_size}
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/backup/nutanix/missing", params=params)
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_customer_nutanix_snapshots(customer: str, tr: Optional[dict]) -> dict:
    enc = quote(customer, safe="")
    empty = {"rows": [], "totals": {}, "as_of": ""}
    ck = f"api:cust_nutanix_snap:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_cust(), f"/api/v1/customers/{enc}/backup/nutanix", params=_build_time_params(tr))
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def refresh_dc_nutanix_snapshots_cache(dc_code: str) -> dict:
    """Force live-SQL: clear backend + GUI wrapper caches (mirror refresh_dc_backup_jobs_cache)."""
    enc = quote(dc_code, safe="")
    try:
        client = _get_client_dc()
        resp = client.post(f"/api/v1/datacenters/{enc}/backup/nutanix/refresh", headers=_auth_headers(), timeout=10.0)
        resp.raise_for_status()
        payload = resp.json() if resp.content else {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    from src.services import cache_service as cs
    for prefix in (f"api:dc_nutanix_snap:{enc}:", f"api:dc_nutanix_snap_tbl:{enc}:", f"api:dc_nutanix_miss:{enc}:"):
        try:
            cs.delete_prefix(prefix)
        except AttributeError:
            cs.clear()
    return payload
```

Note: if the customer endpoint lives on the DC client (not a separate customer service), use `_get_client_dc()` and the matching path. Verify against how `get_customer_*` wrappers pick their client.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_api_client_nutanix_snapshots.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/api_client.py tests/test_api_client_nutanix_snapshots.py
git commit -m "feat(nutanix-snap): GUI api_client wrappers + refresh"
```

---

## Task 8: Frontend panel `build_nutanix_snapshot_panel`

**Files:**
- Modify: `src/components/backup_panel.py`
- Test: `tests/test_nutanix_snapshot_panel.py`

**Interfaces:**
- Consumes: this file's `_kpi_card`, `_gauge_card`, `smart_bytes`; `dmc`, `html`, `dcc`, `DashIconify`, `go`.
- Produces: `build_nutanix_snapshot_panel(data: dict, table: dict | None = None, missing: dict | None = None) -> html.Div`, where `data` is the `get_dc_nutanix_snapshots` payload, `table` the first-page table payload, `missing` the missing-entities payload.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nutanix_snapshot_panel.py
import unittest
from src.components import backup_panel


class TestNutanixPanel(unittest.TestCase):
    def _data(self):
        return {
            "totals": {"total_snapshots": 2, "total_size_bytes": 300, "protected_vms": 3,
                       "missing_entities": 1, "schedule_type_breakdown": {"DAILY": 2},
                       "state_breakdown": {"AVAILABLE": 2}},
            "rows": [], "as_of": "2026-07-08T05:44:00",
        }

    def test_builds_without_error(self):
        panel = backup_panel.build_nutanix_snapshot_panel(self._data(), table={"items": [], "total": 0}, missing={"items": [], "total": 0})
        self.assertIsNotNone(panel)

    def test_handles_empty(self):
        panel = backup_panel.build_nutanix_snapshot_panel({"totals": {}, "rows": []}, None, None)
        self.assertIsNotNone(panel)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_panel.py -v`
Expected: FAIL — `AttributeError: module 'src.components.backup_panel' has no attribute 'build_nutanix_snapshot_panel'`

- [ ] **Step 3: Write minimal implementation** (append to `backup_panel.py`). Reuse `_kpi_card`, `_gauge_card`, `smart_bytes`. Chart = schedule-type donut (a small `go.Pie`). Table = `dc-premium-table` with the spec's columns rendered from `table["items"]`; include a `dmc.TextInput` (`id="backup-nutanix-search"`) + page controls (`id="backup-nutanix-prev"/"backup-nutanix-next"`, a page-store `dcc.Store id="backup-nutanix-page"`). Missing Entities = `dmc.Accordion` with a table of `missing["items"]`.

```python
def _nutanix_sched_donut(breakdown: dict) -> go.Figure:
    labels = list(breakdown.keys()) or ["No data"]
    values = list(breakdown.values()) or [1]
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=0.72,
        marker=dict(colors=["#4318FF", "#12B886", "#FFB547", "#EE5D50", "#15AABF"]),
        textinfo="label+percent", sort=False)])
    fig.update_layout(
        title=dict(text="<b>Snapshots by Schedule</b>", x=0.5, xanchor="center",
                   font=dict(size=11, color="#A3AED0", family="DM Sans")),
        margin=dict(l=8, r=8, t=28, b=8), showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", height=260)
    return fig


def _nutanix_table(items: list[dict]) -> dmc.Table:
    head = html.Thead(html.Tr([html.Th(h, style={"fontSize": "0.75rem", "color": "#A3AED0"}) for h in [
        "Nutanix IP", "Cluster", "Customer", "Schedule", "VMs", "Entity Type",
        "Schedule Type", "Retention", "Start", "Create", "Expiry", "Size"]]))
    body = []
    for r in items or []:
        body.append(html.Tr([
            html.Td(r.get("nutanix_ip")), html.Td(r.get("cluster")),
            html.Td(r.get("customer") or "—"), html.Td(r.get("protection_domain_name")),
            html.Td((r.get("vm_names") or "")[:60]), html.Td(r.get("entity_type") or "—"),
            html.Td(r.get("schedule_type")), html.Td(str(r.get("retention") or "—")),
            html.Td((r.get("start_time") or "")[:19].replace("T", " ")),
            html.Td((r.get("create_time") or "")[:19].replace("T", " ")),
            html.Td((r.get("expiry_time") or "")[:19].replace("T", " ")),
            html.Td(smart_bytes(r.get("size_in_bytes", 0) or 0)),
        ]))
    return dmc.Table(striped=True, highlightOnHover=True, withTableBorder=False,
                     withColumnBorders=False, className="nexus-table dc-premium-table",
                     children=[head, html.Tbody(body)])


def build_nutanix_snapshot_panel(data: dict, table: dict | None = None, missing: dict | None = None):
    totals = (data or {}).get("totals") or {}
    table = table or {"items": [], "total": 0}
    missing = missing or {"items": [], "total": 0}

    kpis = html.Div(
        style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gridTemplateRows": "1fr 1fr",
               "gap": "8px", "width": "100%", "height": "100%"},
        children=[
            _kpi_card("Total snapshots", f"{int(totals.get('total_snapshots', 0)):,}", "solar:camera-bold-duotone"),
            _kpi_card("Total size", smart_bytes(totals.get("total_size_bytes", 0) or 0), "solar:database-bold-duotone"),
            _kpi_card("Protected VMs", f"{int(totals.get('protected_vms', 0)):,}", "solar:server-bold-duotone"),
            _kpi_card("Missing entities", f"{int(totals.get('missing_entities', 0)):,}", "solar:danger-triangle-bold-duotone"),
        ],
    )
    chart = _gauge_card(_nutanix_sched_donut(totals.get("schedule_type_breakdown") or {}))
    state_panel = html.Div(className="nexus-card dc-kpi-card", style={"padding": "20px 24px"},
                           children=[html.Div("STATE", style={"fontSize": "0.7rem", "fontWeight": 700, "color": "#A3AED0"}),
                                     *[html.Div(f"{k}: {v}", style={"fontSize": "0.9rem", "color": "#2B3674"})
                                       for k, v in (totals.get("state_breakdown") or {}).items()]])

    header_row = html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": "16px", "alignItems": "stretch"},
                          children=[html.Div(style={"minWidth": 0, "height": "100%"}, children=kpis), chart, state_panel])

    controls = dmc.Group(gap="sm", children=[
        dmc.TextInput(id="backup-nutanix-search", placeholder="Ara (müşteri, schedule, VM, IP)", size="sm", style={"minWidth": "280px"}),
        dmc.Button("‹", id="backup-nutanix-prev", size="xs", variant="light"),
        html.Span(id="backup-nutanix-pageinfo", children=f"1 / {max(1, -(-table.get('total', 0) // 50))}"),
        dmc.Button("›", id="backup-nutanix-next", size="xs", variant="light"),
    ])
    dcc_store = dcc.Store(id="backup-nutanix-page", data=1)
    table_card = html.Div(className="nexus-card", style={"padding": "16px", "marginTop": "8px"},
                          children=[controls, dcc_store, html.Div(id="backup-nutanix-table", children=_nutanix_table(table.get("items", [])))])

    missing_section = dmc.Accordion(chevronPosition="right", variant="separated", children=[
        dmc.AccordionItem(value="missing", children=[
            dmc.AccordionControl(f"Missing Entities ({missing.get('total', 0)})"),
            dmc.AccordionPanel(_nutanix_table(missing.get("items", []))),
        ]),
    ])

    return html.Div(children=[header_row, html.Div(style={"height": "16px"}), table_card,
                              html.Div(style={"height": "16px"}), missing_section])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_panel.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/components/backup_panel.py tests/test_nutanix_snapshot_panel.py
git commit -m "feat(nutanix-snap): backup panel component"
```

---

## Task 9: DC view wiring

**Files:**
- Modify: `src/pages/dc_view.py` (lines ~5027 `compute_has_backup`, ~5241 eager batch, ~5338 `has_nutanix_backup`, ~5539 Nutanix tab, export near `_backup_rows_for_export`:196)
- Test: `tests/test_dc_view_has_backup.py`

**Interfaces:**
- Consumes: `api.get_dc_nutanix_snapshots`, `build_nutanix_snapshot_panel`, `api.get_dc_nutanix_snapshot_table`, `api.get_dc_nutanix_missing`.
- Produces: updated `compute_has_backup` (now also true when only Nutanix data exists).

- [ ] **Step 1: Write the failing test** (extend the existing file's `_patch_api`/`_call` to include nutanix)

```python
# add to tests/test_dc_view_has_backup.py
def _patch_api_nx(nb=None, zerto=None, veeam=None, nx=None):
    from unittest.mock import patch
    return (
        patch("src.services.api_client.get_dc_netbackup_pools", return_value=nb or _empty()),
        patch("src.services.api_client.get_dc_zerto_sites", return_value=zerto or _empty()),
        patch("src.services.api_client.get_dc_veeam_repos", return_value=veeam or _empty()),
        patch("src.services.api_client.get_dc_nutanix_snapshots", return_value=nx or {"rows": [], "totals": {}}),
    )


def test_returns_true_when_only_nutanix_has_data():
    p_nb, p_z, p_v, p_nx = _patch_api_nx(nx={"rows": [{"snapshot_id": "s1"}], "totals": {"total_snapshots": 1}})
    with p_nb, p_z, p_v, p_nx:
        from src.pages.dc_view import compute_has_backup
        assert compute_has_backup("DC13", {"start": "x", "end": "y", "preset": "7d"}) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_dc_view_has_backup.py::test_returns_true_when_only_nutanix_has_data -v`
Expected: FAIL — Nutanix not counted (or `get_dc_nutanix_snapshots` not patched/called)

- [ ] **Step 3: Write minimal implementation**

At `compute_has_backup` (`dc_view.py:5027-5043`) add the nutanix fetch and include it:
```python
        nx = api.get_dc_nutanix_snapshots(dc_id, tr)
    ...
    return bool((nb or {}).get("pools") or (zerto or {}).get("sites")
                or (veeam or {}).get("repos") or (nx or {}).get("rows"))
```
At the eager batch (`dc_view.py:5241`) add `"nutanix": lambda: api.get_dc_nutanix_snapshots(dc_id, tr)` and capture `nutanix_data = backup_batch["nutanix"]`; in the non-eager branch set `nutanix_data = {"rows": [], "totals": {}}`.
At line 5338 set `has_nutanix_backup = bool(nutanix_data.get("rows"))`.
At the Nutanix `TabsPanel` (after the netbackup panel, ~5568) add:
```python
                                    dmc.TabsPanel(
                                        value="nutanix", pt="lg",
                                        children=dmc.Stack(gap="lg", children=[
                                            html.Div(
                                                id="backup-nutanix-panel",
                                                children=build_nutanix_snapshot_panel(
                                                    nutanix_data,
                                                    table=api.get_dc_nutanix_snapshot_table(str(dc_id), tr, page=1, page_size=50),
                                                    missing=api.get_dc_nutanix_missing(str(dc_id), tr, page=1, page_size=50),
                                                ) if has_nutanix_backup else html.Div(),
                                            ),
                                        ]),
                                    ) if has_nutanix_backup else None,
```
Import `build_nutanix_snapshot_panel` in the `from src.components.backup_panel import (...)` block (`dc_view.py:62-66`).
Add a "Nutanix Snapshots" export sheet: extend `_backup_rows_for_export`/`_build_export_sheets` to append `nutanix_data["rows"]` under `sheets["Nutanix Snapshots"]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_dc_view_has_backup.py -v`
Expected: PASS (existing + new nutanix test)

- [ ] **Step 5: Commit**

```bash
git add src/pages/dc_view.py tests/test_dc_view_has_backup.py
git commit -m "feat(nutanix-snap): wire DC view backup tab"
```

---

## Task 10: DC view table pagination + search callback

**Files:**
- Modify: `src/pages/dc_view_callbacks.py`
- Test: none new (callback wiring; covered by manual verify). Optionally add a pure-helper test if a page-computation helper is extracted.

**Interfaces:**
- Consumes: `api.get_dc_nutanix_snapshot_table`, the panel IDs `backup-nutanix-search`, `backup-nutanix-page`, `backup-nutanix-prev`, `backup-nutanix-next`, `backup-nutanix-table`, `backup-nutanix-pageinfo`, and `dc-main-tabs`/`url` for lazy-guarding.
- Produces: a registered callback updating `backup-nutanix-table` + `backup-nutanix-pageinfo` from page/search.

- [ ] **Step 1: Implement the callback** (mirror `_make_callback` guard in `backup_jobs_section.py:379`, using `should_skip_fetch`-style active-tab guard and `_extract_dc_id`)

```python
# in src/pages/dc_view_callbacks.py (or a new module imported for side effects)
import dash
from dash import Input, Output, State, callback
from src.services import api_client as api
from src.components.backup_panel import _nutanix_table
from src.components.backup_jobs_section import _extract_dc_id


@callback(
    Output("backup-nutanix-table", "children"),
    Output("backup-nutanix-pageinfo", "children"),
    Output("backup-nutanix-page", "data"),
    Input("backup-nutanix-search", "value"),
    Input("backup-nutanix-prev", "n_clicks"),
    Input("backup-nutanix-next", "n_clicks"),
    Input("dc-main-tabs", "value"),
    State("backup-nutanix-page", "data"),
    State("url", "pathname"),
    prevent_initial_call=True,
)
def _update_nutanix_table(search, prev_n, next_n, active_tab, page, pathname):
    dc_id = _extract_dc_id(pathname)
    if not dc_id or (active_tab or "") != "backup":
        return dash.no_update, dash.no_update, dash.no_update
    page = int(page or 1)
    trig = (dash.callback_context.triggered[0]["prop_id"].split(".")[0]
            if dash.callback_context.triggered else "")
    if trig == "backup-nutanix-next":
        page += 1
    elif trig == "backup-nutanix-prev":
        page = max(1, page - 1)
    elif trig == "backup-nutanix-search":
        page = 1
    payload = api.get_dc_nutanix_snapshot_table(dc_id, None, page=page, page_size=50, search=search or "")
    total = payload.get("total", 0)
    pages = max(1, -(-total // 50))
    page = min(page, pages)
    return _nutanix_table(payload.get("items", [])), f"{page} / {pages}", page
```

- [ ] **Step 2: Verify import side-effect registration**

Ensure the module is imported where the other backup callbacks are registered (dc_view imports `backup_jobs_section` for side effect at `dc_view.py:68`; add the equivalent import if the callback lives in a new module).

- [ ] **Step 3: Run the full suite to confirm no regressions**

Run: `.venv/bin/python -m pytest tests/ -q -k "backup or nutanix or dc_view"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/pages/dc_view_callbacks.py src/pages/dc_view.py
git commit -m "feat(nutanix-snap): DC table pagination/search callback"
```

---

## Task 11: Customer view wiring

**Files:**
- Modify: `src/pages/customer_view.py` (`_build_backup_tabs`, ~line 2060; and the caller that passes `backup_assets`/`backup_totals` — add the customer name + a nutanix payload)
- Test: `tests/test_customer_view_tab_sections.py` (extend)

**Interfaces:**
- Consumes: `api.get_customer_nutanix_snapshots`, `build_nutanix_snapshot_panel`.
- Produces: a "Nutanix" tab appended to the backup nested tabs when the customer has snapshot rows.

- [ ] **Step 1: Write the failing test** (mirror the existing tab-section test; assert a Nutanix tab appears when data present). Inspect `tests/test_customer_view_tab_sections.py` for the existing call shape and follow it.

```python
# sketch — adapt to the file's existing helpers
def test_backup_tabs_include_nutanix_when_present():
    from src.pages.customer_view import _build_backup_tabs
    tabs = _build_backup_tabs(
        backup_assets={}, backup_totals={}, eff_by_cat=None,
        include_sold_vs_used=False,
        nutanix_payload={"rows": [{"snapshot_id": "s1"}], "totals": {"total_snapshots": 1}},
    )
    # walk tabs children for a TabsTab with value == "nutanix"
    assert _has_tab(tabs, "nutanix")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_customer_view_tab_sections.py -k nutanix -v`
Expected: FAIL — `_build_backup_tabs` has no `nutanix_payload` param / no nutanix tab

- [ ] **Step 3: Write minimal implementation**

Add `nutanix_payload: dict | None = None` param to `_build_backup_tabs`; when `nutanix_payload and nutanix_payload.get("rows")`, append:
```python
    if nutanix_payload and nutanix_payload.get("rows"):
        backup_tab_defs.append((
            "nutanix", "Nutanix",
            build_nutanix_snapshot_panel(
                nutanix_payload,
                table={"items": nutanix_payload.get("rows", [])[:50], "total": len(nutanix_payload.get("rows", []))},
                missing={"items": [r for r in nutanix_payload.get("rows", []) if r.get("missing_entity")],
                         "total": sum(1 for r in nutanix_payload.get("rows", []) if r.get("missing_entity"))},
            ),
        ))
```
In the caller that builds the backup tab, fetch `nutanix_payload = api.get_customer_nutanix_snapshots(customer_name, tr)` and pass it in. Import `build_nutanix_snapshot_panel` and `api` at top of `customer_view.py` (follow existing import style). Include Nutanix rows in the customer export path alongside the other vendors.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_customer_view_tab_sections.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pages/customer_view.py tests/test_customer_view_tab_sections.py
git commit -m "feat(nutanix-snap): wire customer view backup tab"
```

---

## Task 12: Warm scheduler job

**Files:**
- Modify: `src/services/scheduler_service.py` (mirror `_warm_dc_network_for_range`, ~line 49, and its registration)
- Test: `tests/test_nutanix_snapshot_warm.py`

**Interfaces:**
- Consumes: `api.get_dc_nutanix_snapshots`, `api.get_dc_nutanix_snapshot_table`, `warm_mode`, the DC-id iteration + `cache_time_ranges`/`default_time_range` the network warm uses.
- Produces: `warm_dc_nutanix_snapshots() -> None` and its scheduler registration.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nutanix_snapshot_warm.py
import unittest
from unittest.mock import patch
from src.services import scheduler_service as sched


class TestNutanixWarm(unittest.TestCase):
    def test_warm_calls_api_in_warm_mode(self):
        with patch("src.services.api_client.get_dc_nutanix_snapshots") as g, \
             patch("src.services.api_client.get_dc_nutanix_snapshot_table"), \
             patch("src.services.scheduler_service._warm_dc_ids", return_value=["DC13"]):
            sched.warm_dc_nutanix_snapshots()
        self.assertTrue(g.called)


if __name__ == "__main__":
    unittest.main()
```
(Adjust `_warm_dc_ids` to whatever helper the network warm uses to enumerate DCs; if it inlines DC enumeration, patch that call instead.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_warm.py -v`
Expected: FAIL — `AttributeError: module 'src.services.scheduler_service' has no attribute 'warm_dc_nutanix_snapshots'`

- [ ] **Step 3: Write minimal implementation** (mirror `_warm_dc_network_for_range` + `warm_dc_network_caches`, `scheduler_service.py:49-85`)

```python
def _warm_dc_nutanix_for_range(tr: dict) -> None:
    from src.services import api_client as api
    from src.services.api_client import warm_mode
    with warm_mode():
        for dc_id in _warm_dc_ids():
            try:
                api.get_dc_nutanix_snapshots(dc_id, tr)
                api.get_dc_nutanix_snapshot_table(dc_id, tr, page=1, page_size=50)
            except Exception as exc:
                logger.warning("GUI nutanix warm failed for DC %s: %s", dc_id, exc)


def warm_dc_nutanix_snapshots() -> None:
    try:
        _warm_dc_nutanix_for_range(default_time_range())
        logger.info("GUI nutanix snapshot cache warm-up complete for default range.")
    except Exception as exc:
        logger.warning("GUI nutanix snapshot warm-up failed: %s", exc)
```
Register it next to `warm_dc_network_caches` in the scheduler setup (same cadence). If the network warm enumerates DCs inline rather than via a `_warm_dc_ids()` helper, extract that enumeration into `_warm_dc_ids()` (small refactor) so both warms share it, and update the network warm to use it.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_nutanix_snapshot_warm.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/scheduler_service.py tests/test_nutanix_snapshot_warm.py
git commit -m "feat(nutanix-snap): warm scheduler job"
```

---

## Final verification

- [ ] Run the full suite: `.venv/bin/python -m pytest tests/ -q`
- [ ] Manual verify (see the `verify`/`run` skills): open a DC view (e.g. DC13) → Backup & Replication → Nutanix; confirm KPIs, donut, paginated table, search, and Missing Entities. Open a customer with snapshots → Backup → Nutanix.
- [ ] Confirm the DC "Yenile"/refresh path triggers live SQL (backend + GUI cache cleared).
- [ ] `git log --oneline` shows one commit per task; branch `feature/nutanix-snapshot-backup-tab`.

## Notes / verify-during-implementation

- **Microservice test import path:** Tasks 3–6 import `app.*` / `shared.*`. Confirm `tests/conftest.py` puts `services/datacenter-api` on `sys.path`; if microservice tests use a different import root, match it.
- **Customer service client:** Task 7 assumes `/customers/{c}/backup/nutanix`. Confirm whether customer endpoints are served by the DC service or a separate customer-api, and pick `_get_client_dc()` vs `_get_client_cust()` accordingly (Task 6 route placement must match).
- **`cache.delete_prefix` on backend:** confirm it also clears the `stale:` mirror (Task 5 clears both prefixes explicitly).
- **Panel private-helper import (`_nutanix_table`) in the callback (Task 10):** acceptable within this codebase's conventions (other callbacks import panel helpers); if lint forbids leading-underscore imports, promote `_nutanix_table` to `nutanix_table`.
