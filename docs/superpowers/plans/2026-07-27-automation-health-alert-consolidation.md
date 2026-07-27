# Automation Health Alert Consolidation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the Automation Health page from 40 data alerts to 2 by monitoring only the tables the platform reads and rolling those alerts up per collection flow.

**Architecture:** `freshness_registry.py` gains two curated datasets — `MONITORED` (the 63 tables any service queries) and `FLOWS` (collector → member tables + a customer-facing label). A new pure module `freshness_rollup.py` collapses per-table freshness rows into per-flow rows. `freshness.py` routes discovered specs into monitored/unmonitored buckets and calls the rollup; the response gains `data_flows` and `data_unmonitored`, and `data_counts` is computed over flows instead of tables. The GUI renders one row per alerting flow with per-table detail behind a disclosure, and the unmonitored tables in a collapsed section.

**Tech Stack:** Python 3.11, FastAPI + Pydantic v2 (hmdl-api), Dash + dash-mantine-components (GUI), pytest.

**Spec:** `docs/superpowers/specs/2026-07-27-automation-health-alert-consolidation-design.md`

## Global Constraints

- hmdl-api has **no Redis**; freshness is served from the in-process snapshot (`freshness_snapshot.py`). Never add work to the request path — the ~159-table sweep runs only in the background refresher.
- `resolve()` and everything in `freshness_registry.py` stays **pure** (no DB, no I/O). It is imported by tests without a database.
- Nothing is deleted from the response. Unmonitored tables move to their own bucket; per-table detail stays reachable in the UI.
- Existing response fields (`data_families`, `data_counts`, `data_status`, `data_snapshot_at`) keep their names and shapes. `data_families` continues to be emitted so nothing that reads it breaks.
- User-facing copy is **Turkish**, matching the existing page.
- Run hmdl-api tests from `services/hmdl-api` with `../../.venv/bin/python -m pytest`. Run GUI tests from the repo root with `.venv/bin/python -m pytest`.
- Two pre-existing test failures are unrelated to this work and must not be "fixed" here: `tests/test_dc_view_visibility.py` and `tests/test_network_eager_load.py` fail on a `FakeApi` double missing `get_sellable_summary_light`.

---

### Task 1: Registry — the monitored set

**Files:**
- Modify: `services/hmdl-api/app/services/freshness_registry.py`
- Test: `services/hmdl-api/tests/test_freshness_registry.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `MONITORED: frozenset[str]`, `is_monitored(table: str) -> bool`, and `resolve(...)` now returns a dict carrying an extra `"monitored": bool` key alongside the existing `table`/`column`/`label`/`family`/`warn_hours`/`dead_hours`.

- [ ] **Step 1: Write the failing test**

Append to `services/hmdl-api/tests/test_freshness_registry.py`:

```python
def test_is_monitored_covers_tables_the_platform_reads():
    # Read by datacenter-api / customer-api / crm-engine queries.
    assert fr.is_monitored("cluster_metrics")
    assert fr.is_monitored("raw_vmware_datastore_metrics_agg")
    assert fr.is_monitored("discovery_crm_accounts")
    assert fr.is_monitored("raw_netbackup_jobs_metrics")


def test_monitored_holds_only_base_tables():
    # discover_specs filters table_type = 'BASE TABLE'. A view in MONITORED could
    # never be discovered and would sit in data_missing forever, reporting a
    # curation defect that isn't one. raw_zabbix_network_interface_metrics_v is
    # the live network source but it IS a view — out of this framework's reach.
    assert not fr.is_monitored("raw_zabbix_network_interface_metrics_v")


def test_is_monitored_drops_tables_no_service_queries():
    # Superseded by raw_zabbix_network_interface_metrics_v.
    assert not fr.is_monitored("zabbix_network_interface_metrics")
    # Whole Panduit PDU family: collected, never read.
    assert not fr.is_monitored("raw_panduit_pdu_inventory")
    assert not fr.is_monitored("raw_panduit_pdu_metrics_outlet")
    # VMware collection stopped 2026-03-12; licensed_os.py mentions these in a
    # COMMENT only, and the live source is discovery_netbox_virtualization_vm.
    assert not fr.is_monitored("raw_vmware_vm_config")
    assert not fr.is_monitored("raw_vmware_vm_runtime")


def test_resolve_marks_monitored_flag():
    monitored = fr.resolve(
        "cluster_metrics", ["collection_time"], default_warn=26.0, default_dead=50.0
    )
    assert monitored["monitored"] is True

    unmonitored = fr.resolve(
        "raw_panduit_pdu_inventory", ["collection_time"], default_warn=26.0, default_dead=50.0
    )
    # Still resolved — it must remain visible in the unmonitored bucket, not vanish.
    assert unmonitored is not None
    assert unmonitored["monitored"] is False


def test_resolve_still_drops_excluded_tables():
    assert fr.resolve("loki_devices", ["collection_time"], default_warn=26.0, default_dead=50.0) is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd services/hmdl-api && ../../.venv/bin/python -m pytest tests/test_freshness_registry.py -v
```

Expected: FAIL — `AttributeError: module 'app.services.freshness_registry' has no attribute 'is_monitored'`.

- [ ] **Step 3: Write the implementation**

In `services/hmdl-api/app/services/freshness_registry.py`, insert after the `_EXCLUDE_EXACT` block:

```python
# Tables that at least one service actually queries. Freshness monitoring is
# opt-in by usage: a table nobody reads is not a platform health signal, it is
# the freshness of data the platform abandoned. Auto-discovery monitored all 159
# tables carrying a timestamp column, of which 96 feed no query — that is where
# 33 of the page's 40 alerts came from.
#
# Curated, not computed. hmdl-api cannot see the other services' source at
# runtime, and grepping for table names has two failure modes this set was built
# to avoid: `zabbix_network_interface_metrics` matches inside
# `raw_zabbix_network_interface_metrics_v`, and `raw_vmware_vm_config` matches a
# comment in licensed_os.py that records the table is dead.
#
# Only BASE TABLEs belong here — discover_specs filters on table_type, so a view
# in this set could never be discovered and would sit in data_missing forever
# reporting a curation defect that isn't one. That excludes the live network
# source raw_zabbix_network_interface_metrics_v, which is a view; its freshness
# is out of this framework's reach.
#
# MAINTENANCE: a new query against a new table adds that table here in the same
# commit. A table missing from this set never alerts.
# Seeded 2026-07-27 from a word-boundary sweep of services/, src/, shared/.
MONITORED = frozenset({
    "cluster_metrics", "datacenter_metrics", "discovery_crm_accounts",
    "discovery_crm_pricelevels", "discovery_crm_productpricelevels",
    "discovery_crm_products", "discovery_crm_salesorderdetails",
    "discovery_crm_salesorders", "discovery_loki_location", "discovery_loki_rack",
    "discovery_netbox_inventory_device", "discovery_netbox_virtualization_vm",
    "discovery_nutanix_inventory_cluster", "discovery_nutanix_inventory_vm",
    "discovery_servicecore_incidents", "discovery_servicecore_servicerequests",
    "discovery_servicecore_users", "discovery_vmware_inventory_datastore",
    "ibm_lpar_general", "ibm_lpar_performance_metrics", "ibm_server_general",
    "ibm_server_power", "ibm_vios_general", "nutanix_cluster_metrics",
    "nutanix_host_performance_metrics", "nutanix_snapshot_schedule_metrics",
    "nutanix_vm_metrics", "nutanix_vm_performance_metrics",
    "raw_brocade_port_statistics", "raw_brocade_port_status",
    "raw_brocade_san_fcport_1", "raw_ibm_storage_system",
    "raw_ibm_storage_system_stats", "raw_ibm_storage_vdisk",
    "raw_netbackup_disk_pools_metrics", "raw_netbackup_jobs_metrics",
    "raw_s3icos_pool_metrics", "raw_s3icos_vault_inventory",
    "raw_s3icos_vault_metrics", "raw_veeam_jobs_states",
    "raw_veeam_repositories_states", "raw_veeam_sessions",
    "raw_vmware_datastore_host_mount", "raw_vmware_datastore_metrics_agg",
    "raw_zabbix_hana_linux_host_metrics",
    "raw_zabbix_network_backbone_interface_metrics",
    "raw_zabbix_network_device_health_metrics",
    "raw_zabbix_network_firewall_metrics",
    "raw_zabbix_network_leaf_interface_metrics",
    "raw_zabbix_network_management_interface_metrics",
    "raw_zabbix_network_router_uplink_metrics",
    "raw_zabbix_network_spine_interface_metrics",
    "raw_zabbix_network_switch_shared_interface_metrics",
    "raw_zerto_license_metrics", "raw_zerto_site_metrics", "raw_zerto_vm_metrics",
    "raw_zerto_vpg_metrics", "vm_metrics", "vmhost_metrics",
    "vmware_host_performance_metrics", "vmware_vm_performance_metrics",
    "zabbix_storage_device_metrics", "zabbix_storage_disk_metrics",
})
```

Add the predicate next to `is_excluded`:

```python
def is_monitored(table: str) -> bool:
    """True when at least one service queries this table (see MONITORED)."""
    return table in MONITORED
```

Add the flag to the `resolve()` return dict (keep every existing key):

```python
    return {
        "table": table,
        "column": col,
        "label": _label_for(table),
        "family": ov.get("family") or family_of(table),
        "monitored": is_monitored(table),
        "warn_hours": float(ov.get("warn_hours", default_warn)),
        "dead_hours": float(ov.get("dead_hours", default_dead)),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd services/hmdl-api && ../../.venv/bin/python -m pytest tests/test_freshness_registry.py -v
```

Expected: PASS, including the 5 pre-existing tests.

- [ ] **Step 5: Commit**

```bash
git add services/hmdl-api/app/services/freshness_registry.py services/hmdl-api/tests/test_freshness_registry.py
git commit -m "feat(freshness): monitor only the tables a service actually queries

Auto-discovery monitored every table carrying a timestamp column — 159 of them,
of which 96 feed no query. Those 96 produced 33 of the page's 40 alerts, for data
the platform abandoned. MONITORED is curated rather than computed because
hmdl-api cannot see the other services' source, and name-matching has two proven
failure modes: substring collision and comment matches."
```

---

### Task 2: Registry — collection flows

**Files:**
- Modify: `services/hmdl-api/app/services/freshness_registry.py`
- Test: `services/hmdl-api/tests/test_freshness_registry.py`

**Interfaces:**
- Consumes: `MONITORED` from Task 1.
- Produces: `FLOWS: dict[str, dict]` mapping flow key → `{"label": str, "tables": frozenset[str]}`, and `flow_of(table: str) -> str | None` returning the flow key or `None`.

- [ ] **Step 1: Write the failing test**

Append to `services/hmdl-api/tests/test_freshness_registry.py`:

```python
def test_flow_of_groups_the_datastore_tables():
    assert fr.flow_of("raw_vmware_datastore_metrics_agg") == "vmware_datastore"
    assert fr.flow_of("raw_vmware_datastore_host_mount") == "vmware_datastore"


def test_flow_of_groups_hypervisor_performance_across_vendors():
    # One rollup job feeds all three; they stopped within a day of each other.
    for table in (
        "vmware_host_performance_metrics",
        "vmware_vm_performance_metrics",
        "nutanix_host_performance_metrics",
        "nutanix_vm_performance_metrics",
        "ibm_lpar_performance_metrics",
    ):
        assert fr.flow_of(table) == "hypervisor_performance"


def test_flow_of_returns_none_for_unclassified_table():
    assert fr.flow_of("cluster_metrics") is None


def test_every_flow_member_is_monitored():
    for key, flow in fr.FLOWS.items():
        for table in flow["tables"]:
            assert fr.is_monitored(table), f"{table} in flow {key} is not monitored"


def test_no_table_belongs_to_two_flows():
    seen: set[str] = set()
    for flow in fr.FLOWS.values():
        for table in flow["tables"]:
            assert table not in seen, f"{table} is in more than one flow"
            seen.add(table)


def test_every_flow_has_a_turkish_label():
    for key, flow in fr.FLOWS.items():
        assert flow["label"].strip(), f"flow {key} has no label"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd services/hmdl-api && ../../.venv/bin/python -m pytest tests/test_freshness_registry.py -v
```

Expected: FAIL — `AttributeError: module 'app.services.freshness_registry' has no attribute 'flow_of'`.

- [ ] **Step 3: Write the implementation**

In `services/hmdl-api/app/services/freshness_registry.py`, after `MONITORED`:

```python
# Collection flows: which collector writes which tables. One dead collector is
# one incident, however many tables it feeds — the page used to render a dead
# collector as N alerts (all 10 raw_panduit_* tables stopped in the same minute).
#
# `label` is what a customer reads. It names the DATA, not the table: a customer
# looking at "Raw Vmware Datastore Metrics Agg" has no way to know it is the
# storage figure on their overview.
#
# A table with no flow rolls up under its family, so an unclassified table
# degrades to the previous grouping rather than disappearing.
FLOWS: dict[str, dict] = {
    "vmware_datastore": {
        "label": "Depolama kullanım verisi",
        "tables": frozenset({
            "raw_vmware_datastore_metrics_agg",
            "raw_vmware_datastore_host_mount",
        }),
    },
    "hypervisor_performance": {
        "label": "Sunucu performans verisi",
        "tables": frozenset({
            "vmware_host_performance_metrics",
            "vmware_vm_performance_metrics",
            "nutanix_host_performance_metrics",
            "nutanix_vm_performance_metrics",
            "ibm_lpar_performance_metrics",
        }),
    },
}

_FLOW_BY_TABLE: dict[str, str] = {
    table: key for key, flow in FLOWS.items() for table in flow["tables"]
}


def flow_of(table: str) -> str | None:
    """Flow key that writes this table, or None when it is unclassified."""
    return _FLOW_BY_TABLE.get(table)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd services/hmdl-api && ../../.venv/bin/python -m pytest tests/test_freshness_registry.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/hmdl-api/app/services/freshness_registry.py services/hmdl-api/tests/test_freshness_registry.py
git commit -m "feat(freshness): declare collection flows so one dead collector is one alert

All 10 raw_panduit_* tables stopped in the same minute; the page rendered that as
10 alerts. Flow labels name the data a customer recognises, not the table."
```

---

### Task 3: Flow rollup (pure)

**Files:**
- Create: `services/hmdl-api/app/services/freshness_rollup.py`
- Test: `services/hmdl-api/tests/test_freshness_rollup.py`

**Interfaces:**
- Consumes: `FLOWS`, `flow_of` from Task 2; the per-table row shape produced by `automation_health.build_data_source_row` (`{key, label, cadence, last_run_at, age_hours, status, warn_hours, dead_hours, extra}`).
- Produces:
  - `worst_status(statuses: list[str]) -> str`
  - `build_flow_rows(rows_by_flow: dict[str, list[dict]]) -> list[dict]` where each returned dict is `{"key": str, "label": str, "status": str, "age_hours": float | None, "counts": dict, "sources": list[dict]}`. `rows_by_flow` maps a **flow key** to its member rows; the caller does the grouping.
  - `flow_key_for(table: str, family: str) -> str` — the flow key a table rolls up under, `"family:<Family>"` when unclassified.
  - `flow_counts(flow_rows: list[dict]) -> dict[str, int]` — status tally across flows, the shape `data_counts` takes.

- [ ] **Step 1: Write the failing test**

Create `services/hmdl-api/tests/test_freshness_rollup.py`:

```python
"""Rolling per-table freshness rows up into per-collection-flow rows."""
from app.services import freshness_rollup as roll


def _row(key: str, status: str, age: float | None) -> dict:
    return {
        "key": key, "label": key, "cadence": f"public.{key}",
        "last_run_at": None, "age_hours": age, "status": status,
        "warn_hours": 26.0, "dead_hours": 50.0, "extra": {},
    }


def test_worst_status_prefers_dead_over_everything():
    assert roll.worst_status(["fresh", "stale", "dead"]) == "dead"


def test_worst_status_prefers_stale_over_fresh():
    assert roll.worst_status(["fresh", "stale", "fresh"]) == "stale"


def test_worst_status_all_unknown_is_unknown_not_fresh():
    # Absence of data is not health.
    assert roll.worst_status(["unknown", "unknown"]) == "unknown"


def test_worst_status_mixed_fresh_and_unknown_is_fresh():
    assert roll.worst_status(["fresh", "unknown"]) == "fresh"


def test_worst_status_of_nothing_is_unknown():
    assert roll.worst_status([]) == "unknown"


def test_five_dead_tables_in_one_flow_yield_one_row():
    rows = roll.build_flow_rows({
        "hypervisor_performance": [
            _row("vmware_host_performance_metrics", "dead", 1517.0),
            _row("vmware_vm_performance_metrics", "dead", 1517.0),
            _row("nutanix_host_performance_metrics", "dead", 1485.0),
            _row("nutanix_vm_performance_metrics", "dead", 1485.0),
            _row("ibm_lpar_performance_metrics", "dead", 1490.0),
        ],
    })
    assert len(rows) == 1
    assert rows[0]["status"] == "dead"
    assert rows[0]["counts"]["alert"] == 1


def test_flow_age_is_the_oldest_alerting_member():
    rows = roll.build_flow_rows({
        "vmware_datastore": [
            _row("raw_vmware_datastore_metrics_agg", "dead", 269.0),
            _row("raw_vmware_datastore_host_mount", "dead", 268.0),
        ],
    })
    assert rows[0]["age_hours"] == 269.0


def test_a_fresh_member_does_not_clear_a_dead_sibling():
    rows = roll.build_flow_rows({
        "vmware_datastore": [
            _row("raw_vmware_datastore_metrics_agg", "dead", 269.0),
            _row("raw_vmware_datastore_host_mount", "fresh", 0.4),
        ],
    })
    assert rows[0]["status"] == "dead"
    assert rows[0]["age_hours"] == 269.0


def test_healthy_flow_reports_no_age():
    rows = roll.build_flow_rows({
        "vmware_datastore": [_row("raw_vmware_datastore_metrics_agg", "fresh", 0.4)],
    })
    assert rows[0]["status"] == "fresh"
    assert rows[0]["age_hours"] is None


def test_declared_flow_uses_its_registry_label():
    rows = roll.build_flow_rows({
        "vmware_datastore": [_row("raw_vmware_datastore_metrics_agg", "dead", 269.0)],
    })
    assert rows[0]["label"] == "Depolama kullanım verisi"


def test_family_fallback_key_uses_the_family_name_as_label():
    rows = roll.build_flow_rows({
        "family:NetBox": [_row("discovery_netbox_inventory_device", "fresh", 3.0)],
    })
    assert rows[0]["label"] == "NetBox"


def test_rows_are_sorted_alerting_first():
    rows = roll.build_flow_rows({
        "family:NetBox": [_row("discovery_netbox_inventory_device", "fresh", 3.0)],
        "vmware_datastore": [_row("raw_vmware_datastore_metrics_agg", "dead", 269.0)],
    })
    assert [r["key"] for r in rows] == ["vmware_datastore", "family:NetBox"]


def test_member_rows_are_carried_through_for_the_detail_disclosure():
    rows = roll.build_flow_rows({
        "vmware_datastore": [
            _row("raw_vmware_datastore_metrics_agg", "dead", 269.0),
            _row("raw_vmware_datastore_host_mount", "dead", 268.0),
        ],
    })
    assert [s["key"] for s in rows[0]["sources"]] == [
        "raw_vmware_datastore_metrics_agg", "raw_vmware_datastore_host_mount",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd services/hmdl-api && ../../.venv/bin/python -m pytest tests/test_freshness_rollup.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.freshness_rollup'`.

- [ ] **Step 3: Write the implementation**

Create `services/hmdl-api/app/services/freshness_rollup.py`:

```python
"""Collapse per-table freshness rows into per-collection-flow rows (pure, no DB).

A dead collector feeds N dead tables. Counting tables made one incident read as N
alerts — 10 for the Panduit PDU collector, 5 for the hypervisor performance
rollup. This module counts incidents instead.

Kept separate from app.db.queries.freshness because that module touches the
database; the rollup is pure and testable without one.
"""
from __future__ import annotations

from typing import Any

from app.services import automation_health as ah
from app.services import freshness_registry as reg

_FAMILY_PREFIX = "family:"

# Worst-first. `unknown` sits below the alerting states but above fresh only when
# it is ALL a flow has — a flow with one fresh member is working.
_ALERTING = ("dead", "stale")


def worst_status(statuses: list[str]) -> str:
    """The status a flow reports, given its members' statuses."""
    if not statuses:
        return "unknown"
    for s in _ALERTING:
        if s in statuses:
            return s
    if all(s == "unknown" for s in statuses):
        return "unknown"
    return "fresh"


def _label_for_flow(key: str) -> str:
    if key.startswith(_FAMILY_PREFIX):
        return key[len(_FAMILY_PREFIX):]
    flow = reg.FLOWS.get(key) or {}
    return flow.get("label") or key


def build_flow_rows(rows_by_flow: dict[str, list[dict]]) -> list[dict[str, Any]]:
    """One row per flow. Alerting flows sort first, then by key.

    `age_hours` is the age of the OLDEST alerting member, or None when the flow
    is not alerting — a healthy flow has no incident age to report.
    """
    out: list[dict[str, Any]] = []
    for key in sorted(rows_by_flow):
        sources = rows_by_flow[key]
        statuses = [s.get("status") for s in sources]
        status = worst_status([s for s in statuses if s])
        alerting_ages = [
            float(s["age_hours"])
            for s in sources
            if s.get("status") in _ALERTING and s.get("age_hours") is not None
        ]
        counts = ah.overall_status_counts([s for s in statuses if s])
        # The flow itself is one alert, not one per member.
        counts["alert"] = 1 if status in _ALERTING else 0
        out.append({
            "key": key,
            "label": _label_for_flow(key),
            "status": status,
            "age_hours": max(alerting_ages) if alerting_ages else None,
            "counts": counts,
            "sources": sources,
        })
    out.sort(key=lambda r: (0 if r["status"] in _ALERTING else 1, r["key"]))
    return out


def flow_key_for(table: str, family: str) -> str:
    """Flow key a monitored table rolls up under; falls back to its family."""
    return reg.flow_of(table) or f"{_FAMILY_PREFIX}{family}"


def flow_counts(flow_rows: list[dict]) -> dict[str, int]:
    """Status tally ACROSS flows — this is what the badge and banner show."""
    return ah.overall_status_counts([r["status"] for r in flow_rows])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd services/hmdl-api && ../../.venv/bin/python -m pytest tests/test_freshness_rollup.py -v
```

Expected: PASS (13 tests).

- [ ] **Step 5: Commit**

```bash
git add services/hmdl-api/app/services/freshness_rollup.py services/hmdl-api/tests/test_freshness_rollup.py
git commit -m "feat(freshness): roll per-table freshness up into per-flow incidents

Pure module, no DB, so the rollup rules are testable on fixtures. A flow's age is
its oldest alerting member; a fresh member never clears a dead sibling; all-unknown
reports unknown because absence of data is not health."
```

---

### Task 4: Wire the rollup through the sweep and the response

**Files:**
- Modify: `services/hmdl-api/app/db/queries/freshness.py`
- Modify: `services/hmdl-api/app/services/freshness_snapshot.py:23-37`
- Modify: `services/hmdl-api/app/db/queries/automation_health.py:145-157`
- Modify: `services/hmdl-api/app/models/schemas.py:236-256`
- Test: `services/hmdl-api/tests/test_freshness_queries.py`

**Interfaces:**
- Consumes: `build_flow_rows`, `flow_key_for`, `flow_counts` from Task 3; `resolve()["monitored"]` from Task 1.
- Produces: `compute_freshness()` returns `{"families": [...], "flows": [...], "unmonitored": [...], "missing": [...], "counts": {...}}` where `counts` is now tallied over **flows**. The API response gains `data_flows: list[DataFlow]`, `data_unmonitored: list[AutomationRow]` and `data_missing: list[str]`; `data_counts` is the flow tally.

- [ ] **Step 1: Write the failing test**

Append to `services/hmdl-api/tests/test_freshness_queries.py`:

```python
def test_compute_freshness_splits_monitored_from_unmonitored(monkeypatch):
    from app.db.queries import freshness as fq

    monkeypatch.setattr(fq, "discover_specs", lambda: [
        {"table": "raw_vmware_datastore_metrics_agg", "column": "collection_timestamp",
         "label": "VMware Datastore Metrics", "family": "VMware", "monitored": True,
         "warn_hours": 26.0, "dead_hours": 50.0},
        {"table": "raw_panduit_pdu_inventory", "column": "collection_time",
         "label": "Raw Panduit Pdu Inventory", "family": "Panduit", "monitored": False,
         "warn_hours": 26.0, "dead_hours": 50.0},
    ])
    monkeypatch.setattr(fq, "_age_hours", lambda table, col: 1600.0)

    result = fq.compute_freshness()

    assert [u["key"] for u in result["unmonitored"]] == ["raw_panduit_pdu_inventory"]
    # The unmonitored dead table raises no alert.
    assert result["counts"]["alert"] == 1


def test_compute_freshness_counts_flows_not_tables(monkeypatch):
    from app.db.queries import freshness as fq

    perf = [
        "vmware_host_performance_metrics", "vmware_vm_performance_metrics",
        "nutanix_host_performance_metrics", "nutanix_vm_performance_metrics",
        "ibm_lpar_performance_metrics",
    ]
    monkeypatch.setattr(fq, "discover_specs", lambda: [
        {"table": t, "column": "collection_time", "label": t, "family": "VMware",
         "monitored": True, "warn_hours": 26.0, "dead_hours": 50.0}
        for t in perf
    ])
    monkeypatch.setattr(fq, "_age_hours", lambda table, col: 1500.0)

    result = fq.compute_freshness()

    assert len(result["flows"]) == 1
    assert result["flows"][0]["key"] == "hypervisor_performance"
    assert result["counts"]["alert"] == 1  # not 5


def test_compute_freshness_still_emits_families(monkeypatch):
    from app.db.queries import freshness as fq

    monkeypatch.setattr(fq, "discover_specs", lambda: [
        {"table": "cluster_metrics", "column": "collection_time", "label": "VMware Clusters",
         "family": "VMware", "monitored": True, "warn_hours": 26.0, "dead_hours": 50.0},
    ])
    monkeypatch.setattr(fq, "_age_hours", lambda table, col: 0.5)

    result = fq.compute_freshness()

    assert [f["family"] for f in result["families"]] == ["VMware"]


def test_unmonitored_table_that_is_fresh_still_appears(monkeypatch):
    from app.db.queries import freshness as fq

    monkeypatch.setattr(fq, "discover_specs", lambda: [
        {"table": "raw_brocade_fabric_devices", "column": "collection_time",
         "label": "Raw Brocade Fabric Devices", "family": "Other", "monitored": False,
         "warn_hours": 26.0, "dead_hours": 50.0},
    ])
    monkeypatch.setattr(fq, "_age_hours", lambda table, col: 0.1)

    result = fq.compute_freshness()

    assert len(result["unmonitored"]) == 1
    assert result["counts"]["alert"] == 0


def test_monitored_table_missing_from_discovery_surfaces_as_unknown(monkeypatch):
    """A stale MONITORED entry (table renamed or dropped) must be visible.

    Silently vanishing is how curation rots: the set would keep naming a table
    nobody can find and nobody would ever learn.
    """
    from app.db.queries import freshness as fq

    monkeypatch.setattr(fq, "discover_specs", lambda: [
        {"table": "cluster_metrics", "column": "collection_time", "label": "VMware Clusters",
         "family": "VMware", "monitored": True, "warn_hours": 26.0, "dead_hours": 50.0},
    ])
    monkeypatch.setattr(fq, "_age_hours", lambda table, col: 0.5)

    result = fq.compute_freshness()

    missing = result["missing"]
    # Everything in MONITORED except the one table discovery returned.
    assert "raw_vmware_datastore_metrics_agg" in missing
    assert "cluster_metrics" not in missing
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd services/hmdl-api && ../../.venv/bin/python -m pytest tests/test_freshness_queries.py -v
```

Expected: FAIL — `KeyError: 'unmonitored'`.

- [ ] **Step 3: Write the implementation**

Replace the body of `compute_freshness` in `services/hmdl-api/app/db/queries/freshness.py` (keep `discover_specs` and `_age_hours` unchanged), and add the rollup import at the top:

```python
from app.services import freshness_rollup as roll
```

```python
def compute_freshness() -> dict[str, Any]:
    """{families, flows, unmonitored, counts}.

    `families` is the per-table view kept for drill-down. `flows` is what the page
    and the badge read: one row per collection flow, so a dead collector is one
    alert however many tables it feeds. `counts` is tallied over FLOWS — tallying
    tables is what produced 40 alerts for 2 incidents.

    Tables no service queries land in `unmonitored`: still reported, never counted.
    `missing` names MONITORED tables discovery did not return — a renamed or
    dropped table must be visible, or the curated set rots silently.
    """
    families: dict[str, list[dict]] = {}
    by_flow: dict[str, list[dict]] = {}
    unmonitored: list[dict] = []
    seen: set[str] = set()

    for spec in discover_specs():
        seen.add(spec["table"])
        try:
            age = _age_hours(spec["table"], spec["column"])
        except Exception:  # noqa: BLE001 — one bad table never breaks the sweep
            age = None
        row = ah.build_data_source_row(
            key=spec["table"], label=spec["label"], table=spec["table"],
            last_data_at=None, age_hours=age,
            warn_hours=spec["warn_hours"], dead_hours=spec["dead_hours"],
        )
        if not spec.get("monitored"):
            unmonitored.append(row)
            continue
        families.setdefault(spec["family"], []).append(row)
        by_flow.setdefault(
            roll.flow_key_for(spec["table"], spec["family"]), []
        ).append(row)

    fam_list = [
        {
            "family": fam,
            "counts": ah.overall_status_counts([s["status"] for s in families[fam]]),
            "sources": families[fam],
        }
        for fam in sorted(families)
    ]
    flows = roll.build_flow_rows(by_flow)
    return {
        "families": fam_list,
        "flows": flows,
        "unmonitored": sorted(unmonitored, key=lambda r: r["key"]),
        "missing": sorted(reg.MONITORED - seen),
        "counts": roll.flow_counts(flows),
    }
```

In `services/hmdl-api/app/services/freshness_snapshot.py`, extend the empty snapshot so a consumer reading it before the first sweep gets the same keys:

```python
def get_snapshot() -> dict:
    with _lock:
        if _snapshot is None:
            return {"families": [], "flows": [], "unmonitored": [], "missing": [],
                    "counts": dict(_EMPTY_COUNTS),
                    "generated_at": None, "status": "computing"}
        return _snapshot
```

In `services/hmdl-api/app/db/queries/automation_health.py`, add two keys to the dict at lines 154-157:

```python
        "data_families": snap.get("families", []),
        "data_flows": snap.get("flows", []),
        "data_unmonitored": snap.get("unmonitored", []),
        "data_missing": snap.get("missing", []),
        "data_counts": snap.get("counts", {}),
        "data_status": snap.get("status", "computing"),
        "data_snapshot_at": snap.get("generated_at"),
```

In `services/hmdl-api/app/models/schemas.py`, add the flow model after `DataFamily` (line 240) and two response fields after `data_families` (line 252):

```python
class DataFlow(BaseModel):
    """One collection flow: a collector and every table it writes.

    `age_hours` is the age of the flow's oldest alerting member, or None when the
    flow is healthy. `sources` carries the member tables for UI drill-down.
    """
    key: str
    label: str
    status: str = "unknown"
    age_hours: float | None = None
    counts: AutomationCounts = Field(default_factory=AutomationCounts)
    sources: list[AutomationRow] = Field(default_factory=list)
```

```python
    # Per-collection-flow rollup of the same freshness data. One dead collector is
    # one row here however many tables it feeds; data_counts is tallied over these.
    data_flows: list[DataFlow] = Field(default_factory=list)
    # Tables no service queries: reported so nothing is hidden, never counted.
    data_unmonitored: list[AutomationRow] = Field(default_factory=list)
    # MONITORED names that discovery did not return — a renamed or dropped table.
    # Surfaced so a stale curation entry is visible instead of silently ignored.
    data_missing: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd services/hmdl-api && ../../.venv/bin/python -m pytest tests/ -v
```

Expected: PASS, including the pre-existing `test_freshness_snapshot.py` and `test_automation_health_api.py`.

- [ ] **Step 5: Commit**

```bash
git add services/hmdl-api/app/db/queries/freshness.py services/hmdl-api/app/services/freshness_snapshot.py services/hmdl-api/app/db/queries/automation_health.py services/hmdl-api/app/models/schemas.py services/hmdl-api/tests/test_freshness_queries.py
git commit -m "feat(freshness): serve per-flow rollup and an unmonitored bucket

data_counts is now tallied over flows, so the badge reads 2 where it read 40.
data_families is unchanged and still emitted; unmonitored tables are reported but
never counted."
```

---

### Task 5: GUI — render flows, collapse the unmonitored

**Files:**
- Modify: `src/pages/settings/integrations/hmdl_automation_health.py:84-175`
- Test: `tests/test_hmdl_automation_health_flows.py` (create)

**Interfaces:**
- Consumes: `data_flows`, `data_unmonitored`, `data_counts` from Task 4.
- Produces: no new exports; `build_layout(search: str | None = None) -> html.Div` keeps its signature.

- [ ] **Step 1: Write the failing test**

Create `tests/test_hmdl_automation_health_flows.py`:

```python
"""Automation Health renders one row per collection flow, not one per table.

Assertions read the rendered tree's repr: a Dash component's __repr__ carries both
its id and its text, e.g. ``Div(children=[Text('…')], id='hmdl-ah-flows')``. That
avoids hand-rolling a tree walker whose own bugs would be indistinguishable from
layout bugs.
"""
import dash

from src.pages.settings.integrations import hmdl_automation_health as page


def _render(monkeypatch, payload: dict) -> str:
    monkeypatch.setattr(page.api, "get_hmdl_automation_health", lambda: payload)
    layout = page.build_layout()
    assert isinstance(layout, dash.html.Div)
    return str(layout)


def _flow(key, label, status, age, sources):
    return {"key": key, "label": label, "status": status, "age_hours": age,
            "counts": {"fresh": 0, "stale": 0, "dead": len(sources), "unknown": 0,
                       "alert": 1 if status in ("dead", "stale") else 0},
            "sources": sources}


def _table_row(key, status, age):
    return {"key": key, "label": key, "cadence": f"public.{key}", "last_run_at": None,
            "age_hours": age, "status": status, "warn_hours": 26.0, "dead_hours": 50.0,
            "extra": {}}


_PAYLOAD = {
    "generated_at": None, "automations": [], "counts": {"alert": 0},
    "proxies": [], "proxy_summary": {}, "data_gaps": {},
    "data_families": [],
    "data_flows": [
        _flow("vmware_datastore", "Depolama kullanım verisi", "dead", 269.0,
              [_table_row("raw_vmware_datastore_metrics_agg", "dead", 269.0),
               _table_row("raw_vmware_datastore_host_mount", "dead", 268.0)]),
        _flow("family:NetBox", "NetBox", "fresh", None,
              [_table_row("discovery_netbox_inventory_device", "fresh", 3.0)]),
    ],
    "data_unmonitored": [_table_row("raw_panduit_pdu_inventory", "dead", 1514.0)],
    "data_counts": {"fresh": 1, "stale": 0, "dead": 1, "unknown": 0, "alert": 1},
    "data_status": "ok",
}


def test_flows_container_is_rendered(monkeypatch):
    assert "hmdl-ah-flows" in _render(monkeypatch, _PAYLOAD)


def test_alerting_flow_shows_its_label_not_the_table_name(monkeypatch):
    rendered = _render(monkeypatch, _PAYLOAD)
    assert "Depolama kullanım verisi" in rendered
    # The table name stays reachable (detail disclosure) but is not the headline.
    assert "raw_vmware_datastore_metrics_agg" in rendered


def test_healthy_flow_is_not_listed_as_a_row(monkeypatch):
    # Only alerting flows get a row; a fresh family must not add noise back.
    assert "NetBox" not in _render(monkeypatch, _PAYLOAD)


def test_flow_age_is_rendered_in_days(monkeypatch):
    assert "11 gündür güncellenmiyor" in _render(monkeypatch, _PAYLOAD)


def test_unmonitored_section_renders_and_is_collapsed(monkeypatch):
    rendered = _render(monkeypatch, _PAYLOAD)
    assert "hmdl-ah-unmonitored" in rendered
    assert "raw_panduit_pdu_inventory" in rendered
    assert "İzlenmeyen tablolar (1)" in rendered


def test_computing_state_renders_without_flows(monkeypatch):
    payload = dict(_PAYLOAD, data_status="computing", data_flows=[], data_unmonitored=[])
    assert "hesaplanıyor" in _render(monkeypatch, payload)


def test_no_alerting_flow_renders_the_all_clear(monkeypatch):
    payload = dict(
        _PAYLOAD,
        data_flows=[_flow("family:NetBox", "NetBox", "fresh", None,
                          [_table_row("discovery_netbox_inventory_device", "fresh", 3.0)])],
        data_counts={"fresh": 1, "stale": 0, "dead": 0, "unknown": 0, "alert": 0},
    )
    assert "Tüm veri akışları güncel" in _render(monkeypatch, payload)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_hmdl_automation_health_flows.py -v
```

Expected: FAIL — `assert 'hmdl-ah-flows' in "Div(children=[...])"`, because `build_layout` still renders per-family cards and never emits that container.

- [ ] **Step 3: Write the implementation**

In `src/pages/settings/integrations/hmdl_automation_health.py`, read the new fields in `build_layout` (after line 93):

```python
    data_flows = data.get("data_flows") or []
    data_unmonitored = data.get("data_unmonitored") or []
```

Replace `_family_card` and the `data_body` block (lines 134-158) with a flow renderer:

```python
    def _age_text(age_hours) -> str:
        if age_hours is None:
            return ""
        days = float(age_hours) / 24.0
        if days >= 1:
            return f"{days:.0f} gündür güncellenmiyor"
        return f"{float(age_hours):.0f} saattir güncellenmiyor"

    def _flow_row(flow: dict):
        """One collection flow. The headline names the DATA; the member tables sit
        behind a disclosure so internal users keep what they debug with."""
        status = flow.get("status") or "unknown"
        color = {"dead": "red", "stale": "orange", "unknown": "gray"}.get(status, "green")
        icon = "solar:danger-triangle-bold-duotone" if status in ("dead", "stale") \
            else "solar:check-circle-bold-duotone"
        sources = flow.get("sources") or []
        return dmc.Paper(
            p="md", withBorder=True, radius="md",
            children=[
                dmc.Group(gap="xs", align="center", children=[
                    DashIconify(icon=icon, width=20),
                    dmc.Text(flow.get("label") or flow.get("key") or "—", fw=700),
                    dmc.Text(_age_text(flow.get("age_hours")), size="sm", c=color),
                ]),
                dmc.Accordion(
                    variant="subtle", chevronPosition="left", mt=6,
                    children=[dmc.AccordionItem(value="detay", children=[
                        dmc.AccordionControl(
                            dmc.Text(f"{len(sources)} tablo", size="xs", c="dimmed")
                        ),
                        dmc.AccordionPanel(
                            dmc.Stack(gap=6, children=[_automation_card(s) for s in sources])
                        ),
                    ])],
                ),
            ],
        )

    alerting_flows = [f for f in data_flows if (f.get("status") in ("dead", "stale"))]

    if data_status == "computing":
        data_body = dmc.Text("Veri tazeliği hesaplanıyor… birazdan yenileyin.", size="sm", c="dimmed")
    elif not data_flows:
        data_body = dmc.Text("Veri kaynağı bilgisi yok (hmdl-api erişilemiyor).", size="sm", c="dimmed")
    elif not alerting_flows:
        data_body = dmc.Alert(
            "Tüm veri akışları güncel.", color="green", variant="light",
            icon=DashIconify(icon="solar:check-circle-bold-duotone", width=20),
        )
    else:
        data_body = dmc.Stack(
            gap="sm",
            children=[_flow_row(f) for f in alerting_flows],
        )

    data_body = html.Div(id="hmdl-ah-flows", children=data_body)

    unmonitored_section = dmc.Accordion(
        id="hmdl-ah-unmonitored", variant="contained", chevronPosition="left", mt="md",
        children=[dmc.AccordionItem(value="unmonitored", children=[
            dmc.AccordionControl(
                dmc.Text(
                    f"İzlenmeyen tablolar ({len(data_unmonitored)}) — "
                    "hiçbir servis bu tabloları sorgulamıyor",
                    size="sm", c="dimmed",
                )
            ),
            dmc.AccordionPanel(
                dmc.Stack(gap=6, children=[_automation_card(s) for s in data_unmonitored])
                or dmc.Text("Yok.", size="xs", c="dimmed")
            ),
        ])],
    ) if data_unmonitored else html.Div(id="hmdl-ah-unmonitored")
```

Add `unmonitored_section` to the children of `data_sources_section` (the `dmc.Paper` starting at line 160), immediately after `data_body`.

Confirm `DashIconify` and `html` are already imported at the top of the file; add them to the existing import block if not.

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_hmdl_automation_health_flows.py -v
.venv/bin/python -m pytest tests/ -q -k "hmdl" 
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pages/settings/integrations/hmdl_automation_health.py tests/test_hmdl_automation_health_flows.py
git commit -m "feat(automation-health): show incidents in user language, not table names

The page is reachable by customers, and it listed 40 raw table names in dead
state. It now renders one row per alerting collection flow — 'Depolama kullanım
verisi 11 gündür güncellenmiyor' — with member tables behind a disclosure and the
unmonitored tables in a collapsed section."
```

---

## Verification

After Task 5, verify against the live stack rather than fixtures:

```bash
curl -s "http://localhost:8007/api/v1/collectors/automation-health" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('data_counts.alert :', d['data_counts'].get('alert'), '(was 40)')
print('flows alerting    :', [f['label'] for f in d['data_flows'] if f['status'] in ('dead','stale')])
print('unmonitored       :', len(d['data_unmonitored']), '(expected 96)')
print('missing (curation):', d['data_missing'], '(expected [])')
print('families still on :', len(d['data_families']))"
```

Expected: `alert` is 2, the two labels are `Depolama kullanım verisi` and `Sunucu performans verisi`, `unmonitored` is 96, `data_missing` is empty, and `data_families` is still populated.

Note the hmdl-api container caches the sweep in-process; restart it or wait one `ah_freshness_refresh_min` cycle before reading.

## Out of scope

Restarting the two dead collectors. The datastore flow (dead since 2026-07-16) and the `*_performance_metrics` rollup (dead ~2026-05-26) are operational failures. This plan makes them legible as two named incidents; fixing them is collector work tracked separately.
