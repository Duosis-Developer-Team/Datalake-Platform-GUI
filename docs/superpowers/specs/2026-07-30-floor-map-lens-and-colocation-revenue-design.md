# Floor Map lens switch (Colocation / Load) + rack-level CRM allocation & revenue — design

**Task:** TASK-63 "Globe View Görselleştirmeleri" — *Globe View revize edilecek, datacenter
view'da olduğu gibi (rack bazlı) crm eşleştirmeleri ve kazançlar görselleştirilecek. UI ve UX
modernize edilecek, konsepte uygun olacak.*

**Date:** 2026-07-30
**Related:** [[ADR-0028-colocation-allocation-model]], [[ADR-0027-data-freshness-health-framework]],
[[Colocation-Allocation-And-Revenue]]

---

## 1. What already exists (measured, not assumed)

TASK-63 reads as greenfield but three prior waves already shipped most of the colocation
substrate. This design builds on them rather than re-deriving them.

| Shipped | Where | Commit |
|---|---|---|
| Colocation matching service, `/api/v1/crm/colocation/{dc}`, rack occupancy | customer-api / datacenter-api | `d4fec95f` (TASK-62) |
| Globe DC info card colocation ring (`Colocation`, free-U) | `global_view.py:1225` | `ae64f015` |
| `build_colocation_summary` — tiles + External/Internal/Untagged stacked bar | `src/components/colocation_summary.py` | `d71bd7e2` |
| Floor map colocation rack colouring + full-width summary strip | `floor_map.py` | `034f12dc`, `d0de2987` |
| Allocation model (rack role → customer) replacing tenancy | `shared/colocation/allocation.py` | `a8a03164` |
| Per-U price + `Potential (TL)` columns | DC View Colocation sub-tab | `d8049c3d`, `c77441b2` |

Everything above is on `main` and pushed (`152aa3bf`).

**The Globe View drill-down is `globe → building → floor_map`** (`app.py:1740`,
`advance_to_floor_map`). The floor map is Globe View's deepest level, so rack-level work
belongs there — not in the `build_3d_rack_overlay` hologram, which draws decorative
micro-cards (name / U / power / status) with no customer or money data.

### The actual gaps

1. **Floor map right panel is empty until a rack is clicked** — roughly half the viewport
   renders "Click a rack to inspect" and nothing else. The colocation customer/revenue
   tables exist only in DC View, one navigation away.
2. **No rack ↔ customer visual link.** `allocation[].racks` already carries the rack-name
   list per customer; nothing consumes it.
3. **"Health" on the globe is unreadable and misnamed** — see §2.
4. **Turkish strings survive the English relabel** (`ecf609d6`): floor map legend, floor map
   hover template, `"Dedike:"` rack-detail badge, globe `"{n}U boş"`.
5. **Dead code:** `_create_map_figure` (`global_view.py:312-505`, ~190 lines) is never
   called — a leftover of the MapLibre migration (`3eb55fe8`). It contains
   `random.randint(8, 180)` feeding a **fabricated "Ping: N ms · Active Route"** hover row.
6. **Stale test:** `tests/test_floor_map_legend.py::test_legend_uses_fill_based_labels`
   asserts the label `"Boş / Kapalı"`, renamed in `034f12dc`. Failing on `main` today.

---

## 2. Decision: "Health" becomes "Load"

Today's globe "health" is one formula copied to four sites (`global_view.py` 261, 523, 630,
1143):

```
health = (CPU% + RAM%) / 2      # ≥70 red, ≥40 orange, else green
```

That is a **load average**, not health. It says nothing about whether anything is down.
Two problems follow:

- **It is invisible.** The globe has no legend, so the pin colour is unexplained. The only
  place the number surfaces is the MapLibre hover popup, where it is labelled **"Avg Load"**
  — a different name from the `"{x}% Health"` badge showing the same number
  (`global_view.py:665`, `:1198`).
- **The word is taken.** [[ADR-0027-data-freshness-health-framework]] makes "health" mean
  data freshness + automation health platform-wide, surfaced on its own page and sidebar
  badge. Availability/SLA owns outages. A third "health" on the floor map would make one
  word mean three things.

**Decision:** keep the number, fix the name. Everywhere on Globe View and Floor Map this
quantity is called **Load**. No new metric is invented; the existing formula is renamed and
pushed down to rack level.

**Rejected:** building a composite hardware-health score (worst-of across CPU/RAM, ICMP
loss, storage `health_status`). It is a genuinely new product concept that overlaps two
existing surfaces, and it cannot be defined honestly without measuring per-class coverage
first. Out of scope — recorded in §8 as a follow-up.

---

## 3. Decision: Floor map gains a lens switch

A `dmc.SegmentedControl` above the canvas with two values:

| Lens | Question it answers | Rack colour source |
|---|---|---|
| **Colocation** (default) | *Can I sell space here?* — U occupancy | existing `_color_by_fill` |
| **Load** | *Can I place workload here?* — CPU/RAM | new `_color_by_load` |

Same racks, same layout, same click targets. Only the colour mapping and the legend change.
The two lenses answer genuinely different questions about the same rack: a rack can be
physically half-empty while its hosts are saturated, or full of idle hardware. Neither is
visible today.

### Colour scales

Both lenses share the three-step 50/80 thresholds already used by `_color_by_fill`, so a
colour learned in one lens reads the same way in the other. They differ only in their
extra states, and each lens ships its own legend.

**Colocation lens** (unchanged, labels translated):

| Key | Colour | Label |
|---|---|---|
| `empty` | `#06AED4` turquoise | Fully free (sellable) |
| `green` | `#17B26A` | Space available |
| `orange` | `#F79009` | Moderate |
| `red` | `#F04438` | Nearly full |
| `closed` | `#475467` | Closed / inactive |
| `unknown` | `#F2F4F7` | Unknown |

**Load lens** (new):

| Key | Colour | Label | Rule |
|---|---|---|---|
| `green` | `#17B26A` | Light load | `load_pct < 50` |
| `orange` | `#F79009` | Moderate load | `50 ≤ load_pct ≤ 80` |
| `red` | `#F04438` | Heavy load | `load_pct > 80` |
| `closed` | `#475467` | Closed / inactive | rack status ∈ {inactive, planned, closed} |
| `unmonitored` | `#F2F4F7` | Not monitored | no device in this rack has metrics |

There is deliberately **no turquoise "idle" step** in the Load lens. A 0% reading is far
more often "collector is not reporting" than "hardware is idle", and rendering that as a
prime-capacity colour would invent good news. Racks with no matched metrics render
`unmonitored`, never `0%` — the same rule ADR-0028 applies to an unresolved price
(em dash, never `0`).

---

## 4. Decision: where Load data comes from

Rack load does not exist today. `get_rack_devices` (`dc_service.py:7800`) returns NetBox
inventory columns only — name, position, role, type, manufacturer, u_height — and nothing
joins it to metrics. The metrics themselves do exist:

| Device class | Metric table | Utilisation columns | Join to NetBox |
|---|---|---|---|
| VMware host | `vmhost_metrics` | `cpu_ghz_used / cpu_ghz_capacity`, `memory_used_gb / memory_capacity_gb` | by name: `vmhost` ↔ `device.name` |
| Nutanix host | `nutanix_host_metrics` | `cpu_usage_avg / total_cpu_capacity`, `memory_usage_avg / total_memory_capacity` | by name: `host_name` ↔ `device.name` |
| IBM Power | `ibm_server_general` | `server_processor_utilizedprocunits / server_processor_totalprocunits`, `(totalmem − availablemem) / totalmem` | by name: `server_details_servername` ↔ `device.name` |

Name matching is not a new risk here: `shared/vmware/host_cpu_ghz.py::resolve_host_ghz`
already matches `vmhost` to NetBox `device.name` in production and falls back cleanly when
it misses. This design uses the same key, **case-insensitively** (`lower(name)`), matching
the `lower(name)` join idiom in `shared/licensing/os_sql.py`.

### Per-rack aggregation

```
device_load_pct = max(cpu_pct, ram_pct)          # per matched device
rack_load_pct   = max(device_load_pct)           # worst monitored device in the rack
```

**MAX, not average.** A rack holding one saturated host among twenty idle ones is a rack you
cannot place work in; an average hides exactly the condition the lens exists to surface.

### New endpoint

`GET /api/v1/datacenters/{dc_code}/racks/load` → same shape family as
`/racks/occupancy`:

```json
{
  "racks": [
    {"rack_name": "104", "load_pct": 73.2, "cpu_pct": 73.2, "ram_pct": 61.0,
     "monitored_devices": 4, "total_devices": 11, "hottest_device": "esx-13-04"}
  ],
  "summary": {"monitored_racks": 38, "total_racks": 214}
}
```

Racks with `monitored_devices == 0` are returned with `load_pct: null` — present in the
payload so the UI can distinguish "no metrics" from "rack absent".

**DC scoping:** the rack set comes from the same canonical per-DC rack query the floor map
and occupancy endpoint already use, then devices are filtered by
`rack_name = ANY(%s::text[])`. A second, independently-derived DC-scoping rule is exactly
the trap [[ADR-0028-colocation-allocation-model]] §6 documents — two screens disagreeing
about one datacenter. The load payload covers exactly the racks the floor map draws.

**Caching:** 6h singleflight, matching `get_dc_racks_occupancy` — rack membership changes on
operator timescales. Note this makes the Load figure a *recent snapshot*, not live: the
lens answers "is this rack generally hot", not "is it hot right now".

---

## 5. Decision: the right panel earns its space

The `span=4` column currently holds a single empty state until a rack is clicked. It becomes
a two-state panel:

**Default (no rack selected) — Colocation customers.** Fed by `api.get_colocation(dc_id)`,
the same payload DC View's Colocation sub-tab renders:

- **Dedicated Customers** — Customer · Racks · Allocated U · Potential (TL) — Allocated · Used U
- **Internal Resources** — Resource · Rack · Used U · Potential (TL) — Used

Column semantics, header wording, the `UNATTRIBUTED` tooltip and the *potential, never
billed* framing are taken verbatim from `dc_view.build_colocation_tab` — two screens showing
the same numbers under different labels is the failure ADR-0028 §4 was written to prevent.

**Rack selected** — today's rack detail panel, unchanged apart from string translation, plus
a back affordance returning to the customer list.

### Rack ↔ customer highlighting

`allocation[].racks` already carries each customer's rack-name list. Clicking a customer row
highlights those racks on the map (bright outline, others dimmed) and clicking again clears
it. This is the literal reading of the task's *"rack bazlı crm eşleştirmeleri"* — and it
needs no new backend data.

Highlighting is a **third rendering state layered over whichever lens is active**, not a
fourth lens: the colours keep their meaning, the selected racks gain an outline.

---

## 6. Decision: Globe View alignment

Scoped tightly — the task's rack-level substance lives on the floor map, and the globe's job
is to stay consistent with it.

1. `"{x}% Health"` badges → `"{x}% Load"` (`global_view.py:665`, `:1198`), matching the
   popup's existing "Avg Load" wording.
2. `f"{coloc_free}U boş"` → `f"{coloc_free}U free"` (`:1229`).
3. Delete `_create_map_figure` and `_health_colors` (dead since `3eb55fe8`), removing the
   fabricated ping generator with them.
4. `_build_globe_data`'s `health` key → `load`, with `DashGlobe.react.js` reading the new key.

**Not in scope:** re-colouring globe pins by colocation occupancy, or a globe-level lens
switch. The pins carry `coloc_*` fields already; adding a second unexplained colour meaning
to an unlegended map makes it worse, not better. Revisit once the floor map lens has
established the colour language.

---

## 7. Non-goals

- **Realized (billed) colocation revenue.** ADR-0028: the datalake holds only `PRJ-` project
  orders; recurring-service invoices never arrive, so every TL figure stays *potential at
  list price*. Shipping a "billed" column would ship an empty column.
- **Composite hardware-health scoring** (ICMP loss, storage `health_status`) — §2.
- **Reworking `build_3d_rack_overlay`.** The hologram stays decorative; the floor map is
  where rack truth lives.
- **RBAC changes.** `sec:dc_view:colocation` remains the sole gate for colocation data, and
  the floor map panel honours it. ADR-0028 records that adding sub-node permissions
  *widened* access because permissions inherit downward — that mistake is not repeated.

---

## 8. Known risks and follow-ups

- **Load coverage is unmeasured.** Docker is down in this environment, so the NetBox
  `device.name` ↔ `vmhost` / `host_name` / `server_details_servername` hit rate could not be
  counted. If coverage is low the Load lens renders mostly `unmonitored` — honest, but thin.
  **First action when the stack is up: count matched vs total rack devices per DC and record
  it in the KB.** The design degrades correctly either way; only its usefulness is at stake.
- **Customer colocation hardware has no metrics at all** and never will — Bulutistan does not
  monitor customer-owned equipment. Those racks are permanently `unmonitored` in the Load
  lens. This is correct, and worth stating in the legend tooltip.
- **Every capacity figure inherits the NetBox duplicate-rack ambiguity** (ADR-0028 §6, 25
  ISTANBUL racks under two DC labels). Unchanged by this work.
- Follow-up: composite hardware health as a distinct, named concept, if the business wants
  one.

---

## 9. Test strategy

Pure functions first — `_color_by_load`, the per-rack MAX aggregation, and the load-row
parser are all unit-testable with no DB.

- **Aggregation:** MAX-not-average is pinned by a fixture with one hot host among cold ones.
- **Unmonitored:** a rack with devices but zero metric matches returns `load_pct: null` and
  renders `unmonitored` — asserted explicitly, because the tempting bug is `0`.
- **Closed-before-load:** a closed rack renders `closed` even with a hot host, mirroring
  `_color_by_fill`'s closed-before-empty ordering.
- **Lens switch:** the legend swaps labels and the figure's rack colours change.
- **Panel parity:** the floor map customer table renders the same column headers and basis
  wording as `dc_view.build_colocation_tab`, so the two screens cannot drift.
- **Highlight:** selecting a customer marks exactly that customer's `racks` list.
- **Regression:** `tests/test_floor_map_legend.py` is repaired to the shipped labels.

Baseline on this worktree: **1678 passed, 25 pre-existing failures, 2 pre-existing collection
errors** — all reproduced identically on `main`, none in colocation or floor-map code except
the stale legend test above.
