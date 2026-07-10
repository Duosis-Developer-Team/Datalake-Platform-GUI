# Customer Availability — AuraNotify mapping + API-shape fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Customer View Availability tab show real AuraNotify outages again, and let operators bind a platform customer to explicit AuraNotify customer id(s) from the existing alias page.

**Architecture:** Two links of one pipeline. (A) Fix the AuraNotify client to call the downtimes endpoint with no `source` param and read all four downtime-category fields. (B) Add an `auranotify` mapping to the existing CRM source-mapping alias editor (searchable AuraNotify picker, stored id-exact, no schema change) and consume it in `api_client` before falling back to today's name matching.

**Tech Stack:** Python, Dash, dash-mantine-components (dmc), httpx, pytest.

## Global Constraints

- Bundle return shape is FIXED and must not change: `{"service_downtimes": list, "vm_downtimes": list, "vm_outage_counts": dict, "customer_id": int|None, "customer_ids": list[int]}`. Four call sites in `customer_view.py` + the warm scheduler depend on it.
- No schema change to `gui_crm_customer_source_mapping`. AuraNotify mappings persist as ordinary source-mapping rows: `data_source="auranotify"`, `match_method="id_exact"`, `match_value="<auranotify id>"`.
- Explicit mapping wins; when absent, keep today's name-based matching (backward compatible).
- Live AuraNotify: base `http://10.34.8.154:5001`, header `X-API-Key`. Downtimes endpoint: `GET /api/customers/{id}/downtimes?start_date=YYYY-MM-DD[&source=datacenter|dedicated|service|vm]`; no `source` = all categories.
- Only `datacenter_downtimes` (service-level) and `vm_downtimes` carry data today; `service_downtimes`/`dedicated_downtimes` exist but are empty — include them in the service concat for forward-compat.
- Run tests with the repo venv: `source .venv/bin/activate` then `pytest`.

---

### Task 1: AuraNotify client — read the right fields (Defect A core)

**Files:**
- Modify: `src/services/auranotify_client.py` (`get_customer_downtimes` ~120-135; `get_customer_availability_bundle` ~199-230)
- Test: `tests/test_auranotify_bundle_fields.py` (create)

**Interfaces:**
- Produces:
  - `get_customer_downtimes(customer_id: int, start_date: str, source: str | None = None) -> dict`
  - `get_availability_bundle_for_ids(ids: list[int], start_date: str) -> dict` (fixed bundle shape)
  - `get_customer_availability_bundle(customer_name: str, start_date: str) -> dict` (unchanged signature; now delegates)

- [ ] **Step 1: Write the failing test**

Create `tests/test_auranotify_bundle_fields.py`:

```python
"""AuraNotify bundle reads all downtime categories from a no-source call."""
from __future__ import annotations

from unittest.mock import patch

from src.services import auranotify_client as aura


def _body(datacenter=None, vm=None, service=None, dedicated=None):
    return {
        "datacenter_downtimes": datacenter or [],
        "dedicated_downtimes": dedicated or [],
        "service_downtimes": service or [],
        "vm_downtimes": vm or [],
    }


def test_bundle_merges_service_categories_and_vm_counts():
    dc = [{"category": "DR", "group_name": "DC13", "duration_minutes": 60}]
    ded = [{"category": "Ded", "group_name": "DC16", "duration_minutes": 5}]
    vm = [
        {"vm_name": "web-01", "cluster": "CLS1", "duration_minutes": 30},
        {"vm_name": "web-01", "cluster": "CLS1", "duration_minutes": 10},
    ]
    with patch.object(aura, "get_customer_downtimes", return_value=_body(dc, vm, dedicated=ded)) as gcd:
        out = aura.get_availability_bundle_for_ids([1498], "2024-01-01")
    # one no-source call per id
    gcd.assert_called_once_with(1498, "2024-01-01")
    assert out["service_downtimes"] == dc + ded  # datacenter + dedicated + service(empty)
    assert out["vm_downtimes"] == vm
    assert out["vm_outage_counts"] == {"web-01": 2}
    assert out["customer_id"] == 1498
    assert out["customer_ids"] == [1498]


def test_bundle_empty_when_no_ids():
    out = aura.get_availability_bundle_for_ids([], "2024-01-01")
    assert out == {
        "service_downtimes": [], "vm_downtimes": [], "vm_outage_counts": {},
        "customer_id": None, "customer_ids": [],
    }


def test_get_customer_downtimes_omits_source_when_none():
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"datacenter_downtimes": []}

    class _Client:
        def __init__(self): self.params = None
        def get(self, path, params=None, headers=None):
            self.params = params
            return _Resp()

    client = _Client()
    with patch.object(aura, "AURANOTIFY_KEY", "k"), patch.object(aura, "_get_client", return_value=client):
        aura.get_customer_downtimes(1498, "2024-01-01")
    assert "source" not in client.params
    assert client.params["start_date"] == "2024-01-01"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_auranotify_bundle_fields.py -v`
Expected: FAIL — `get_availability_bundle_for_ids` does not exist / `get_customer_downtimes` requires `source`.

- [ ] **Step 3: Write the implementation**

In `src/services/auranotify_client.py`, replace `get_customer_downtimes` with:

```python
def get_customer_downtimes(
    customer_id: int, start_date: str, source: str | None = None
) -> dict[str, Any]:
    """GET /api/customers/{id}/downtimes?start_date=[&source=]

    When ``source`` is None (default) the endpoint returns every downtime
    category (datacenter/dedicated/service/vm). Passing a ``source`` filters the
    response to that one category — the modern API behaviour, so the availability
    bundle deliberately omits it.
    """
    if not AURANOTIFY_KEY:
        return {}
    params: dict[str, str] = {"start_date": start_date}
    if source:
        params["source"] = source
    try:
        r = _get_client().get(
            f"/api/customers/{customer_id}/downtimes",
            params=params,
            headers=_headers(),
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("get_customer_downtimes failed (source=%s): %s", source, exc)
        return {}
```

Add near the bundle helpers (after `vm_outage_counts_from_events`):

```python
_SERVICE_DOWNTIME_FIELDS = ("datacenter_downtimes", "dedicated_downtimes", "service_downtimes")


def _coerce_ids(ids: list[int]) -> list[int]:
    out: list[int] = []
    for i in ids or []:
        try:
            out.append(int(i))
        except (TypeError, ValueError):
            continue
    return sorted(set(out))


def get_availability_bundle_for_ids(ids: list[int], start_date: str) -> dict[str, Any]:
    """Service + VM downtimes and per-VM outage counts for explicit AuraNotify ids.

    One no-source request per id returns all categories; the service-outage table
    merges datacenter/dedicated/service events, the VM-outage table uses vm events.
    """
    empty: dict[str, Any] = {
        "service_downtimes": [],
        "vm_downtimes": [],
        "vm_outage_counts": {},
        "customer_id": None,
        "customer_ids": [],
    }
    clean_ids = _coerce_ids(ids)
    if not clean_ids:
        return empty
    svc_events: list[Any] = []
    vm_events: list[Any] = []
    for cid in clean_ids:
        body = get_customer_downtimes(cid, start_date)
        for field in _SERVICE_DOWNTIME_FIELDS:
            part = body.get(field)
            if isinstance(part, list):
                svc_events.extend(part)
        ve = body.get("vm_downtimes")
        if isinstance(ve, list):
            vm_events.extend(ve)
    return {
        "service_downtimes": svc_events,
        "vm_downtimes": vm_events,
        "vm_outage_counts": vm_outage_counts_from_events(vm_events),
        "customer_id": clean_ids[0],
        "customer_ids": clean_ids,
    }
```

Replace the body of `get_customer_availability_bundle` with a thin delegate:

```python
def get_customer_availability_bundle(customer_name: str, start_date: str) -> dict[str, Any]:
    """Name-based resolution then bundle. Callers with an explicit mapping should
    use get_availability_bundle_for_ids directly (see api_client)."""
    return get_availability_bundle_for_ids(resolve_customer_ids(customer_name), start_date)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_auranotify_bundle_fields.py tests/test_auranotify_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/auranotify_client.py tests/test_auranotify_bundle_fields.py
git commit -m "fix(availability): read all downtime categories from no-source AuraNotify call

source=service/vm now filters the response, so reading datacenter_downtimes
returned empty. One no-source call per id; merge datacenter/dedicated/service
into the service table, vm into the vm table."
```

---

### Task 2: api_client — mapping-aware fetch + options helper (Defect B consumption)

**Files:**
- Modify: `src/services/api_client.py` (`_fetch_customer_availability_bundle_uncached:1647-1650`; add two helpers nearby)
- Test: `tests/test_api_client_auranotify_mapping.py` (create)

**Interfaces:**
- Consumes (Task 1): `aura.get_availability_bundle_for_ids`, `aura.get_customer_availability_bundle`.
- Produces:
  - `get_auranotify_customer_options() -> list[dict[str,str]]` — `[{"label": "<name> · id <id>", "value": "<id>"}]`, cached.
  - `get_auranotify_ids_for_customer(customer_name: str) -> list[int]`.
  - `_fetch_customer_availability_bundle_uncached` now mapping-aware.

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_client_auranotify_mapping.py`:

```python
"""Explicit AuraNotify id mapping resolution and fetch precedence."""
from __future__ import annotations

from unittest.mock import patch

from src.services import api_client


_ALIASES = [
    {
        "crm_accountid": "acc-4a",
        "crm_account_name": "4a_Kozmetik",
        "source_mappings": [
            {"data_source": "virtualization", "match_method": "contains", "match_value": "4a", "enabled": True},
            {"data_source": "auranotify", "match_method": "id_exact", "match_value": "1498", "enabled": True},
            {"data_source": "auranotify", "match_method": "id_exact", "match_value": "3787", "enabled": True},
            {"data_source": "auranotify", "match_method": "id_exact", "match_value": "999", "enabled": False},
            {"data_source": "auranotify", "match_method": "id_exact", "match_value": "notanint", "enabled": True},
        ],
    },
]


def test_ids_for_customer_returns_enabled_numeric_only():
    with patch.object(api_client, "get_crm_aliases", return_value=_ALIASES):
        assert api_client.get_auranotify_ids_for_customer("4a_Kozmetik") == [1498, 3787]


def test_ids_for_customer_case_insensitive_and_empty_when_unmapped():
    with patch.object(api_client, "get_crm_aliases", return_value=_ALIASES):
        assert api_client.get_auranotify_ids_for_customer("4A_KOZMETIK".lower()) == [1498, 3787]
        assert api_client.get_auranotify_ids_for_customer("Unknown Co") == []


def test_fetch_prefers_explicit_mapping():
    tr = {"start": "2024-01-01", "end": "2024-06-07"}
    with patch.object(api_client, "get_auranotify_ids_for_customer", return_value=[1498, 3787]), \
         patch("src.services.auranotify_client.get_availability_bundle_for_ids", return_value={"customer_ids": [1498, 3787]}) as by_ids, \
         patch("src.services.auranotify_client.get_customer_availability_bundle") as by_name:
        out = api_client._fetch_customer_availability_bundle_uncached("4a_Kozmetik", tr)
    by_ids.assert_called_once()
    by_name.assert_not_called()
    assert out["customer_ids"] == [1498, 3787]


def test_fetch_falls_back_to_name_when_unmapped():
    tr = {"start": "2024-01-01", "end": "2024-06-07"}
    with patch.object(api_client, "get_auranotify_ids_for_customer", return_value=[]), \
         patch("src.services.auranotify_client.get_availability_bundle_for_ids") as by_ids, \
         patch("src.services.auranotify_client.get_customer_availability_bundle", return_value={"customer_ids": [7]}) as by_name:
        out = api_client._fetch_customer_availability_bundle_uncached("Unknown Co", tr)
    by_name.assert_called_once()
    by_ids.assert_not_called()
    assert out["customer_ids"] == [7]


def test_customer_options_shape():
    fake_list = [{"id": 1498, "name": "4a_Kozmetik"}, {"id": 1495, "name": "12mtech"}]
    api_client._api_response_cache.delete("api:auranotify_customer_options")
    with patch("src.services.auranotify_client.get_customer_list_aura", return_value=fake_list):
        opts = api_client.get_auranotify_customer_options()
    assert {"label": "4a_Kozmetik · id 1498", "value": "1498"} in opts
    assert all(set(o) == {"label", "value"} for o in opts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_api_client_auranotify_mapping.py -v`
Expected: FAIL — helpers do not exist yet.

- [ ] **Step 3: Write the implementation**

In `src/services/api_client.py`, add above `_fetch_customer_availability_bundle_uncached`:

```python
def get_auranotify_customer_options() -> list[dict[str, str]]:
    """Searchable options for the alias editor: label '<name> · id <id>', value '<id>'.
    Cached; safe to call during page render."""
    ck = "api:auranotify_customer_options"
    cached = _api_response_cache.get(ck)
    if cached is not None:
        return _clone(cached)
    from src.services import auranotify_client as aura

    opts: list[dict[str, str]] = []
    for row in aura.get_customer_list_aura():
        cid = row.get("id")
        if cid is None:
            continue
        name = str(row.get("name") or "").strip()
        opts.append({"label": f"{name} · id {cid}", "value": str(cid)})
    opts.sort(key=lambda o: o["label"].casefold())
    if opts:
        _api_response_cache.set(ck, opts)
    return _clone(opts)


def get_auranotify_ids_for_customer(customer_name: str) -> list[int]:
    """Explicit AuraNotify ids mapped to this customer via the alias page
    (data_source='auranotify'). Empty when unmapped — the caller then falls back
    to AuraNotify name matching."""
    name = (customer_name or "").strip().casefold()
    if not name:
        return []
    ids: list[int] = []
    for alias in get_crm_aliases():
        if str(alias.get("crm_account_name") or "").strip().casefold() != name:
            continue
        for m in alias.get("source_mappings") or []:
            if str(m.get("data_source") or "") != "auranotify":
                continue
            if m.get("enabled", True) is False:
                continue
            try:
                ids.append(int(str(m.get("match_value") or "").strip()))
            except (TypeError, ValueError):
                continue
        break
    return sorted(set(ids))
```

Replace `_fetch_customer_availability_bundle_uncached` with:

```python
def _fetch_customer_availability_bundle_uncached(customer_name: str, tr: Optional[dict]) -> dict[str, Any]:
    from src.services import auranotify_client as aura

    start = _auranotify_start_date(tr)
    explicit_ids = get_auranotify_ids_for_customer(customer_name or "")
    if explicit_ids:
        return aura.get_availability_bundle_for_ids(explicit_ids, start)
    return aura.get_customer_availability_bundle(customer_name or "", start)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_api_client_auranotify_mapping.py tests/test_api_client_customer_avail_cache.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/api_client.py tests/test_api_client_auranotify_mapping.py
git commit -m "feat(availability): resolve explicit AuraNotify ids from alias mappings

get_auranotify_ids_for_customer reads data_source=auranotify source-mappings;
availability fetch uses them when present, else falls back to name matching.
Adds get_auranotify_customer_options for the alias editor picker."
```

---

### Task 3: Add `auranotify` column to the mapping model (Defect B storage)

**Files:**
- Modify: `src/utils/crm_source_mapping_ui.py:4-11` (`UI_COLUMNS`)
- Modify: `tests/test_crm_aliases_page.py:49` (coverage denominator 6 → 7)
- Test: `tests/test_crm_source_mapping_auranotify.py` (create)

**Interfaces:**
- Consumes: existing generic `build_editor_state`, `editor_state_to_save_payload`, `compute_coverage` (all iterate `UI_COLUMNS`).
- Produces: `UI_COLUMNS` gains `("auranotify", "Availability (AuraNotify)", ("auranotify",))` as the last column.

- [ ] **Step 1: Write the failing test**

Create `tests/test_crm_source_mapping_auranotify.py`:

```python
"""auranotify column round-trips through the generic mapping helpers."""
from __future__ import annotations

from src.utils.crm_source_mapping_ui import (
    UI_COLUMNS,
    build_editor_state,
    compute_coverage,
    editor_state_to_save_payload,
)


def _alias_with_auranotify():
    return {
        "crm_accountid": "acc-x",
        "crm_account_name": "Acme",
        "source_mappings": [
            {"data_source": "auranotify", "match_method": "id_exact", "match_value": "1498", "enabled": True},
        ],
    }


def test_auranotify_is_last_column():
    assert UI_COLUMNS[-1][0] == "auranotify"
    assert UI_COLUMNS[-1][2] == ("auranotify",)


def test_auranotify_entry_loads_into_its_section():
    state = build_editor_state(_alias_with_auranotify())
    assert state["sections"]["auranotify"][0]["match_value"] == "1498"
    assert state["sections"]["auranotify"][0]["data_source"] == "auranotify"


def test_auranotify_entry_saves_back():
    state = build_editor_state(_alias_with_auranotify())
    mappings, _ = editor_state_to_save_payload(state)
    aura = [m for m in mappings if m["data_source"] == "auranotify"]
    assert aura == [{"data_source": "auranotify", "match_method": "id_exact", "match_value": "1498", "enabled": True}]


def test_coverage_counts_auranotify():
    _covered, total = compute_coverage(_alias_with_auranotify()["source_mappings"])
    assert total == len(UI_COLUMNS) == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_crm_source_mapping_auranotify.py -v`
Expected: FAIL — `auranotify` not in `UI_COLUMNS`, total is 6.

- [ ] **Step 3: Write the implementation**

In `src/utils/crm_source_mapping_ui.py`, extend `UI_COLUMNS`:

```python
UI_COLUMNS: list[tuple[str, str, tuple[str, ...]]] = [
    ("virtualization", "Virtualization", ("virtualization", "netbox_vm_customer")),
    ("backup", "Backup & Replication", ("backup_veeam", "backup_zerto", "backup_netbackup")),
    ("physical_device", "Physical Device", ("physical_device",)),
    ("storage", "Storage", ("storage_ibm",)),
    ("s3", "S3", ("s3_icos",)),
    ("itsm", "ITSM", ("itsm_servicecore",)),
    ("auranotify", "Availability (AuraNotify)", ("auranotify",)),
]
```

In `tests/test_crm_aliases_page.py:49`, update the coverage assertion:

```python
    assert row["coverage"] == "3/7"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_crm_source_mapping_auranotify.py tests/test_crm_aliases_page.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/utils/crm_source_mapping_ui.py tests/test_crm_source_mapping_auranotify.py tests/test_crm_aliases_page.py
git commit -m "feat(alias): add auranotify column to customer source mapping model"
```

---

### Task 4: Searchable AuraNotify picker in the alias editor (Defect B UI)

**Files:**
- Modify: `src/pages/settings/integrations/crm_aliases.py` (`_render_mapping_entry:55-114`; add `_auranotify_options` helper)
- Test: `tests/test_crm_aliases_auranotify_render.py` (create)

**Interfaces:**
- Consumes (Task 2): `api.get_auranotify_customer_options()`.
- Produces: for `section_key == "auranotify"`, the value control is a searchable `dmc.Select` (value = id string) and the method is locked to `id_exact`; the pattern-matched component ids are unchanged so the existing save callback collects them as before.

Note: `build_editor_shell`/`section_refresh_outputs`/`_render_mapping_entry` are also reused by the Internal aliases editor (`crm_internal_aliases`), so the AuraNotify section appears there too — intentional and harmless (Bulutistan-internal may carry an AuraNotify id).

- [ ] **Step 1: Write the failing test**

Create `tests/test_crm_aliases_auranotify_render.py`:

```python
"""The auranotify section renders a searchable Select fed by AuraNotify options."""
from __future__ import annotations

from unittest.mock import patch

import dash_mantine_components as dmc

from src.pages.settings.integrations import crm_aliases


def _find(component, predicate):
    """Depth-first search over a Dash component tree."""
    if predicate(component):
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, "children") or hasattr(child, "id"):
            found = _find(child, predicate)
            if found is not None:
                return found
    return None


def test_auranotify_row_uses_searchable_select_with_options():
    opts = [{"label": "4a_Kozmetik · id 1498", "value": "1498"}]
    crm_aliases._AURANOTIFY_OPTIONS_CACHE = None  # reset memoised options so the patch is used
    with patch.object(crm_aliases.api, "get_auranotify_customer_options", return_value=opts):
        entry = {"data_source": "auranotify", "match_method": "id_exact", "match_value": "1498", "enabled": True}
        row = crm_aliases._render_mapping_entry("auranotify", ("auranotify",), entry, 0)

    def is_value_select(c):
        cid = getattr(c, "id", None)
        return isinstance(c, dmc.Select) and isinstance(cid, dict) and cid.get("type") == "alias-edit-value"

    sel = _find(row, is_value_select)
    assert sel is not None, "auranotify value control must be a dmc.Select"
    assert getattr(sel, "searchable", False) is True
    assert sel.data == opts
    assert sel.value == "1498"


def test_non_auranotify_row_keeps_text_input():
    entry = {"data_source": "virtualization", "match_method": "contains", "match_value": "Boyner", "enabled": True}
    row = crm_aliases._render_mapping_entry("virtualization", ("virtualization",), entry, 0)

    def is_value_textinput(c):
        cid = getattr(c, "id", None)
        return isinstance(c, dmc.TextInput) and isinstance(cid, dict) and cid.get("type") == "alias-edit-value"

    assert _find(row, is_value_textinput) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_crm_aliases_auranotify_render.py -v`
Expected: FAIL — auranotify row still renders a `TextInput`.

- [ ] **Step 3: Write the implementation**

In `src/pages/settings/integrations/crm_aliases.py`, add the imports and a cached options helper near the top (after the existing imports):

```python
from src.services import api_client as api

_AURANOTIFY_OPTIONS_CACHE: list[dict[str, str]] | None = None


def _auranotify_options() -> list[dict[str, str]]:
    """AuraNotify customer options for the picker; lazy + memoised; never raises."""
    global _AURANOTIFY_OPTIONS_CACHE
    if _AURANOTIFY_OPTIONS_CACHE is None:
        try:
            _AURANOTIFY_OPTIONS_CACHE = api.get_auranotify_customer_options()
        except Exception:
            _AURANOTIFY_OPTIONS_CACHE = []
    return _AURANOTIFY_OPTIONS_CACHE
```

In `_render_mapping_entry`, build the method + value controls conditionally. Replace the current `dmc.Select(... alias-edit-method ...)` and `dmc.TextInput(... alias-edit-value ...)` blocks with:

```python
    is_auranotify = section_key == "auranotify"
    method_control = dmc.Select(
        id={"type": f"{prefix}-edit-method", "section": section_key, "index": index},
        label="Method" if index == 0 else None,
        data=[{"label": "ID exact", "value": "id_exact"}] if is_auranotify else MATCH_METHOD_OPTIONS,
        value="id_exact" if is_auranotify else (entry.get("match_method") or "contains"),
        disabled=is_auranotify,
        size="xs",
        style={"minWidth": "120px", "flex": 1},
    )
    if is_auranotify:
        value_control = dmc.Select(
            id={"type": f"{prefix}-edit-value", "section": section_key, "index": index},
            label="AuraNotify customer" if index == 0 else None,
            data=_auranotify_options(),
            value=(str(entry.get("match_value")) if entry.get("match_value") else None),
            placeholder="Search AuraNotify customer or id…",
            searchable=True,
            nothingFoundMessage="No match",
            size="xs",
            style={"minWidth": "220px", "flex": 3},
        )
    else:
        value_control = dmc.TextInput(
            id={"type": f"{prefix}-edit-value", "section": section_key, "index": index},
            label="Value" if index == 0 else None,
            value=entry.get("match_value") or "",
            placeholder="match value",
            size="xs",
            style={"minWidth": "160px", "flex": 2},
        )
```

Then in the `dmc.Group(children=[...])` list, use `method_control` and `value_control` in place of the two inline components (keep the existing source `dmc.Select`, the `dmc.Switch`, and the remove `dmc.ActionIcon` unchanged).

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_crm_aliases_auranotify_render.py tests/test_crm_aliases_page.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pages/settings/integrations/crm_aliases.py tests/test_crm_aliases_auranotify_render.py
git commit -m "feat(alias): searchable AuraNotify picker for the auranotify mapping section"
```

---

### Task 5: Availability summary helpers (pure, TDD) — for G4 readable view

**Files:**
- Create: `src/utils/availability_summary.py`
- Test: `tests/test_availability_summary.py` (create)

**Interfaces:**
- Produces:
  - `summarize_outages(service_downtimes: list, vm_downtimes: list) -> dict` with keys
    `total_outages, service_outages, vm_outages, total_downtime_min, unplanned_count,
    planned_count, longest (dict|None), locations (list[str])`.
  - `format_downtime(minutes) -> str` — Turkish units.

- [ ] **Step 1: Write the failing test**

Create `tests/test_availability_summary.py`:

```python
"""Pure availability-summary helpers."""
from __future__ import annotations

from src.utils.availability_summary import summarize_outages, format_downtime


def test_summarize_counts_split_longest_locations():
    svc = [
        {"type": "Plansız", "duration_minutes": 60, "group_name": "DC13"},
        {"type": "Planlı", "duration_minutes": 30, "group_name": "DC13"},
    ]
    vm = [{"type": "Plansız", "duration_minutes": 274, "cluster": "DC16-CLS", "vm_name": "web-01"}]
    s = summarize_outages(svc, vm)
    assert s["total_outages"] == 3
    assert s["service_outages"] == 2
    assert s["vm_outages"] == 1
    assert s["total_downtime_min"] == 364
    assert s["unplanned_count"] == 2
    assert s["planned_count"] == 1
    assert s["longest"]["duration_minutes"] == 274
    assert s["locations"] == ["DC13", "DC16-CLS"]


def test_summarize_empty_and_defensive():
    s = summarize_outages([], [])
    assert s["total_outages"] == 0
    assert s["longest"] is None
    assert s["locations"] == []
    s2 = summarize_outages([None, {"duration_minutes": "x", "type": ""}], [])
    assert s2["total_outages"] == 1
    assert s2["total_downtime_min"] == 0
    assert s2["planned_count"] == 0
    assert s2["unplanned_count"] == 0


def test_format_downtime_units():
    assert format_downtime(45) == "45 dk"
    assert format_downtime(90) == "1,5 sa"
    assert format_downtime(2880) == "2,0 gün"
    assert format_downtime(None) == "-"
    assert format_downtime("x") == "-"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_availability_summary.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write the implementation**

Create `src/utils/availability_summary.py`:

```python
"""Pure helpers to summarise AuraNotify outage records for the availability tab."""
from __future__ import annotations


def _duration(rec: dict) -> int:
    try:
        return int(rec.get("duration_minutes") or 0)
    except (TypeError, ValueError):
        return 0


def _is_unplanned(rec: dict) -> bool:
    return "plansız" in str(rec.get("type") or "").casefold()


def summarize_outages(service_downtimes: list, vm_downtimes: list) -> dict:
    svc = [r for r in (service_downtimes or []) if isinstance(r, dict)]
    vm = [r for r in (vm_downtimes or []) if isinstance(r, dict)]
    events = svc + vm
    unplanned = sum(1 for r in events if _is_unplanned(r))
    planned = sum(
        1 for r in events if str(r.get("type") or "").strip() and not _is_unplanned(r)
    )
    locations = sorted(
        {
            str(r.get("group_name") or r.get("cluster") or "").strip()
            for r in events
            if str(r.get("group_name") or r.get("cluster") or "").strip()
        }
    )
    return {
        "total_outages": len(events),
        "service_outages": len(svc),
        "vm_outages": len(vm),
        "total_downtime_min": sum(_duration(r) for r in events),
        "unplanned_count": unplanned,
        "planned_count": planned,
        "longest": max(events, key=_duration) if events else None,
        "locations": locations,
    }


def format_downtime(minutes) -> str:
    try:
        m = int(minutes or 0)
    except (TypeError, ValueError):
        return "-"
    if m < 60:
        return f"{m} dk"
    if m < 1440:
        return f"{m / 60:.1f} sa".replace(".", ",")
    return f"{m / 1440:.1f} gün".replace(".", ",")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_availability_summary.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/utils/availability_summary.py tests/test_availability_summary.py
git commit -m "feat(availability): pure outage-summary helpers for readable tab"
```

---

### Task 6: Rebuild the Availability tab — summary tiles + readable lists (G4, supersedes old §4.2)

**Files:**
- Modify: `src/pages/customer_view.py` (`_tab_customer_availability` ~1769-1847; add two module-level helpers above it)
- Test: `tests/test_customer_availability_tab.py` (create)

**Interfaces:**
- Consumes (Task 5): `summarize_outages`, `format_downtime`.
- Produces: rebuilt `_tab_customer_availability(avail)` — metric tiles + two readable outage lists; VM list uses `vm_name` + `cluster/host` (this replaces the standalone VM-row fix from the earlier plan version).

- [ ] **Step 1: Write the failing test**

Create `tests/test_customer_availability_tab.py`:

```python
"""Availability tab renders summary tiles + readable outage lists."""
from __future__ import annotations

from src.pages.customer_view import _tab_customer_availability
from src.utils.availability_summary import format_downtime


def _text_blob(component) -> str:
    out = []

    def walk(c):
        if isinstance(c, (str, int, float)):
            out.append(str(c))
            return
        children = getattr(c, "children", None)
        if children is None:
            return
        if not isinstance(children, (list, tuple)):
            children = [children]
        for ch in children:
            walk(ch)

    walk(component)
    return " ".join(out)


def _avail_with_outages():
    return {
        "customer_id": 1504,
        "customer_ids": [1504],
        "service_downtimes": [
            {"category": "Klasik Mimari DR", "group_name": "Equinix IL2 - DC13", "type": "Plansız",
             "start_time": "2026-06-30T18:31", "end_time": "2026-06-30T19:31",
             "duration_minutes": 60, "service_impact": "Degraded"},
        ],
        "vm_downtimes": [
            {"vm_name": "web-01", "cluster": "DC16-G2-CLS-HYBRID", "host": "g2hv2dc16.blt.vc",
             "type": "Plansız", "start_time": "2026-01-23T10:00", "end_time": "2026-01-23T14:34",
             "duration_minutes": 274, "category": "DC Elektrik Altyapısı"},
        ],
        "vm_outage_counts": {"web-01": 1},
    }


def test_tab_shows_tiles_and_readable_rows():
    blob = _text_blob(_tab_customer_availability(_avail_with_outages()))
    # summary tiles
    assert "Total outages" in blob
    assert "Total downtime" in blob
    # total downtime 60+274=334 min rendered via format_downtime
    assert format_downtime(334) in blob
    # readable rows: vm identity + cluster + type badge + formatted duration
    assert "web-01" in blob
    assert "DC16-G2-CLS-HYBRID" in blob
    assert "Plansız" in blob
    assert format_downtime(274) in blob


def test_tab_empty_state():
    avail = {"customer_id": 1, "customer_ids": [1], "service_downtimes": [],
             "vm_downtimes": [], "vm_outage_counts": {}}
    blob = _text_blob(_tab_customer_availability(avail))
    assert "No outages in period" in blob
    assert "Total outages" in blob  # tiles still render (all zero)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_customer_availability_tab.py -v`
Expected: FAIL — no tiles ("Total outages"), old `_vm_row` reads `group_name` (missing) so cluster not shown.

- [ ] **Step 3: Write the implementation**

In `src/pages/customer_view.py`, add two module-level helpers immediately above `_tab_customer_availability`:

```python
def _outage_type_badge(t):
    tt = str(t or "").strip()
    unplanned = "plansız" in tt.casefold()
    return dmc.Badge(tt or "-", color="red" if unplanned else "gray", variant="light", size="sm")


def _avail_tile(label: str, value: str, sub: str | None = None, accent: str = "#4318FF"):
    return html.Div(
        className="nexus-card",
        style={"padding": "16px 18px"},
        children=[
            html.Div(label, style={"color": "#A3AED0", "fontSize": "0.72rem", "fontWeight": 600,
                                   "textTransform": "uppercase", "letterSpacing": "0.02em",
                                   "fontFamily": "DM Sans"}),
            html.Div(value, style={"color": accent, "fontSize": "1.5rem", "fontWeight": 700,
                                   "fontFamily": "DM Sans", "marginTop": "4px", "lineHeight": 1.1}),
            html.Div(sub, style={"color": "#707EAE", "fontSize": "0.72rem", "marginTop": "2px",
                                 "fontFamily": "DM Sans"}) if sub else None,
        ],
    )
```

Replace the entire `_tab_customer_availability` function body with:

```python
def _tab_customer_availability(avail: dict):
    """AuraNotify outages for the customer — readable summary tiles + detail lists."""
    from src.utils.availability_summary import summarize_outages, format_downtime

    svc = avail.get("service_downtimes") or []
    vm = avail.get("vm_downtimes") or []
    cid = avail.get("customer_id")
    cids = [x for x in (avail.get("customer_ids") or []) if x is not None]
    if not cids and cid is not None:
        cids = [cid]

    s = summarize_outages(svc, vm)

    def _sort_recent(rows):
        return sorted(
            [r for r in rows if isinstance(r, dict)],
            key=lambda r: str(r.get("start_time") or ""),
            reverse=True,
        )

    def _svc_row(e: dict):
        return html.Tr([
            html.Td(str(e.get("category") or "-")),
            html.Td(str(e.get("group_name") or "-")),
            html.Td(_outage_type_badge(e.get("type"))),
            html.Td(str(e.get("start_time") or "-")),
            html.Td(str(e.get("end_time") or "-")),
            html.Td(format_downtime(e.get("duration_minutes"))),
            html.Td(str(e.get("service_impact") or e.get("outage_status") or "-")),
        ])

    def _vm_row(e: dict):
        cluster_host = " / ".join(
            str(e.get(k)) for k in ("cluster", "host") if str(e.get(k) or "").strip()
        ) or "-"
        return html.Tr([
            html.Td(str(e.get("vm_name") or e.get("vm") or "-")),
            html.Td(cluster_host),
            html.Td(_outage_type_badge(e.get("type"))),
            html.Td(str(e.get("start_time") or "-")),
            html.Td(str(e.get("end_time") or "-")),
            html.Td(format_downtime(e.get("duration_minutes"))),
            html.Td(str(e.get("category") or e.get("reason") or "-")),
        ])

    svc_cols = ["Category", "Datacenter group", "Type", "Start", "End", "Duration", "Impact"]
    vm_cols = ["VM", "Cluster / Host", "Type", "Start", "End", "Duration", "Category"]

    longest = s["longest"]
    longest_val = format_downtime(longest.get("duration_minutes")) if longest else "-"
    longest_sub = (str(longest.get("category") or longest.get("group_name") or "")[:28]
                   if longest else "No outages")
    down_accent = "#E31A1A" if s["total_downtime_min"] else "#05CD99"
    unpl_accent = "#E31A1A" if s["unplanned_count"] else "#05CD99"
    tiles = dmc.SimpleGrid(
        cols={"base": 2, "sm": 3, "lg": 5}, spacing="sm", mb="lg",
        children=[
            _avail_tile("Total outages", str(s["total_outages"]),
                        f"{s['service_outages']} service · {s['vm_outages']} VM"),
            _avail_tile("Total downtime", format_downtime(s["total_downtime_min"]), "in period", down_accent),
            _avail_tile("Unplanned", str(s["unplanned_count"]), f"{s['planned_count']} planned", unpl_accent),
            _avail_tile("Longest outage", longest_val, longest_sub, "#FFB547"),
            _avail_tile("Locations", str(len(s["locations"])), (", ".join(s["locations"])[:28] or "—")),
        ],
    )

    children: list = [
        dmc.Text(
            f"AuraNotify availability (customer ids: {cids or 'none'}) — aligned with report period start.",
            size="sm", c="dimmed",
        ),
        tiles,
    ]
    if svc:
        children.append(_section_card(
            "Service & datacenter outages",
            "Infrastructure interruptions affecting this customer",
            _maybe_paginated_table(svc_cols, [_svc_row(e) for e in _sort_recent(svc)]),
        ))
    if vm:
        children.append(_section_card(
            "VM outages",
            "Virtual machine downtime records",
            _maybe_paginated_table(vm_cols, [_vm_row(e) for e in _sort_recent(vm)]),
        ))
    if not svc and not vm:
        children.append(dmc.Alert(
            color="teal", variant="light", title="No outages in period",
            children="No service or VM downtime records for this customer in the selected report period.",
        ))
    return dmc.Stack(gap="lg", children=children)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_customer_availability_tab.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pages/customer_view.py tests/test_customer_availability_tab.py
git commit -m "feat(availability): readable tab — summary tiles + clean outage lists"
```

---

### Task 7: Targeted suite + standalone preview + (deferred) live verification

**Files:** none (verification only).

- [ ] **Step 1: Run the feature's test set**

Run: `source .venv/bin/activate && pytest tests/test_auranotify_bundle_fields.py tests/test_api_client_auranotify_mapping.py tests/test_crm_source_mapping_auranotify.py tests/test_crm_aliases_auranotify_render.py tests/test_availability_summary.py tests/test_customer_availability_tab.py tests/test_crm_aliases_page.py tests/test_api_client_customer_avail_cache.py -q`
Expected: all PASS. (Repo-root `pytest` also collects `services/*/tests` which fail to import in this venv — a pre-existing environment gap, not a regression.)

- [ ] **Step 2: Standalone preview (no live AuraNotify needed)**

Render `_tab_customer_availability` with representative sample data (both a populated customer and the empty state) in a standalone Dash app on a spare port, screenshot with headless Chrome, and review the layout for readability. This confirms the tiles + lists render correctly without needing the AuraNotify service.

- [ ] **Step 3: Deferred live verification (when AuraNotify :5001 is back)**

Map a real customer with data (e.g. `Affinitybox · id 1514`, or a VM-outage customer) via the alias editor, open Customer View → Availability, confirm tiles + lists populate from real data and match the offline analysis. Run the full all-customer outage analysis at the same time and tune tile choices if the real distribution warrants.
