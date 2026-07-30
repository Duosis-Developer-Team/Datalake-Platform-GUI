# Average-Utilization Sellable Track — Design

**Date:** 2026-07-30
**Branch:** `worktree-avg-utilization-sellable`
**Reference:** [task/query-map/05-sellable-potential.md](../../../task/query-map/05-sellable-potential.md)
**Supersedes nothing.**

## Problem

Two defects reported by Can Duosis (WhatsApp, 2026-07-29):

1. The **`Sellable (Ort.)`** column on the CRM Inventory Overview report is a placeholder —
   the arithmetic mean of the allocation and max-utilization columns. There is no
   average-utilization data behind it at all.
2. As a consequence the column reads **lower** than `Sellable (Max util)`, which is
   backwards and made the screen look like it was losing money on the average basis.

The intended semantics, in Can's words:

> artık bizim üç tip hesaplama yöntemimiz olacak; allocation (fiziksel olarak ayrılan
> alan), max utilization, avg utilization — ve bunu en alttan yani max ve allocation
> nasıl hesaplanıyorsa onlar gibi yapmalıyız. host seviyesinde avg kullanımı alıp onun
> üstünden hesaplatacaksın.

His worked example: if CPU averaged 45% utilization over the period and peaked at 65%,
then 55% is sellable on the average basis versus 35% on the max basis. Therefore
**avg sellable must exceed max sellable**, always.

## Measured evidence

Everything below was read from the code at `152aa3bf` and cross-checked against the
2026-07-29 screenshots. These findings constrain the design and must not be re-derived
from assumptions.

### 1. The avg column is a literal mean of the other two

`src/components/crm_inventory_report.py:377`:

```python
"sellable_avg_fmt": shared.fmt_qty_tl_block(
    _mean(sellable_alloc_qty, sellable_max_qty),
    unit,
    _mean(potential_tl_alloc, potential_tl_max),
) if profile == "dual_track" else "—\n—",
```

`tests/test_crm_inventory_report.py:60` encodes this as intended behaviour
(`"""Sellable (Ort.) = mean of alloc and max-util, in qty and TL."""`), so it is a
deliberate placeholder, not an accidental regression.

Every cell in the screenshot reproduces exactly:

| Family / resource | Alloc | Max util | (Alloc+Max)/2 | Displayed as Ort. |
|---|---|---|---|---|
| Hyperconverged CPU | 1,237 | 5,108 | 3,172.5 | **3,173** |
| Hyperconverged RAM | 2,474 | 10,216 | 6,345 | **6,345** |
| Hyperconverged Storage | 123,722 | 510,788 | 317,255 | **317,255** |
| Klasik CPU | 482 | 1,109 | 795.5 | **795** |
| Klasik RAM | 964 | 2,217 | 1,590.5 | **1,590** |
| Klasik Storage | 48,181 | 110,862 | 79,521.5 | **79,521** |

The TL sub-rows match the same way (e.g. Hyperconverged CPU
`(124,267 + 513,035) / 2 = 318,651`).

### 2. All three resource rows share ONE unit count per track

`shared/sellable/computation.py:511-513`:

```python
n_cpu_max, _              = _accumulate("max", "max", False)
n_ram_max, host_stor_max  = _accumulate("max", "max", False)   # identical call
_, host_stor_max_shared   = _accumulate("max", "max", True)
```

`n_cpu_max` and `n_ram_max` come from the *same* call. Every resource row is that single
unit count multiplied by its ratio component. The screenshots prove it — the max/alloc
ratio is identical across all three rows of a family:

| Family | CPU | RAM | Storage |
|---|---|---|---|
| Hyperconverged | 5,108 / 1,237 = **4.129** | 10,216 / 2,474 = **4.129** | 510,788 / 123,722 = **4.129** |
| Klasik Mimari | 1,109 / 482 = **2.301** | 2,217 / 964 = **2.300** | 110,862 / 48,181 = **2.301** |

(The third decimal wobbles only because the rendered cells are rounded to whole units;
the underlying panel values share one unit count exactly.)

**Consequence:** the entire task reduces to producing a third unit count, `n_avg`. Once
that exists, all nine cells follow automatically. Storage needs no avg definition of its
own — see finding 4.

### 3. CPU has no peak source anywhere in the sellable pipeline

- `CLASSIC_HOST_ROWS` (`services/datacenter-api/app/db/queries/vmware.py:813`) is
  `SELECT DISTINCT ON (vmhost) ... ORDER BY vmhost, "timestamp" DESC` — the **latest
  instantaneous reading**, not a window peak.
- `NUTANIX_HOST_ROWS` (`nutanix.py:299`) selects
  `COALESCE(h.cpu_usage_avg, 0) AS cpu_used_hz`, again at the latest `collectiontime`.
  On Hyperconverged the "max utilization" column is literally driven by a column named
  `cpu_usage_avg`.
- The project's own documentation confirms the semantics —
  `task/query-map/README.md:119`: *"Utilization (kullanım): Kaynağın gerçekte ne kadar
  kullanıldığı (ör. `cpu_ghz_used`)"* — an instantaneous value.
- RAM, by contrast, **does** have a genuine peak: `CLASSIC_HOST_MEM_PEAK`
  (`vmware.py:831`) and `NUTANIX_HOST_MEM_PEAK` (`nutanix.py:328`), both picking the
  worst timestamp in the window.
- A `cpu_used_ghz_max` field does exist (`shared/vmware/host_cpu_ghz.py:167`) but only in
  the customer-view VM path; it never reaches the sellable pipeline.

**Consequence:** without a real CPU peak, `n_max` is not a max, so `n_avg` and `n_max`
would differ only by "latest reading vs window average" — the reported symptom would
survive the fix.

### 4. Storage has no time dimension in the sellable model

- `host_raw_headroom` storage branch (`shared/sellable/host_sellable.py:127-137`) uses
  `stor_cap_gb`, `stor_provisioned_gb`, `stor_used_pct` — all instantaneous.
- `HostSellableResult.n_units_min` vs `n_units_max`
  (`host_sellable.py:174-212`) is **exclusive vs shared datastore mounts**, not a time
  range.
- `computation.py:525-526` sums the *same* field for both tracks:

  ```python
  stor_constrained_alloc = sum(r.stor_constrained_min for r in host_stor_alloc)
  stor_constrained_max   = sum(r.stor_constrained_min for r in host_stor_max)
  ```

  The two differ only because the lists were produced with different CPU/RAM tracks.

**Consequence:** storage's own raw headroom is identical across tracks today, and will
stay identical. Its avg column falls out of the triple-min. This is also the safe
outcome commercially: storage usage grows monotonically rather than oscillating, so a
window average of storage would sit below today's occupancy and advertise space that is
already written.

## Decisions

Settled with Arca on 2026-07-30. Recorded so they are not silently revisited.

| # | Decision | Rationale |
|---|---|---|
| 1 | **Window stays 7 days.** `default_time_range()` = 6 days back + today. Not 30. | Can never specified a window; "geçtiğimiz ay %45" was an illustration of *what avg means*. Moving to 30 d changes the existing alloc and max numbers, scans ~4× the rows on `vmhost_metrics`/`cluster_metrics` (datacenter-api has an OOM history on exactly this shape), and reaches back across the 2026-07-16 collector outage. Window length is a separate decision for Can. |
| 2 | **Basis: host-level `AVG(used)` and `AVG(cap)`** over the window. | Mirrors the existing peak query shape, which takes both `used` and `cap` from the chosen timestamp. Averaging a percentage against today's capacity would diverge whenever capacity changed mid-window. |
| 3 | **CPU max becomes a real window peak.** | Finding 3. Without it the avg fix is cosmetic. Approved by Arca; Can must be told because it moves numbers already on screen. |
| 4 | **Storage gets no avg definition.** | Finding 4. |
| 5 | **All three tracks share one window.** | Otherwise a single row would mix periods. Satisfied for free by decision 1. |

## Non-goals

- A user-selectable window on CRM Inventory Overview. That page passes
  `time_range=None` (`src/pages/crm_inventory_overview.py:231,263`) and falls back to the
  7-day default. Adding a selector is a separate feature.
- Storage time-series ingestion.
- The 24 unrelated pre-existing test failures (see Baseline).
- **DC13 KM storage freshness monitoring.** This is the *other* job Can raised
  ("storage verileri (km ortamlar için) dc13'te gelmemiş"). Freshness is evaluated
  per-table (`services/hmdl-api/app/services/freshness_registry.py`), with no
  DC/cluster breakdown, so a DC-specific gap is invisible while other DCs keep the table
  fresh. Separate branch, separate design pass.

## Design

A third track named `avg`, alongside the existing `allocation` and `max` tracks, plus a
correction that gives the `max` track a genuine CPU peak.

### Layer 1 — SQL (`services/datacenter-api/app/db/queries/`)

Four new queries, each mirroring the shape of the corresponding RAM peak query so the
three tracks stay structurally comparable:

| Query | Purpose |
|---|---|
| `CLASSIC_HOST_CPU_PEAK` | per-host worst `100.0 * cpu_ghz_used / cpu_ghz_capacity` timestamp in window; returns `used`, `cap`, `pct` from that row |
| `NUTANIX_HOST_CPU_PEAK` | same over `nutanix_host_metrics` |
| `CLASSIC_HOST_AVG` | per-host `AVG(cpu_ghz_used)`, `AVG(cpu_ghz_capacity)`, `AVG(memory_used_gb)`, `AVG(memory_capacity_gb)` across the window |
| `NUTANIX_HOST_AVG` | same over `nutanix_host_metrics` |

Each also needs its `_FILTERED` cluster-scoped variant, matching the existing convention.

### Layer 2 — datacenter-api host payload (`app/services/dc_service.py`)

New fields on the host row, applied by enrichers modelled on `_apply_host_mem_peak`:

- `cpu_used_ghz_peak`, `cpu_cap_ghz_at_peak`, `cpu_peak_util_pct`
- `cpu_used_ghz_avg`, `cpu_cap_ghz_avg`, `cpu_avg_util_pct`
- `mem_used_gb_avg`, `mem_cap_gb_avg`, `mem_avg_util_pct`

Enrichers stay no-ops when the query returns nothing, exactly as `_apply_host_mem_peak`
does today, so a missing metric degrades to current behaviour rather than to zero.

### Layer 3 — `shared/sellable/`

`host_raw_headroom()` gains a third track value:

- `cpu_track="avg"` → reads `cpu_used_ghz_avg`, `cpu_avg_util_pct`
- `ram_track="avg"` → reads `mem_used_gb_avg` / `mem_cap_gb_avg` / `mem_avg_util_pct`
- `cpu_track="max"` → **changes** to read `cpu_used_ghz_peak`, falling back to
  `cpu_used_ghz` when the peak field is absent

`_normalize_cpu_track` / `_normalize_ram_track` keep mapping the legacy `peak` alias to
`max`.

The two constraint entry points use different helpers and both need the third track:

- `constrain_by_ratio_per_host_triple_dual` (`computation.py:506-513`) uses the local
  `_accumulate` closure:

  ```python
  n_cpu_avg, _             = _accumulate("avg", "avg", False)
  n_ram_avg, host_stor_avg = _accumulate("avg", "avg", False)
  ```

- `constrain_by_ratio_per_host_dual` (`computation.py:361-395`) uses
  `host_effective_units` directly:

  ```python
  n_cpu_avg = host_effective_units(hosts, ratio, cpu_track="avg", ram_track="avg", ...)
  n_ram_avg = host_effective_units(hosts, ratio, cpu_track="avg", ram_track="avg", ...)
  ```

  This second path is **not dead code** — `triple_dual` delegates to it when `hosts` is
  empty (`computation.py:466-476`), which yields an all-zero result. Two gotchas there:
  `host_effective_units` has **no CPU `max` branch at all** (any track other than
  `physical` falls into the `effective` branch reading `cpu_total`/`cpu_alloc`), and it
  reads RAM peak fields inline rather than via `host_raw_headroom`. Add explicit `max` and
  `avg` CPU branches so the two entry points agree instead of diverging silently.

`PanelResult` (`models.py`) gains `sellable_avg_util: float | None = None`, populated for
cpu / ram / storage exactly as `sellable_max_util` is.

The gate (`apply_utilization_gate`) and the threshold formula
(`apply_threshold(total, allocated, pct)`) are **unchanged**. Only the `allocated`
argument differs per track — which is the whole point of Can's model.

### Layer 4 — customer-api

- `sellable_service.py`: carry `sellable_avg_util` through panel construction,
  serialisation (`:3178`), and snapshot hydration (`:2991`).
- `inventory_overview_service.py:505`: expose the avg quantity and its TL alongside
  `max_qty`.
- Snapshot: **no migration needed.** `gui_panel_result_snapshot` stores the panel as a
  single `payload jsonb` column (`UPSERT_PANEL_RESULT_SNAPSHOT`,
  `app/db/queries/sellable.py:405`), so a new serialised key flows in without DDL.
  Hydration (`sellable_service.py:2991`) uses the
  `float(d["k"]) if d.get("k") is not None else None` pattern, which already tolerates
  payloads written before the key existed — those rows read back as `None`, and the GUI
  renders `—` rather than a wrong number.
- Power families keep the allocation-only profile — `sellable_avg_util` stays `None`
  there, mirroring how `sellable_max_util` is nulled at `:2380`.

### Layer 5 — GUI

- `src/components/crm_inventory_report.py`: `sellable_avg_fmt` reads the real
  `sellable_avg_qty` / `potential_tl_avg`. Delete the `_mean` helper — nothing else uses
  it.
- `src/utils/virt_sellable_aggregate.py`: propagate `sellable_avg_util` and null it on
  power merge, alongside the existing `sellable_max_util` handling at `:167,176`.

### Data flow

```
vmhost_metrics / nutanix_host_metrics
  └─ CLASSIC|NUTANIX_HOST_AVG, *_CPU_PEAK          (Layer 1)
      └─ host payload: *_avg, *_peak fields         (Layer 2)
          └─ host_raw_headroom(track) → _unit_limits triple-min
              └─ n_alloc / n_max / n_avg            (Layer 3)
                  └─ PanelResult.sellable_{allocation,max_util,avg_util}
                      └─ customer-api panel + snapshot   (Layer 4)
                          └─ Sellable (Alloc|Max util|Ort.)  (Layer 5)
```

## Verification criteria

1. **Ordering.** For every dual-track row: `alloc ≤ max ≤ avg`, in both quantity and TL.
2. **Ratio coupling intact.** Within a family, `max/alloc` must be equal across the CPU,
   RAM and Storage rows, and once the third track exists `avg/alloc` must be equal across
   the same three rows. Compare on the unrounded panel values, not the rendered cells —
   the displayed integers make Klasik RAM read 2.2998 against CPU's 2.3008. Assert to a
   relative tolerance (1e-6 on panel values). A real divergence means the triple-min
   chain was broken.
3. **Storage raw unchanged.** Storage's own headroom must be byte-identical across the
   three tracks; only its unit count may differ.
4. **Before/after table** for the CPU peak change, captured from a real DC and attached
   to the PR.

## Test plan (TDD)

Order matters — the first step is inverting a test that currently asserts the bug.

1. Invert `tests/test_crm_inventory_report.py::test_prepare_service_row_sellable_average`:
   avg must come from its own field, and must exceed max. Red.
2. `shared/sellable` unit tests: a host fixture with known `avg < peak` values must yield
   `n_avg > n_max > n_alloc`.
3. CPU peak regression: a fixture whose latest reading is below its window peak must
   produce a *lower* CPU max sellable than today's code does — the correction, asserted
   explicitly so it cannot silently revert.
4. Ratio-coupling test: assert criterion 2 across the three resource rows of one family.
5. Storage-invariance test: assert criterion 3.
6. Query-shape tests next to the existing ones in
   `services/datacenter-api/tests/`, following `test_compute_fast_path.py`.
7. Null-safety: a panel with no avg data renders `—`, never `0` and never a mean.

## Risks

| Risk | Mitigation |
|---|---|
| CPU peak lowers `n_max`; because all three rows share one unit count, **all three max cells drop together** whenever CPU is the binding resource. | Expected and correct. Measure it, publish the before/after table, and tell Can before he sees it. If RAM or storage binds, the column will not move at all. |
| A 7-day window that overlaps a collector gap yields an average over fewer samples. | Out of scope to fix here, but the avg enricher must no-op on empty results rather than write 0 — a zero would read as "nothing used, sell everything". |
| Existing snapshot rows have no avg column. | Nullable column; `None` renders `—`. |
| Power / allocation-only families have no second track. | `sellable_avg_util` stays `None`, matching existing `sellable_max_util` treatment. |

## Baseline

Recorded at branch creation (`152aa3bf`, clean worktree) so later failures are
attributable:

- **1,678 passed, 26 failed, 1 skipped**, plus **2 collection errors**:
  - `tests/test_backup_sidebar_helpers.py` — `KeyError: '_compute_backup_tr'` (helper
    renamed/removed; test loads it by `exec`).
  - `tests/test_zabbix_query_deduplication.py` — `ModuleNotFoundError: No module named
    'app.db'`; a service test living in the GUI root `tests/`, where `app.py` shadows the
    service `app` package. Passes when run alone.
- One failure is **in our blast radius** and will be fixed as part of this work:
  `tests/test_virt_sellable_aggregate.py::test_aggregate_virt_sellable_panels_totals`
  asserts `total_tl == 20.0` but gets `13.0`. The code
  (`virt_sellable_aggregate.py:294-295`) deliberately zeroes TL when
  `sellable_constrained <= 0`; the third fixture panel has no `sellable_constrained`.
  The **test is stale**, the behaviour is correct — a "potential never billed" guard.
- The remaining 24 failures are unrelated (dc_view visibility, floor map, LDAP, docker
  compose, network eager load) and are left untouched.

## Open items for Can

1. Window: keep 7 days, or move to 30? Moving it changes the alloc and max numbers too.
2. Awareness: the CPU max correction will move numbers currently on screen (downward
   where CPU binds).
