# Colocation Usage Breakdown — Design Spec

**Date:** 2026-07-25
**Context:** Follow-up to TASK-62 (colocation visualization). The DC "Colocation" tab's
"Dedicated Customers" table shows only external colocation customers (5 in DC13), which reads as
"only 5 customers use this DC" when in reality most used-U is Bulutistan-internal gear or devices
with no `tenant_name` in NetBox. We surface where the used rack-U actually goes, in English, in two
places: the DC Colocation tab and the Floor Map.

## Problem

`used_u` (occupied rack-U) has three origins that the UI currently hides:
- **External** — external colocation customers (the existing table). DC13 ≈ 149U.
- **Internal** — Bulutistan's own gear (`is_internal_tenant`). DC13 ≈ 481U.
- **Untagged** — devices with no `tenant_name` in NetBox (unattributable). DC13 ≈ 648U (the largest).

Showing only External makes the picture misleading. Untagged being the biggest slice is itself a
useful NetBox data-quality signal.

## Goals / Non-goals

- **Goal:** show the External/Internal/Untagged split of used-U in the DC Colocation tab and the
  Floor Map; relabel colocation UI to English.
- **Non-goal:** globe/global-view changes (explicitly moved to the Floor Map). No new endpoints.
  No NetBox write-back / tagging workflow. No change to the de-dup / exact-per-customer logic
  shipped in `7e015d98`.

## Design

### 1. Backend — used-U partition (`shared/colocation/occupancy.py`)

New pure function that partitions used-U into the three groups so they sum **exactly** to the
de-duplicated `used_u` (clean 100% stacked bar):

```
used_u_breakdown(cursor, dc_pattern=None) -> {
    "external_u": int, "internal_u": int, "untagged_u": int,
    "external_customer_count": int,
}
```

- Reuses the same device→rack join + de-fan discipline as `tenant_occupancy_rows` /
  `_dedupe_physical_racks` (dedupe by `(rack_name, site_name)`; front-face; `COUNT(DISTINCT u)`).
- **Each occupied `(rack_name, site_name, u)` slot is assigned to exactly ONE group** by priority
  **External > Internal > Untagged**: if any external tenant occupies the slot → external; else if
  any internal tenant → internal; else → untagged. So `external_u + internal_u + untagged_u == used_u`.
- `external_customer_count` = distinct non-internal, non-blank tenant names in scope.
- Classification of a tenant string reuses `is_internal_tenant`; a blank/NULL tenant is untagged.

Exposed by BOTH consumers (so each has the split without an extra round-trip):
- **customer-api** `ColocationMatchingService.get_colocation` → merge the four fields into the
  returned `aggregate`.
- **datacenter-api** `get_dc_racks_occupancy` → merge the four fields into its `summary`.

### 2. Frontend — reusable summary component (`src/components/colocation_summary.py`)

`build_colocation_summary(aggregate: dict, customer_count: int | None = None) -> component`

- **KPI tiles** (English): Total U · Used U · Free U · Racks. (Reuses existing `_kpi`/`_ring` style.)
- **"Used U — where it goes"**: a single 100%-width stacked bar with three segments —
  🟠 External · 🔵 Internal · ⚪ Untagged — proportional to `external_u/internal_u/untagged_u`.
- **Three sub-labels** under the bar: `External {u}U ({n} customers)` · `Internal {u}U` ·
  `Untagged {u}U`.
- Degrades gracefully when the split fields are absent/zero (bar hidden, tiles still shown).

A standalone component module avoids a dc_view ↔ floor_map import cycle; both import it.

### 3. Placement

- **DC View → Colocation tab** (`dc_view.build_colocation_tab`):
  - Rename the tab label to **"Colocation"** (was "Kolokasyon").
  - Put `build_colocation_summary` at the top (above the customers table).
  - Relabel the table to English: section **"Dedicated Customers"**, subtitle
    "Device tenant → CRM match", columns **Customer · CRM Account · Match · Rack · Used U (own)**.
    The empty-state text becomes English.
- **Floor Map** (`floor_map.build_floor_map_layout`):
  - Add `build_colocation_summary` as a **full-width strip directly below the header**, above the
    map/detail grid. Data from `api.get_dc_racks_occupancy(dc_id)` (already fetched context;
    `summary` now carries the split + `external_customer_count`). The floor-map strip shows the
    bar + counts only (no customers table).

### 4. Naming / i18n

All colocation-facing UI text becomes English: "Colocation", "Dedicated Customers",
Total U / Used U / Free U / Racks, External / Internal / Untagged, "Used U (own)".

## Data-flow

```
discovery_netbox_inventory_device + loki_device_types + discovery_loki_rack
   └─ shared.colocation.occupancy.used_u_breakdown (de-fanned, slot-priority partition)
        ├─ customer-api get_colocation.aggregate  ─┐
        └─ datacenter-api get_dc_racks_occupancy.summary ─┐
                                                          ├─ build_colocation_summary (component)
   DC View Colocation tab  ← get_colocation ───────────────┘   (bar + tiles)
   Floor Map strip         ← get_dc_racks_occupancy ──────────┘
```

## Testing (TDD)

- `used_u_breakdown`: priority (external>internal>untagged), exact partition (sum == used_u),
  de-fan (duplicate rack rows don't inflate), untagged = blank/NULL tenant, external_customer_count.
- `build_colocation_summary`: renders three bar segments + three sub-values; graceful when fields 0/absent.
- customer-api `get_colocation`: `aggregate` includes `external_u/internal_u/untagged_u/external_customer_count`.
- datacenter-api `get_dc_racks_occupancy`: `summary` includes the same four fields.
- `build_colocation_tab`: English labels present; summary component present.
- `build_floor_map_layout`: colocation summary strip present.

## Risks

- **Slot-overlap edge cases** (a slot with both internal and external devices): priority external
  wins; documented, negligible. Partition still sums to used_u.
- **Cross-DC label ambiguity** (Istanbul cluster) already handled by the shipped de-fan; the split
  inherits it (per-DC best-effort, total exact).
- Touches the shared `occupancy` module + both service payloads; covered by tests + live re-verify.
