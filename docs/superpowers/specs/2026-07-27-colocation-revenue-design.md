# Colocation Revenue & Physical Inventory Restructure — Design

**Date:** 2026-07-27
**Branch:** `worktree-physical-inventory-colocation-revenue`
**Supersedes nothing.** Builds on [2026-07-23-colocation-service-visualization-design.md](2026-07-23-colocation-service-visualization-design.md)
and [2026-07-25-colocation-usage-breakdown-design.md](2026-07-25-colocation-usage-breakdown-design.md).

## Problem

Colocation lives as its own top-level DC View tab, disconnected from Physical Inventory
even though rack-U occupancy *is* physical inventory. Separately, the platform shows no
money figure for colocation at all: Bulutistan sells rack space per-U in CRM, but that
price never reaches the UI, so free rack space carries no visible commercial value.

A third defect surfaced during exploration: the Colocation "Internal Resources" table
claims to reflect the Administration → Integrations → Internal (Bulutistan) source
mappings screen. It does not. See "Internal mapping defect" below.

## Measured data reality

All figures below were read from prod `bulutlake` on 2026-07-27. They constrain the
design and must not be re-derived from assumptions.

### CRM colocation product family

`discovery_crm_products` contains four colocation-adjacent products. Only one is priced
per rack-U:

| Product | productid | UOM | TRY | USD | EUR |
|---|---|---|---|---|---|
| Veri Merkezi Barındırma Hizmeti **(U)** | `ee635018-5c6d-f011-b4cc-6045bd93381c` | U | 10,430.84 | 220.76 | 193.91 |
| Veri Merkezi Barındırma Hizmeti (Standart Kabinet) | `ec635018-…` | Adet | 187,750.94 | 3,973.59 | 3,490.33 |
| Veri Merkezi Barındırma Hizmeti (Standart Dışı Kabinet) | `ea635018-…` | Adet | 232,453.88 | 4,919.69 | 4,321.36 |
| Smart Hands Kabin Destek Hizmeti | `00c8d7e0-…` | Adet | 6,223.26 | 131.71 | 115.69 |

The `(U)` product is the **only** product in the entire CRM priced with `uomid_name = 'U'`.

### Realized colocation sales

`discovery_crm_salesorderdetails` holds exactly two colocation lines, both on the `(U)`
product:

| Customer | Qty | Extended amount (TL) | Effective unit price | statecode |
|---|---|---|---|---|
| BEYAZ BİLGİSAYAR … BEYAZNET | 1 U | 34,700.64 | 34,700.64 | 0 |
| CLOUDSERV BİLİŞİM … | 1 U | 16,859.98 | 16,859.98 | 0 |

Three consequences drive the design:

1. **Realized unit price ≠ list price.** 34,700.64 and 16,859.98 against a 10,430.84 list
   price — 3.3× and 1.6×. A per-customer revenue figure cannot be computed as
   `U × list price`; it would be fiction.
2. **CRM colocation buyers and NetBox rack tenants are disjoint sets.** The DC13 Dedicated
   Customers table shows Boyner, AytemizBank, A101, Moneygram, Turkonay — all five
   `UNMATCHED` to CRM. BEYAZNET and CLOUDSERV do not appear as rack tenants anywhere.
   A "billed" column would therefore be empty on every row that exists today.
3. **Both orders carry `statecode = 0`.** The existing realized-billing path in
   `services/datacenter-api/app/db/queries/crm_potential.py` (`DC_POTENTIAL_SUMMARY`)
   filters `statecode IN (3, 4)`, so these two sales are already excluded from every
   realized figure the platform computes.

The cabinet-priced products have zero rows in `salesorderdetails`.

### Free rack-U per DC

Computed via `shared.colocation.occupancy.occupancy_rows` (188 deduplicated racks — the
`(rack_name, site_name)` fan-out guard documented in that module is load-bearing).

**Reading:** every row except DC13 is the grouped reading
(`occupancy_rows(cur, dc_pattern=None)` grouped by `dc`); DC13 is corrected here to the
per-DC query path (`occupancy_rows(cur, "%DC13%")`) that the shipped Colocation tab and
Floor Map actually use — see "Capacity discrepancy — RESOLVED" below for why the two
readings disagree for DC13 (and, in the opposite direction, for DH3). Because of that same
defect, the per-DC rows below do **not** sum to the platform **Total** row, which is the
separately-deduplicated `"*"` path and is authoritative platform-wide — do not "fix" that
apparent mismatch by re-deriving it from the rows above.

| DC | Racks | Total U | Used U | Free U | Free U × list (TL) |
|---|---|---|---|---|---|
| DC13 | 57 | 2,629 | 1,169 | 1,460 | 15,229,026 |
| DC16 | 38 | 1,596 | 234 | 1,362 | 14,206,804 |
| DH3 | 30 | 1,420 | 266 | 1,154 | 12,037,189 |
| DC14 | 28 | 1,251 | 501 | 750 | 7,823,130 |
| DC11 | 12 | 564 | 201 | 363 | 3,786,395 |
| DC15 | 10 | 470 | 164 | 306 | 3,191,837 |
| DC17 | 4 | 168 | 26 | 142 | 1,481,179 |
| ICT11 | 3 | 141 | 54 | 87 | 907,483 |
| AZ11 | 2 | 96 | 31 | 65 | 678,005 |
| Vadi Ofis | 1 | 42 | 1 | 41 | 427,664 |
| ICT21 | 1 | 47 | 16 | 31 | 323,356 |
| UZ11 | 1 | 47 | 20 | 27 | 281,633 |
| DC12 | 1 | 42 | 28 | 14 | 146,032 |
| **Total** | **188** | **8,603** | **2,711** | **5,892** | **61,458,509** |

**Scale finding that shapes the DC card design:** DC13's card currently reads
"Potential Sales (Virtualization) 574.8 Bin TL – 1.91 Milyon TL". Colocation potential in
the same DC is 15.23 M TL — 8× to 26× larger. Summing colocation into the virtualization
range would make the combined figure colocation-dominated and erase every movement in the
virtualization signal. **Decision: colocation is rendered as a separate line, never summed
into the virtualization range.**

## Terminology (binding)

Two money figures exist and must never be conflated in code, labels, or tooltips:

- **Potential** — `U × unit price`. Always computable, no CRM matching required. Means
  "what this rack space would be worth at the configured price", not revenue.
- **Realized / Billed** — `discovery_crm_salesorderdetails.extendedamount` for a tenant
  matched to a CRM account. Truthful but currently empty for every rack tenant.

This release ships **Potential only**. Realized is out of scope (see Non-goals).

## Design

### 1. Price source — live, not hardcoded

A new query module reads the unit price from `discovery_crm_productpricelevels` for
productid `ee635018-5c6d-f011-b4cc-6045bd93381c`, currency `Turkish Lira`, returning the
most recently modified row. No literal `10430.84` appears anywhere in application code;
a CRM price change must propagate without a deploy.

An override hook plugs into the existing Administration → Integrations → CRM price
overrides screen (`src/pages/settings/integrations/crm_price_overrides.py`), so a
negotiated average can replace the list price without touching code. Resolution order:
admin override → live CRM price level → `None`.

When the price resolves to `None`, every potential figure renders as `—` with an
explanatory tooltip. It must never fall back to zero, which would read as "no
opportunity" rather than "price unknown".

The cabinet-priced products are deliberately excluded: they have zero realized sales and
their unit (a whole cabinet) is not what rack occupancy measures. Noted as future work.

### 2. Physical Inventory tab restructure

`src/pages/dc_view.py` currently renders `phys-inv` and `colo` as sibling top-level tabs
(lines ~5573-5580 and ~5897-5904). After this change:

```
Physical Inventory          (parent tab, value="phys-inv")
├── Overview                (sub-tab — today's build_physical_inventory_tab content)
└── Colocation              (sub-tab — today's build_colocation_tab content)
```

The top-level `Colocation` tab is removed. This follows the existing nested-tab pattern
already used by Virtualization (Klasik / Hyperconverged / Power) and Backup (Image /
Application / Replication), so no new UI mechanism is introduced.

`src/auth/permission_catalog.py` moves `sec:dc_view:colocation` under the
`sec:dc_view:phys_inv` section. Existing colocation grants must continue to resolve —
a user who today holds colocation permission but not phys_inv must not silently lose
access. Migration behaviour is specified in the implementation plan.

### 3. Colocation summary card

`src/components/colocation_summary.py` gains a fifth tile:

```
Total U | Used U | Free U | Racks | Free U Potential
2,629     1,169    1,460    57      15.23 M TL
```

The tile carries a tooltip naming the price source and unit price so the number is
traceable to CRM. The existing four-column `SimpleGrid` becomes five columns. The tile
reads `free_u` from the same aggregate the other four tiles already use, so it can never
disagree with the Free U tile beside it.

**Capacity discrepancy — RESOLVED 2026-07-27, and it changes the design.**

The apparent DC13 gap (deployed UI 2,629 / 1,460 versus 2,719 / 1,550 in this spec's first
draft) is neither a stale build nor a `u_height` patch. Root cause: **25 racks at site
ISTANBUL are registered in NetBox under two DC labels at once** — DC13+DH3 or DC13+DH4 —
with *conflicting* heights. Racks 101-105 and 201-205 carry both 47 and 52; racks 303-306
carry both 42 and 52.

`_dedupe_physical_racks` collapses each `(rack_name, site_name)` to one row, so which
capacity survives depends on which rows were in the query set:

| Reading | DC13 total U | DC13 free U | Platform total U | Platform free U |
|---|---|---|---|---|
| `occupancy_rows(cur, "%DC13%")` — what the UI calls | 2,629 | 1,460 | — | — |
| `occupancy_rows(cur, None)` grouped by `dc` | 2,719 | 1,550 | 8,603 | 5,892 |
| Sum of per-DC queries | 2,629 | 1,460 | 9,241 | 6,201 |

The third row double-counts the 25 cross-label racks. DH3 swings the opposite way from
DC13 (+728 U per-DC versus grouped), which is the same effect seen from the other side.

**Design consequence — binding.** Any per-DC potential figure MUST come from the same
per-DC query path the DC View Colocation tab uses. Deriving a per-DC split by grouping the
all-DC payload's rack rows yields 1,550 free U for DC13 on one screen while the Colocation
tab shows 1,460 on another — the same datacenter, two numbers, ~0.94 M TL apart. Two
surfaces disagreeing about one datacenter is worse than either number being imperfect.

**Underlying data defect, out of scope here:** one physical rack cannot be both 47U and
52U. The NetBox duplication needs fixing at source; until it is, every colocation capacity
figure carries that ambiguity. Recorded, not fixed by this plan.

### 4. Dedicated Customers table

`build_colocation_tab` in `src/pages/dc_view.py` gains one right-hand column:

| Customer | CRM Account | Match | Rack | Used U (own) | **Potential (TL)** |
|---|---|---|---|---|---|
| Boyner | — | UNMATCHED | 122, 123, 124 | 85 | 886,621 |
| AytemizBank | — | UNMATCHED | 112, 114 | 29 | 302,494 |

The column header carries a footnote: computed at list price, not billed revenue. This
wording is load-bearing — the measured data shows none of these tenants has a CRM
colocation contract, and the column must not imply otherwise.

The Internal Resources table gains the same column, representing the opportunity cost of
Bulutistan-occupied rack space.

### 5. DC Summary sellable

`src/pages/dc_summary_sellable.py` gains a **Physical — Colocation** entry alongside the
existing virtualization families, showing free U and its TL value. It reuses the existing
family-tile presentation rather than introducing a new layout.

### 6. DC cards and the Potential Sales KPI

`src/pages/datacenters.py` renders "Potential Sales (Virtualization)" in three places
(the card at ~line 257, and the KPI tiles at ~674 and ~1015). Each gains a sibling line:

```
Potential Sales (Virtualization)
574.8 Bin TL – 1.91 Milyon TL

Potential Sales (Colocation)
15.23 Milyon TL
```

Colocation shows a single value, not a range: free U is an exact count and the unit price
is a single figure, so no interval exists. The existing virtualization label stays
unchanged; the two lines are never added together.

### 7. Internal mapping defect

**Defect:** `shared/colocation/occupancy.py:81` classifies internal tenants from a
hardcoded tuple:

```python
INTERNAL_TENANT_PREFIXES = ("bulutistan", "bulut broker", "cpe-tenant", "dc11 arista")
```

`is_internal_tenant()` (line 162) prefix-matches against it. Meanwhile
`src/pages/settings/integrations/crm_internal_aliases.py` writes internal source mappings
to `gui_crm_customer_source_mapping` under the reserved `crm_accountid = "INTERNAL"`.
Nothing reads that table when splitting internal from external colocation. Whatever an
operator enters in Administration has no effect on the Internal Resources table.

**Fix:** `is_internal_tenant` resolves against the Administration mappings, with the four
hardcoded prefixes retained as a seed/fallback for when the table is empty or unreachable.
The resolver is injected rather than imported at module scope, so `shared/colocation`
keeps no database dependency and stays unit-testable.

Because this changes which tenants count as internal, the External/Internal/Untagged split
on the summary bar will shift. The implementation plan captures before/after counts so the
change is measured, not assumed.

## Non-goals

- **Realized/billed revenue per tenant.** Deferred until rack tenants are actually matched
  to CRM accounts. The two existing colocation orders are `statecode = 0` and belong to
  customers with no rack footprint; shipping a billed column now would ship an empty column.
- **Cabinet-priced products.** Zero sales, wrong unit.
- **Fixing the `statecode IN (3,4)` filter** in `crm_potential.py`. Recorded as a known
  inconsistency; changing it affects every realized figure platform-wide and needs its own
  scope.
- **Currency switching.** TRY only; USD/EUR price levels exist but the UI is TL throughout.

## Testing

- **Price resolution** — unit tests for override → CRM → `None` precedence, and that
  `None` renders `—` rather than 0.
- **Potential arithmetic** — `used_u × price` and `free_u × price` against fixture rows,
  including the zero-price and zero-U cases.
- **Internal classification** — `is_internal_tenant` against an injected mapping set,
  plus fallback behaviour when the mapping source is empty.
- **Tab structure** — the Colocation sub-tab renders under Physical Inventory, and the
  removed top-level tab no longer appears.
- **Permission migration** — a principal holding only the old colocation grant still
  reaches the sub-tab.
- **Rack dedup regression** — free-U totals still match the 188-rack / 5,892-free-U
  baseline measured above, guarding the `(rack_name, site_name)` fan-out.

## Open risk

The potential figures are large (61.5 M TL platform-wide) and derive from list price
applied to *all* free rack-U, including racks that may be reserved, decommissioned, or
physically unsellable. The number answers "what is unsold rack space worth at list price",
which is narrower than "what we could earn". Labels and tooltips must carry that framing.
