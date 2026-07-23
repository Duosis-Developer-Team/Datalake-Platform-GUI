# TASK-62 — Colocation (Kolokasyon) Service Visualization — Design

**Ticket:** TASK-62 "Collacation Hizmeti Görselleştirilmesi" · Customer: Bulutistan · Project: BulutDL / Data Görselleştirme
**Date:** 2026-07-23 · **Status:** Design approved, spec under review
**Repo:** `Datalake-Platform-GUI` (frontend `src/` + backend services `services/*` live in the same repo)

## 1. Goal

Take free rack space (in rack-units, **U**) derived from Loki/NetBox inventory, match it to the relevant
CRM colocation service (customer-dedicated cabinet / U space), and **visualize** it in **both** the
Datacenter view and the Globe view.

Ticket text: *"Müşterilere dedike verilebilir alanlar var racklerde, u bazlı işlem yapılacak. Loki'den alınan
veriler ile racklerdeki boş alanlar crm'deki ilgili hizmet ile eşleştirilip görselleştirilecek. Hem Datacenter
hem de globe view'da."*

## 2. Approved scope decisions

| Decision | Choice |
|---|---|
| **Grain** | **Layered** — DC-aggregate metric on Globe + DC; per-customer / per-U drill-down on floor map + rack elevation |
| **CRM depth** | **Full stack** — physical free-U + tenant→customer matching + `dc_hosting_u` sellable wiring + crm-engine publication + CRM inventory report row |
| **CRM/TL shaping** | **Full sold-U vs used-U vs free-U reconciliation** — build the infrastructure completely; near-empty CRM sold side is an external backfill dependency, not solved here |

## 3. Data reality (verified read-only against `bulutlake` @ 10.134.16.6:5000, 2026-07-23)

This ground truth reshaped the plan and MUST be respected during implementation.

| Signal | Reality | Consequence |
|---|---|---|
| Rack `tenant_name` (`discovery_loki_rack`) | **10 / 234 racks** populated (~4%): Boyner(7), AytemizBank(2), Turkonay(1) | Per-**rack** customer attribution is a dead end — **do not** use it as the primary key |
| Device `tenant_name` (`discovery_netbox_inventory_device`, 2220 deduped rows) | **906 / 2220** (~41%), but mostly **internal** (Bulutistan-Virtualization 427, Linux 149, Network&Security 129…). **~7 external colo customers**: AytemizBank(3 racks/52U), Paycore(2/54U), CPE-Tenant(10/73U), Moneygram(2/26U), Boyner(5/137U), A101(1/16U), Turkonay(1/6U) | Per-customer attribution works via **devices**, but is sparse (~7 customers). Filter out internal Bulutistan tenants for the "customer" view |
| CRM colocation **sold** | **≈ 2 U total.** `000BLT-156 Veri Merkezi Barındırma Hizmeti (U)` = 2 lines / 2 U; `000BLT-20 Cross Connect` = 4 Adet. UOM "U" appears in **2 rows** in the entire CRM sales | Sold-vs-free reconciliation is effectively empty today. Wiring publishes `sellable ≈ free_U × TL` — a *potential-to-sell* story until CRM colocation SKUs are backfilled (external) |
| Physical U capacity/occupancy | Solid — 234 racks (all `active`), real `u_height`, device heights via `loki_device_types.u_height` | The free/sellable-U core is fully buildable and is the high-value deliverable |

### 3a. Occupancy math is a trap (must fix)

Two divergent, both-wrong calculations exist today:
- **Floor map** (`src/pages/floor_map.py:145`) counts devices as **1 U each** → undercounts multi-U gear.
- **The naive "Σ device_type.u_height"** approach overcounts wildly — a spot check gave rack "116" = **135 U used in a 47 U rack** because (a) rack **names are not unique** across DCs/halls (join on name fans out), (b) front/rear **faces** double-count, (c) chassis **child devices** are counted alongside their parent.

Correct occupancy MUST: key by **`rack_id`** (not name), dedupe by `(position, face)`, use real `loki_device_types.u_height`, and **cap at `capacity_u`**.

### 3b. Schema drift (must fix)

`services/datacenter-api/app/db/queries/crm_potential.py` references tables that **do not exist**:
- `discovery_loki_racks` (plural) — real table is `discovery_loki_rack` (singular, 234 rows)
- `discovery_netbox_inventory_device_type` — real table is `loki_device_types` (has `u_height`)

The `DC_SALES_POTENTIAL` rack path is therefore dead/broken and is replaced by this design.

## 4. What already exists (reuse, do not rebuild)

- **Floor Map** (`src/pages/floor_map.py` + callbacks in `app.py`): colors racks by U-fill (blue/green/orange/red), hover shows occupied/free/pct + "Satılabilir alan var". Two-phase render. Data via `get_dc_racks` + per-rack `get_rack_devices`.
- **Rack elevation** `_build_rack_unit_diagram` (`app.py:1783`): per-U CSS rack, device per slot.
- **dc_detail.py**: flat rack list, already displays each rack's `tenant_name` (`dc_detail.py:64,118`).
- **Globe** (`src/pages/global_view.py` + `dash_globe_component`): one MapLibre marker per DC. Extra per-point fields ride along automatically into `clickedPoint` with zero JS change (Tier A). Detail card `build_dc_info_card` renders RingProgress tiles (room for a 4th). Prefetch warmer (`global_view_prefetch.py`) already pulls rack + device data per DC.
- **CRM side**: colocation modeled as panels `dc_hosting_u` (unit **U**) + `dc_hosting_kabinet` (unit Adet), family `dc_hosting`, `resource_kind='other'`, seeded in `services/customer-api/migrations/webui/006_seed_panel_definitions.sql:105-106`. Products matched by name (`shared/sellable/panel_mapping.py:121-122`: "Veri Merkezi Barındırma" + "(U)"/"Kabinet").
- **Tenant→customer resolution**: `gui_crm_customer_alias` (NetBox tenant → CRM accountid) + `tenant_matches_text_rules` (`services/datacenter-api/app/services/dc_service.py:96`) + `gui_crm_customer_source_mapping`. Proven on the VM side (`dc_sales_potential_v2.py`); **not yet driven off physical devices/racks** — that wiring is this task.
- **CRM inventory report** (`src/components/crm_inventory_report.py`, `src/pages/crm_inventory_overview.py`): rows show CRM Sold / Total / Used / Free / Sellable / Unit price. A panel with `has_infra_source=False` but CRM TL > 0 renders "CRM entitled — infra telemetry pending" — the exact current state of the colocation panels.

## 5. Architecture — one occupancy source of truth

The spine is a **single canonical occupancy computation** consumed by every layer, ending the divergence in §3a:

```
bulutlake view  v_rack_occupancy        ← correct math, ONE place
   columns: rack_id, dc, hall, rack_name, capacity_u,
            used_u, free_u, pct, tenant_names[]
   used_u = Σ loki_device_types.u_height, keyed by rack_id,
            deduped by (position, face), capped at capacity_u
        │
        ├──► datacenter-api  → bulk endpoints (globe aggregate, floor map, DC "Kolokasyon" tab)
        └──► customer-api sellable → dc_hosting_u infra source (total=capacity_u, allocated=used_u) → TL
```

**Chosen wiring for sellable (approved):** point the `dc_hosting_u` infra source at **`v_rack_occupancy`** rather
than adding a custom sellable code path. Rationale: the current sellable infra-source model is a naive
`SUM(column)`, which cannot express the correct occupancy math; baking the math into the view means both
datacenter-api and customer-api agree by construction. (Rejected alternative: a new `colocation` sellable
*profile* in `sellable_service.py` — more code, second place for the math to drift.)

**View ownership note:** `v_rack_occupancy` is a small read-only DB view over `discovery_*`/`loki_*` tables.
Those tables are populated by external collectors (the `datalake` repo). The view DDL will be managed as a
datacenter-api-owned migration/bootstrap against `bulutlake`; confirm during implementation whether it should
instead live in the `datalake` repo's SQL. Either way it is additive and read-only.

## 6. Components

### 6.1 Backend — data layer (`services/datacenter-api`)
- **`v_rack_occupancy`** view — correct per-rack math (§3a), replacing the broken `crm_potential.py` rack path (§3b).
- **`GET /api/v1/datacenters/{dc}/racks/occupancy`** — bulk; one call replaces the current ~78 per-rack `get_rack_devices` fetches. Returns per rack `{rack_id, name, hall, capacity_u, used_u, free_u, pct, tenants[]}`.
- **Per-DC colocation aggregate** added to `/api/v1/datacenters/summary` (and/or `/datacenters/{id}`): `coloc_total_u, coloc_used_u, coloc_free_u`, so the globe needs no per-DC device fan-out at page load.

### 6.2 Backend — customer/CRM matching + sellable (`services/customer-api`, `services/crm-engine`)
- **Tenant→customer resolver for physical devices**: reuse `gui_crm_customer_alias` + `tenant_matches_text_rules`, driven off **device** `tenant_name` aggregated per rack; **exclude internal Bulutistan tenants** from the "customer" set. Output: per-customer colocation footprint (racks, used-U) joined to that account's CRM `dc_hosting` sold lines.
- **`dc_hosting_u` sellable wiring**: add the missing `007`-style infra source (`services/customer-api/migrations/webui/007_seed_panel_infra_sources.sql` pattern) pointing at `v_rack_occupancy` (total=`capacity_u`, allocated=`used_u`), threshold 80%, `resource_kind='other'` (no ratio coupling), TL/U price override (`gui_crm_price_override` / catalog). crm-engine auto-publishes it into the `inventory-overview` payload.

### 6.3 Frontend — layered visualization (`src/`)
- **Globe** (`global_view.py`): add `coloc_free_u/used_u/total_u` to each point in `_build_globe_data`; add a 4th "Kolokasyon" ring to `build_dc_info_card` (**Tier A — no JS rebuild**). Optional later: pin-color overlay = JS rebuild of `dash_globe_component`.
- **DC view** (`dc_view.py` + `dc_view_callbacks.py`): new lazy **"Kolokasyon" tab** — register `"colo"` in `_LAZY_TAB_KEYS`, add `dc-tab-colo-root` + `TabsTab`/`TabsPanel` + `build_colocation_tab(...)` + a branch in `build_dc_lazy_tab_panel`, extend outputs in `expand_dc_view_on_tab`, gate with section code `sec:dc_view:colo`. Content: DC KPIs (capacity/used/free/sellable-TL), **dedicated-customers table** (customer → racks → used-U → CRM match status), sold-vs-free reconciliation.
- **Floor map** (`floor_map.py`): switch to the bulk occupancy endpoint + **correct** real-U occupancy; keep green/orange/red fill; add tenant on hover + a "dedicated customer" accent where resolved.
- **Rack elevation** (`_build_rack_unit_diagram`): annotate U-ranges with owning customer where device `tenant_name` resolves (e.g. "U10–U14 · AytemizBank").
- **CRM inventory report** (`crm_inventory_report.py`): `dc_hosting_u`/`dc_hosting_kabinet` rows now populate (sold/used/free/sellable/TL) — no UI change; they stop showing "infra telemetry pending".

## 7. Data flow

`v_rack_occupancy` → datacenter-api endpoints → { globe aggregate | floor map | DC Kolokasyon tab }.
`v_rack_occupancy` → customer-api `dc_hosting_u` sellable → crm-engine `inventory-overview` → CRM report row.
Tenant→customer resolver runs in customer-api (owns the alias tables); surfaced in the DC-tab customer table
and floor/rack overlays.

## 8. Testing

- **Unit:** occupancy math — the 135-U-in-47-U case must cap at 47; dedup `(position, face)`; multi-U gear sums real heights; non-unique rack-name guard (key by `rack_id`).
- **Unit:** tenant→customer resolution — internal Bulutistan tenants excluded; alias + text-rule paths.
- **Unit:** sellable formula `sellable = max(capacity_u × 0.80 − used_u, 0)`, `potential_tl = sellable_u × TL/U`.
- **Data-contract test:** assert `discovery_loki_rack`, `loki_device_types`, `discovery_netbox_inventory_device` exist (guards the §3b drift from recurring).
- **Fixtures:** encode the ~7-customer sparse reality so the per-customer layer is tested despite thin prod data.

## 9. Non-goals (this task)

- Power-based sellable (`kabin_enerji` is a string like "12 kW" — parse deferred to Phase 2).
- CRM colocation sales **backfill** / SKU digitization (external data dependency).
- `dc_hosting_kabinet` (Adet) reconciliation beyond wiring the row.
- Globe pin-color overlay (Tier B / JS rebuild) — optional follow-up.

## 10. Open items to confirm during implementation

1. **`v_rack_occupancy` ownership** — datacenter-api-managed view vs `datalake` repo SQL (§5).
2. **TL/U price source** — `gui_crm_price_override` vs product catalog default; confirm a sensible default when unset.
3. **Baseline test run** — execute the datacenter-api / customer-api / GUI suites (Python 3.11 venv) at implementation kickoff before first change.

## 11. Key references

- `docs/backend-brief-rack-sellable.md` — prior backend brief (uses the now-known-broken table names; superseded on schema by §3b).
- `datalake-knowledge-base/wiki/CRM-Inventory-Infra-Matching.md`, `datalake-knowledge-base/wiki/datalake-collectors/NetBox-Loki.md`.
- `services/datacenter-api/app/db/queries/discovery_rack.py` (rack/device queries), `crm_potential.py` (broken rack path to replace).
- `services/customer-api/migrations/webui/006_seed_panel_definitions.sql:105-106`, `007_seed_panel_infra_sources.sql` (schema to extend).
- `src/pages/floor_map.py`, `src/pages/dc_view.py`, `src/pages/global_view.py`, `src/components/crm_inventory_report.py` (UI surfaces).
