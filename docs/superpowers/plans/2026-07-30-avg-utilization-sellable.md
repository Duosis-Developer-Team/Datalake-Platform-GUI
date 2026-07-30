# Average-Utilization Sellable Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fake `Sellable (Ort.)` column — currently the arithmetic mean of the allocation and max-utilization columns — with a real third sellable track computed from host-level average utilization, and give the max track a genuine CPU window peak so the three tracks are actually distinct.

**Architecture:** The sellable engine already computes one *unit count* per "track" and multiplies it by the family's resource ratio to produce the CPU / RAM / Storage rows. Adding a third track therefore means producing one more unit count, `n_avg`, from new host-level `AVG(used)`/`AVG(cap)` SQL — everything downstream follows. Storage needs no average of its own: it has no time dimension in this model and inherits its avg cell through the triple-min. Separately, `cpu_track="max"` is corrected to read a real per-host peak instead of the latest snapshot.

**Tech Stack:** Python 3.11, psycopg2 (raw SQL, `%s` placeholders), FastAPI (datacenter-api, customer-api), Dash/Plotly (GUI), pytest.

**Design spec:** [docs/superpowers/specs/2026-07-30-avg-utilization-sellable-design.md](../specs/2026-07-30-avg-utilization-sellable-design.md) — read the "Measured evidence" section before starting; it records why storage is excluded and why CPU needs a peak.

## Global Constraints

- **Run Python via the main checkout's interpreter.** Worktrees have no own `.venv`:
  `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python`. Python 3.11 is required; the system `python3` is 3.9 and fails on `X | Y` type syntax. Every `pytest` command below assumes this interpreter. Export it once per shell:
  `PY=/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python`
- **Service tests need `PYTHONPATH` set; the bare `cd services/<svc> && pytest` form does not work here.** Service modules import both `app.*` (the service directory) and `shared.*` (the repo root), and this repo has no `pytest.ini`, `conftest.py`, or `pyproject.toml` supplying either. CI gets away with `cd services/datacenter-api && pytest tests/` because its environment differs. Locally, always use:
  `cd services/<svc> && PYTHONPATH=.:../.. $PY -m pytest tests/... -q`
  This is pre-existing and affects untouched tests too — verified by running `tests/test_compute_fast_path.py`, which fails identically without it. Do not "fix" it by editing tracked files. GUI-root tests (`tests/...`) need no `PYTHONPATH` and run from the worktree root.
- **Time window is unchanged: 7 days.** `default_time_range()` returns `end = today`, `start = today - 6 days`. Do not introduce a 30-day window, a new window parameter, or a window selector.
- **Storage gets no average of its own.** Never add an avg branch to the storage arm of `host_raw_headroom`. Storage's avg cell must come only from the triple-min unit count.
- **The threshold formula is untouched.** `apply_threshold(total, allocated, pct)` and `apply_utilization_gate(...)` keep their current bodies. Only the `allocated` argument differs per track.
- **Each resource's `avg` branch mirrors that same resource's `max` branch.** CPU max uses the *current* capacity as its denominator, so CPU avg does too. RAM max uses capacity-at-peak, so RAM avg uses average capacity. Do not "harmonize" the two resources — that would change existing max numbers beyond the intended CPU fix.
- **Missing average data must never become `0` — but "no hosts at all" must.** These are two different situations and the plan requires opposite answers:
  - *A host exists but its average metric is absent.* Never write `0`: a zero used-value reads as "this machine is idle, sell all of it". The enricher no-ops (Task 2), and `host_raw_headroom`'s `avg` arm returns `0.0` **headroom** for that host (Task 3) — claiming nothing rather than everything. At the panel level `sellable_avg_util` stays `None` when no track was computed at all, so the GUI renders `—`.
  - *There are no host rows whatsoever.* Then `sellable_avg_util` is `0.0`, not `None` (Task 5's empty-hosts fallback). "No hosts" is a known answer — nothing is sellable — not missing data, and `—` would wrongly suggest the figure is unavailable.
- **The SQL tests in Task 1 assert query shape, deliberately.** There is no test database in this repo, so a round-trip test is not available. The risk being guarded is a malformed query — averaging the wrong column, keeping a `DISTINCT ON` that defeats the average, a placeholder-count mismatch against the parameter tuple. Shape assertions catch exactly those. Do not rewrite them as mocked-cursor tests, and do not treat them as vacuous.
- **Naming, exactly as written:** field `sellable_avg_util` (PanelResult, serialized payload), host payload fields `cpu_used_ghz_avg` / `cpu_cap_ghz_avg` / `cpu_avg_util_pct` / `cpu_used_ghz_peak` / `cpu_cap_ghz_at_peak` / `cpu_peak_util_pct` / `mem_used_gb_avg` / `mem_cap_gb_avg` / `mem_avg_util_pct`, API fields `sellable_avg_qty` / `potential_tl_avg`, track literal `"avg"`.
- **No DB migration.** `gui_panel_result_snapshot` stores a single `payload jsonb`; new keys need no DDL.
- **Commit after every task.** Do not batch commits across tasks.

## Baseline (recorded at `152aa3bf`)

`1678 passed, 26 failed, 1 skipped`, plus 2 collection errors. Reproduce the baseline with:

```bash
$PY -m pytest tests/ -q --ignore=tests/test_backup_sidebar_helpers.py --ignore=tests/test_zabbix_query_deduplication.py
```

The two ignored files are pre-existing collection failures (`KeyError: '_compute_backup_tr'`; `ModuleNotFoundError: No module named 'app.db'`) that abort the whole run. **Do not fix them — out of scope.** Of the 26 failures, exactly one is in scope and is repaired in Task 9. The other 25 must still fail at the end, unchanged. If a *new* test starts failing, it is yours.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `services/datacenter-api/app/db/queries/vmware.py` | Classic KM per-host CPU peak + CPU/RAM average SQL | 1 |
| `services/datacenter-api/app/db/queries/nutanix.py` | Hyperconverged per-host CPU peak + CPU/RAM average SQL | 1 |
| `services/datacenter-api/app/services/dc_service.py` | Run the new queries, index by short hostname, enrich host payloads | 2 |
| `shared/sellable/host_sellable.py` | `host_raw_headroom` gains the `avg` track; CPU `max` reads the peak field | 3 |
| `shared/sellable/computation.py` | `host_effective_units` CPU `max`/`avg` branches; `n_avg` in both constraint entry points | 4, 5 |
| `shared/sellable/models.py` | `PanelResult.sellable_avg_util` | 4 |
| `services/customer-api/app/services/sellable_service.py` | Carry avg fields into `host_units`; serialize; hydrate; null on power families | 6, 7 |
| `services/customer-api/app/services/inventory_overview_service.py` | Expose `sellable_avg_qty` / `potential_tl_avg` | 7 |
| `src/utils/virt_sellable_aggregate.py` | Propagate/​null `sellable_avg_util` on power merge | 8 |
| `src/components/crm_inventory_report.py` | Read the real field; delete `_mean` | 8 |
| `tests/test_virt_sellable_aggregate.py` | Repair the one in-scope stale baseline test | 9 |

Tasks 1→8 are strictly ordered: each layer consumes the field names the previous one produces. Task 9 is independent and may run any time.

---

### Task 1: Per-host CPU peak and average SQL

**Files:**
- Modify: `services/datacenter-api/app/db/queries/vmware.py` (append after `CLASSIC_HOST_MEM_PEAK`, which ends at line 851)
- Modify: `services/datacenter-api/app/db/queries/nutanix.py` (append after `NUTANIX_HOST_MEM_PEAK`, which ends at line 356)
- Test: `services/datacenter-api/tests/test_host_avg_peak_queries.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: four SQL constants — `vmware.CLASSIC_HOST_CPU_PEAK`, `vmware.CLASSIC_HOST_AVG`, `nutanix.NUTANIX_HOST_CPU_PEAK`, `nutanix.NUTANIX_HOST_AVG`. Classic queries take params `(dc_pattern, cluster_filter[], cluster_filter[], start_ts, end_ts)`. Nutanix queries take params `(dc_code, cluster_filter[], cluster_filter[], start_ts, end_ts)`. `*_CPU_PEAK` returns rows of `(host_name, used, cap, util_pct)`. `*_AVG` returns rows of `(host_name, cpu_used_avg, cpu_cap_avg, cpu_util_pct_avg, mem_used_avg, mem_cap_avg, mem_util_pct_avg)`. Classic returns GHz and GB; Nutanix converts Hz→GHz and bytes→GB in SQL.

These deliberately mirror the existing `*_MEM_PEAK` queries so the three tracks stay structurally comparable. Note the cluster-filter idiom `(cardinality(%s::text[]) = 0 OR cluster = ANY(%s::text[]))` — the array param is passed twice, which is why there are two `cluster_filter[]` params.

- [ ] **Step 1: Write the failing test**

Create `services/datacenter-api/tests/test_host_avg_peak_queries.py`:

```python
"""Shape tests for per-host CPU peak / CPU+RAM average queries.

These are string-shape assertions, not DB round-trips: the repo has no test
database, and the risk being guarded is a malformed query shape (wrong
placeholder count, averaging the wrong column, forgetting the cluster filter).
"""
from app.db.queries import nutanix as nq
from app.db.queries import vmware as vq


class TestClassicHostCpuPeak:
    def test_picks_worst_timestamp_per_host(self):
        sql = vq.CLASSIC_HOST_CPU_PEAK
        assert "DISTINCT ON (vmhost)" in sql
        # Peak = highest utilisation ratio, not merely the highest absolute GHz.
        assert "ORDER BY vmhost, (used_ghz / NULLIF(cap_ghz, 0)) DESC" in sql
        assert "public.vmhost_metrics" in sql

    def test_has_five_placeholders_matching_mem_peak(self):
        assert vq.CLASSIC_HOST_CPU_PEAK.count("%s") == vq.CLASSIC_HOST_MEM_PEAK.count("%s")

    def test_scoped_to_km_clusters_with_optional_filter(self):
        sql = vq.CLASSIC_HOST_CPU_PEAK
        assert "cluster ILIKE '%%KM%%'" in sql
        assert "cardinality(%s::text[]) = 0 OR cluster = ANY(%s::text[])" in sql


class TestClassicHostAvg:
    def test_averages_across_window_not_latest_snapshot(self):
        sql = vq.CLASSIC_HOST_AVG
        # The guard is against picking ONE row per host, which would defeat the
        # average. A DISTINCT ON inside a cluster-identity CTE is fine (and is
        # what the Nutanix variants do), so assert on the per-host key only.
        assert "DISTINCT ON (vmhost)" not in sql
        assert "AVG(cpu_ghz_used)" in sql
        assert "AVG(cpu_ghz_capacity)" in sql
        assert "AVG(memory_used_gb)" in sql
        assert "AVG(memory_capacity_gb)" in sql
        assert "GROUP BY vmhost" in sql

    def test_placeholder_count_matches_mem_peak(self):
        assert vq.CLASSIC_HOST_AVG.count("%s") == vq.CLASSIC_HOST_MEM_PEAK.count("%s")


class TestNutanixHostCpuPeak:
    def test_picks_worst_timestamp_and_converts_hz(self):
        sql = nq.NUTANIX_HOST_CPU_PEAK
        assert "DISTINCT ON (host_name)" in sql
        assert "1000000000.0" in sql, "Hz must be converted to GHz in SQL"
        assert "public.nutanix_host_metrics" in sql

    def test_placeholder_count_matches_mem_peak(self):
        assert nq.NUTANIX_HOST_CPU_PEAK.count("%s") == nq.NUTANIX_HOST_MEM_PEAK.count("%s")


class TestNutanixHostAvg:
    def test_averages_and_converts_both_units(self):
        sql = nq.NUTANIX_HOST_AVG
        # DISTINCT ON (cluster_uuid) in the dc_clusters CTE is legitimate --
        # it resolves cluster identity, exactly as NUTANIX_HOST_MEM_PEAK does.
        # What must NOT appear is a per-host DISTINCT ON, which would collapse
        # the window to a single row and defeat the average.
        assert "DISTINCT ON (host_name)" not in sql
        assert "DISTINCT ON (cluster_uuid)" in sql
        assert "AVG(" in sql
        assert "GROUP BY h.host_name" in sql
        assert "1000000000.0" in sql, "Hz -> GHz"
        assert "1073741824.0" in sql, "bytes -> GB"

    def test_placeholder_count_matches_mem_peak(self):
        assert nq.NUTANIX_HOST_AVG.count("%s") == nq.NUTANIX_HOST_MEM_PEAK.count("%s")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/datacenter-api && PYTHONPATH=.:../.. $PY -m pytest tests/test_host_avg_peak_queries.py -q`
Expected: FAIL — `AttributeError: module 'app.db.queries.vmware' has no attribute 'CLASSIC_HOST_CPU_PEAK'`

- [ ] **Step 3: Add the classic queries**

Append to `services/datacenter-api/app/db/queries/vmware.py` after `CLASSIC_HOST_MEM_PEAK`:

```python
# Per-host CPU peak within time range (classic KM). Mirrors CLASSIC_HOST_MEM_PEAK:
# picks the single worst-utilisation timestamp per host and reports used/cap from
# that row. Replaces the previous behaviour where the "max" CPU track read the
# LATEST sample from CLASSIC_HOST_ROWS.
# Params: (dc_pattern, cluster_filter[], cluster_filter[], start_ts, end_ts)
CLASSIC_HOST_CPU_PEAK = """
WITH ts_agg AS (
    SELECT vmhost,
           "timestamp",
           COALESCE(cpu_ghz_used, 0)     AS used_ghz,
           COALESCE(cpu_ghz_capacity, 0) AS cap_ghz
    FROM public.vmhost_metrics
    WHERE datacenter ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND (cardinality(%s::text[]) = 0 OR cluster = ANY(%s::text[]))
      AND "timestamp" BETWEEN %s AND %s
)
SELECT DISTINCT ON (vmhost)
    vmhost,
    used_ghz,
    cap_ghz,
    COALESCE(100.0 * used_ghz / NULLIF(cap_ghz, 0), 0) AS util_pct
FROM ts_agg
WHERE cap_ghz > 0
ORDER BY vmhost, (used_ghz / NULLIF(cap_ghz, 0)) DESC, used_ghz DESC
"""

# Per-host CPU + RAM average across the whole time range (classic KM).
# Averages used AND capacity separately so a mid-window capacity change does not
# distort the ratio. No DISTINCT ON: every sample in the window contributes.
# Params: (dc_pattern, cluster_filter[], cluster_filter[], start_ts, end_ts)
CLASSIC_HOST_AVG = """
SELECT
    vmhost,
    COALESCE(AVG(cpu_ghz_used), 0)                       AS cpu_used_ghz_avg,
    COALESCE(AVG(cpu_ghz_capacity), 0)                   AS cpu_cap_ghz_avg,
    COALESCE(100.0 * AVG(cpu_ghz_used)
             / NULLIF(AVG(cpu_ghz_capacity), 0), 0)      AS cpu_util_pct_avg,
    COALESCE(AVG(memory_used_gb), 0)                     AS mem_used_gb_avg,
    COALESCE(AVG(memory_capacity_gb), 0)                 AS mem_cap_gb_avg,
    COALESCE(100.0 * AVG(memory_used_gb)
             / NULLIF(AVG(memory_capacity_gb), 0), 0)    AS mem_util_pct_avg
FROM public.vmhost_metrics
WHERE datacenter ILIKE %s
  AND cluster ILIKE '%%KM%%'
  AND (cardinality(%s::text[]) = 0 OR cluster = ANY(%s::text[]))
  AND "timestamp" BETWEEN %s AND %s
GROUP BY vmhost
"""
```

- [ ] **Step 4: Add the Nutanix queries**

Append to `services/datacenter-api/app/db/queries/nutanix.py` after `NUTANIX_HOST_MEM_PEAK`:

```python
# Per-host CPU peak from nutanix_host_metrics (hyperconverged scope). Mirrors
# NUTANIX_HOST_MEM_PEAK. Note the source column is cpu_usage_avg — that is the
# only CPU usage column Nutanix exposes, so "peak" here means the timestamp at
# which that averaged value was highest.
# Params: (dc_code, cluster_filter[], cluster_filter[], start_ts, end_ts)
NUTANIX_HOST_CPU_PEAK = """
WITH dc_clusters AS (
    SELECT DISTINCT ON (cluster_uuid)
        cluster_uuid::text AS cluster_uuid,
        cluster_name
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND (cardinality(%s::text[]) = 0 OR cluster_name = ANY(%s::text[]))
      AND collection_time >= NOW() - INTERVAL '7 days'
    ORDER BY cluster_uuid, collection_time DESC
),
ts_agg AS (
    SELECT h.host_name,
           h.collectiontime,
           COALESCE(h.cpu_usage_avg, 0)         AS used_hz,
           COALESCE(h.total_cpu_capacity, 0)    AS cap_hz
    FROM public.nutanix_host_metrics h
    INNER JOIN dc_clusters c ON h.cluster_uuid::text = c.cluster_uuid
    WHERE h.collectiontime BETWEEN %s AND %s
)
SELECT DISTINCT ON (host_name)
    host_name,
    COALESCE(used_hz / 1000000000.0, 0),
    COALESCE(cap_hz / 1000000000.0, 0),
    COALESCE(100.0 * used_hz / NULLIF(cap_hz, 0), 0)
FROM ts_agg
WHERE cap_hz > 0
ORDER BY host_name, (used_hz / NULLIF(cap_hz, 0)) DESC, used_hz DESC
"""

# Per-host CPU + RAM average across the whole time range (hyperconverged).
# Hz -> GHz and bytes -> GB conversions happen in SQL, matching
# NUTANIX_HOST_MEM_PEAK, so the Python layer treats classic and Nutanix rows
# identically.
# Params: (dc_code, cluster_filter[], cluster_filter[], start_ts, end_ts)
NUTANIX_HOST_AVG = """
WITH dc_clusters AS (
    SELECT DISTINCT ON (cluster_uuid)
        cluster_uuid::text AS cluster_uuid,
        cluster_name
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND (cardinality(%s::text[]) = 0 OR cluster_name = ANY(%s::text[]))
      AND collection_time >= NOW() - INTERVAL '7 days'
    ORDER BY cluster_uuid, collection_time DESC
)
SELECT
    h.host_name,
    COALESCE(AVG(h.cpu_usage_avg) / 1000000000.0, 0)              AS cpu_used_ghz_avg,
    COALESCE(AVG(h.total_cpu_capacity) / 1000000000.0, 0)         AS cpu_cap_ghz_avg,
    COALESCE(100.0 * AVG(h.cpu_usage_avg)
             / NULLIF(AVG(h.total_cpu_capacity), 0), 0)           AS cpu_util_pct_avg,
    COALESCE(AVG(h.memory_usage_avg) / 1073741824.0, 0)           AS mem_used_gb_avg,
    COALESCE(AVG(h.total_memory_capacity) / 1073741824.0, 0)      AS mem_cap_gb_avg,
    COALESCE(100.0 * AVG(h.memory_usage_avg)
             / NULLIF(AVG(h.total_memory_capacity), 0), 0)        AS mem_util_pct_avg
FROM public.nutanix_host_metrics h
INNER JOIN dc_clusters c ON h.cluster_uuid::text = c.cluster_uuid
WHERE h.collectiontime BETWEEN %s AND %s
GROUP BY h.host_name
"""
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd services/datacenter-api && PYTHONPATH=.:../.. $PY -m pytest tests/test_host_avg_peak_queries.py -q`
Expected: PASS (9 tests)

- [ ] **Step 6: Commit**

```bash
git add services/datacenter-api/app/db/queries/vmware.py \
        services/datacenter-api/app/db/queries/nutanix.py \
        services/datacenter-api/tests/test_host_avg_peak_queries.py
git commit -m "feat(datacenter-api): per-host CPU peak and CPU/RAM average queries

CPU had no peak query at all: the max-utilisation track read the latest
sample from CLASSIC_HOST_ROWS / NUTANIX_HOST_ROWS. Adds real window-peak
queries for CPU plus window-average queries for CPU and RAM, mirroring the
existing *_MEM_PEAK shape so all three sellable tracks stay comparable."
```

---

### Task 2: Enrich host payloads with peak and average fields

**Files:**
- Modify: `services/datacenter-api/app/services/dc_service.py` — add helpers next to `_host_mem_peak_map` (line 1502) and `_apply_host_mem_peak` (line 1570); wire into `_fetch_classic_host_rows_all` (the `try` block at ~1660 and the loop at ~1686) and `_fetch_hyperconv_host_rows_all` (lines 1733-1787)
- Test: `services/datacenter-api/tests/test_host_avg_enrichment.py` (create)

**Interfaces:**
- Consumes: the four SQL constants from Task 1.
- Produces: host dicts carrying `cpu_used_ghz_peak`, `cpu_cap_ghz_at_peak`, `cpu_peak_util_pct`, `cpu_used_ghz_avg`, `cpu_cap_ghz_avg`, `cpu_avg_util_pct`, `mem_used_gb_avg`, `mem_cap_gb_avg`, `mem_avg_util_pct`. Also two new static methods: `_host_avg_map(rows) -> dict[str, dict[str, float]]` and `_apply_host_avg(payload, avg) -> dict`, plus `_apply_host_cpu_peak(payload, peak) -> dict`.

`_host_mem_peak_map` is reused unchanged for the CPU peak rows — both return `(name, used, cap, pct)` 4-tuples. The average rows are 7-tuples, so they need their own indexer.

- [ ] **Step 1: Write the failing test**

Create `services/datacenter-api/tests/test_host_avg_enrichment.py`:

```python
"""Host payload enrichment for the avg track and the corrected CPU peak."""
from app.services.dc_service import DCService


class TestHostAvgMap:
    def test_indexes_by_short_hostname(self):
        rows = [("esx01.bulut.local", 12.0, 40.0, 30.0, 100.0, 512.0, 19.5)]
        out = DCService._host_avg_map(rows)
        assert set(out) == {"esx01"}
        assert out["esx01"]["cpu_used_ghz_avg"] == 12.0
        assert out["esx01"]["cpu_cap_ghz_avg"] == 40.0
        assert out["esx01"]["cpu_avg_util_pct"] == 30.0
        assert out["esx01"]["mem_used_gb_avg"] == 100.0
        assert out["esx01"]["mem_cap_gb_avg"] == 512.0
        assert out["esx01"]["mem_avg_util_pct"] == 19.5

    def test_skips_rows_without_hostname(self):
        assert DCService._host_avg_map([(None, 1, 2, 3, 4, 5, 6), ("", 1, 2, 3, 4, 5, 6)]) == {}

    def test_handles_none_metrics_as_zero(self):
        out = DCService._host_avg_map([("h1", None, None, None, None, None, None)])
        assert out["h1"]["cpu_used_ghz_avg"] == 0.0


class TestApplyHostAvg:
    def test_attaches_all_six_fields(self):
        payload = {"host": "esx01", "cpu_cap_ghz": 40.0}
        out = DCService._apply_host_avg(payload, {
            "cpu_used_ghz_avg": 12.0, "cpu_cap_ghz_avg": 40.0, "cpu_avg_util_pct": 30.0,
            "mem_used_gb_avg": 100.0, "mem_cap_gb_avg": 512.0, "mem_avg_util_pct": 19.5,
        })
        assert out["cpu_used_ghz_avg"] == 12.0
        assert out["mem_avg_util_pct"] == 19.5

    def test_noop_when_avg_missing(self):
        """Missing avg data must leave the payload alone, never write 0 --
        a zero would read as 'nothing used, sell everything'."""
        payload = {"host": "esx01", "cpu_cap_ghz": 40.0}
        assert DCService._apply_host_avg(payload, None) == payload
        assert "cpu_used_ghz_avg" not in DCService._apply_host_avg(payload, None)

    def test_noop_when_all_values_zero(self):
        payload = {"host": "esx01"}
        out = DCService._apply_host_avg(payload, {
            "cpu_used_ghz_avg": 0.0, "cpu_cap_ghz_avg": 0.0, "cpu_avg_util_pct": 0.0,
            "mem_used_gb_avg": 0.0, "mem_cap_gb_avg": 0.0, "mem_avg_util_pct": 0.0,
        })
        assert "cpu_used_ghz_avg" not in out

    def test_does_not_mutate_input(self):
        payload = {"host": "esx01"}
        DCService._apply_host_avg(payload, {
            "cpu_used_ghz_avg": 1.0, "cpu_cap_ghz_avg": 2.0, "cpu_avg_util_pct": 50.0,
            "mem_used_gb_avg": 3.0, "mem_cap_gb_avg": 4.0, "mem_avg_util_pct": 75.0,
        })
        assert payload == {"host": "esx01"}


class TestApplyHostCpuPeak:
    def test_attaches_peak_fields(self):
        out = DCService._apply_host_cpu_peak({"host": "esx01"}, (26.0, 40.0, 65.0))
        assert out["cpu_used_ghz_peak"] == 26.0
        assert out["cpu_cap_ghz_at_peak"] == 40.0
        assert out["cpu_peak_util_pct"] == 65.0

    def test_noop_when_peak_missing_or_empty(self):
        payload = {"host": "esx01"}
        assert DCService._apply_host_cpu_peak(payload, None) == payload
        assert DCService._apply_host_cpu_peak(payload, (0.0, 0.0, 0.0)) == payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/datacenter-api && PYTHONPATH=.:../.. $PY -m pytest tests/test_host_avg_enrichment.py -q`
Expected: FAIL — `AttributeError: type object 'DCService' has no attribute '_host_avg_map'`

- [ ] **Step 3: Add the three helpers**

In `services/datacenter-api/app/services/dc_service.py`, immediately after `_host_mem_peak_map` (which ends at line 1510):

```python
    @staticmethod
    def _host_avg_map(rows) -> dict[str, dict[str, float]]:
        """Index per-host CPU+RAM window averages by short hostname.

        Row shape (see CLASSIC_HOST_AVG / NUTANIX_HOST_AVG):
        (host, cpu_used_ghz, cpu_cap_ghz, cpu_pct, mem_used_gb, mem_cap_gb, mem_pct)
        """
        out: dict[str, dict[str, float]] = {}
        for r in rows or []:
            if not r or not r[0]:
                continue
            key = str(r[0]).strip().lower().split(".")[0]
            out[key] = {
                "cpu_used_ghz_avg": float(r[1] or 0),
                "cpu_cap_ghz_avg": float(r[2] or 0),
                "cpu_avg_util_pct": float(r[3] or 0),
                "mem_used_gb_avg": float(r[4] or 0),
                "mem_cap_gb_avg": float(r[5] or 0),
                "mem_avg_util_pct": float(r[6] or 0),
            }
        return out
```

Then, immediately after `_apply_host_mem_peak` (which ends at line 1580):

```python
    @staticmethod
    def _apply_host_cpu_peak(payload: dict, peak: tuple[float, float, float] | None) -> dict:
        """Attach per-host CPU window peak. No-op when absent, so the sellable
        max track falls back to the latest sample rather than to zero."""
        if not peak:
            return payload
        used, cap, pct = peak
        if used <= 0 and cap <= 0:
            return payload
        out = dict(payload)
        out["cpu_used_ghz_peak"] = round(used, 2)
        out["cpu_cap_ghz_at_peak"] = round(cap, 2)
        out["cpu_peak_util_pct"] = round(pct, 1)
        return out

    @staticmethod
    def _apply_host_avg(payload: dict, avg: dict[str, float] | None) -> dict:
        """Attach per-host CPU+RAM window averages.

        No-op when the metric is absent or entirely zero: writing 0 would make
        the avg sellable track read the host as completely idle and offer the
        whole machine for sale.
        """
        if not avg:
            return payload
        if not any(float(v or 0) > 0 for v in avg.values()):
            return payload
        out = dict(payload)
        out["cpu_used_ghz_avg"] = round(float(avg.get("cpu_used_ghz_avg") or 0), 2)
        out["cpu_cap_ghz_avg"] = round(float(avg.get("cpu_cap_ghz_avg") or 0), 2)
        out["cpu_avg_util_pct"] = round(float(avg.get("cpu_avg_util_pct") or 0), 1)
        out["mem_used_gb_avg"] = round(float(avg.get("mem_used_gb_avg") or 0), 2)
        out["mem_cap_gb_avg"] = round(float(avg.get("mem_cap_gb_avg") or 0), 2)
        out["mem_avg_util_pct"] = round(float(avg.get("mem_avg_util_pct") or 0), 1)
        return out
```

- [ ] **Step 4: Run helper tests to verify they pass**

Run: `cd services/datacenter-api && PYTHONPATH=.:../.. $PY -m pytest tests/test_host_avg_enrichment.py -q`
Expected: PASS (9 tests)

- [ ] **Step 5: Wire the queries into the classic fetch**

In `_fetch_classic_host_rows_all`, inside the existing `with conn.cursor() as cur:` block, after the `peak_rows = ...` call:

```python
                    cpu_peak_rows = self._run_rows(
                        cur,
                        vq.CLASSIC_HOST_CPU_PEAK,
                        (dc_wc, empty_clusters, empty_clusters, start_ts, end_ts),
                    )
                    avg_rows = self._run_rows(
                        cur,
                        vq.CLASSIC_HOST_AVG,
                        (dc_wc, empty_clusters, empty_clusters, start_ts, end_ts),
                    )
```

After the existing `peak_map = self._host_mem_peak_map(peak_rows)`:

```python
        cpu_peak_map = self._host_mem_peak_map(cpu_peak_rows)
        avg_map = self._host_avg_map(avg_rows)
```

And in the per-host loop, replace the single enrichment line:

```python
            payload = self._apply_host_mem_peak(payload, peak_map.get(key))
```

with:

```python
            payload = self._apply_host_mem_peak(payload, peak_map.get(key))
            payload = self._apply_host_cpu_peak(payload, cpu_peak_map.get(key))
            payload = self._apply_host_avg(payload, avg_map.get(key))
```

- [ ] **Step 6: Wire the queries into the hyperconverged fetch**

In `_fetch_hyperconv_host_rows_all`, after the existing `peak_rows = ...` call (line 1746-1750):

```python
                    cpu_peak_rows = self._run_rows(
                        cur,
                        nq.NUTANIX_HOST_CPU_PEAK,
                        (dc_code, empty_clusters, empty_clusters, start_ts, end_ts),
                    )
                    avg_rows = self._run_rows(
                        cur,
                        nq.NUTANIX_HOST_AVG,
                        (dc_code, empty_clusters, empty_clusters, start_ts, end_ts),
                    )
```

After `peak_map = self._host_mem_peak_map(peak_rows)` (line 1759):

```python
        cpu_peak_map = self._host_mem_peak_map(cpu_peak_rows)
        avg_map = self._host_avg_map(avg_rows)
```

And replace line 1786:

```python
            payload = self._apply_host_mem_peak(payload, peak_map.get(key))
            payload = self._apply_host_cpu_peak(payload, cpu_peak_map.get(key))
            payload = self._apply_host_avg(payload, avg_map.get(key))
```

- [ ] **Step 7: Run the datacenter-api suite**

Run: `cd services/datacenter-api && PYTHONPATH=.:../.. $PY -m pytest tests/ -q`
Expected: PASS — no new failures versus the pre-task run of the same command. Record the count.

- [ ] **Step 8: Commit**

```bash
git add services/datacenter-api/app/services/dc_service.py \
        services/datacenter-api/tests/test_host_avg_enrichment.py
git commit -m "feat(datacenter-api): attach CPU peak and CPU/RAM average to host rows

Runs the new peak/average queries alongside the existing RAM peak and
enriches each host payload. Enrichers no-op on missing or all-zero metrics:
a zero average would read as an idle host and offer the whole machine as
sellable."
```

---

### Task 3: `avg` track in `host_raw_headroom`, and CPU `max` reads the real peak

**Files:**
- Modify: `shared/sellable/host_sellable.py:86-139` (`host_raw_headroom`)
- Test: `tests/test_host_sellable_avg_track.py` (create)

**Interfaces:**
- Consumes: host dict fields from Task 2.
- Produces: `host_raw_headroom(host, resource=..., threshold_pct=..., cpu_track="avg"|"max"|"effective"|"physical", ram_track="avg"|"max"|"physical")`. Consumed by `compute_host_sellable_units` (unchanged signature — it forwards its own `cpu_track`/`ram_track` through) and therefore by `_accumulate` in Task 5.

This is the heart of the change. The formula stays `apply_utilization_gate(cap, used, util, threshold)`; only which `used` is selected changes. Per the Global Constraints, each resource's `avg` branch mirrors **that resource's own** `max` branch: CPU max uses current capacity, so CPU avg does too; RAM max uses capacity-at-peak, so RAM avg uses average capacity.

- [ ] **Step 1: Write the failing test**

Create `tests/test_host_sellable_avg_track.py`:

```python
"""The avg utilization track, and the corrected CPU max track.

Ordering invariant under test: allocated >= peak used >= avg used, therefore
sellable(alloc) <= sellable(max) <= sellable(avg).
"""
from shared.sellable.host_sellable import host_raw_headroom

# 100 GHz / 512 GB host at an 80% threshold.
# VMs are ALLOCATED 70 GHz, PEAK at 40 GHz, AVERAGE 25 GHz.
HOST = {
    "cpu_cap_ghz": 100.0,
    "cpu_alloc_ghz": 70.0,
    "cpu_used_ghz": 30.0,          # latest sample -- what "max" wrongly used
    "cpu_used_ghz_peak": 40.0,     # real window peak
    "cpu_cap_ghz_at_peak": 100.0,
    "cpu_peak_util_pct": 40.0,
    "cpu_used_ghz_avg": 25.0,
    "cpu_cap_ghz_avg": 100.0,
    "cpu_avg_util_pct": 25.0,
    "cpu_used_pct": 30.0,
    "mem_cap_gb": 512.0,
    "mem_alloc_gb": 400.0,
    "mem_used_pct": 50.0,
    "mem_cap_gb_at_peak": 512.0,
    "mem_used_gb_peak": 300.0,
    "mem_peak_util_pct": 58.6,
    "mem_cap_gb_avg": 512.0,
    "mem_used_gb_avg": 180.0,
    "mem_avg_util_pct": 35.2,
}


class TestCpuTracks:
    def test_alloc_track_uses_allocated_ghz(self):
        # 100 * 0.8 - 70 = 10
        assert host_raw_headroom(HOST, resource="cpu", threshold_pct=80.0,
                                 cpu_track="effective") == 10.0

    def test_max_track_uses_window_peak_not_latest_sample(self):
        # 100 * 0.8 - 40 (peak) = 40, NOT 80 - 30 (latest) = 50
        assert host_raw_headroom(HOST, resource="cpu", threshold_pct=80.0,
                                 cpu_track="max") == 40.0

    def test_max_track_falls_back_to_latest_when_no_peak(self):
        host = {k: v for k, v in HOST.items() if k != "cpu_used_ghz_peak"}
        assert host_raw_headroom(host, resource="cpu", threshold_pct=80.0,
                                 cpu_track="max") == 50.0

    def test_avg_track_uses_window_average(self):
        # 100 * 0.8 - 25 = 55
        assert host_raw_headroom(HOST, resource="cpu", threshold_pct=80.0,
                                 cpu_track="avg") == 55.0

    def test_avg_exceeds_max_exceeds_alloc(self):
        kw = dict(resource="cpu", threshold_pct=80.0)
        alloc = host_raw_headroom(HOST, cpu_track="effective", **kw)
        mx = host_raw_headroom(HOST, cpu_track="max", **kw)
        avg = host_raw_headroom(HOST, cpu_track="avg", **kw)
        assert alloc < mx < avg

    def test_avg_track_is_zero_without_avg_data(self):
        """No avg metric -> no headroom claimed. Never the full machine."""
        host = {"cpu_cap_ghz": 100.0, "cpu_alloc_ghz": 70.0}
        assert host_raw_headroom(host, resource="cpu", threshold_pct=80.0,
                                 cpu_track="avg") == 0.0


class TestRamTracks:
    def test_alloc_track_uses_allocated_gb(self):
        # 512 * 0.8 - 400 = 9.6
        assert host_raw_headroom(HOST, resource="ram", threshold_pct=80.0,
                                 ram_track="physical") == 512.0 * 0.8 - 400.0

    def test_max_track_uses_peak(self):
        assert host_raw_headroom(HOST, resource="ram", threshold_pct=80.0,
                                 ram_track="max") == 512.0 * 0.8 - 300.0

    def test_avg_track_uses_average_used_and_average_cap(self):
        assert host_raw_headroom(HOST, resource="ram", threshold_pct=80.0,
                                 ram_track="avg") == 512.0 * 0.8 - 180.0

    def test_avg_exceeds_max_exceeds_alloc(self):
        kw = dict(resource="ram", threshold_pct=80.0)
        alloc = host_raw_headroom(HOST, ram_track="physical", **kw)
        mx = host_raw_headroom(HOST, ram_track="max", **kw)
        avg = host_raw_headroom(HOST, ram_track="avg", **kw)
        assert alloc < mx < avg


class TestStorageUnaffected:
    def test_storage_ignores_track_arguments(self):
        """Storage has no time dimension: identical across all tracks."""
        host = {**HOST, "stor_cap_gb": 1000.0, "stor_provisioned_gb": 500.0,
                "stor_used_pct": 50.0}
        vals = {
            host_raw_headroom(host, resource="storage", threshold_pct=85.0,
                              cpu_track=t, ram_track=t)
            for t in ("effective", "max", "avg")
        }
        assert len(vals) == 1


class TestGateStillApplies:
    def test_avg_track_blocked_when_average_exceeds_threshold(self):
        host = {**HOST, "cpu_used_ghz_avg": 95.0, "cpu_avg_util_pct": 95.0}
        assert host_raw_headroom(host, resource="cpu", threshold_pct=80.0,
                                 cpu_track="avg") == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_host_sellable_avg_track.py -q`
Expected: FAIL — `test_max_track_uses_window_peak_not_latest_sample` gets `50.0` (latest sample) and `test_avg_track_uses_window_average` gets `10.0` (unknown track falls through to the `effective` branch).

- [ ] **Step 3: Rewrite the CPU and RAM arms of `host_raw_headroom`**

In `shared/sellable/host_sellable.py`, replace the `cpu` and `ram` blocks (lines 99-125) with:

```python
    if resource == "cpu":
        cap = float(host.get("cpu_cap_ghz") or host.get("cpu_total") or 0.0)
        if cpu_track == "physical":
            alloc = float(host.get("cpu_alloc_ghz_physical") or host.get("cpu_alloc_phys") or 0.0)
            util = float(host.get("cpu_used_pct") or host.get("cpu_util_pct") or 0.0)
        elif cpu_track == "max":
            # Real window peak; falls back to the latest sample when the peak
            # query returned nothing for this host.
            alloc = float(host.get("cpu_used_ghz_peak") or host.get("cpu_used_ghz") or 0.0)
            util = float(
                host.get("cpu_peak_util_pct")
                or host.get("cpu_used_pct")
                or host.get("cpu_util_pct")
                or 0.0
            )
        elif cpu_track == "avg":
            # No fallback: without an average we claim no headroom rather than
            # treating the host as idle.
            alloc = float(host.get("cpu_used_ghz_avg") or 0.0)
            if alloc <= 0.0:
                return 0.0
            util = float(host.get("cpu_avg_util_pct") or 0.0)
        else:
            alloc = float(host.get("cpu_alloc_ghz") or host.get("cpu_alloc") or 0.0)
            util = float(host.get("cpu_used_pct") or host.get("cpu_util_pct") or 0.0)
        return apply_utilization_gate(cap, alloc, util, threshold_pct)

    if resource == "ram":
        if ram_track == "max":
            cap = float(
                host.get("mem_cap_gb_at_peak")
                or host.get("mem_peak_total")
                or host.get("mem_cap_gb")
                or host.get("ram_total")
                or 0.0
            )
            used = float(host.get("mem_used_gb_peak") or host.get("mem_peak_used") or 0.0)
            util = float(host.get("mem_peak_util_pct") or host.get("mem_used_pct") or 0.0)
            return apply_utilization_gate(cap, used, util, threshold_pct)
        if ram_track == "avg":
            used = float(host.get("mem_used_gb_avg") or 0.0)
            if used <= 0.0:
                return 0.0
            cap = float(
                host.get("mem_cap_gb_avg")
                or host.get("mem_cap_gb")
                or host.get("ram_total")
                or 0.0
            )
            util = float(host.get("mem_avg_util_pct") or 0.0)
            return apply_utilization_gate(cap, used, util, threshold_pct)
        cap = float(host.get("mem_cap_gb") or host.get("ram_total") or 0.0)
        alloc = float(host.get("mem_alloc_gb") or host.get("ram_alloc") or 0.0)
        util = float(host.get("mem_used_pct") or host.get("ram_util_pct") or 0.0)
        return apply_utilization_gate(cap, alloc, util, threshold_pct)
```

Also extend the two normalizers just above so `"avg"` survives them unchanged — they currently only rewrite `"peak"` to `"max"`, so `"avg"` already passes through; add it to their docstrings:

```python
def _normalize_cpu_track(cpu_track: str) -> str:
    """Map legacy ``peak`` track name to ``max``. Known tracks:
    ``effective`` (allocation), ``physical``, ``max`` (window peak), ``avg``."""
    return "max" if cpu_track == "peak" else cpu_track


def _normalize_ram_track(ram_track: str) -> str:
    """Map legacy ``peak`` track name to ``max``. Known tracks:
    ``physical`` (allocation), ``max`` (window peak), ``avg``."""
    return "max" if ram_track == "peak" else ram_track
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PY -m pytest tests/test_host_sellable_avg_track.py -q`
Expected: PASS (12 tests)

- [ ] **Step 5: Check the CPU max change against existing expectations**

Run: `$PY -m pytest tests/test_host_sellable.py tests/test_host_aggregate.py tests/test_sellable_constraint_viz.py -q`
and `cd services/customer-api && PYTHONPATH=.:../.. $PY -m pytest tests/test_host_based_computation.py -q`

Expected: PASS. If a test fails **because** CPU max now uses a peak, that is the intended correction — update the fixture's expected number and note it in the commit body. Do not revert the behaviour. If a test fails for any other reason, stop and investigate.

- [ ] **Step 6: Commit**

```bash
git add shared/sellable/host_sellable.py tests/test_host_sellable_avg_track.py
git commit -m "feat(sellable): add avg utilization track, fix CPU max to use real peak

host_raw_headroom gains cpu_track/ram_track == 'avg', reading the new
window-average host fields. The CPU 'max' track now reads cpu_used_ghz_peak
instead of the latest sample, falling back to the old field when no peak is
available.

Each resource's avg branch mirrors that resource's own max branch: CPU uses
current capacity as denominator, RAM uses averaged capacity. The avg track
claims zero headroom when average data is missing rather than treating the
host as idle."
```

---

### Task 4: `PanelResult.sellable_avg_util`

**Files:**
- Modify: `shared/sellable/models.py:88-90`
- Test: `tests/test_sellable_models_avg_field.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `PanelResult.sellable_avg_util: float | None = None`, included in `to_dict()` via `asdict`. Consumed by Tasks 5, 7, 8.

- [ ] **Step 1: Write the failing test**

Create `tests/test_sellable_models_avg_field.py`:

```python
"""PanelResult carries a third sellable track."""
from shared.sellable.models import PanelResult


def _panel(**kw) -> PanelResult:
    base = dict(panel_key="p1", label="L", family="virt_classic",
                resource_kind="cpu", display_unit="vCPU")
    return PanelResult(**{**base, **kw})


def test_sellable_avg_util_defaults_to_none():
    assert _panel().sellable_avg_util is None


def test_sellable_avg_util_round_trips_through_to_dict():
    d = _panel(sellable_allocation=10.0, sellable_max_util=40.0,
               sellable_avg_util=55.0).to_dict()
    assert d["sellable_avg_util"] == 55.0
    assert d["sellable_max_util"] == 40.0
    assert d["sellable_allocation"] == 10.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_sellable_models_avg_field.py -q`
Expected: FAIL — `TypeError: PanelResult.__init__() got an unexpected keyword argument 'sellable_avg_util'`

- [ ] **Step 3: Add the field**

In `shared/sellable/models.py`, replace lines 88-90:

```python
    # Allocation vs max-utilization vs avg-utilization sellable tracks.
    # Ordering invariant: allocation <= max_util <= avg_util, because
    # allocated >= peak used >= average used.
    sellable_allocation: float | None = None
    sellable_max_util: float | None = None
    sellable_avg_util: float | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PY -m pytest tests/test_sellable_models_avg_field.py -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add shared/sellable/models.py tests/test_sellable_models_avg_field.py
git commit -m "feat(sellable): add PanelResult.sellable_avg_util"
```

---

### Task 5: Produce `n_avg` in both constraint entry points

**Files:**
- Modify: `shared/sellable/computation.py:289-345` (`host_effective_units`), `:348-438` (`constrain_by_ratio_per_host_dual`), `:441-630` (`constrain_by_ratio_per_host_triple_dual`)
- Test: `tests/test_sellable_avg_unit_count.py` (create)

**Interfaces:**
- Consumes: `host_raw_headroom` tracks (Task 3), `PanelResult.sellable_avg_util` (Task 4).
- Produces: every `PanelResult` returned by either constraint function carries `sellable_avg_util` for `resource_kind` in `{cpu, ram, storage}`. Storage's value is `n_avg * ratio.storage_gb_per_unit`, derived through the triple-min — never from a storage-specific average.

`constrain_by_ratio_per_host_triple_dual` is the only path used in production (`sellable_service.py:2256`); `constrain_by_ratio_per_host_dual` is its empty-hosts fallback (`computation.py:466`). Both must set the field so the fallback returns `0.0` rather than `None`, which the GUI would render as `—` and look like missing data instead of "no hosts".

- [ ] **Step 1: Write the failing test**

Create `tests/test_sellable_avg_unit_count.py`:

```python
"""n_avg: the third unit count, and the ratio coupling it must preserve."""
from shared.sellable.computation import (
    constrain_by_ratio_per_host_dual,
    constrain_by_ratio_per_host_triple_dual,
)
from shared.sellable.models import PanelResult, ResourceRatio


def _ratio() -> ResourceRatio:
    # 1 unit = 1 vCPU + 2 GB RAM + 100 GB storage (the Hyperconverged shape).
    return ResourceRatio(cpu_per_unit=1.0, ram_gb_per_unit=2.0, storage_gb_per_unit=100.0)


def _panels() -> list[PanelResult]:
    def p(kind, unit):
        return PanelResult(panel_key=f"p_{kind}", label=kind, family="virt_classic",
                           resource_kind=kind, display_unit=unit, sellable_raw=1e9)
    return [p("cpu", "vCPU"), p("ram", "GB"), p("storage", "GB")]


def _host() -> dict:
    """allocated 70 GHz > peak 40 > avg 25; RAM allocated 400 > peak 300 > avg 180."""
    return {
        "host": "esx01", "cluster": "KM01",
        "cpu_cap_ghz": 100.0, "cpu_total": 100.0,
        "cpu_alloc_ghz": 70.0, "cpu_alloc": 70.0,
        "cpu_used_ghz": 30.0,
        "cpu_used_ghz_peak": 40.0, "cpu_cap_ghz_at_peak": 100.0, "cpu_peak_util_pct": 40.0,
        "cpu_used_ghz_avg": 25.0, "cpu_cap_ghz_avg": 100.0, "cpu_avg_util_pct": 25.0,
        "cpu_used_pct": 30.0,
        "mem_cap_gb": 512.0, "ram_total": 512.0,
        "mem_alloc_gb": 400.0, "ram_alloc": 400.0, "mem_used_pct": 50.0,
        "mem_cap_gb_at_peak": 512.0, "mem_used_gb_peak": 300.0, "mem_peak_util_pct": 58.6,
        "mem_cap_gb_avg": 512.0, "mem_used_gb_avg": 180.0, "mem_avg_util_pct": 35.2,
        "stor_cap_gb": 100000.0, "stor_provisioned_gb": 10000.0, "stor_used_pct": 10.0,
        "stor_exclusive_free_gb": 90000.0,
    }


def _by_kind(panels):
    return {p.resource_kind: p for p in panels}


class TestTripleDual:
    def test_all_three_tracks_populated(self):
        out = _by_kind(constrain_by_ratio_per_host_triple_dual(
            _panels(), _ratio(), [_host()],
            cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
        ))
        for kind in ("cpu", "ram", "storage"):
            assert out[kind].sellable_avg_util is not None, kind
            assert out[kind].sellable_max_util is not None, kind
            assert out[kind].sellable_allocation is not None, kind

    def test_avg_exceeds_max_exceeds_alloc_on_every_row(self):
        out = _by_kind(constrain_by_ratio_per_host_triple_dual(
            _panels(), _ratio(), [_host()],
            cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
        ))
        for kind in ("cpu", "ram", "storage"):
            p = out[kind]
            assert p.sellable_allocation < p.sellable_max_util < p.sellable_avg_util, kind

    def test_ratio_coupling_identical_across_resources(self):
        """The three rows are one unit count times the ratio, so avg/alloc must
        match across CPU, RAM and Storage. This is the invariant that proves the
        triple-min chain was not broken."""
        out = _by_kind(constrain_by_ratio_per_host_triple_dual(
            _panels(), _ratio(), [_host()],
            cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
        ))
        ratios = [
            out[k].sellable_avg_util / out[k].sellable_allocation
            for k in ("cpu", "ram", "storage")
        ]
        assert max(ratios) - min(ratios) < 1e-6, ratios

    def test_storage_avg_comes_from_unit_count_not_storage_average(self):
        """Storage has no average of its own: its avg cell is n_avg * ratio."""
        out = _by_kind(constrain_by_ratio_per_host_triple_dual(
            _panels(), _ratio(), [_host()],
            cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
        ))
        n_avg = out["cpu"].sellable_avg_util / 1.0        # cpu_per_unit
        assert abs(out["storage"].sellable_avg_util - n_avg * 100.0) < 1e-6


class TestEmptyHostsFallback:
    def test_avg_is_zero_not_none_when_no_hosts(self):
        """No hosts is 'nothing sellable', not 'unknown'."""
        out = _by_kind(constrain_by_ratio_per_host_triple_dual(
            _panels(), _ratio(), [],
            cpu_threshold_pct=80.0, ram_threshold_pct=80.0,
        ))
        assert out["cpu"].sellable_avg_util == 0.0
        assert out["ram"].sellable_avg_util == 0.0

    def test_dual_path_populates_avg_directly(self):
        out = _by_kind(constrain_by_ratio_per_host_dual(
            _panels(), _ratio(), [_host()],
            cpu_threshold_pct=80.0, ram_threshold_pct=80.0,
        ))
        assert out["cpu"].sellable_avg_util is not None
        assert out["cpu"].sellable_allocation < out["cpu"].sellable_avg_util
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_sellable_avg_unit_count.py -q`
Expected: FAIL — `AssertionError: cpu` on `test_all_three_tracks_populated` (`sellable_avg_util` is `None`).

- [ ] **Step 3: Give `host_effective_units` explicit CPU max/avg branches**

`host_effective_units` currently has no CPU `max` branch — every track except `physical` falls into the `effective` branch. Replace the CPU selection block (lines 313-327) with:

```python
        if cpu_track == "physical":
            cpu_total = float(h.get("cpu_total_phys") or h.get("cpu_total") or 0.0)
            cpu_alloc = float(h.get("cpu_alloc_phys") or 0.0)
            ghz = float(h.get("ghz_per_core") or 1.0)
            cpu_den = ratio.cpu_per_unit * ghz if ghz > 0 else ratio.cpu_per_unit
            cpu_util = float(h.get("cpu_util_pct") or 0.0)
        elif cpu_track == "max":
            cpu_total = float(h.get("cpu_total") or 0.0)
            cpu_alloc = float(h.get("cpu_used_ghz_peak") or h.get("cpu_used_ghz") or 0.0)
            cpu_den = ratio.cpu_per_unit * max(effective_ghz_per_unit, 1e-9)
            cpu_util = float(h.get("cpu_peak_util_pct") or h.get("cpu_util_pct") or 0.0)
        elif cpu_track == "avg":
            cpu_total = float(h.get("cpu_total") or 0.0)
            cpu_alloc = float(h.get("cpu_used_ghz_avg") or 0.0)
            cpu_den = ratio.cpu_per_unit * max(effective_ghz_per_unit, 1e-9)
            cpu_util = float(h.get("cpu_avg_util_pct") or 0.0)
        else:
            cpu_total = float(h.get("cpu_total") or 0.0)
            cpu_alloc = float(h.get("cpu_alloc") or 0.0)
            cpu_den = ratio.cpu_per_unit * max(effective_ghz_per_unit, 1e-9)
            cpu_util = float(h.get("cpu_util_pct") or 0.0)
        raw_cpu = apply_utilization_gate(
            cpu_total,
            cpu_alloc,
            cpu_util,
            cpu_threshold_pct,
        )
```

Then extend the RAM selection block (lines 328-337) with an `avg` arm:

```python
        if ram_track in ("max", "peak"):
            ram_total = float(
                h.get("mem_cap_gb_at_peak") or h.get("ram_peak_total") or 0.0
            )
            ram_alloc = float(h.get("mem_used_gb_peak") or h.get("ram_peak_used") or 0.0)
            ram_util = float(h.get("mem_peak_util_pct") or h.get("ram_peak_util_pct") or 0.0)
        elif ram_track == "avg":
            ram_total = float(h.get("mem_cap_gb_avg") or h.get("ram_total") or 0.0)
            ram_alloc = float(h.get("mem_used_gb_avg") or 0.0)
            ram_util = float(h.get("mem_avg_util_pct") or 0.0)
        else:
            ram_total = float(h.get("ram_total") or 0.0)
            ram_alloc = float(h.get("ram_alloc") or 0.0)
            ram_util = float(h.get("ram_util_pct") or 0.0)
```

Update the docstring track list to name `max` and `avg` for both parameters.

- [ ] **Step 4: Add `n_avg` to `constrain_by_ratio_per_host_dual`**

After the existing `n_ram_max = host_effective_units(...)` call (ends line 395), add:

```python
    n_cpu_avg = host_effective_units(
        hosts,
        ratio,
        cpu_threshold_pct=cpu_threshold_pct,
        ram_threshold_pct=ram_threshold_pct,
        cpu_track="avg",
        ram_track="avg",
        effective_ghz_per_unit=effective_ghz_per_unit,
    )
    n_ram_avg = n_cpu_avg
```

In the `cpu` branch, add `constrained_avg` and pass it:

```python
        if p.resource_kind == "cpu":
            constrained_eff = n_cpu_eff * ratio.cpu_per_unit
            constrained_max = n_cpu_max * ratio.cpu_per_unit
            constrained_avg = n_cpu_avg * ratio.cpu_per_unit
            ratio_bound = constrained_eff + 1e-6 < p.sellable_raw
            out.append(
                replace(
                    p,
                    sellable_allocation=constrained_eff,
                    sellable_max_util=constrained_max,
                    sellable_avg_util=constrained_avg,
                    sellable_effective=constrained_eff,
                    sellable_physical=None,
                    sellable_constrained=constrained_eff,
                    ratio_bound=ratio_bound,
                    computation_mode="host_based",
                )
            )
```

And in the `ram` branch, add `sellable_avg_util=n_ram_avg * ratio.ram_gb_per_unit` to the existing `replace(...)` call alongside `sellable_max_util=constrained_max`.

- [ ] **Step 5: Add `n_avg` to `constrain_by_ratio_per_host_triple_dual`**

After line 513 (`_, host_stor_max_shared = _accumulate("max", "max", True)`), add:

```python
    n_cpu_avg, host_stor_avg = _accumulate("avg", "avg", False)
    n_ram_avg = n_cpu_avg
```

After the existing `stor_constrained_max` assignment (line 526), add:

```python
    stor_constrained_avg = sum(r.stor_constrained_min for r in host_stor_avg)
```

Inside the `if cluster_storage_raw_gb is not None:` block, alongside the existing alloc/max pair:

```python
        n_bn_avg = min(n_cpu_avg, n_ram_avg) if n_ram_avg > 0 else n_cpu_avg
        stor_cap_avg = max(n_bn_avg, 0.0) * ratio.storage_gb_per_unit
        stor_constrained_avg = min(max(cluster_storage_raw_gb, 0.0), stor_cap_avg)
```

Inside the `if ibm_storage_range is not None:` block, alongside the existing pair:

```python
        n_bn_avg = min(n_cpu_avg, n_ram_avg) if n_ram_avg > 0 else n_cpu_avg
        compute_cap_avg = max(n_bn_avg, 0.0) * ratio.storage_gb_per_unit
        pool_avg = stor_constrained_avg
        stor_constrained_avg = (
            min(max(pool_avg, 0.0), compute_cap_avg) if compute_cap_avg > 0 else 0.0
        )
```

Then add the derived values near line 571:

```python
    cpu_avg_val = n_cpu_avg * ratio.cpu_per_unit
    ram_avg_val = n_ram_avg * ratio.ram_gb_per_unit
```

and pass `sellable_avg_util=cpu_avg_val`, `sellable_avg_util=ram_avg_val`, `sellable_avg_util=stor_constrained_avg` into the three existing `replace(...)` calls for `cpu`, `ram` and `storage` respectively.

- [ ] **Step 6: Run test to verify it passes**

Run: `$PY -m pytest tests/test_sellable_avg_unit_count.py -q`
Expected: PASS (6 tests)

- [ ] **Step 7: Run the whole sellable surface**

Run: `$PY -m pytest tests/ -q -k "sellable or host_aggregate or virt" --ignore=tests/test_backup_sidebar_helpers.py`
and `cd services/customer-api && PYTHONPATH=.:../.. $PY -m pytest tests/ -q`

Expected: only the known baseline failure `test_virt_sellable_aggregate.py::test_aggregate_virt_sellable_panels_totals` (repaired in Task 9). Any other failure is yours.

- [ ] **Step 8: Commit**

```bash
git add shared/sellable/computation.py tests/test_sellable_avg_unit_count.py
git commit -m "feat(sellable): compute n_avg unit count in both constraint paths

Adds the third unit count to constrain_by_ratio_per_host_triple_dual (the
production path) and to constrain_by_ratio_per_host_dual (its empty-hosts
fallback), and gives host_effective_units the CPU max/avg branches it never
had -- every track but 'physical' previously fell through to 'effective'.

Storage's avg value is derived through the triple-min, not from any
storage-specific average, so the avg/alloc ratio stays identical across the
CPU, RAM and Storage rows."
```

---

### Task 6: Carry avg fields into `host_units`

**Files:**
- Modify: `services/customer-api/app/services/sellable_service.py:2120-2158`
- Test: `services/customer-api/tests/test_host_units_avg_fields.py` (create)

**Interfaces:**
- Consumes: host payload fields from Task 2.
- Produces: `host_units` dicts carrying unit-converted `mem_used_gb_avg` / `mem_cap_gb_avg` / `mem_avg_util_pct`, consumed by `host_raw_headroom` via `constrain_by_ratio_per_host_triple_dual`.

The existing loop converts RAM peak fields into the panel's display unit and re-assigns them **after** the `**h` spread, because the spread carries raw GB. RAM average must get the same treatment or it would be compared against converted capacities. CPU fields need no conversion — `host_raw_headroom`'s CPU arm reads `cpu_cap_ghz` (raw GHz) as its denominator, and `**h` already carries the raw CPU avg/peak fields through.

- [ ] **Step 1: Write the failing test**

Create `services/customer-api/tests/test_host_units_avg_fields.py`:

```python
"""host_units must carry RAM avg fields converted into panel display units."""
from app.services.sellable_service import SellableService
from shared.sellable.models import UnitConversion

# GB -> TB, i.e. divide by 1024.
GB_TO_TB = UnitConversion(from_unit="GB", to_unit="TB", factor=1024.0, operation="divide")

HOST = {
    "host": "esx01", "cluster": "KM01", "ghz_per_core": 2.0,
    "cpu_cap_ghz": 100.0, "cpu_alloc_ghz": 70.0, "cpu_used_pct": 30.0,
    "mem_cap_gb": 1024.0, "mem_alloc_gb": 800.0, "mem_used_pct": 50.0,
    "mem_used_gb_peak": 600.0, "mem_cap_gb_at_peak": 1024.0, "mem_peak_util_pct": 58.6,
    "mem_used_gb_avg": 360.0, "mem_cap_gb_avg": 1024.0, "mem_avg_util_pct": 35.2,
    "cpu_used_ghz_avg": 25.0, "cpu_used_ghz_peak": 40.0,
    "stor_cap_gb": 0.0, "stor_provisioned_gb": 0.0, "stor_used_pct": 0.0,
}


def test_ram_avg_converted_like_ram_peak():
    """RAM avg is converted into display units exactly like RAM peak, because
    host_raw_headroom compares it against converted capacities."""
    u = SellableService._normalize_host_unit(
        HOST, cpu_conv=None, ram_conv=GB_TO_TB, sto_conv=None
    )
    assert abs(u["mem_used_gb_avg"] - 360.0 / 1024.0) < 1e-9
    assert abs(u["mem_cap_gb_avg"] - 1024.0 / 1024.0) < 1e-9
    assert u["mem_avg_util_pct"] == 35.2
    # Sanity: peak gets the identical treatment.
    assert abs(u["mem_used_gb_peak"] - 600.0 / 1024.0) < 1e-9


def test_cpu_avg_and_peak_pass_through_unconverted():
    """host_raw_headroom's CPU arm uses raw cpu_cap_ghz as its denominator, so
    the CPU avg/peak fields must ride the **h spread as raw GHz."""
    u = SellableService._normalize_host_unit(
        HOST, cpu_conv=None, ram_conv=GB_TO_TB, sto_conv=None
    )
    assert u["cpu_used_ghz_avg"] == 25.0
    assert u["cpu_used_ghz_peak"] == 40.0


def test_ram_avg_cap_falls_back_to_current_cap():
    """Only the used average has no fallback; the capacity denominator may fall
    back to current capacity so a partial metric still computes."""
    host = {k: v for k, v in HOST.items() if k != "mem_cap_gb_avg"}
    u = SellableService._normalize_host_unit(
        host, cpu_conv=None, ram_conv=GB_TO_TB, sto_conv=None
    )
    assert abs(u["mem_cap_gb_avg"] - 1024.0 / 1024.0) < 1e-9
```

`_normalize_host_unit` does not exist yet — the host-unit construction is inline inside a long private method. Step 3 extracts it.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/customer-api && PYTHONPATH=.:../.. $PY -m pytest tests/test_host_units_avg_fields.py -q`
Expected: FAIL — `AttributeError: type object 'SellableService' has no attribute '_normalize_host_unit'`

- [ ] **Step 3: Extract the per-host normalization into a testable helper**

The enclosing method is long and the host-unit construction is the part under test. Extract just the per-host dict build. Add this static method to `SellableService`, immediately above the method containing line 2120:

```python
    @staticmethod
    def _normalize_host_unit(
        h: dict,
        *,
        cpu_conv: "dict | None",
        ram_conv: "dict | None",
        sto_conv: "dict | None",
    ) -> dict:
        """Normalize one host row into panel display units for the sellable engine.

        Raw CPU fields (cpu_cap_ghz, cpu_used_ghz*, cpu_used_ghz_avg) pass
        through the ``**h`` spread unconverted because host_raw_headroom's CPU
        arm uses cpu_cap_ghz as its denominator. RAM peak and RAM average are
        converted here, mirroring each other.
        """
        ghz = float(h.get("ghz_per_core") or 1.0)
        cap_ghz = float(h.get("cpu_cap_ghz") or 0.0)
        alloc_sales = float(h.get("cpu_alloc_ghz") or 0.0)
        alloc_phys = float(h.get("cpu_alloc_ghz_physical") or alloc_sales * ghz)
        ram_util = float(h.get("mem_used_pct") or 0.0)
        return {
            **h,
            "cpu_total": convert_unit(cap_ghz, cpu_conv),
            "cpu_alloc": convert_unit(alloc_sales, cpu_conv),
            "cpu_total_phys": cap_ghz,
            "cpu_alloc_phys": alloc_phys,
            "ghz_per_core": ghz,
            "ram_total": convert_unit(float(h.get("mem_cap_gb") or 0.0), ram_conv),
            "ram_alloc": convert_unit(float(h.get("mem_alloc_gb") or 0.0), ram_conv),
            "cpu_used_pct": float(h.get("cpu_used_pct") or 0.0),
            "mem_used_pct": ram_util,
            "mem_used_gb_peak": convert_unit(
                float(h.get("mem_used_gb_peak") or 0.0), ram_conv
            ),
            "mem_cap_gb_at_peak": convert_unit(
                float(h.get("mem_cap_gb_at_peak") or h.get("mem_cap_gb") or 0.0), ram_conv
            ),
            "mem_peak_util_pct": float(h.get("mem_peak_util_pct") or ram_util),
            "mem_used_gb_avg": convert_unit(
                float(h.get("mem_used_gb_avg") or 0.0), ram_conv
            ),
            "mem_cap_gb_avg": convert_unit(
                float(h.get("mem_cap_gb_avg") or h.get("mem_cap_gb") or 0.0), ram_conv
            ),
            "mem_avg_util_pct": float(h.get("mem_avg_util_pct") or 0.0),
            "stor_cap_gb": convert_unit(float(h.get("stor_cap_gb") or 0.0), sto_conv),
            "stor_provisioned_gb": convert_unit(
                float(h.get("stor_provisioned_gb") or 0.0), sto_conv
            ),
            "stor_used_pct": float(h.get("stor_used_pct") or 0.0),
        }
```

Note the deliberate asymmetry: `mem_cap_gb_avg` falls back to `mem_cap_gb` (so RAM avg still has a denominator when only the used average arrived), but `mem_used_gb_avg` has **no** fallback — Task 3's `avg` arm returns `0.0` when used is absent, which is the safe direction.

Then rewrite the loop body at lines 2120-2158 to use it, keeping the running sums intact:

```python
        for h in host_rows:
            hu = self._normalize_host_unit(
                h, cpu_conv=cpu_conv, ram_conv=ram_conv, sto_conv=sto_conv
            )
            host_units.append(hu)
            hc, ha = hu["cpu_total"], hu["cpu_alloc"]
            mc, ma = hu["ram_total"], hu["ram_alloc"]
            stor_cap, stor_alloc = hu["stor_cap_gb"], hu["stor_provisioned_gb"]
            stor_util = hu["stor_used_pct"]
            cpu_total += hc
            cpu_alloc += ha
            ram_total += mc
            ram_alloc += ma
```

Leave everything after that (the `if family == "virt_hyperconverged":` block onward) untouched — it already reads these locals.

No test seam is needed: `_normalize_host_unit` is a static method and the test calls it directly. `convert_unit(value, conv)` takes a `UnitConversion` dataclass (`shared/sellable/models.py:51`) with `factor` and `operation` (`"divide"` by default, or `"multiply"`), and treats `conv is None` as identity — which is why the test passes `cpu_conv=None` and `sto_conv=None`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/customer-api && PYTHONPATH=.:../.. $PY -m pytest tests/test_host_units_avg_fields.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Verify the extraction changed no behaviour**

Run: `cd services/customer-api && PYTHONPATH=.:../.. $PY -m pytest tests/ -q`
Expected: same result as before this task. The extraction must be behaviour-preserving.

- [ ] **Step 6: Commit**

```bash
git add services/customer-api/app/services/sellable_service.py \
        services/customer-api/tests/test_host_units_avg_fields.py
git commit -m "refactor(customer-api): extract _normalize_host_unit, carry RAM avg

Pulls the per-host normalization out of a long method so it can be tested
directly, and adds the RAM average fields with the same unit conversion the
RAM peak fields already get. CPU avg/peak need no conversion: they ride the
**h spread as raw GHz, which is what host_raw_headroom's CPU arm expects."
```

---

### Task 7: Serialize, hydrate, and expose the avg track through the API

**Files:**
- Modify: `services/customer-api/app/services/sellable_service.py:2380` (`_apply_allocation_only_pricing`), `:2401-2424` (`_apply_dual_track_pricing`), `:2991` (hydration), `:3178` (serialization)
- Modify: `services/customer-api/app/services/inventory_overview_service.py:492-525`
- Test: `services/customer-api/tests/test_sellable_avg_api_contract.py` (create)

**Interfaces:**
- Consumes: `PanelResult.sellable_avg_util` (Tasks 4, 5).
- Produces: payload key `sellable_avg_util` (snapshot JSONB + API), and `_panel_pricing_fields` keys `sellable_avg_qty` and `potential_tl_avg`. Consumed by Task 8.

No migration: `gui_panel_result_snapshot` is a single `payload jsonb` column, and hydration's `d.get(...)`-with-`None` idiom already tolerates payloads written before the key existed.

- [ ] **Step 1: Write the failing test**

Create `services/customer-api/tests/test_sellable_avg_api_contract.py`:

```python
"""API/snapshot contract for the avg sellable track."""
from app.services.inventory_overview_service import _panel_pricing_fields
from shared.sellable.models import PanelResult


def _panel(**kw) -> PanelResult:
    base = dict(panel_key="p1", label="CPU", family="virt_classic",
                resource_kind="cpu", display_unit="vCPU",
                unit_price_tl=100.0, has_price=True, has_infra_source=True)
    return PanelResult(**{**base, **kw})


class TestPricingFields:
    def test_exposes_avg_qty_and_tl(self):
        out = _panel_pricing_fields(
            _panel(sellable_allocation=10.0, sellable_max_util=40.0,
                   sellable_avg_util=55.0, potential_tl_min=1000.0,
                   potential_tl_max=4000.0),
            hide_used=True,
        )
        assert out["sellable_avg_qty"] == 55.0
        assert out["potential_tl_avg"] == 55.0 * 100.0

    def test_avg_is_none_when_track_absent(self):
        """Missing avg must render as em-dash, not as 0 and not as a mean."""
        out = _panel_pricing_fields(
            _panel(sellable_allocation=10.0, sellable_max_util=40.0),
            hide_used=True,
        )
        assert out["sellable_avg_qty"] is None
        assert out["potential_tl_avg"] is None

    def test_no_infra_source_returns_none_avg(self):
        out = _panel_pricing_fields(_panel(has_infra_source=False), hide_used=True)
        assert out["sellable_avg_qty"] is None
        assert out["potential_tl_avg"] is None


class TestSerializationRoundTrip:
    def test_avg_survives_serialize_then_hydrate(self):
        from app.services.sellable_service import SellableService
        payload = SellableService._panel_summary_dict(_panel(sellable_avg_util=55.0))
        assert payload["sellable_avg_util"] == 55.0
        restored = SellableService._panel_result_from_dict(payload)
        assert restored.sellable_avg_util == 55.0

    def test_legacy_payload_without_avg_hydrates_to_none(self):
        """Snapshots written before this change must not break."""
        from app.services.sellable_service import SellableService
        payload = SellableService._panel_summary_dict(_panel(sellable_avg_util=55.0))
        del payload["sellable_avg_util"]
        assert SellableService._panel_result_from_dict(payload).sellable_avg_util is None


class TestPowerFamiliesUnaffected:
    def test_allocation_only_nulls_the_avg_track(self):
        from app.services.sellable_service import SellableService
        p = _panel(family="virt_power", sellable_constrained=5.0,
                   sellable_max_util=9.0, sellable_avg_util=9.0)
        SellableService._apply_allocation_only_pricing(p)
        assert p.sellable_max_util is None
        assert p.sellable_avg_util is None
```

Method names verified against the source: serialization is the static `_panel_summary_dict` (the dict literal at line 3165), hydration is the static `_panel_result_from_dict` (the `PanelResult(...)` construction at line 2975), and `_apply_allocation_only_pricing` is a `@staticmethod` — all three are callable on the class without an instance.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/customer-api && PYTHONPATH=.:../.. $PY -m pytest tests/test_sellable_avg_api_contract.py -q`
Expected: FAIL — `KeyError: 'sellable_avg_qty'`

- [ ] **Step 3: Serialize and hydrate the field**

In the serialization dict (line 3178), directly after `"sellable_max_util": panel.sellable_max_util,`:

```python
            "sellable_avg_util": panel.sellable_avg_util,
```

In the hydration call (line 2991), directly after the `sellable_max_util=` entry:

```python
            sellable_avg_util=(
                float(d["sellable_avg_util"]) if d.get("sellable_avg_util") is not None else None
            ),
```

- [ ] **Step 4: Null the avg track on allocation-only families**

In `_apply_allocation_only_pricing`, after line 2380 (`panel.sellable_max_util = None`):

```python
        panel.sellable_avg_util = None
```

- [ ] **Step 5: Expose avg quantity and TL from the overview service**

In `inventory_overview_service.py`, add `"sellable_avg_qty": None` and `"potential_tl_avg": None` to the early-return dict at lines 493-501. Then in the main path, after `max_qty = panel.sellable_max_util` (line 505):

```python
    avg_qty = panel.sellable_avg_util
```

and after `potential_tl_max = panel.potential_tl_max` (line 513):

```python
    potential_tl_avg = (
        compute_potential_tl(avg_qty, unit_price)
        if avg_qty is not None and panel.has_price
        else None
    )
```

Finally add both keys to the returned dict (lines 517-525):

```python
        "sellable_avg_qty": avg_qty,
        "potential_tl_avg": potential_tl_avg,
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd services/customer-api && PYTHONPATH=.:../.. $PY -m pytest tests/test_sellable_avg_api_contract.py -q`
Expected: PASS (6 tests)

- [ ] **Step 7: Run the customer-api suite**

Run: `cd services/customer-api && PYTHONPATH=.:../.. $PY -m pytest tests/ -q`
Expected: no new failures.

- [ ] **Step 8: Commit**

```bash
git add services/customer-api/app/services/sellable_service.py \
        services/customer-api/app/services/inventory_overview_service.py \
        services/customer-api/tests/test_sellable_avg_api_contract.py
git commit -m "feat(customer-api): serialize and expose the avg sellable track

Adds sellable_avg_util to the panel payload (no migration -- the snapshot is
a single jsonb column) and sellable_avg_qty / potential_tl_avg to the
inventory overview contract. Legacy snapshots without the key hydrate to
None so the UI shows an em-dash instead of a fabricated number. Power
families null the track alongside sellable_max_util."
```

---

### Task 8: GUI reads the real field; delete `_mean`

**Files:**
- Modify: `src/components/crm_inventory_report.py:160-173` (delete `_mean`), `:377-381` (read the real field)
- Modify: `src/utils/virt_sellable_aggregate.py:167,176`
- Test: `tests/test_crm_inventory_report.py` (modify `test_prepare_service_row_sellable_average`)

**Interfaces:**
- Consumes: `sellable_avg_qty` / `potential_tl_avg` from Task 7.
- Produces: the rendered `sellable_avg_fmt` cell. Terminal task — nothing consumes it.

This is the step that closes the reported defect. The existing test asserts the bug, so it gets inverted rather than added to.

- [ ] **Step 1: Invert the test that currently asserts the bug**

In `tests/test_crm_inventory_report.py`, replace `test_prepare_service_row_sellable_average` (line 59-65) with:

```python
def test_prepare_service_row_sellable_average_uses_real_avg_field():
    """Sellable (Ort.) comes from the avg-utilization track, NOT from the mean
    of alloc and max. Average utilization is below peak utilization, so the avg
    track must yield MORE sellable capacity than the max track -- the defect
    Can reported was avg reading lower than max."""
    row = prepare_service_row(_sample_row(
        inventory_hide_used=True,
        sellable_avg_qty=30.0,
        potential_tl_avg=45000.0,
    ))
    assert "30 vCPU" in row["sellable_avg_fmt"]
    assert "45,000 TL" in row["sellable_avg_fmt"]
    # The old placeholder would have produced the mean of 18 and 22.
    assert "20 vCPU" not in row["sellable_avg_fmt"]


def test_sellable_average_absent_renders_em_dash():
    """No avg data must render as em-dash, never 0 and never a mean."""
    row = prepare_service_row(_sample_row(inventory_hide_used=True))
    assert row["sellable_avg_fmt"].startswith("—")
```

Confirm `_sample_row` (defined around line 20-40) passes unknown keyword arguments straight into the row dict; if it takes an explicit allow-list, add `sellable_avg_qty` and `potential_tl_avg` to it.

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_crm_inventory_report.py -q -k sellable_average`
Expected: FAIL — the cell still contains `20 vCPU` from the mean.

- [ ] **Step 3: Read the real fields and delete `_mean`**

In `src/components/crm_inventory_report.py`, in `prepare_service_row`, add near the other row extractions:

```python
    sellable_avg_qty = row.get("sellable_avg_qty")
    potential_tl_avg = row.get("potential_tl_avg")
```

Replace the `sellable_avg_fmt` entry (lines 377-381) with:

```python
        "sellable_avg_fmt": shared.fmt_qty_tl_block(
            sellable_avg_qty, unit, potential_tl_avg,
        ) if profile == "dual_track" else "—\n—",
```

Then delete the whole `_mean` function (lines 160-173) — Task 8's grep in Step 5 confirms nothing else references it.

- [ ] **Step 4: Propagate the field through the virt aggregate**

In `src/utils/virt_sellable_aggregate.py`, add a line after each existing `sellable_max_util = None` assignment — line 167 (single-panel branch) and line 176 (merged branch):

```python
            single["sellable_avg_util"] = None
```

```python
        merged["sellable_avg_util"] = None
```

- [ ] **Step 5: Verify `_mean` is gone and unreferenced**

Run: `grep -rn "_mean\b" src/ tests/`
Expected: no hits in `src/components/crm_inventory_report.py`. Hits for `is_meaningful_value` are a different symbol and are fine.

- [ ] **Step 6: Run test to verify it passes**

Run: `$PY -m pytest tests/test_crm_inventory_report.py tests/test_crm_inventory_overview_page.py tests/test_crm_inventory_export.py -q`
Expected: PASS except the known baseline failure `test_crm_inventory_overview_page.py::test_fill_callback_does_not_listen_to_time_range` (`AttributeError: 'function' object has no attribute 'inputs'`), which is out of scope.

- [ ] **Step 7: Commit**

```bash
git add src/components/crm_inventory_report.py src/utils/virt_sellable_aggregate.py \
        tests/test_crm_inventory_report.py
git commit -m "fix(gui): Sellable (Ort.) reads the real avg track, not a mean

The column was the arithmetic mean of the alloc and max columns, which made
average utilization look less profitable than peak utilization. It now reads
sellable_avg_qty / potential_tl_avg, and renders an em-dash when the track is
absent. Deletes the _mean helper."
```

---

### Task 9: Repair the one in-scope stale baseline test

**Files:**
- Modify: `tests/test_virt_sellable_aggregate.py:22-32`

**Interfaces:**
- Consumes: nothing. Independent of Tasks 1-8; may run at any point.
- Produces: nothing.

`test_aggregate_virt_sellable_panels_totals` asserts `total_tl == 20.0` and gets `13.0`. The code is right and the test is stale: `aggregate_virt_sellable_panels` zeroes a panel's TL when `sellable_constrained <= 1e-9` (`virt_sellable_aggregate.py:294-295`), a deliberate "potential that can never be billed" guard. The fixture's third panel carries `potential_tl: 7.0` with no `sellable_constrained`, so its 7.0 is correctly dropped: 10.0 + 3.0 + 0.0 = 13.0.

- [ ] **Step 1: Confirm the failure and its cause**

Run: `$PY -m pytest "tests/test_virt_sellable_aggregate.py::test_aggregate_virt_sellable_panels_totals" -q`
Expected: FAIL with `assert 13.0 == 20.0`

- [ ] **Step 2: Correct the expectation and document why**

Replace `test_aggregate_virt_sellable_panels_totals` (lines 22-32) with:

```python
def test_aggregate_virt_sellable_panels_totals():
    """A panel with no sellable capacity contributes no TL.

    aggregate_virt_sellable_panels zeroes potential_tl when
    sellable_constrained <= 0 -- revenue that can never be billed must not
    inflate the total. The 'other' panel below has no sellable_constrained, so
    its 7.0 TL is dropped: 10.0 + 3.0 = 13.0.
    """
    panels = [
        {"resource_kind": "cpu", "potential_tl": 10.0, "sellable_constrained": 5.0, "display_unit": "Core"},
        {"resource_kind": "ram", "potential_tl": 3.0, "sellable_constrained": 100.0},
        {"resource_kind": "other", "potential_tl": 7.0},
    ]
    total_tl, by_kind, has_known = aggregate_virt_sellable_panels(panels)
    assert total_tl == 13.0
    assert has_known is True
    assert float(by_kind["cpu"]["tl"]) == 10.0
    assert float(by_kind["ram"]["tl"]) == 3.0


def test_aggregate_counts_tl_when_panel_has_sellable_capacity():
    """Same shape, but the third panel is sellable -- so its TL counts."""
    panels = [
        {"resource_kind": "cpu", "potential_tl": 10.0, "sellable_constrained": 5.0, "display_unit": "Core"},
        {"resource_kind": "ram", "potential_tl": 3.0, "sellable_constrained": 100.0},
        {"resource_kind": "other", "potential_tl": 7.0, "sellable_constrained": 1.0},
    ]
    total_tl, _, _ = aggregate_virt_sellable_panels(panels)
    assert total_tl == 20.0
```

- [ ] **Step 3: Run test to verify it passes**

Run: `$PY -m pytest tests/test_virt_sellable_aggregate.py -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_virt_sellable_aggregate.py
git commit -m "test: correct stale virt sellable TL total expectation

The test predates the 'potential that can never be billed' guard, which
zeroes a panel's TL when sellable_constrained <= 0. Corrects 20.0 to 13.0 and
adds the mirror case where the third panel IS sellable, so the guard itself
stays covered."
```

---

### Task 10: Measure the CPU peak impact and write the before/after table

**Files:**
- Create: `docs/qa/2026-07-30-avg-utilization-before-after.md`

**Interfaces:**
- Consumes: the completed Tasks 1-9.
- Produces: the PR evidence table promised in the spec.

The spec commits to publishing this so Can does not read the corrected CPU max numbers as a new bug. Whether the max column moves at all depends on whether CPU is the binding resource in the triple-min — that is a measurement, not a prediction.

- [ ] **Step 1: Run the full suite and confirm the baseline delta**

Run: `$PY -m pytest tests/ -q --ignore=tests/test_backup_sidebar_helpers.py --ignore=tests/test_zabbix_query_deduplication.py`

Expected: 25 pre-existing failures remain (26 minus the one repaired in Task 9), plus the new tests passing. **No new failures.** If the count differs, stop and reconcile before writing the document.

- [ ] **Step 2: Capture the numbers**

Bring up the stack and read the CRM Inventory Overview report for one DC with Hyperconverged and Klasik families present, recording per resource row: `Sellable (Alloc)`, `Sellable (Max util)`, `Sellable (Ort.)`, in quantity and TL. Compare against the 2026-07-29 screenshot values recorded in the spec's evidence table.

If the stack cannot be brought up, say so explicitly in the document rather than estimating — the spec forbids substituting a prediction for the measurement.

- [ ] **Step 3: Write the document**

Create `docs/qa/2026-07-30-avg-utilization-before-after.md` with:
- The verification criteria from the spec, each marked pass or fail with its measured evidence.
- A before/after table per family and resource for all three columns.
- The measured `avg/alloc` and `max/alloc` ratios, demonstrating they are equal across the three resource rows of each family.
- A one-paragraph note for Can: which numbers moved, why (CPU max now uses a real window peak rather than the latest sample), and confirmation that the window is still 7 days.
- The two open questions from the spec, restated: window 7 vs 30, and awareness of the CPU max correction.

- [ ] **Step 4: Commit**

```bash
git add docs/qa/2026-07-30-avg-utilization-before-after.md
git commit -m "docs(qa): before/after evidence for the avg utilization track"
```

---

## Self-Review

**Spec coverage.** Layer 1 → Task 1. Layer 2 → Task 2. Layer 3 → Tasks 3, 4, 5. Layer 4 → Tasks 6, 7. Layer 5 → Task 8. Verification criteria 1 and 2 → Task 5 Steps 1 and 6 (unit level) plus Task 10 (production level). Criterion 3 → Task 3's `TestStorageUnaffected`. Criterion 4 → Task 10. Test plan items 1-7 map to Tasks 8, 5, 3, 5, 3, 1, and 7-8 respectively. Baseline record → Task 9 plus Task 10 Step 1. Risk "avg must not become 0" → Task 2 Steps 3-4 and Task 3 Step 3. Risk "legacy snapshots" → Task 7. Risk "power families" → Task 7 Step 4.

**Not covered by any task, deliberately.** The two non-goals (window selector, DC13 KM storage freshness) and the 25 out-of-scope baseline failures.

**Type consistency.** `sellable_avg_util` is the `PanelResult` field and payload key throughout (Tasks 4, 5, 7, 8). `sellable_avg_qty` / `potential_tl_avg` are the API and GUI names throughout (Tasks 7, 8) — the rename happens once, in `_panel_pricing_fields`, mirroring how `sellable_max_util` becomes `sellable_max_qty` today. The track literal is `"avg"` in every call site. `_host_avg_map` returns `dict[str, dict[str, float]]` in Task 2 and is consumed as a dict in the same task.

**Names verified against source, no assumptions left.** Serialization `_panel_summary_dict` and hydration `_panel_result_from_dict` (both `@staticmethod` on `SellableService`); `convert_unit(value, conv)` takes a `UnitConversion` dataclass with `factor` / `operation`, `None` meaning identity; `_sample_row(**kwargs)` in `tests/test_crm_inventory_report.py:15` does `base.update(kwargs)`, so Task 8's new row keys pass straight through with no allow-list to extend.

**One measurement deliberately left open.** Task 10 Step 2 cannot predict whether the max column moves — that depends on whether CPU is the binding resource in each family's triple-min, which is a property of live data. The task requires measuring it and forbids substituting an estimate.
