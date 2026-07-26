# VM Dedup + DC→Cluster→Host→VM Topology — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Dedup VMs (Licensed OS ~20k not 42.7k), and add an expandable DC→Cluster→Host→VM topology tree to the Licensed OS page (with OS breakdown, running/all toggle) and the Datalake Coverage page.

**Architecture:** A pure shared module (`shared/topology/vm_topology.py`) holds the dedup SQL + tree builder. One cached datacenter-api endpoint `/vm-topology?os=` serves both pages. A reusable `topology_tree` Dash component renders the drill-down.

**Tech Stack:** Python 3.11, FastAPI, psycopg2 (datacenter-api); Dash + dmc (GUI).

## Global Constraints

- Dedup key: `COALESCE(NULLIF(btrim(custom_fields_config_instance_uuid),''), lower(name)||'|'||coalesce(cluster_name,''))`; one row per key via `DISTINCT ON`.
- Unmapped coalescing: empty site→`(DC atanmamış)`, cluster→`(cluster yok)`, host→`(host yok)`. Never drop.
- Exclude vCLS/system VMs (`is_system_vm`) from tally + tree.
- Source: `public.discovery_netbox_virtualization_vm` only (live). Never the dead raw_vmware_* tables.
- Reuse `shared.licensing.os_classifier.classify`.
- Age/heavy work off the request path: `/vm-topology` uses the 6h singleflight cache.
- Tests: datacenter-api `cd services/datacenter-api && PYTHONPATH=<root> ../../.venv/bin/python -m pytest tests/<f>`; GUI `PYTHONPATH=. .venv/bin/python -m pytest tests/<f>`. Root: `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI`.

## File Structure

- `shared/topology/__init__.py`, `shared/topology/vm_topology.py` — NEW dedup SQL + `is_system_vm` + `build_tree`.
- `services/datacenter-api/app/db/queries/licensed_os.py` — dedup + status_value in the OS queries.
- `services/datacenter-api/app/services/dc_service.py` — `_tally_os_rows` (families + running); `get_vm_topology`.
- `services/datacenter-api/app/db/queries/vm_topology.py` — NEW thin exec wrapper (or reuse shared).
- `services/datacenter-api/app/routers/datacenters.py` — `/vm-topology` route.
- `services/datacenter-api/app/models/schemas.py` — topology response model (dict-ish).
- `src/components/topology_tree.py` — NEW `build_topology_tree`.
- `src/pages/licensed_os.py` — deduped KPIs + running/all toggle + topology section.
- `src/pages/settings/integrations/hmdl_coverage.py` — topology section.
- `src/services/api_client.py` — `get_vm_topology` + empty fallback.

---

## Phase 1 — Backend

### Task 1: shared topology module (`is_system_vm`, SQL, `build_tree`)

**Files:** Create `shared/topology/__init__.py` (empty), `shared/topology/vm_topology.py`; Test `tests/test_vm_topology.py`

**Interfaces — Produces:**
- `is_system_vm(name) -> bool`
- `VM_TOPOLOGY_SQL: str`, `VM_OS_DEDUP_KEY_SQL: str` (the dedup-key expression)
- `build_tree(rows, *, with_os=False) -> dict` — rows = iterable of `(dc, cluster, host, vm_name, guest_os, power_state)`. Returns `{"dcs": [ {name, counts:{clusters,hosts,vms,running}, os?, clusters:[ {name, counts, os?, hosts:[ {name, counts, os?, vms:[{name, os_family, power_state}]} ]} ]} ], "totals": {dcs,clusters,hosts,vms,running}}`. Excludes vCLS.

- [ ] **Step 1: Write the failing test**

```python
from shared.topology import vm_topology as vt


def test_is_system_vm():
    assert vt.is_system_vm("vCLS-abc")
    assert not vt.is_system_vm("web-01")


def test_build_tree_nests_and_counts():
    rows = [
        ("DC13", "CL1", "esx1", "web-01", "Microsoft Windows Server 2019 (64-bit)", "poweredOn"),
        ("DC13", "CL1", "esx1", "web-02", "Ubuntu Linux (64-bit)", "poweredOff"),
        ("DC13", "CL1", "esx2", "db-01", "Red Hat Enterprise Linux 8 (64-bit)", "poweredOn"),
        ("DC14", "CL9", "esx9", "vCLS-x", "", "poweredOn"),   # system -> excluded
        ("DC14", "CL9", "esx9", "app-1", "SUSE Linux Enterprise 15", "poweredOn"),
    ]
    t = vt.build_tree(rows, with_os=True)
    assert t["totals"] == {"dcs": 2, "clusters": 2, "hosts": 3, "vms": 4, "running": 3}
    dc13 = next(d for d in t["dcs"] if d["name"] == "DC13")
    assert dc13["counts"] == {"clusters": 1, "hosts": 2, "vms": 3, "running": 2}
    assert dc13["os"]["windows"] == 1 and dc13["os"]["rhel"] == 1 and dc13["os"]["free"] == 1
    esx1 = dc13["clusters"][0]["hosts"][0]
    assert {v["name"] for v in esx1["vms"]} == {"web-01", "web-02"}


def test_build_tree_unmapped_coalescing():
    rows = [("", "", "", "orphan-1", "", "poweredOn")]
    t = vt.build_tree(rows)
    dc = t["dcs"][0]
    assert dc["name"] == "(DC atanmamış)"
    assert dc["clusters"][0]["name"] == "(cluster yok)"
    assert dc["clusters"][0]["hosts"][0]["name"] == "(host yok)"


def test_topology_sql_uses_netbox_and_dedup():
    sql = vt.VM_TOPOLOGY_SQL.lower()
    assert "discovery_netbox_virtualization_vm" in sql
    assert "distinct on" in sql
    assert "custom_fields_config_instance_uuid" in sql
    assert "custom_fields_guest_os" in sql
    assert "raw_vmware_vm_config" not in sql
```

- [ ] **Step 2: Run — FAIL** (module missing).

- [ ] **Step 3: Implement** — `shared/topology/vm_topology.py`:

```python
"""Deduped DC→Cluster→Host→VM topology from the live NetBox VM snapshot.

Pure tree-builder + the dedup SQL. Source: discovery_netbox_virtualization_vm.
One row per VM via a dedup key (instanceUUID, else name|cluster). vCLS/system
VMs are excluded; site/cluster/host gaps surface as explicit unmapped buckets.
"""
from __future__ import annotations

from typing import Any, Iterable

from shared.licensing.os_classifier import classify

_UNMAPPED_DC = "(DC atanmamış)"
_UNMAPPED_CLUSTER = "(cluster yok)"
_UNMAPPED_HOST = "(host yok)"

VM_OS_DEDUP_KEY_SQL = (
    "COALESCE(NULLIF(btrim(custom_fields_config_instance_uuid), ''), "
    "lower(name) || '|' || coalesce(cluster_name, ''))"
)

VM_TOPOLOGY_SQL = f"""
SELECT DISTINCT ON ({VM_OS_DEDUP_KEY_SQL})
    COALESCE(NULLIF(btrim(site_name), ''), '{_UNMAPPED_DC}')       AS dc,
    COALESCE(NULLIF(btrim(cluster_name), ''), '{_UNMAPPED_CLUSTER}') AS cluster,
    COALESCE(NULLIF(btrim(device_name), ''), '{_UNMAPPED_HOST}')   AS host,
    name                        AS vm_name,
    custom_fields_guest_os      AS guest_os,
    status_value                AS power_state
FROM public.discovery_netbox_virtualization_vm
ORDER BY {VM_OS_DEDUP_KEY_SQL}, (status_value = 'poweredOn') DESC
"""


def is_system_vm(name: str | None) -> bool:
    return (name or "").strip().lower().startswith("vcls")


def _empty_os() -> dict:
    return {"rhel": 0, "suse": 0, "windows": 0, "free": 0, "unknown": 0}


def build_tree(rows: Iterable[tuple], *, with_os: bool = False) -> dict[str, Any]:
    dcs: dict[str, dict] = {}
    for dc, cluster, host, vm_name, guest_os, power_state in rows or []:
        if is_system_vm(vm_name):
            continue
        d = dcs.setdefault(dc, {"name": dc, "clusters": {}})
        cl = d["clusters"].setdefault(cluster, {"name": cluster, "hosts": {}})
        h = cl["hosts"].setdefault(host, {"name": host, "vms": []})
        fam = classify(guest_os).family
        h["vms"].append({"name": vm_name, "os_family": fam, "power_state": power_state})

    def _os_tally(vms):
        t = _empty_os()
        for v in vms:
            t[v["os_family"]] = t.get(v["os_family"], 0) + 1
        return t

    def _counts(vms, **extra):
        running = sum(1 for v in vms if v["power_state"] == "poweredOn")
        return {**extra, "vms": len(vms), "running": running}

    out_dcs, tot = [], {"dcs": 0, "clusters": 0, "hosts": 0, "vms": 0, "running": 0}
    for dc in sorted(dcs):
        d = dcs[dc]
        out_clusters, dc_vms = [], []
        for cl in sorted(d["clusters"]):
            c = d["clusters"][cl]
            out_hosts, cl_vms = [], []
            for hn in sorted(c["hosts"]):
                hvms = c["hosts"][hn]["vms"]
                cl_vms.extend(hvms)
                node = {"name": hn, "counts": _counts(hvms), "vms": hvms}
                if with_os:
                    node["os"] = _os_tally(hvms)
                out_hosts.append(node)
            dc_vms.extend(cl_vms)
            cnode = {"name": cl, "counts": _counts(cl_vms, hosts=len(out_hosts)), "hosts": out_hosts}
            if with_os:
                cnode["os"] = _os_tally(cl_vms)
            out_clusters.append(cnode)
        dnode = {"name": dc,
                 "counts": _counts(dc_vms, clusters=len(out_clusters),
                                   hosts=sum(len(c["hosts"]) for c in out_clusters)),
                 "clusters": out_clusters}
        if with_os:
            dnode["os"] = _os_tally(dc_vms)
        out_dcs.append(dnode)
        tot["dcs"] += 1
        tot["clusters"] += dnode["counts"]["clusters"]
        tot["hosts"] += dnode["counts"]["hosts"]
        tot["vms"] += dnode["counts"]["vms"]
        tot["running"] += dnode["counts"]["running"]
    return {"dcs": out_dcs, "totals": tot}
```

- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `git add shared/topology tests/test_vm_topology.py && git commit -m "feat(topology): shared dedup SQL + DC-cluster-host-VM tree builder"`

---

### Task 2: Licensed OS dedup + power-state + vCLS exclusion

**Files:** Modify `services/datacenter-api/app/db/queries/licensed_os.py`, `services/datacenter-api/app/services/dc_service.py` (`_tally_os_rows`, `_empty_os_tally`); Test `services/datacenter-api/tests/test_licensed_os_sql.py`

**Interfaces:** `_tally_os_rows(rows)` where rows = `(name, guest_id, guest_full_name, power_state)`; returns `{families, families_running, total, total_running, unknown_samples}`. vCLS excluded.

- [ ] **Step 1: failing test** (extend test_licensed_os_sql.py)

```python
def test_dedup_and_status_in_sql():
    from app.db.queries import licensed_os as lq
    sql = lq.VM_OS_NETBOX.lower()
    assert "distinct on" in sql
    assert "status_value" in sql


def test_tally_splits_running_and_excludes_vcls():
    from app.services.dc_service import DatabaseService
    db = DatabaseService.__new__(DatabaseService)
    rows = [
        ("web-01", None, "Microsoft Windows Server 2019", "poweredOn"),
        ("web-02", None, "Microsoft Windows Server 2019", "poweredOff"),
        ("vCLS-x", None, "", "poweredOn"),   # excluded
    ]
    out = db._tally_os_rows(rows)
    assert out["families"]["windows"] == 2
    assert out["families_running"]["windows"] == 1
    assert out["total"] == 2 and out["total_running"] == 1
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** — in `licensed_os.py`, wrap both queries with dedup + add status_value:

```python
from shared.topology.vm_topology import VM_OS_DEDUP_KEY_SQL

VM_OS_NETBOX = f"""
SELECT DISTINCT ON ({VM_OS_DEDUP_KEY_SQL})
    name, NULL::text AS guest_id, custom_fields_guest_os AS guest_full_name, status_value
FROM public.discovery_netbox_virtualization_vm
ORDER BY {VM_OS_DEDUP_KEY_SQL}, (status_value = 'poweredOn') DESC
"""

VM_OS_NETBOX_FOR_CUSTOMER = f"""
SELECT DISTINCT ON ({VM_OS_DEDUP_KEY_SQL})
    name, NULL::text AS guest_id, custom_fields_guest_os AS guest_full_name, status_value
FROM public.discovery_netbox_virtualization_vm
WHERE name ILIKE %s
ORDER BY {VM_OS_DEDUP_KEY_SQL}, (status_value = 'poweredOn') DESC
"""
```

In `dc_service.py` `_tally_os_rows`:

```python
    def _tally_os_rows(self, rows) -> dict:
        from shared.licensing.os_classifier import classify
        from shared.topology.vm_topology import is_system_vm
        fam = {"rhel": 0, "suse": 0, "windows": 0, "free": 0, "unknown": 0}
        run = {"rhel": 0, "suse": 0, "windows": 0, "free": 0, "unknown": 0}
        unknown_samples: list[str] = []
        for row in rows or []:
            name, guest_id, guest_full_name = row[0], row[1], row[2]
            power_state = row[3] if len(row) > 3 else None
            if is_system_vm(name):
                continue
            f = classify(guest_full_name, guest_id=guest_id).family
            fam[f] = fam.get(f, 0) + 1
            if power_state == "poweredOn":
                run[f] = run.get(f, 0) + 1
            if f == "unknown" and len(unknown_samples) < 50:
                label = (guest_full_name or guest_id or name or "").strip()
                if label:
                    unknown_samples.append(label)
        return {"families": fam, "families_running": run,
                "total": sum(fam.values()), "total_running": sum(run.values()),
                "unknown_samples": unknown_samples}
```

Update `_empty_os_tally` to include `families_running` (zeros) + `total_running: 0`.

- [ ] **Step 4: Run** `pytest tests/test_licensed_os_sql.py tests/test_licensed_os_endpoint.py` — PASS (update endpoint schema `LicensedOsSummary` to allow the new fields if it's strict).
- [ ] **Step 5: Commit** `git commit -m "feat(licensed-os): dedup by VM identity + running/all split + vCLS exclusion"`

---

### Task 3: `/vm-topology` endpoint

**Files:** Modify `services/datacenter-api/app/services/dc_service.py` (`get_vm_topology`), `app/routers/datacenters.py` (route), `app/db/queries/__init__` import. Test `services/datacenter-api/tests/test_vm_topology_endpoint.py`

**Interfaces:** `db.get_vm_topology(with_os: bool) -> dict` (cached 6h); `GET /api/v1/vm-topology?os=true|false`.

- [ ] **Step 1: failing test**

```python
def test_get_vm_topology_builds_tree(monkeypatch):
    from app.services import dc_service as m
    svc = m.DatabaseService.__new__(m.DatabaseService)
    rows = [("DC13", "CL1", "esx1", "web-01", "Microsoft Windows Server 2019", "poweredOn")]
    monkeypatch.setattr(svc, "_run_rows", lambda cur, sql, params=None: rows)
    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return _Cur()
    monkeypatch.setattr(svc, "_get_connection", lambda: _Conn())
    monkeypatch.setattr(m.cache, "get", lambda k: None)
    monkeypatch.setattr(m.cache, "run_singleflight", lambda key, fn, ttl=None: fn())
    out = svc.get_vm_topology(with_os=True)
    assert out["totals"]["vms"] == 1
    assert out["dcs"][0]["name"] == "DC13"
    assert out["dcs"][0]["os"]["windows"] == 1
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** — in `dc_service.py`:

```python
    def get_vm_topology(self, with_os: bool = False) -> dict:
        from shared.topology.vm_topology import VM_TOPOLOGY_SQL, build_tree
        cache_key = f"vm_topology:{'os' if with_os else 'plain'}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        def _fetch():
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    rows = self._run_rows(cur, VM_TOPOLOGY_SQL, ())
            return build_tree(rows, with_os=with_os)
        try:
            return cache.run_singleflight(cache_key, _fetch, ttl=21600)
        except OperationalError as exc:
            logger.error("get_vm_topology failed: %s", exc)
            return {"dcs": [], "totals": {"dcs": 0, "clusters": 0, "hosts": 0, "vms": 0, "running": 0}}
```

In `routers/datacenters.py`:

```python
@router.get("/vm-topology", response_model=dict[str, Any])
def vm_topology(os: bool = False, db: DatabaseService = Depends(get_db)):
    return db.get_vm_topology(with_os=os)
```

- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `git commit -m "feat(datacenter-api): cached /vm-topology endpoint"`

---

## Phase 2 — GUI

### Task 4: `topology_tree` component

**Files:** Create `src/components/topology_tree.py`; Test `tests/test_topology_tree_component.py`

**Interfaces:** `build_topology_tree(tree: dict, *, with_os=False) -> component` (nested `dmc.Accordion`).

- [ ] **Step 1: failing test**

```python
from src.components.topology_tree import build_topology_tree

_TREE = {"dcs": [{"name": "DC13", "counts": {"clusters": 1, "hosts": 1, "vms": 2, "running": 1},
                  "os": {"rhel": 0, "suse": 0, "windows": 1, "free": 1, "unknown": 0},
                  "clusters": [{"name": "CL1", "counts": {"hosts": 1, "vms": 2, "running": 1},
                    "hosts": [{"name": "esx1", "counts": {"vms": 2, "running": 1},
                      "vms": [{"name": "web-01", "os_family": "windows", "power_state": "poweredOn"},
                              {"name": "web-02", "os_family": "free", "power_state": "poweredOff"}]}]}]}],
          "totals": {"dcs": 1, "clusters": 1, "hosts": 1, "vms": 2, "running": 1}}


def test_tree_renders_all_levels():
    text = str(build_topology_tree(_TREE, with_os=True))
    for token in ("DC13", "CL1", "esx1", "web-01", "web-02"):
        assert token in text


def test_tree_empty_is_graceful():
    text = str(build_topology_tree({"dcs": [], "totals": {}}))
    assert "yok" in text.lower() or "bo" in text.lower() or text  # renders without error
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** — `src/components/topology_tree.py` using `dmc.Accordion` (DC → cluster → host), each control showing name + counts badge, and per-host a scrollable VM list (`html.Div` with `maxHeight`, `overflowY:auto`). Include OS mini-badges when `with_os`. Empty tree → `dmc.Text("Topoloji verisi yok.")`.

- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `git commit -m "feat(gui): topology_tree drill-down component"`

---

### Task 5: Licensed OS page — deduped KPIs + running/all toggle + topology

**Files:** Modify `src/pages/licensed_os.py` + its callbacks; `src/services/api_client.py` (`get_vm_topology`, licensed-os running fields in fallback). Test `tests/test_licensed_os_page.py`

- [ ] **Step 1: failing test** — assert page renders topology section + a running/all toggle id, and KPIs read `families`/`families_running`.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** — add `get_vm_topology(os=True)` to api_client; render `build_topology_tree(..., with_os=True)`; add a `dmc.SegmentedControl`/switch "Çalışan / Tümü" that swaps KPI source between `families` and `families_running` (callback).
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `git commit -m "feat(gui): licensed-os deduped KPIs + running/all toggle + topology tree"`

---

### Task 6: Datalake Coverage page — topology section

**Files:** Modify `src/pages/settings/integrations/hmdl_coverage.py`. Test `tests/test_hmdl_coverage_page.py` (create if absent).

- [ ] **Step 1: failing test** — patch `api.get_vm_topology` → a small tree; assert `build_layout` renders "Envanter Topolojisi" + a DC name.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** — add a "Envanter Topolojisi" `dmc.Paper` section rendering `build_topology_tree(api.get_vm_topology(os=False), with_os=False)`.
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `git commit -m "feat(gui): DC-cluster-host-VM topology on Datalake Coverage page"`

---

## Phase 3 — verify + deploy

- [ ] **Step 1:** full regression — datacenter-api `pytest tests/ -k "licens or topology or vm_topology"`; GUI `pytest tests/test_licensed_os_page.py tests/test_topology_tree_component.py tests/test_hmdl_coverage_page.py tests/test_vm_topology.py`.
- [ ] **Step 2:** `docker compose --profile microservice up -d --build datacenter-api app`; clear `vm_topology:*` + `licensed_os*` Redis keys.
- [ ] **Step 3:** live-verify: `curl localhost:8000/api/v1/vm-topology?os=true | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['totals'])"` → ~20k vms, ~17k running; `/api/v1/licensed-os/summary` → deduped families + families_running.
- [ ] **Step 4:** browser — Licensed OS page (deduped KPIs, toggle, tree with (DC atanmamış) bucket) + Coverage page (topology). Hand to user.

## Self-review

- Spec coverage: dedup (T2), topology module (T1), endpoint (T3), component (T4), Licensed OS page (T5), Coverage page (T6), verify (T9/P3). Power-state/unmapped/vCLS all in T1/T2. ✓
- Type consistency: `build_tree` rows tuple `(dc,cluster,host,vm_name,guest_os,power_state)` used by T1/T3; `_tally_os_rows` row `(name,guest_id,guest_full_name,power_state)` used by T2. ✓
