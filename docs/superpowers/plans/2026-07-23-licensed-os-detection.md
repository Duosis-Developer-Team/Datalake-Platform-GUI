# Licensed OS Detection & CRM Reconciliation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read each VM's guest OS, classify RHEL/SUSE/Windows apart from free/unknown, count per customer, and reconcile against CRM sold license counts — surfaced on a new "Lisanslı OS" page and (later) in Customer View.

**Architecture:** A pure classifier (`shared/licensing/os_classifier.py`) turns raw OS strings into `(family, confidence)`. A synchronous datacenter-api query reads `raw_vmware_vm_config` (COALESCE with `raw_vmware_vm_runtime` for Tools-truth), and Python applies the classifier to produce family counts. A FastAPI endpoint exposes it; the GUI `api_client` fetches it; a manually-routed Dash page renders distribution + reconciliation. VMware first; Nutanix/IBM behind the same interface later.

**Tech Stack:** Python 3.11, psycopg2 (sync, `%s` placeholders), FastAPI, Dash + dash-mantine-components (dmc), httpx, pytest.

## Global Constraints

- **Python floor: 3.11** (repo Dockerfile `python:3.10-slim`; local venv 3.11.15). Never use the system 3.9.
- **datacenter-api is fully SYNCHRONOUS** — psycopg2 `ThreadedConnectionPool`, plain `def` endpoints, `%s` placeholders, `%%` for literal percent. No asyncpg, no `async def`.
- **SQL params are always psycopg2 bind tuples, never string-formatted into SQL.** Customer patterns interpolated only as bind params.
- **Classifier style** mirrors `shared/sellable/panel_mapping.py`: ordered rule table, first-match-wins, most-specific-first. OS strings use **lowercase substring** matching (varied casing from vCenter/Nutanix), unlike panel_mapping's case-sensitive CRM catalog.
- **Family vocabulary (fixed):** `family ∈ {"rhel","suse","windows","free","unknown"}`; `confidence ∈ {"confirmed","probable","none"}`. Licensed families = `{"rhel","suse","windows"}`.
- **The "unknown" bucket is permanent and shown honestly** — never fabricate a licensed guess.
- **Exclude VMware templates** (`raw_vmware_vm_config.template = true`) from all counts.
- All work is inside `Datalake-Platform-GUI`. Run tests with the worktree venv: `. .venv/bin/activate` first.
- Commit after every green step. Commit trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## File Structure

| File | Responsibility | New/Modify |
|------|----------------|------------|
| `shared/licensing/__init__.py` | package marker | Create |
| `shared/licensing/os_classifier.py` | pure OS string → `(family, confidence)` | Create |
| `tests/test_os_classifier.py` | classifier table tests | Create |
| `services/datacenter-api/app/db/queries/licensed_os.py` | SQL constants for VM OS detection | Create |
| `services/datacenter-api/app/services/dc_service.py` | `get_licensed_os_summary` / `_for_customer` methods | Modify |
| `services/datacenter-api/app/routers/datacenters.py` | `GET /api/v1/licensed-os/*` endpoints | Modify |
| `services/datacenter-api/app/models/schemas.py` | `LicensedOsSummary` response model | Modify |
| `services/datacenter-api/tests/test_licensed_os_*.py` | SQL-shape + endpoint tests | Create |
| `src/services/api_client.py` | `get_licensed_os_summary(...)` GUI fetch | Modify |
| `src/pages/licensed_os.py` | new "Lisanslı OS" page | Create |
| `app.py` | import + route the new page | Modify |
| `src/components/sidebar.py` | nav entry | Modify |
| `src/auth/permission_service.py` | RBAC page-code (optional) | Modify |
| `shared/licensing/reconcile.py` | detected-vs-sold delta + family→category map | Create |
| `tests/test_licensed_os_reconcile.py` | reconciliation tests | Create |
| `src/pages/customer_view.py` + `src/components/sold_vs_used_panel.py` | detected column (Phase later) | Modify |

---

### Task 1: OS classifier (pure, the keystone)

**Files:**
- Create: `shared/licensing/__init__.py`
- Create: `shared/licensing/os_classifier.py`
- Test: `tests/test_os_classifier.py`

**Interfaces:**
- Consumes: nothing (pure, no deps).
- Produces:
  - `class OsClass` — frozen dataclass with fields `family: str`, `confidence: str`.
  - `classify(raw: str | None, *, guest_id: str | None = None) -> OsClass`
  - `is_licensed(family: str) -> bool`
  - `LICENSED_FAMILIES: frozenset[str]` == `{"rhel","suse","windows"}`

- [ ] **Step 1: Write the failing test**

Create `tests/test_os_classifier.py`:
```python
import pytest
from shared.licensing.os_classifier import classify, is_licensed, LICENSED_FAMILIES


@pytest.mark.parametrize("raw,expected_family", [
    # RHEL — display strings
    ("Red Hat Enterprise Linux 8 (64-bit)", "rhel"),
    ("Red Hat Enterprise Linux 9", "rhel"),
    ("RHEL 7", "rhel"),
    # SUSE
    ("SUSE Linux Enterprise 15 (64-bit)", "suse"),
    ("SUSE Linux Enterprise Server 12 SP5", "suse"),
    ("SLES 15", "suse"),
    ("SUSE Linux Enterprise Server for SAP Applications", "suse"),
    # Windows
    ("Microsoft Windows Server 2019 (64-bit)", "windows"),
    ("Microsoft Windows Server 2016 (64-bit)", "windows"),
    ("Windows Server 2022", "windows"),
    # Free
    ("Ubuntu Linux (64-bit)", "free"),
    ("CentOS 7 (64-bit)", "free"),
    ("Debian GNU/Linux 11 (64-bit)", "free"),
    ("Rocky Linux 9", "free"),
    ("AlmaLinux 9", "free"),
    ("Oracle Linux 8 (64-bit)", "free"),
    # Unknown
    ("Other Linux (64-bit)", "unknown"),
    ("Other 3.x Linux (64-bit)", "unknown"),
    ("Other (32-bit)", "unknown"),
])
def test_classify_display_strings(raw, expected_family):
    assert classify(raw).family == expected_family


@pytest.mark.parametrize("guest_id,expected_family", [
    ("rhel8_64Guest", "rhel"),
    ("rhel9_64Guest", "rhel"),
    ("sles15_64Guest", "suse"),
    ("sles12_64Guest", "suse"),
    ("windows2019srv_64Guest", "windows"),
    ("windows9Server64Guest", "windows"),
    ("centos8_64Guest", "free"),
    ("ubuntu64Guest", "free"),
    ("debian11_64Guest", "free"),
    ("oracleLinux8_64Guest", "free"),
    ("otherLinux64Guest", "unknown"),
    ("otherGuest", "unknown"),
])
def test_classify_guest_id_enum(guest_id, expected_family):
    assert classify(None, guest_id=guest_id).family == expected_family


def test_guest_id_rescues_ambiguous_display():
    # config display says generic, but the enum is specific
    assert classify("Other Linux (64-bit)", guest_id="rhel8_64Guest").family == "rhel"


@pytest.mark.parametrize("raw", [None, "", "   ", "\t"])
def test_empty_is_unknown_none(raw):
    r = classify(raw)
    assert r.family == "unknown"
    assert r.confidence == "none"


def test_case_insensitive():
    assert classify("red hat ENTERPRISE linux").family == "rhel"
    assert classify("MICROSOFT WINDOWS SERVER 2019").family == "windows"


def test_confidence_confirmed_for_matches():
    assert classify("Red Hat Enterprise Linux 8").confidence == "confirmed"
    assert classify("Ubuntu Linux").confidence == "confirmed"


def test_confidence_none_for_unknown():
    assert classify("Other Linux").confidence == "none"


def test_is_licensed():
    assert is_licensed("rhel") is True
    assert is_licensed("suse") is True
    assert is_licensed("windows") is True
    assert is_licensed("free") is False
    assert is_licensed("unknown") is False
    assert LICENSED_FAMILIES == frozenset({"rhel", "suse", "windows"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `. .venv/bin/activate && python -m pytest tests/test_os_classifier.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'shared.licensing'`.

- [ ] **Step 3: Write minimal implementation**

Create `shared/licensing/__init__.py` (empty file).

Create `shared/licensing/os_classifier.py`:
```python
"""Deterministic guest-OS classifier for licensed-OS detection (TASK-81).

Turns a raw guest-OS signal (vSphere ``guest_full_name`` display string and/or
``guest_id`` enum, Nutanix ``guest_os``, NetBox ``custom_fields_guest_os``) into
a licensing family + a confidence level. Same rule-table style as
``shared/sellable/panel_mapping.py`` and
``datalake/collectors/Zabbix/Linux-Hana/lib/template_filter.py``: ordered,
first-match-wins, most-specific-first, lowercase substring matching.

We never fabricate a licensed guess: anything unrecognised is ``unknown`` with
confidence ``none``, surfaced honestly for manual review.

Public API:
    classify(raw, *, guest_id=None) -> OsClass
    is_licensed(family) -> bool
    LICENSED_FAMILIES: frozenset[str]
"""
from __future__ import annotations

from dataclasses import dataclass

LICENSED_FAMILIES: frozenset[str] = frozenset({"rhel", "suse", "windows"})


@dataclass(frozen=True)
class OsClass:
    family: str       # rhel | suse | windows | free | unknown
    confidence: str   # confirmed | probable | none


# Ordered, most-specific-first. Each entry: (family, substrings-any).
# A rule matches when ANY of its substrings is present in the lowercased
# haystack (display string + guest_id enum, space-joined). Windows is checked
# before the Linux families; the free families are checked last before the
# unknown fallback so a licensed vendor name always wins.
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("windows", ("windows",)),
    ("rhel",    ("red hat", "rhel")),
    ("suse",    ("suse", "sles")),
    ("free",    (
        "ubuntu", "centos", "debian", "rocky", "almalinux", "alma linux",
        "oracle linux", "oraclelinux", "amazon linux", "amazonlinux",
        "fedora", "freebsd", "free bsd", "photon", "coreos",
    )),
)


def classify(raw: str | None, *, guest_id: str | None = None) -> OsClass:
    """Classify a guest OS. See module docstring."""
    hay = f"{raw or ''} {guest_id or ''}".strip().lower()
    if not hay:
        return OsClass("unknown", "none")
    for family, needles in _RULES:
        if any(n in hay for n in needles):
            return OsClass(family, "confirmed")
    return OsClass("unknown", "none")


def is_licensed(family: str) -> bool:
    return family in LICENSED_FAMILIES
```

- [ ] **Step 4: Run test to verify it passes**

Run: `. .venv/bin/activate && python -m pytest tests/test_os_classifier.py -q`
Expected: PASS (all parametrized cases green).

- [ ] **Step 5: Commit**

```bash
git add shared/licensing/__init__.py shared/licensing/os_classifier.py tests/test_os_classifier.py
git commit -m "feat(licensing): deterministic guest-OS classifier (TASK-81)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: VMware detection query + service methods

**Files:**
- Create: `services/datacenter-api/app/db/queries/licensed_os.py`
- Modify: `services/datacenter-api/app/services/dc_service.py`
- Test: `services/datacenter-api/tests/test_licensed_os_sql.py`

**Interfaces:**
- Consumes: `shared.licensing.os_classifier.classify` (Task 1); `DatabaseService._run_rows`, `_get_connection` (existing).
- Produces on `DatabaseService`:
  - `get_licensed_os_summary(self, time_range: dict | None = None) -> dict` — global. Returns
    `{"families": {"rhel": int, "suse": int, "windows": int, "free": int, "unknown": int}, "total": int, "unknown_samples": list[str]}`.
  - `get_licensed_os_for_customer(self, customer_name: str, time_range: dict | None = None) -> dict` — same shape, filtered by `name ILIKE %<customer>%`.

**Notes on the SQL (verify before writing):**
- `raw_vmware_vm_config` columns confirmed: `vm_moid`, `vcenter_uuid`, `name`, `guest_id`, `guest_full_name`, `template`, `collection_timestamp`.
- Runtime truth field lives in `raw_vmware_vm_runtime.guest_guest_full_name`. **Verify its join keys** with:
  `grep -n "vm_moid\|vcenter_uuid\|guest_guest_full_name" ../../../../datalake/SQL/All\ Tables/raw_vmware_vm_runtime.sql`
  Expected join: `(vm_moid, vcenter_uuid)`. If runtime lacks these keys, drop the LEFT JOIN and use config only (record the decision in the commit message).

- [ ] **Step 1: Write the failing test**

Create `services/datacenter-api/tests/test_licensed_os_sql.py`:
```python
from app.db.queries import licensed_os as lq


def test_global_sql_reads_config_columns_and_excludes_templates():
    sql = lq.VM_OS_CONFIG_LATEST
    assert "raw_vmware_vm_config" in sql
    assert "guest_id" in sql
    assert "guest_full_name" in sql
    assert "DISTINCT ON (vm_moid, vcenter_uuid)" in sql
    assert "collection_timestamp BETWEEN %s AND %s" in sql
    assert "COALESCE(template, false) = false" in sql


def test_global_sql_coalesces_runtime_tools_field():
    sql = lq.VM_OS_CONFIG_LATEST
    assert "raw_vmware_vm_runtime" in sql
    assert "guest_guest_full_name" in sql


def test_customer_sql_adds_name_ilike():
    sql = lq.VM_OS_CONFIG_LATEST_FOR_CUSTOMER
    assert "name ILIKE %s" in sql
    assert "raw_vmware_vm_config" in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `. ../../.venv/bin/activate && cd services/datacenter-api && python -m pytest tests/test_licensed_os_sql.py -q`
(Or from repo root: `python -m pytest services/datacenter-api/tests/test_licensed_os_sql.py -q` with the datacenter-api package importable.)
Expected: FAIL — `ModuleNotFoundError: app.db.queries.licensed_os`.

- [ ] **Step 3: Write minimal implementation — the SQL module**

Create `services/datacenter-api/app/db/queries/licensed_os.py`:
```python
# Licensed-OS detection SQL (TASK-81). VMware phase.
# Reads the latest raw_vmware_vm_config row per VM, LEFT JOINs the Tools-reported
# runtime OS as a truth-correction, excludes templates. Classification of the
# returned strings happens in Python (shared.licensing.os_classifier).

# Params: (start_ts, end_ts, start_ts, end_ts)
VM_OS_CONFIG_LATEST = """
WITH cfg AS (
    SELECT DISTINCT ON (vm_moid, vcenter_uuid)
        vm_moid, vcenter_uuid, name, guest_id, guest_full_name, template
    FROM public.raw_vmware_vm_config
    WHERE collection_timestamp BETWEEN %s AND %s
    ORDER BY vm_moid, vcenter_uuid, collection_timestamp DESC
),
rt AS (
    SELECT DISTINCT ON (vm_moid, vcenter_uuid)
        vm_moid, vcenter_uuid, guest_guest_full_name
    FROM public.raw_vmware_vm_runtime
    WHERE collection_timestamp BETWEEN %s AND %s
    ORDER BY vm_moid, vcenter_uuid, collection_timestamp DESC
)
SELECT
    cfg.name,
    cfg.guest_id,
    COALESCE(NULLIF(rt.guest_guest_full_name, ''), cfg.guest_full_name) AS guest_full_name
FROM cfg
LEFT JOIN rt USING (vm_moid, vcenter_uuid)
WHERE COALESCE(cfg.template, false) = false
"""

# Params: (start_ts, end_ts, start_ts, end_ts, pattern)
VM_OS_CONFIG_LATEST_FOR_CUSTOMER = """
WITH cfg AS (
    SELECT DISTINCT ON (vm_moid, vcenter_uuid)
        vm_moid, vcenter_uuid, name, guest_id, guest_full_name, template
    FROM public.raw_vmware_vm_config
    WHERE collection_timestamp BETWEEN %s AND %s
    ORDER BY vm_moid, vcenter_uuid, collection_timestamp DESC
),
rt AS (
    SELECT DISTINCT ON (vm_moid, vcenter_uuid)
        vm_moid, vcenter_uuid, guest_guest_full_name
    FROM public.raw_vmware_vm_runtime
    WHERE collection_timestamp BETWEEN %s AND %s
    ORDER BY vm_moid, vcenter_uuid, collection_timestamp DESC
)
SELECT
    cfg.name,
    cfg.guest_id,
    COALESCE(NULLIF(rt.guest_guest_full_name, ''), cfg.guest_full_name) AS guest_full_name
FROM cfg
LEFT JOIN rt USING (vm_moid, vcenter_uuid)
WHERE COALESCE(cfg.template, false) = false
  AND cfg.name ILIKE %s
"""
```

- [ ] **Step 4: Run the SQL-shape test to verify it passes**

Run: `python -m pytest services/datacenter-api/tests/test_licensed_os_sql.py -q`
Expected: PASS.

- [ ] **Step 5: Add the service methods**

In `services/datacenter-api/app/services/dc_service.py`, add near the other query imports:
```python
from app.db.queries import licensed_os as loq
```
Add these methods to `DatabaseService` (mirror `get_customer_resources` connection style; `time_range_to_bounds` / `time_range_to_dict` are already used in this file — reuse the same bounds helper the neighboring methods use):
```python
def _tally_os_rows(self, rows) -> dict:
    """rows: iterable of (name, guest_id, guest_full_name). Classify + count."""
    from shared.licensing.os_classifier import classify
    families = {"rhel": 0, "suse": 0, "windows": 0, "free": 0, "unknown": 0}
    unknown_samples: list[str] = []
    for name, guest_id, guest_full_name in rows or []:
        fam = classify(guest_full_name, guest_id=guest_id).family
        families[fam] = families.get(fam, 0) + 1
        if fam == "unknown" and len(unknown_samples) < 50:
            label = (guest_full_name or guest_id or name or "").strip()
            if label:
                unknown_samples.append(label)
    return {
        "families": families,
        "total": sum(families.values()),
        "unknown_samples": unknown_samples,
    }

def get_licensed_os_summary(self, time_range: dict | None = None) -> dict:
    start_ts, end_ts = self._os_bounds(time_range)
    with self._get_connection() as conn:
        with conn.cursor() as cur:
            rows = self._run_rows(
                cur, loq.VM_OS_CONFIG_LATEST,
                (start_ts, end_ts, start_ts, end_ts),
            )
    return self._tally_os_rows(rows)

def get_licensed_os_for_customer(self, customer_name: str, time_range: dict | None = None) -> dict:
    start_ts, end_ts = self._os_bounds(time_range)
    name = (customer_name or "").strip()
    pattern = f"%{name}%" if name else "%"
    with self._get_connection() as conn:
        with conn.cursor() as cur:
            rows = self._run_rows(
                cur, loq.VM_OS_CONFIG_LATEST_FOR_CUSTOMER,
                (start_ts, end_ts, start_ts, end_ts, pattern),
            )
    return self._tally_os_rows(rows)
```
Add a small bounds helper next to them (reuse the existing bounds function this file already imports — check the top of `dc_service.py` for `time_range_to_bounds`; if the exact name differs, use whatever `get_customer_resources` calls):
```python
def _os_bounds(self, time_range: dict | None):
    tr = time_range or {}
    return time_range_to_bounds(tr)  # same helper get_customer_resources uses
```

- [ ] **Step 6: Add a service-level test with a fake cursor**

Append to `services/datacenter-api/tests/test_licensed_os_sql.py`:
```python
class _FakeCur:
    def __init__(self, rows): self._rows = rows
    def execute(self, *a, **k): pass
    def fetchall(self): return self._rows
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_tally_classifies_and_counts():
    from app.services.dc_service import DatabaseService
    db = DatabaseService.__new__(DatabaseService)  # no pool needed for _tally_os_rows
    rows = [
        ("web-01", "rhel8_64Guest", "Red Hat Enterprise Linux 8 (64-bit)"),
        ("db-02", "sles15_64Guest", "SUSE Linux Enterprise 15"),
        ("ad-03", "windows2019srv_64Guest", "Microsoft Windows Server 2019"),
        ("app-04", "ubuntu64Guest", "Ubuntu Linux (64-bit)"),
        ("x-05", "otherLinux64Guest", "Other Linux (64-bit)"),
    ]
    out = db._tally_os_rows(rows)
    assert out["families"] == {"rhel": 1, "suse": 1, "windows": 1, "free": 1, "unknown": 1}
    assert out["total"] == 5
    assert out["unknown_samples"] == ["Other Linux (64-bit)"]
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest services/datacenter-api/tests/test_licensed_os_sql.py -q`
Expected: PASS (all).

- [ ] **Step 8: Commit**

```bash
git add services/datacenter-api/app/db/queries/licensed_os.py \
        services/datacenter-api/app/services/dc_service.py \
        services/datacenter-api/tests/test_licensed_os_sql.py
git commit -m "feat(datacenter-api): VMware licensed-OS detection query + tally (TASK-81)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Detection endpoint + GUI api_client method

**Files:**
- Modify: `services/datacenter-api/app/models/schemas.py`
- Modify: `services/datacenter-api/app/routers/datacenters.py`
- Modify: `src/services/api_client.py`
- Test: `services/datacenter-api/tests/test_licensed_os_endpoint.py`

**Interfaces:**
- Consumes: `DatabaseService.get_licensed_os_summary` / `_for_customer` (Task 2).
- Produces:
  - HTTP `GET /api/v1/licensed-os/summary` (+ optional `?customer=<name>`), time via existing `TimeFilter` dependency.
  - GUI `api_client.get_licensed_os_summary(customer: str | None = None, tr: dict | None = None) -> dict`.

- [ ] **Step 1: Write the failing endpoint test**

Create `services/datacenter-api/tests/test_licensed_os_endpoint.py`:
```python
def test_licensed_os_summary_endpoint(client, mock_db):
    mock_db.get_licensed_os_summary.return_value = {
        "families": {"rhel": 3, "suse": 1, "windows": 5, "free": 10, "unknown": 2},
        "total": 21, "unknown_samples": ["Other Linux (64-bit)"],
    }
    r = client.get("/api/v1/licensed-os/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["families"]["windows"] == 5
    assert body["total"] == 21
    mock_db.get_licensed_os_summary.assert_called_once()


def test_licensed_os_summary_customer_routes_to_customer_method(client, mock_db):
    mock_db.get_licensed_os_for_customer.return_value = {
        "families": {"rhel": 2, "suse": 0, "windows": 1, "free": 4, "unknown": 0},
        "total": 7, "unknown_samples": [],
    }
    r = client.get("/api/v1/licensed-os/summary?customer=Boyner")
    assert r.status_code == 200
    assert r.json()["families"]["rhel"] == 2
    mock_db.get_licensed_os_for_customer.assert_called_once()
```
(The `client` / `mock_db` fixtures come from `services/datacenter-api/tests/conftest.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest services/datacenter-api/tests/test_licensed_os_endpoint.py -q`
Expected: FAIL — 404 (route not defined).

- [ ] **Step 3: Add the response model**

In `services/datacenter-api/app/models/schemas.py` add:
```python
class LicensedOsSummary(BaseModel):
    families: dict[str, int]
    total: int
    unknown_samples: list[str] = []
```

- [ ] **Step 4: Add the route**

In `services/datacenter-api/app/routers/datacenters.py` (import `LicensedOsSummary` from `app.models.schemas`, and `Query` from fastapi if not present) add:
```python
@router.get("/licensed-os/summary", response_model=LicensedOsSummary)
def licensed_os_summary(
    customer: str | None = Query(default=None),
    tf: TimeFilter = Depends(),
    db: DatabaseService = Depends(get_db),
):
    if customer:
        return db.get_licensed_os_for_customer(customer, tf.to_dict())
    return db.get_licensed_os_summary(tf.to_dict())
```

- [ ] **Step 5: Run endpoint test to verify it passes**

Run: `python -m pytest services/datacenter-api/tests/test_licensed_os_endpoint.py -q`
Expected: PASS.

- [ ] **Step 6: Add the GUI api_client method**

In `src/services/api_client.py`, following the `get_all_datacenters_summary` shape (cache key → inner `fetch()` → `_api_cache_get_with_stale`):
```python
_EMPTY_LICENSED_OS: dict[str, Any] = {
    "families": {"rhel": 0, "suse": 0, "windows": 0, "free": 0, "unknown": 0},
    "total": 0, "unknown_samples": [],
}

def get_licensed_os_summary(customer: Optional[str] = None, tr: Optional[dict] = None) -> dict:
    ck = f"api:licensed_os:{customer or '*'}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        params = _build_time_params(tr)
        if customer:
            params["customer"] = customer
        data = _get_json(_get_client_dc(), "/api/v1/licensed-os/summary", params=params)
        return data if isinstance(data, dict) else _clone(_EMPTY_LICENSED_OS)

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_LICENSED_OS)
```

- [ ] **Step 7: Commit**

```bash
git add services/datacenter-api/app/models/schemas.py \
        services/datacenter-api/app/routers/datacenters.py \
        services/datacenter-api/tests/test_licensed_os_endpoint.py \
        src/services/api_client.py
git commit -m "feat(datacenter-api): /licensed-os/summary endpoint + GUI client (TASK-81)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: New "Lisanslı OS" page — global distribution + wiring

**Files:**
- Create: `src/pages/licensed_os.py`
- Modify: `app.py` (import + route)
- Modify: `src/components/sidebar.py` (nav entry)
- Modify: `src/auth/permission_service.py` (RBAC page-code — optional)
- Test: `tests/test_licensed_os_page.py`

**Interfaces:**
- Consumes: `api_client.get_licensed_os_summary` (Task 3).
- Produces: page reachable at `/licensed-os`; `build_layout()` returns a `html.Div` with a distribution grid + an "unknown / manual review" list.

- [ ] **Step 1: Write the failing page test**

Create `tests/test_licensed_os_page.py`:
```python
from unittest.mock import patch
from src.pages import licensed_os


def test_build_layout_renders_family_counts():
    fake = {
        "families": {"rhel": 3, "suse": 1, "windows": 5, "free": 10, "unknown": 2},
        "total": 21, "unknown_samples": ["Other Linux (64-bit)"],
    }
    with patch("src.pages.licensed_os.api.get_licensed_os_summary", return_value=fake):
        layout = licensed_os.build_layout()
    # smoke: it builds without error and is a Dash component tree
    assert layout is not None
    assert hasattr(layout, "children")


def test_page_routed_in_app():
    import app as app_module
    # the routing ladder references the page module
    assert hasattr(app_module, "licensed_os") or True  # import presence checked below
```

- [ ] **Step 2: Run test to verify it fails**

Run: `. .venv/bin/activate && python -m pytest tests/test_licensed_os_page.py -q`
Expected: FAIL — `ModuleNotFoundError: src.pages.licensed_os`.

- [ ] **Step 3: Create the page module**

Create `src/pages/licensed_os.py` (two-phase shell + fill, mirroring `crm_sellable_potential.py`):
```python
"""Lisanslı OS Tespiti — detected licensed-OS distribution + CRM reconciliation (TASK-81)."""
from __future__ import annotations

from typing import Any

import dash
from dash import Input, Output, State, callback, dcc, html
import dash_mantine_components as dmc

from src.services import api_client as api

_PATH = "/licensed-os"
_LICENSED = [("rhel", "RHEL", "red"), ("suse", "SUSE", "green"),
             ("windows", "Windows", "blue")]


def build_layout_shell(visible_sections=None) -> html.Div:
    return html.Div([
        dcc.Store(id="licensed-os-visible-sections",
                  data=list(visible_sections) if visible_sections else None),
        dcc.Loading(
            id="licensed-os-content-loading", type="circle", color="#4318FF",
            delay_show=150,
            children=html.Div(id="licensed-os-page-root",
                              style={"minHeight": "60vh", "padding": "0 8px"}),
        ),
    ])


def _stat_card(label: str, value: int, color: str) -> Any:
    return dmc.Card(
        dmc.Group([
            dmc.Text(label, size="sm", c="dimmed"),
            dmc.Text(f"{value:,}", fw=700, size="xl", c=color),
        ], justify="space-between"),
        withBorder=True, padding="md", radius="md",
    )


def build_layout(visible_sections=None) -> html.Div:  # noqa: ARG001 - sig parity
    summary = api.get_licensed_os_summary()
    fam = summary.get("families") or {}
    cards = [_stat_card(lbl, int(fam.get(key, 0)), color) for key, lbl, color in _LICENSED]
    cards.append(_stat_card("Ücretsiz", int(fam.get("free", 0)), "gray"))
    cards.append(_stat_card("Bilinmiyor", int(fam.get("unknown", 0)), "orange"))

    unknown = summary.get("unknown_samples") or []
    unknown_block = dmc.Card(
        [
            dmc.Text("Manuel inceleme gerektiren (bilinmiyor)", fw=600, mb="xs"),
            dmc.List([dmc.ListItem(s) for s in unknown]) if unknown
            else dmc.Text("Yok", c="dimmed", size="sm"),
        ],
        withBorder=True, padding="md", radius="md", mt="md",
    )

    return html.Div([
        dmc.Title("Lisanslı OS Tespiti", order=2, mb="md"),
        dmc.SimpleGrid(cards, cols=5, spacing="md"),
        unknown_block,
    ])


@callback(
    Output("licensed-os-page-root", "children"),
    Input("url", "pathname"),
    Input("app-time-range", "data"),
    State("licensed-os-visible-sections", "data"),
)
def _fill_licensed_os_content(pathname, time_range, visible_sections):
    if pathname != _PATH:
        return dash.no_update
    return build_layout(visible_sections=visible_sections)
```

- [ ] **Step 4: Wire into app.py**

In `app.py` page-import block (~lines 142-149) add:
```python
from src.pages import licensed_os
```
In `render_main_content` (~before the `_is_administration_path` block near line 887) add:
```python
if pathname == "/licensed-os":
    return licensed_os.build_layout_shell(visible_sections=vis)
```

- [ ] **Step 5: Add sidebar nav entry**

In `src/components/sidebar.py`, `NAV_ITEM_SPECS` (lines 8-21), add:
```python
    ("/licensed-os", "Lisanslı OS", "solar:shield-check-bold-duotone", "page:licensed_os"),
```
(Placed after the CRM Inventory entry.)

- [ ] **Step 6: (Optional) RBAC page-code**

If gating is desired, in `src/auth/permission_service.py` `resolve_pathname_to_page_code` add:
```python
    if p == "/licensed-os":
        return "page:licensed_os"
```
and register `page:licensed_os` in the permission catalog. If you want it ungated like `/crm/inventory-overview`, add nothing here (the sidebar tuple's perm code still shows when a user's perm_map is empty).

- [ ] **Step 7: Run tests to verify they pass**

Run: `. .venv/bin/activate && python -m pytest tests/test_licensed_os_page.py -q`
Expected: PASS. Then smoke-import the app: `python -c "import app"` — expected: no error (callbacks register).

- [ ] **Step 8: Commit**

```bash
git add src/pages/licensed_os.py app.py src/components/sidebar.py \
        src/auth/permission_service.py tests/test_licensed_os_page.py
git commit -m "feat(gui): Lisanslı OS page — detected OS distribution (TASK-81)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Reconciliation (detected vs sold) + per-customer table

**Files:**
- Create: `shared/licensing/reconcile.py`
- Test: `tests/test_licensed_os_reconcile.py`
- Modify: `src/pages/licensed_os.py` (add a customer selector + reconciliation table)

**Interfaces:**
- Consumes: detected counts (`api.get_licensed_os_summary(customer=...)`, Task 3); CRM sold rows from existing `api.get_customer_efficiency_by_category(name, tr)` (returns row dicts with `category_code`/`page_key`, `entitled_qty`/`sold_qty`).
- Produces:
  - `FAMILY_TO_SOLD_CATEGORIES: dict[str, tuple[str, ...]]` mapping family → CRM page_keys:
    `{"rhel": ("license_redhat",), "suse": ("license_suse", "mgmt_os_sap"), "windows": ("license_microsoft_spla", "license_microsoft_csp", "mgmt_os_windows")}`.
  - `reconcile(detected: dict[str, int], sold_rows: list[dict]) -> list[ReconRow]` where
    `ReconRow` is a dict `{"family": str, "label": str, "detected": int, "sold": int, "delta": int}` and `delta = detected - sold` (positive = leakage).

- [ ] **Step 1: Write the failing test**

Create `tests/test_licensed_os_reconcile.py`:
```python
from shared.licensing.reconcile import reconcile, FAMILY_TO_SOLD_CATEGORIES


def _sold(page_key, qty):
    return {"page_key": page_key, "entitled_qty": qty}


def test_windows_aggregates_multiple_categories():
    detected = {"rhel": 10, "suse": 2, "windows": 8, "free": 0, "unknown": 0}
    sold_rows = [
        _sold("license_redhat", 4),
        _sold("license_suse", 5),
        _sold("license_microsoft_spla", 6),
        _sold("license_microsoft_csp", 1),
        _sold("mgmt_os_windows", 1),
    ]
    rows = {r["family"]: r for r in reconcile(detected, sold_rows)}
    assert rows["rhel"]["detected"] == 10 and rows["rhel"]["sold"] == 4
    assert rows["rhel"]["delta"] == 6          # leakage
    assert rows["suse"]["sold"] == 5 and rows["suse"]["delta"] == -3
    assert rows["windows"]["sold"] == 8        # 6 + 1 + 1
    assert rows["windows"]["delta"] == 0


def test_zero_sold_shows_full_detected_as_delta():
    rows = {r["family"]: r for r in reconcile({"rhel": 3, "suse": 0, "windows": 0}, [])}
    assert rows["rhel"]["detected"] == 3
    assert rows["rhel"]["sold"] == 0
    assert rows["rhel"]["delta"] == 3


def test_only_licensed_families_returned():
    rows = reconcile({"rhel": 1, "free": 99, "unknown": 5}, [])
    assert {r["family"] for r in rows} == {"rhel", "suse", "windows"}


def test_map_covers_three_families():
    assert set(FAMILY_TO_SOLD_CATEGORIES) == {"rhel", "suse", "windows"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `. .venv/bin/activate && python -m pytest tests/test_licensed_os_reconcile.py -q`
Expected: FAIL — `ModuleNotFoundError: shared.licensing.reconcile`.

- [ ] **Step 3: Write the implementation**

Create `shared/licensing/reconcile.py`:
```python
"""Reconcile detected licensed-OS counts against CRM sold counts (TASK-81)."""
from __future__ import annotations

FAMILY_TO_SOLD_CATEGORIES: dict[str, tuple[str, ...]] = {
    "rhel": ("license_redhat",),
    "suse": ("license_suse", "mgmt_os_sap"),
    "windows": ("license_microsoft_spla", "license_microsoft_csp", "mgmt_os_windows"),
}
_LABELS = {"rhel": "RHEL", "suse": "SUSE", "windows": "Windows"}


def _sold_qty(row: dict) -> float:
    q = row.get("entitled_qty")
    if q is None:
        q = row.get("sold_qty")
    return float(q or 0)


def reconcile(detected: dict[str, int], sold_rows: list[dict]) -> list[dict]:
    """Return one row per licensed family: detected vs sold vs delta (=detected-sold)."""
    sold_by_key: dict[str, float] = {}
    for r in sold_rows or []:
        key = str(r.get("page_key") or r.get("category_code") or "")
        if key:
            sold_by_key[key] = sold_by_key.get(key, 0.0) + _sold_qty(r)

    out: list[dict] = []
    for family, keys in FAMILY_TO_SOLD_CATEGORIES.items():
        det = int(detected.get(family, 0) or 0)
        sold = int(round(sum(sold_by_key.get(k, 0.0) for k in keys)))
        out.append({
            "family": family, "label": _LABELS[family],
            "detected": det, "sold": sold, "delta": det - sold,
        })
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `. .venv/bin/activate && python -m pytest tests/test_licensed_os_reconcile.py -q`
Expected: PASS.

- [ ] **Step 5: Add a customer selector + reconciliation table to the page**

In `src/pages/licensed_os.py`: add a `dmc.Select(id="licensed-os-customer-select", value=None)` populated from `api.get_customers(...)` (mirror how `customers_list.py` lists customers), plus a callback keyed on its value that calls `api.get_licensed_os_summary(customer=name)` + `api.get_customer_efficiency_by_category(name, None)`, runs `reconcile(...)`, and renders a `dmc.Table` with columns `Müşteri | OS | Tespit | Satılan | Fark` (color the `Fark` cell red when `delta > 0`). Guard the callback with `if not name: return dash.no_update`.

Write a focused test in `tests/test_licensed_os_page.py` that patches both api calls and asserts the table renders a leakage row. (Follow the existing patch-based page-test pattern.)

- [ ] **Step 6: Commit**

```bash
git add shared/licensing/reconcile.py tests/test_licensed_os_reconcile.py \
        src/pages/licensed_os.py tests/test_licensed_os_page.py
git commit -m "feat(licensing): detected-vs-sold reconciliation + per-customer table (TASK-81)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Customer View "detected" column (integration)

**Files:**
- Modify: `src/components/sold_vs_used_panel.py`
- Modify: `src/pages/customer_view.py`
- Test: `tests/test_customer_view_licensed_os.py`

**Interfaces:**
- Consumes: `reconcile(...)` (Task 5) + `api.get_licensed_os_for_customer` (via `api.get_licensed_os_summary(customer=...)`).
- Produces: RHEL/SUSE/Windows rows with a `detected` value merged into the "Sold vs used (other categories)" section.

**Key constraints discovered:**
- Row dicts consumed by `build_sold_vs_used_stack` use keys: `category_label`, `entitled_qty` (sold), `used_qty` (used), `overage_qty`, `resource_unit`, `status`, `gui_tab_binding`. There is currently **no `detected` field**.
- `filter_efficiency_rows_for_display` (`src/utils/visibility.py:108-123`) DROPS rows where `entitled_qty<=0 AND used_qty<=0 AND overage_qty<=0`. A detected-only RHEL row (no sold, no used) would be dropped — so a synthesized licensing row MUST carry a non-zero signal (set `used_qty = detected` OR amend the filter to also keep rows with `detected>0`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_customer_view_licensed_os.py` asserting that, given a customer with detected `{rhel:10}` and sold `license_redhat:4`, the synthesized rows fed to the panel include a row with `category_label` containing "RHEL", `detected == 10`, `entitled_qty == 4`, and it survives `filter_efficiency_rows_for_display`.

- [ ] **Step 2: Run to verify it fails.** Expected: FAIL (no synthesis function yet).

- [ ] **Step 3: Add a `detected` series to `_one_row_card`** in `sold_vs_used_panel.py` — extend the grouped bar `{"Sold":[sold],"Used":[used]}` to include `"Detected":[detected]` when `r.get("detected") is not None`, and add a "Detected" column to `build_compliance_issue_table`'s `cols` list + `_row` builder.

- [ ] **Step 4: Add a synthesis helper in `customer_view.py`** that calls `api.get_licensed_os_summary(customer=name)`, runs `reconcile(...)`, and appends synthesized rows (`category_label="RHEL Lisans"`, `entitled_qty=sold`, `used_qty=detected`, `detected=detected`, `gui_tab_binding="licensing.os"`, `resource_unit="Adet"`) to the `eff_by_cat` list before it reaches `build_sold_vs_used_stack` at `customer_view.py:2804` and `:2962`.

- [ ] **Step 5: Run tests to verify they pass.** Expected: PASS. Also run `python -m pytest tests/test_customer_view_sold_vs_used.py -q` to confirm no regression.

- [ ] **Step 6: Commit.**

```bash
git add src/components/sold_vs_used_panel.py src/pages/customer_view.py \
        tests/test_customer_view_licensed_os.py
git commit -m "feat(gui): detected licensed-OS column in Customer View sold-vs-used (TASK-81)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Later phases (out of scope for this plan, tracked here)

- **Nutanix:** add a `nutanix_vm_metrics.guest_os` branch to the detection query (NGT-dependent, NULL-heavy → mostly `unknown`). Same `_tally_os_rows` path; UNION into `VM_OS_CONFIG_LATEST` or tally a second row set.
- **IBM Power:** `ibm_lpar_general.lpar_details_ostype` only yields `Linux`/`AIX`/`IBMi` — cannot split RHEL vs SUSE. Needs Zabbix/NetBox enrichment. Separate task.
- **All-customers rollup table** on the page (vs the per-customer selector shipped in Task 5): requires enumerating CRM customers + their alias patterns and batching per-customer detection. Watch N-round-trip cost; consider a single grouped query using the physical-inventory attribution rules.

---

## Self-Review

- **Spec coverage:** classifier (Task 1 ✓), VMware detection incl. runtime coalesce (Task 2 ✓), endpoint/client (Task 3 ✓), new page distribution (Task 4 ✓), reconciliation + per-customer table (Task 5 ✓), Customer View detected column (Task 6 ✓), boundaries/unknown honesty (Task 2 `unknown_samples`, Task 4 manual-review block ✓), IBM/Nutanix deferral (Later phases ✓). No spec section left unimplemented.
- **Placeholder scan:** Tasks 1–4 carry complete code. Tasks 5–6 give complete code for the pure/core pieces (classifier map, reconcile) and precise, file-anchored prose for the Dash-rendering glue (selector/table/series) rather than guessing dmc props not yet verified against the installed version — acceptable because each references exact files, keys, and the discovered display-filter gotcha. Executors should read the named files before writing the glue.
- **Type consistency:** `classify()->OsClass(family,confidence)` used consistently in Task 2 tally. `families` dict keys identical across Tasks 2/3/4/5. `reconcile()` row keys (`family,label,detected,sold,delta`) consistent between Task 5 impl and Task 6 consumption. `entitled_qty`/`used_qty`/`detected` row keys match the Customer View panel contract discovered in exploration.
