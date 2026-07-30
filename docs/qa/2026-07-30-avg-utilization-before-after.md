# QA Evidence — Average-Utilization Sellable Track (Task 10)

**Date:** 2026-07-30
**Branch:** `worktree-avg-utilization-sellable`
**Reported by:** Can Duosis (WhatsApp, 2026-07-29)
**Design:** [`docs/superpowers/specs/2026-07-30-avg-utilization-sellable-design.md`](../superpowers/specs/2026-07-30-avg-utilization-sellable-design.md)
**Plan / ledger:** `.superpowers/sdd/2026-07-30-avg-utilization-sellable/{plan,progress.md}`
**Interpreter:** `PY=/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python` (Python 3.11.15; the system `python3` is 3.9 and breaks on `X | Y` syntax)

This is the evidence document promised in the design spec so Can does not read the
corrected CPU max numbers as a new bug. Everything in §2–§4 (the unit-level evidence) was
re-run by me, directly against the code on this branch, on 2026-07-30 — the commands and
raw output are inline so they can be reproduced by anyone. The one item the spec commits
to but this document **cannot** supply is the production before/after measurement — see
§5, "Production measurement — BLOCKED", below. It is written as an explicit gap, not a
guess.

---

## 1. Verification criteria (from the spec)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | **Ordering.** For every dual-track row: `alloc ≤ max ≤ avg`, in both qty and TL. | **PASS (unit level)** | §2, §3 below — holds on every host-level pathology and every family-level scenario tested. Production confirmation deferred (§5). |
| 2 | **Ratio coupling intact.** `max/alloc` equal across CPU/RAM/Storage; once `avg` exists, `avg/alloc` equal across the same three rows, to 1e-6 relative tolerance on unrounded panel values. | **PASS (unit level)** | §3 — ratio spread measured at `0.000000000` across all 6 family-level scenarios. Production confirmation deferred (§5). |
| 3 | **Storage raw unchanged.** Storage's own headroom byte-identical across all three tracks; only the unit count may differ. | **PASS (unit level)** | §2.6 — `{'effective': 350.0, 'max': 350.0, 'avg': 350.0}`, plus the existing `TestStorageUnaffected` suite, re-run below. |
| 4 | **Before/after table** for the CPU peak change, captured from a real DC. | **DEFERRED — environment blocked** | §5. No live stack; not estimated. |

---

## 2. Host-level invariant evidence — `shared.sellable.host_sellable.host_raw_headroom`

Script: `host_level_check.py` (kept in scratch, reproduced inline). Run:

```
PYTHONPATH=. $PY host_level_check.py
```

Four data shapes that broke `avg >= max` before the Task 3 clamp existed, plus an idle
host, plus a direct storage-invariance check. Three of the four shapes are the exact
counterexamples recorded in the ledger (Task 3 review), reproduced here against the
**current, fixed** code:

```python
from shared.sellable.host_sellable import host_raw_headroom

def show(label, host, resource, **kw):
    mx = host_raw_headroom(host, resource=resource, cpu_track="max", ram_track="max", **kw)
    avg = host_raw_headroom(host, resource=resource, cpu_track="avg", ram_track="avg", **kw)
    print(f"{label}: max={mx:.3f} avg={avg:.3f} avg>=max: {avg >= mx}")
```

**Raw output:**

```
=== 1. RAM capacity drift (collector emitted cap=0 rows for part of window) ===
ram_capacity_drift: resource=ram max=109.600 avg=109.600 avg>=max: True

=== 2. Genuine-zero RAM average (COALESCE(AVG(...),0) with all-NULL usage) ===
genuine_zero_ram_avg: resource=ram max=109.600 avg=320.000 avg>=max: True

=== 3. Ratio-selected CPU peak (peak row picked by utilisation ratio, not raw usage) ===
ratio_selected_cpu_peak: resource=cpu max=152.000 avg=152.000 avg>=max: True

=== 4. Mid-window RAM capacity expansion (DIMM added; usage rises with the new headroom) ===
mid_window_capacity_expansion: resource=ram max=4.800 avg=4.800 avg>=max: True

=== 5. Idle host: real 0.0 CPU average must get full credit ===
idle_host: cpu max=40.000 avg=80.000 (expect avg == 80.0, full credit)

=== 6. Storage raw headroom: byte-identical across all three tracks ===
storage headroom per track: {'effective': 350.0, 'max': 350.0, 'avg': 350.0}
identical across tracks: True
```

### 2.1–2.3 Cross-check against the ledger's recorded pre-clamp numbers

The ledger (Task 3, review 1) recorded these three shapes breaking the invariant
**before** the clamp existed:

| Shape | Pre-clamp (ledger) | Current (measured above) | Held now |
|---|---|---|---|
| RAM capacity drift | max=109.600 / avg=**76.720** | max=109.600 / avg=**109.600** | clamped up — yes |
| Genuine-zero RAM average | max=109.600 / avg=**20.000** | max=109.600 / avg=**320.000** | fixed by honouring the real zero (`_first_present`), not the clamp — yes |
| Ratio-selected CPU peak | max=152.000 / avg=**106.000** | max=152.000 / avg=**152.000** | clamped up — yes |

Note on shape 2: the pre-clamp value of 20.000 came from an `or`-chain bug (a real `0.0`
average being discarded in favour of the peak-used value, 300 GB, paired against the
average capacity, 400 GB → `400*0.8-300=20`). The fix here is `_first_present` honouring
the genuine zero, which alone produces `400*0.8-0=320` — already above max, no clamp
needed. Shapes 1 and 3 genuinely need the `max(avg_calc, max_calc)` clamp to hold.

### 2.4 A fourth shape I constructed: mid-window RAM capacity expansion

The ledger's Task 3 fix-round note mentions the coordinator verified "a fourth (mid-window
DIMM expansion)" counterexample during review, but no such fixture was committed to the
test suite — the three above are the ones with a permanent regression test. I built this
one myself to exercise a distinct failure mode: a host whose RAM capacity grows mid-window
(e.g. a DIMM added), with usage climbing into the new headroom. Concretely:

- Pre-expansion (this is also the per-timestamp peak row): cap 256 GB, used 200 GB (78.1%).
- Post-expansion: cap 512 GB, used climbs to 450 GB as workload grows into the new space.
- `AVG(cap)` blends both halves → 384 GB; `AVG(used)` → 325 GB → **84.6%** average
  utilisation — which trips the 80% gate on the *blended* average even though no single
  sampled row (peak included) was ever gated on its own.

Pre-clamp, this shape's raw avg headroom is `0.0` (gated) against a max headroom of `4.8`
— a genuine inversion (`avg < max`). With the current clamp, `avg = max(0.0, 4.8) = 4.8`,
holding the invariant. This is a case where the final `avg` cell legitimately equals `max`
(see the clamped-row discussion in §6) — it is not a sign of dead data, it is the clamp
doing exactly its job on a real capacity-change artefact.

### 2.5 Existing regression suite, re-run for corroboration

```
$ $PY -m pytest tests/test_host_sellable_avg_track.py -q -k "Storage or Invariant" -v
tests/test_host_sellable_avg_track.py .....                              [100%]
5 passed in 0.04s
```

---

## 3. Family-level invariant evidence — `shared.sellable.computation.constrain_by_ratio_per_host_triple_dual`

Script: `family_level_check.py`. Same `_host()`/`_ratio()`/`_panels()` shapes as
`tests/test_sellable_avg_unit_count.py`, run directly (not just cited) so the numbers
below are mine. `ResourceRatio` takes `family` as its first field
(`ResourceRatio(family="virt_classic", cpu_per_unit=1.0, ram_gb_per_unit=2.0, storage_gb_per_unit=100.0)`).

Run:

```
PYTHONPATH=. $PY family_level_check.py
```

**Raw output** (alloc / max / avg per row, `avg>=max`, and `avg/alloc` ratio):

```
--- 1. full data ---
  cpu      alloc=4.8000 max=40.0000 avg=55.0000  avg>=max: True  avg/alloc=11.458333
  ram      alloc=9.6000 max=80.0000 avg=110.0000  avg>=max: True  avg/alloc=11.458333
  storage  alloc=480.0000 max=4000.0000 avg=5500.0000  avg>=max: True  avg/alloc=11.458333
  ratio spread (max-min) across rows: 0.000000000  equal-within-1e-6: True

--- 2. missing RAM average ---
  cpu      alloc=4.8000 max=40.0000 avg=54.8000  avg>=max: True  avg/alloc=11.416667
  ram      alloc=9.6000 max=80.0000 avg=109.6000  avg>=max: True  avg/alloc=11.416667
  storage  alloc=480.0000 max=4000.0000 avg=5480.0000  avg>=max: True  avg/alloc=11.416667
  ratio spread (max-min) across rows: 0.000000000  equal-within-1e-6: True

--- 3. missing CPU average ---
  cpu      alloc=4.8000 max=40.0000 avg=40.0000  avg>=max: True  avg/alloc=8.333333
  ram      alloc=9.6000 max=80.0000 avg=80.0000  avg>=max: True  avg/alloc=8.333333
  storage  alloc=480.0000 max=4000.0000 avg=4000.0000  avg>=max: True  avg/alloc=8.333333
  ratio spread (max-min) across rows: 0.000000000  equal-within-1e-6: True

--- 4. mixed fleet (one host without averages) ---
  cpu      alloc=9.6000 max=80.0000 avg=95.0000  avg>=max: True  avg/alloc=9.895833
  ram      alloc=19.2000 max=160.0000 avg=190.0000  avg>=max: True  avg/alloc=9.895833
  storage  alloc=960.0000 max=8000.0000 avg=9500.0000  avg>=max: True  avg/alloc=9.895833
  ratio spread (max-min) across rows: 0.000000000  equal-within-1e-6: True

--- 5. capacity drift (RAM avg capacity corrupted) ---
  cpu      alloc=4.8000 max=40.0000 avg=54.8000  avg>=max: True  avg/alloc=11.416667
  ram      alloc=9.6000 max=80.0000 avg=109.6000  avg>=max: True  avg/alloc=11.416667
  storage  alloc=480.0000 max=4000.0000 avg=5480.0000  avg>=max: True  avg/alloc=11.416667
  ratio spread (max-min) across rows: 0.000000000  equal-within-1e-6: True

--- 6. no hosts at all ---
  cpu      alloc=0.0000 max=0.0000 avg=0.0000  avg>=max: True  avg/alloc=nan
  ram      alloc=0.0000 max=0.0000 avg=0.0000  avg>=max: True  avg/alloc=nan
  storage  alloc=None max=None avg=None (both None -> consistent em-dash, not a violation)
  ratio spread (max-min) across rows: nan  equal-within-1e-6: False
```

**Reading scenario 6:** with no hosts, CPU and RAM all collapse to `0.0` (a known value —
"nothing sellable" — not a missing one), so `avg/alloc` is `0/0` and mathematically
undefined; that is expected, not a defect. Storage in the empty-hosts path falls through
to `constrain_by_ratio_per_host_dual`'s generic branch, which — pre-existing, accepted gap
per the plan's Global Constraints — leaves storage's `max_util`/`avg_util` both `None`.
Both being `None` renders an em-dash in **both** the Max and Ort. columns consistently; it
is not "a number in Max beside a missing Ort." All five other scenarios show `avg >= max`
on every row and an identical `avg/alloc` ratio across CPU/RAM/Storage to nine decimal
places (`0.000000000` spread, well inside the 1e-6 tolerance).

**Notable finding while building scenario 5:** its numbers are byte-identical to
scenario 2 (missing RAM average). That is not a bug in the script — both scenarios hit the
same fallback path (RAM avg headroom clamped to that host's RAM max headroom, 109.6), just
via two different root causes (a missing key vs. a corrupted-low average). The clamp
neutralises both identically, which is exactly the intended safety net.

---

## 4. Rendered-cell evidence — `src.components.crm_inventory_report.prepare_service_row`

Script: `gui_cell_check.py`, using the same fixture shape as `_sample_row()` in
`tests/test_crm_inventory_report.py`.

```
$ PYTHONPATH=. $PY gui_cell_check.py
=== 1. dual_track row with real avg data: avg figure above max figure ===
sellable_max_fmt: '22 vCPU\n33,000 TL'
sellable_avg_fmt: '30 vCPU\n45,000 TL'

=== 2. dual_track row with NO avg data: em-dash, never 0 ===
sellable_avg_fmt: '—'

=== 3. non-dual_track profile (allocation_only): two-line em-dash ===
sellable_avg_fmt: '—\n—'

All three assertions held.
```

- **Case 1** — a `dual_track` row with real avg data renders `30 vCPU / 45,000 TL`, above
  `22 vCPU / 33,000 TL` in Max, on both the quantity and the TL line. This is the defect
  closed at the screen.
- **Case 2** — absent avg data (`sellable_avg_qty`/`potential_tl_avg` both `None`) renders
  a single em-dash (`—`), never `0` and never a mean. `fmt_qty_tl_block`'s
  `qty_missing="—"` default fires when both qty and TL are `None`
  (`src/pages/crm_shared.py:40-41`).
- **Case 3** — a non-`dual_track` profile (`allocation_only`) always renders the two-line
  em-dash `"—\n—"` for the Ort. column regardless of what avg data is present on the row
  (`crm_inventory_report.py:363-365`: the `sellable_avg_fmt` ternary is gated on
  `profile == "dual_track"`). This matches how the Max column already behaves for
  non-dual profiles.

---

## 5. Production measurement — BLOCKED (environment)

**Status: cannot be taken.** Checked directly on this machine: the Docker daemon is
running (29.2.1) but **no containers are up**, and ports `5000`, `8000`–`8003`, and `8050`
are all closed. There is no live customer-api / datacenter-api / crm-engine / GUI stack to
read a before/after number from. Per the task constraints, this is reported as an explicit
gap — **no number has been estimated, extrapolated, or modelled** in its place.

### 5.1 What is missing

Criterion 4 (before/after table) and the production half of criteria 1–2: a real read of
the CRM Inventory Overview report, per DC, per family, per resource row, for
`Sellable (Alloc)` / `Sellable (Max util)` / `Sellable (Ort.)` in both qty and TL — plus
the clamped-row count (§6) — against live data.

### 5.2 What was already recorded as "before" (2026-07-29, pre-fix)

The design spec's "Measured evidence" section recorded these screenshot values against
the placeholder `(alloc+max)/2` formula. They are the last real numbers seen on screen
before this branch shipped and are reproduced here **only as the historical "before"
reference** — they are not a substitute for a post-fix production read:

| Family / resource | Alloc | Max util (2026-07-29, pre-CPU-fix) | Ort. (old placeholder, mean) |
|---|---|---|---|
| Hyperconverged CPU | 1,237 | 5,108 | 3,173 |
| Hyperconverged RAM | 2,474 | 10,216 | 6,345 |
| Hyperconverged Storage | 123,722 | 510,788 | 317,255 |
| Klasik CPU | 482 | 1,109 | 795 |
| Klasik RAM | 964 | 2,217 | 1,590 |
| Klasik Storage | 48,181 | 110,862 | 79,521 |

Two things will differ once a real read is taken: (a) the Ort. column will come from the
real avg track rather than the mean, and per Can's model must land **above** Max, not
below it; (b) the Max util column itself may move, because the CPU max track now reads a
real 7-day window peak instead of the latest instantaneous sample — see §7. Whether Max
actually moves depends on whether CPU is the binding resource in each family's triple-min,
which the design explicitly could not predict from code alone (design spec, "Risks"). This
is a measurement to take once the stack is up, not something to fill in now.

### 5.3 Exact steps to fill this in once the stack is up

1. **Bring up the stack** (out of scope for this document — not to be done as part of
   this task) and confirm the three services are reachable:
   `datacenter-api` (`8000:8000`), `customer-api` (`8001:8000`), `crm-engine`
   (`8070:8000`), per `docker-compose.yml`.
2. **Pick a DC with both families present.** Any DC whose CRM Inventory Overview shows
   both a Hyperconverged and a Klasik Mimari row (e.g. via
   `GET {crm-engine}/api/v1/crm/inventory-overview?dc_code=<DC>` — the GUI itself calls
   this exact endpoint via `api.get_crm_inventory_overview(dc_code)`,
   `src/services/api_client.py:2807-2820`).
3. **Read the report.** For each of the two families × three resources (CPU/RAM/Storage),
   record `sellable_alloc_qty` / `sellable_max_qty` / `sellable_avg_qty` and their
   `potential_tl_*` siblings from the JSON payload (or the rendered
   `Sellable (Alloc|Max util|Ort.)` columns on the page). Populate a table shaped like the
   one in §5.2, now with three tracks instead of the placeholder.
4. **Check the invariant on real data:** for every row, `alloc ≤ max ≤ avg` in both qty and
   TL, and `max/alloc` and `avg/alloc` equal across the family's three resource rows to
   1e-6 relative tolerance on the unrounded values (not the rounded, displayed integers —
   the design spec notes Klasik RAM's rendered ratio wobbles to 2.2998 against CPU's 2.3008
   purely from rounding).
5. **Run the clamped-row count** (§6) against the same live read.
6. **Force a recompute if the snapshot is stale:**
   `GET .../crm/inventory-overview?dc_code=<DC>&force_recompute=true` bypasses the
   `gui_panel_result_snapshot` cache (`inventory_overview_service.py`,
   `sellable_service.py:2991` hydration path) so the read reflects current data rather
   than a snapshot taken before this branch's fields existed.
7. **Attach the resulting table to the PR**, alongside this document, closing criterion 4
   and the production half of criteria 1–2.

---

## 6. Clamped-row count — cannot be computed now, method recorded for later

The avg track is floored at the max track (Task 3's `max(avg_calc, max_calc)` clamp). That
clamp *guarantees* the ordering invariant, but it can also **hide a dead average-data
pipeline**: if the average-metric queries stopped flowing entirely, every host would fall
back through `_first_present` to its peak value, every avg cell would silently collapse to
its max value, and the report would still look perfectly monotonic and healthy — while the
reported defect (Can's "Ort. should read higher than Max") would in fact still be present,
just masked rather than fixed.

**This cannot be measured now** — it requires the live payload from §5. Once the stack is
up:

- **Primary method (API-level, no DB access needed):** pull the JSON from
  `GET {crm-engine}/api/v1/crm/inventory-overview?dc_code=<DC>` for every DC, and for every
  row where `has_infra_source` is true and the profile is `dual_track`, compare
  `sellable_avg_qty` to `sellable_max_qty` (a small float tolerance, e.g. `1e-6 * max(1,
  abs(max_qty))`, to absorb floating rounding — do not compare on the rendered/rounded
  integers). Count rows where they are equal, grouped by `dc_code` and `family`.
- **Alternative (DB-level):** `gui_panel_result_snapshot.payload` (jsonb, keyed by
  `dc_code`/`family`/`clusters_csv`) carries the same `sellable_avg_util` /
  `sellable_max_util` fields per panel — inspect one row's payload shape first
  (`SELECT payload FROM gui_panel_result_snapshot LIMIT 1;`) before writing a bulk query,
  since the exact nesting is a JSON array of panels per snapshot row, not flat columns.
- **Interpretation, per the plan's own guardrail:** a handful of clamped rows is normal —
  hosts with a genuine collector gap correctly falling back to their peak. **If every
  dual-track row in a DC (or across all DCs) comes back `avg == max`, that means the
  average-data pipeline (the new `*_AVG` queries from Task 1, wired in Task 2) is not
  reaching the engine at all** — in which case the reported defect is not actually fixed,
  only masked, and this must be raised as a finding rather than shipped quietly. Name the
  affected DCs and families explicitly when this check is run.

---

## 7. Note for Can (plain language, Türkçe)

Can Bey,

**Neydi:** `Sellable (Ort.)` sütunu gerçek bir ortalama kullanım verisine dayanmıyordu;
arkada sadece `Alloc` ve `Max util` sütunlarının aritmetik ortalaması hesaplanıyordu. Bu
yüzden ekranda Ort. her zaman Max'ten düşük görünüyordu — sizin de belirttiğiniz gibi
mantığın tam tersiydi, çünkü ortalama kullanım her zaman zirve kullanımdan düşük olduğu
için satılabilir kapasite ortalama bazda daha yüksek olmalı.

**Ne değişti:** Artık host seviyesinde gerçek 7 günlük pencere içindeki ortalama CPU/RAM
kullanımı hesaplanıyor ve Ort. sütunu bu gerçek veriden geliyor — placeholder ortalama
formülü tamamen kaldırıldı. Sonuç olarak Ort. artık Max util'in üzerinde çıkıyor (alloc ≤
max ≤ ort. sırası her satırda korunuyor).

**Bir yan düzeltme de yapıldı:** Max util sütunundaki CPU değeri, daha önce yanlışlıkla o
anki (son ölçüm) değeri kullanıyordu; artık 7 günlük pencuredeki gerçek zirve (peak) değeri
kullanıyor. Bu, CPU'nun darboğaz olduğu ailelerde Max util rakamının **aşağı** doğru
hareket etmesine sebep olabilir — bu bir regresyon değil, önceden yanlış hesaplanan bir
değerin düzeltilmesi. RAM veya Storage darboğaz oluşturuyorsa sütun hiç kımıldamaz; bunu
canlı ortamda ölçüp ayrı bir tabloda paylaşacağız (şu an ortam ayakta değil, bu yüzden
gerçek "önce/sonra" rakamlarını henüz veremiyoruz — tahmini rakam da paylaşmıyoruz).

**Zaman penceresi:** 7 gün olarak kaldı, sessizce değiştirilmedi. 30 güne çekmek ayrı bir
karar — ister misiniz, konuşalım (aşağıda açık soru olarak da not ettim).

---

## 8. Open questions and flags

1. **Window: 7 vs 30 days.** Kept at 7 days per the design decision. Can's "geçtiğimiz ay
   %45" was an illustration of what "average" means, not a request to move the window.
   Moving to 30 days would also change the existing `Alloc` and `Max util` numbers already
   on screen, scans ~4× the rows on `vmhost_metrics`/`cluster_metrics` (datacenter-api has
   a prior OOM history on this exact query shape), and reaches back across the 2026-07-16
   collector outage. Open for Can/product to decide; not changed here.
2. **Awareness of the CPU max correction.** The CPU `max` track now reads a genuine 7-day
   window peak (`cpu_used_ghz_peak`) instead of the latest instantaneous sample. Where CPU
   is the binding resource in a family's triple-min, the whole family's `Max util` row
   (all three resources, since they share one unit count) will move — typically downward,
   since a window peak is ≥ a single later sample. This must be communicated to Can before
   he notices it himself; §7 above does this. Whether it actually moves in any given
   family/DC is a live-data question, deferred to §5.
3. **The "Satılabilir 0" label, once the third column exists.**
   `src/components/crm_inventory_report.py:285-292` (moved from the brief's stale
   `:299-306` after Task 8's edit) appends `\n(Satılabilir 0 — <reason>)` to a service
   label whenever the **allocation** quantity is `≤ 0`, regardless of what Max or Ort. show.
   Because `alloc ≤ max ≤ avg`, a row can now legitimately show that "Satılabilir 0" hint
   next to a *positive* Max **and** a positive Ort. figure — e.g. a ratio-bound family
   where CPU allocation heads to zero but RAM/Storage still carry sellable headroom on the
   max/avg tracks. This behaviour is pre-existing (it already applied against the Max
   column) and this branch does not change the logic, per the brief's explicit
   instruction. It becomes more visible now that there are two non-zero columns instead of
   one. **I cannot enumerate which real rows hit this** without the production read in §5
   — add "list any (dc, family, resource) rows where the alloc-zero hint co-occurs with
   positive Max/Ort. values" to the checklist in §5.3. **Question for the product owner:**
   should the label's wording change now that a family can be "zero on Alloc" while
   legitimately double-digit-positive on Max and Ort. (e.g. clarify it means "nothing
   sellable at today's committed allocation," not "nothing sellable at all")?
4. **Clamped-row count, once measured (§6).** A handful of `avg == max` rows is a normal,
   healthy signature of collector gaps falling back correctly. **All of them, in a DC or
   across the fleet, is a red flag that the average-data pipeline isn't flowing** — the
   defect would be masked, not fixed, and must be raised rather than shipped quietly.

---

## 9. Deferred minor findings (for final-review triage)

Carried forward from the ledger (`progress.md`), none touched in this branch:

| # | Task | Finding | Disposition |
|---|---|---|---|
| 1 | 1 | `NUTANIX_HOST_MEM_PEAK` (`nutanix.py:348-356`) orders by absolute `used_bytes DESC` first, whereas `CLASSIC_HOST_MEM_PEAK` orders by utilisation ratio first — the RAM "max" track can pick the wrong per-host timestamp when memory capacity changed mid-window. Low impact (capacity is usually constant per host, so both orderings usually agree). | Deferred, pre-existing, untouched by this branch. |
| 2 | 3 | The util-discrimination test sets peak util == avg util (95/95 in the fixture), so it proves util is load-bearing but would not catch a regression that wired util from the wrong track. | Deferred — test-quality gap, follow-up test recommended (differing peak/avg util values). |
| 3 | 3 | The `max(avg_calc, max_calc)` clamp can mask a dead avg pipeline — see §6, now mitigated by this document's clamped-row-count requirement. | Mitigated by this task; not a code gap. |
| 4 | 5 | Storage panels in the `constrain_by_ratio_per_host_dual` generic branch get neither `max_util` nor `avg_util` (both stay `None`) — pre-existing (the `max_util` gap predates this branch), renders a consistent em-dash in both columns. | Accepted gap, recorded in the plan's Global Constraints, not fixed. |
| 5 | 5 | `test_genuine_zero_cpu_average_is_honoured` does not discriminate — its fixture yields identical results against the pre-fix code, so it would still pass if the fix were reverted. | Deferred — test-quality gap only. |
| 6 | 6 | `_normalize_host_unit`'s `conv` parameters are annotated `dict | None` but the actual values are `UnitConversion` instances. Quoted forward refs, no runtime effect, no type checker wired into CI. | Cosmetic, deferred. |
| 7 | 6 | `test_cpu_avg_and_peak_pass_through_unconverted` passes `cpu_conv=None`, and `convert_unit(x, None)` is the identity function — so the test would not catch a regression that added an explicit `convert_unit(..., cpu_conv)` call for the CPU avg/peak fields. Only bites once a CPU panel's display unit differs from GHz. | Deferred — test-quality gap. |
| 8 | 7 | `sellable_service.py`'s `_panel_summary_dict` (~line 3217) carries `potential_tl_max` with no `potential_tl_avg` sibling. Feeds the `compute_summary` / `DashboardSummary` rollup endpoint, **not** the by-track capacity report this branch targets — no task in the plan extends that endpoint. | Deferred — different consumer, note for whoever wires avg into the summary path later. |

---

## Appendix: exact commands run for this document

```bash
# Host-level (shared/sellable/host_sellable.py)
PYTHONPATH=. $PY host_level_check.py

# Family-level (shared/sellable/computation.py)
PYTHONPATH=. $PY family_level_check.py

# GUI cell rendering (src/components/crm_inventory_report.py)
PYTHONPATH=. $PY gui_cell_check.py

# Changed/added test files on this branch (git diff --stat 152aa3bf..HEAD -- tests/ services/*/tests/)
$PY -m pytest -q \
  tests/test_crm_inventory_report.py \
  tests/test_host_sellable_avg_track.py \
  tests/test_sellable_avg_unit_count.py \
  tests/test_sellable_models_avg_field.py \
  tests/test_virt_sellable_aggregate.py
# -> 72 passed

cd services/customer-api && PYTHONPATH=.:../.. $PY -m pytest -q \
  tests/test_host_units_avg_fields.py tests/test_sellable_avg_api_contract.py
# -> 13 passed
cd services/customer-api && PYTHONPATH=.:../.. $PY -m pytest -q
# -> 554 passed, 1 failed (pre-existing: test_sellable_service.py::
#    test_recompute_family_constraints_global_host_fallback_uses_star_compute)

cd services/datacenter-api && PYTHONPATH=.:../.. $PY -m pytest -q \
  tests/test_host_avg_enrichment.py tests/test_host_avg_peak_queries.py
# -> 20 passed
cd services/datacenter-api && PYTHONPATH=.:../.. $PY -m pytest -q
# -> 300 passed, 2 failed (pre-existing: test_dc_service_host_rows_slice.py::
#    test_classic_host_rows_single_sql_for_cluster_subsets,
#    test_host_rows.py::test_datastore_metrics_excludes_backup_datastores),
#    29 skipped

# Repo-root whole suite (see §"Whole-suite hang" for the workaround)
$PY -m pytest tests/ -q \
  --ignore=tests/test_backup_sidebar_helpers.py \
  --ignore=tests/test_zabbix_query_deduplication.py \
  --ignore=tests/test_dc_summary_arch_usage.py
# -> 25 failed, 1712 passed, 1 skipped   <- matches the expected baseline exactly
```

### Whole-suite hang — pre-existing, unrelated, not fixed

The literal command from the plan
(`$PY -m pytest tests/ -q --ignore=tests/test_backup_sidebar_helpers.py
--ignore=tests/test_zabbix_query_deduplication.py`, no third ignore) hangs on this
machine. Root cause (documented in the ledger since Task 8, independently confirmed here):
`tests/test_dc_summary_arch_usage.py` constructs an **un-mocked** `DatabaseService()`,
which reads `DB_HOST`/`DB_PASS` from `.env` (loaded via `load_dotenv()` at import time,
`src/auth/config.py`) and tries to open a real `psycopg2` connection pool — a call that
never returns quickly in this sandboxed environment.

Two ways I confirmed this, neither committed anywhere:

1. **Additionally ignore the one file** (`--ignore=tests/test_dc_summary_arch_usage.py`,
   used for the number reported above) — clean, no side effects: **25 failed, 1712
   passed, 1 skipped**, exactly the "26 baseline minus the one fixed in Task 9" the plan
   predicts, with **no new failures** — the 25 failing test names are unchanged from the
   documented baseline.
2. **`env DB_HOST= DB_PASS=` override** (matching what Task 8's implementer used) — also
   avoids the hang (`test_dc_summary_arch_usage.py` alone: `1 passed in 0.05s`), but
   running the *whole* suite this way gives **26 failed**, one more than expected. The
   extra failure is `test_db_service.py::TestGetCustomerList::test_returns_list`, which
   patches `psycopg2.pool.ThreadedConnectionPool` and expects `DatabaseService()._pool` to
   be that mock; forcing `DB_HOST=""` makes `_init_pool()` return before ever calling
   `ThreadedConnectionPool`, so `_pool` stays `None` and the test's own
   `svc._pool.getconn.side_effect = ...` line raises `AttributeError`. This is an artefact
   of *my* environment override, not a branch regression — confirmed by the fact that
   approach 1 (which doesn't touch `DB_HOST` at all) does not reproduce it.

Neither workaround was committed; both were used only to obtain a whole-suite number on
this machine. The correct, uncontaminated number is **25 failed, 1712 passed, 1 skipped**
from approach 1.
