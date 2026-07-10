# Customer Availability — AuraNotify mapping + API-shape fix

**Date:** 2026-07-10
**Status:** Design — approved for planning
**Excel task ref:** row 39 "Customer Avaliability Düzenlemeleri" (Devam ediyor)
**Author:** Arca (with Claude)

## 1. Background

The Customer View has an **Availability** tab (`_tab_customer_availability`,
`src/pages/customer_view.py`). It shows AuraNotify service/VM outage records for the
selected customer, and drives a per-VM "outage(s)" badge in the virtualization tables.

The data pipeline has two links:

```
customer selected → [1] which AuraNotify customer id(s)? → AuraNotify API
                  → [2] which response fields do we read?   → Availability tab
```

Two independent defects live on this pipeline. Both were confirmed against the **live**
AuraNotify API (`http://10.34.8.154:5001`) on 2026-07-10.

### Defect A — link [2]: response shape changed, tab is currently blank (HIGH impact)

The AuraNotify downtimes endpoint changed its `source` query-param semantics. `source`
now **filters** the response to one category. Valid values: `datacenter`, `dedicated`,
`service`, `vm`, or omitted = all categories.

Our client (`auranotify_client.get_customer_availability_bundle`) still calls:

```python
svc_body = get_customer_downtimes(cid, start_date, "service")   # source=service
vm_body  = get_customer_downtimes(cid, start_date, "vm")        # source=vm
se = svc_body.get("datacenter_downtimes")   # source=service filters this to []
ve = vm_body.get("datacenter_downtimes")    # source=vm filters this to []
```

Live evidence (customer `4a_Kozmetik`, id 1498, since 2024-01-01):

| call | `datacenter_downtimes` |
|---|---|
| `source=datacenter` / no source | **18** |
| `source=service` (our code) | **0** |
| `source=vm` (our code) | **0** |

Repo-wide live scan (1602 customers, no-source call):

| field | customers with data |
|---|---|
| `datacenter_downtimes` | **1213** |
| `vm_downtimes` | **399** |
| `service_downtimes` | 0 |
| `dedicated_downtimes` | 0 |

**Result:** the Service-outages table is empty for all 1213 customers that have
datacenter outages, and the VM-outages table is empty for all 399 customers that have VM
outages. The tab is effectively non-functional regardless of which customer id is used.

### Defect B — link [1]: id resolution is name-fuzzy (MEDIUM impact)

`auranotify_client.resolve_customer_ids(customer_name)` matches our customer **name**
against AuraNotify's `/api/customers/list` names: `name == prefix` or
`name.startswith(prefix + "_")`. AuraNotify holds the same logical customer under
divergent names/ids — e.g. `4a_Kozmetik` (id 1498) vs
`4A KOZMETİK SANAYİ VE TİCARET ANONİM ŞİRKETİ` (id 3787). When our CRM name does not
line up with AuraNotify's base name, the tab shows the wrong customer's outages or none.

The stakeholder request (Can Duosis, 2026-07-10): add AuraNotify to the existing
**customer alias mapping** page (Administration → Integrations → Customer source
mappings) so an operator can bind a platform customer to explicit AuraNotify id(s).

## 2. Goals / non-goals

**Goals**
- G1. Fix the client so the Availability tab shows real service and VM outages again.
- G2. Let operators map a platform customer → explicit AuraNotify customer id(s) from the
  existing alias page, by searching AuraNotify by name **or** entering an id directly.
- G3. When an explicit mapping exists, use it; otherwise keep today's name-based matching
  (backward compatible — 1602 customers will not be mapped on day one).

**Non-goals**
- No schema change to `gui_crm_customer_source_mapping`.
- No change to the DC-level annual availability page (`availability_annual.py`) — its
  `/api/sla/datacenter-services` path is unaffected and already works.
- No new matching by contact email domain (the API now returns `contacts[].email`; noted
  as a future signal, out of scope here).
- No auto-population/bulk-mapping of all customers.

## 3. Data shapes (from live API, 2026-07-10)

`GET /api/customers/list` → `[{id:int, name:str, contacts:[{email,name,phone}]}]` (1602 rows).

`GET /api/customers/{id}/downtimes?start_date=YYYY-MM-DD[&source=...]` →
```
{ customer_id, customer_name, period_start, period_end,
  datacenter_downtimes: [...], dedicated_downtimes: [...],
  service_downtimes: [...],    vm_downtimes: [...],
  summary: {datacenter_count, dedicated_count, service_count, vm_count, total_count} }
```

`datacenter_downtimes[]` keys: `category, group_name, type, start_time, end_time,
duration_minutes, service_impact, outage_status, scope, reason, dc_impact, senaryo,
created_at, id`. (No `vm_name` — DC-wide event.)

`vm_downtimes[]` keys: the same, **plus** `vm_name, cluster, host, customer, endpoint`.
(No `group_name`.)

## 4. Design

### 4.1 Defect A — client fix (`src/services/auranotify_client.py`)

Replace the two filtered calls with **one no-source call per AuraNotify id** and read the
correct fields.

- `get_customer_downtimes(customer_id, start_date, source=None)` — make `source` optional;
  when `None`, omit the param (returns all categories). Keep the param for callers that
  want one category, but the bundle stops passing it.
- New `get_availability_bundle_for_ids(ids: list[int], start_date: str) -> dict` holds the
  bundle logic, taking ids directly:
  - one `get_customer_downtimes(cid, start_date)` per id (no source);
  - **Service outages** = concat of `datacenter_downtimes + dedicated_downtimes +
    service_downtimes` across ids (service/dedicated empty today, included for forward
    compat);
  - **VM outages** = concat of `vm_downtimes` across ids;
  - `vm_outage_counts` = `vm_outage_counts_from_events(vm_downtimes)` (records carry
    `vm_name`, so counts populate correctly);
  - return `{service_downtimes, vm_downtimes, vm_outage_counts, customer_id, customer_ids}`
    (unchanged shape — callers untouched).
- `get_customer_availability_bundle(customer_name, start_date)` becomes a thin wrapper:
  `ids = resolve_customer_ids(customer_name)` then `get_availability_bundle_for_ids(...)`.
  This preserves the name-based path as the fallback used by Defect-B design below.

### 4.2 Defect A — display tweak (`src/pages/customer_view.py`)

`_tab_customer_availability` `_vm_row` currently reads `group_name`, which VM records lack.
Adjust the VM table columns to the real VM shape: show `vm_name`, `cluster`/`host`,
`start`, `end`, `duration`, `reason`/`category`. `_svc_row` already matches the
`datacenter_downtimes` shape and needs no change. Keep the empty-state and pagination.

### 4.3 Defect B — AuraNotify mapping in the alias editor

**Storage (no schema change).** Persist as a normal source-mapping entry:
`data_source = "auranotify"`, `match_method = "id_exact"`, `match_value = "<auranotify id>"`,
`enabled`. Stored via the existing `PUT /api/v1/crm/aliases/{id}/source-mappings` path.

**Editor UI (`crm_aliases.py` + `crm_source_mapping_ui.py`).**
- Add a new column to `UI_COLUMNS`: `("auranotify", "Availability (AuraNotify)",
  ("auranotify",))`.
- Special-case the row renderer for the `auranotify` section only: the value control is a
  **searchable `dmc.Select`** whose options are the AuraNotify customer list as
  `{label: "<name> · id <id>", value: "<id>"}`. Searching filters by label, so the
  operator finds a customer by typing its **name or its id number** (both appear in the
  label) — one control satisfies "search by name or enter id directly". The method control
  is fixed to `id_exact` (rendered read-only/hidden); source is fixed to `auranotify`.
  Multiple entries allowed (e.g. Boyner → its 8 sub-account ids).
- The AuraNotify option list is fetched once when the alias page builds
  (`api.get_auranotify_customer_options()` wrapping `aura.get_customer_list_aura()`),
  cached, and passed to the editor. 1602 options in a searchable Select is acceptable.
- Because the row still emits the same pattern-matched ids
  (`{"type":"alias-edit-value","section":"auranotify","index":n}`), the existing
  `save_editor_mappings_cb` collection and `editor_state_to_save_payload` handle it with no
  change.

**Consumption (`src/services/api_client.py`).** No circular import — `api_client` already
imports `auranotify_client` lazily; the reverse is not introduced.
- New `get_auranotify_ids_for_customer(customer_name) -> list[int]`: read cached
  `get_crm_aliases()`, find the alias whose `crm_account_name` case-insensitively equals
  `customer_name`, collect enabled `source_mappings` with `data_source == "auranotify"`,
  parse `match_value` as int, dedupe.
- In `_fetch_customer_availability_bundle_uncached(customer_name, tr)`:
  ```python
  ids = api.get_auranotify_ids_for_customer(customer_name)
  if ids:
      return aura.get_availability_bundle_for_ids(ids, start)
  return aura.get_customer_availability_bundle(customer_name, start)  # name-based fallback
  ```

**Name↔alias assumption.** Customer View's `selected_customer` and the alias page's
`crm_account_name` both originate from CRM PRJ-* orders, so an exact (case-insensitive)
match is expected. If it ever mismatches, the code falls back to name-based matching —
no worse than today.

## 5. Edge cases & backward compatibility

- No mapping for a customer → name-based fallback (today's behavior).
- Mapping present but AuraNotify unreachable / key unset → `get_customer_downtimes`
  already returns `{}`; bundle returns empty lists; tab shows the empty-state.
- Non-numeric / stale `match_value` → skipped during int-parse; other ids still used.
- `service_downtimes`/`dedicated_downtimes` empty today but included in the concat, so the
  fix is correct if AuraNotify starts populating them.
- Bundle return shape is unchanged, so the four call sites in `customer_view.py` and the
  warm scheduler (`refresh_warmed_customer_availability_bundles`) are untouched.

## 6. Testing

Pure-helper unit tests (no live API), following the repo's existing
`tests/test_api_client_customer_avail_cache*.py` and mapping-UI test style:
- `get_availability_bundle_for_ids`: given fake per-id responses with populated
  `datacenter_downtimes` + `vm_downtimes`, asserts service table = datacenter+dedicated+
  service concat, vm table = vm concat, and `vm_outage_counts` keyed by `vm_name`.
- `get_customer_downtimes`: asserts `source=None` omits the query param.
- `get_auranotify_ids_for_customer`: given fake aliases, returns the mapped ids for a
  name match, `[]` for no match, and ignores non-`auranotify` / disabled / non-numeric
  mappings.
- Resolution precedence: explicit mapping wins; empty mapping falls back to name path.
- Mapping-UI helper: `UI_COLUMNS` includes `auranotify`; a saved auranotify entry
  round-trips through `editor_state_to_save_payload` with `id_exact`/`auranotify`.

## 7. Files touched

- `src/services/auranotify_client.py` — `get_customer_downtimes` optional source;
  `get_availability_bundle_for_ids`; rewire `get_customer_availability_bundle`.
- `src/services/api_client.py` — `get_auranotify_ids_for_customer`,
  `get_auranotify_customer_options`, mapping-aware `_fetch_customer_availability_bundle_uncached`.
- `src/utils/crm_source_mapping_ui.py` — add `auranotify` to `UI_COLUMNS`.
- `src/pages/settings/integrations/crm_aliases.py` — auranotify-section row renderer
  (searchable Select) + thread AuraNotify options into the editor.
- `src/pages/settings/integrations/crm_aliases_callbacks.py` — load/pass AuraNotify
  options; verify save collection unaffected.
- `src/pages/customer_view.py` — `_vm_row` column adjustment for the real VM shape.
- `tests/` — the units in §6.

## 8. Verification (live)

1. Map a known customer with data (e.g. `Affinitybox` → id 1514, 22 datacenter recs; or a
   VM-outage customer like `Abrak_Enerji` → id 1504) via the alias editor.
2. Open Customer View → that customer → Availability: Service and/or VM outages tables now
   populate; VM badges appear in the virtualization tables.
3. An unmapped customer still resolves via name (regression check).
```
