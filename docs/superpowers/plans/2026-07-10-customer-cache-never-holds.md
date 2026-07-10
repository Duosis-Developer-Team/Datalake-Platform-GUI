# Customer-View Cache "Never Holds" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the customer-view cache actually persist and serve fast, by (a) making the warm path effective, (b) preventing a slow/timed-out fetch from becoming a permanent empty, (c) making the backend `/resources` query complete within budget, and (d) hardening the shared-cache selection on the fleet.

**Architecture:** The bug is a 5-layer chain, not one defect (see live-confirmed diagnosis 2026-07-10). Cold `/resources` for a non-warmed customer takes ~104s (TimescaleDB index-only scan of a 7-day all-customer window, ILIKE `%name%` applied as a filter, ~30 statements run sequentially). That exceeds the GUI's 120s read timeout under real concurrent page load; the GUI then returns an empty fallback and — crucially — **does not cache it**, and the backend `cache_set` only runs on full success, so nothing is cached on either side and every reload repeats. Warm never seeds the first success (NO-OP scheduler hook, no `warm_mode`, only "Boyner"), and the browser-local `anchor_latest` toggle makes the warm write a cache key the request never reads.

**Tech Stack:** Python 3, Dash/Flask GUI (`src/`), FastAPI customer-api (`services/customer-api/`), psycopg2 + TimescaleDB (`bulutlake` on 10.134.16.6), Redis shared cache, pytest, docker-compose (local) / k8s (prod).

## Global Constraints

- **TDD, one behavior per test, frequent commits.** Every code task: failing test → run-fail → minimal impl → run-pass → commit.
- **No behavior change to correct paths.** Do not cache genuinely-empty payloads as if populated; do not mask real "no data" as data.
- **Do not touch the other session's branch work** (`feature/customer-availability-auranotify-mapping` — AuraNotify availability). This plan is about customer *resources* cache; keep commits scoped.
- **GUI cache getters live in** `src/services/api_client.py`; warm in `src/services/app_background_warm.py`; scheduler in `src/services/scheduler_service.py`.
- **customer-api resources query** in `services/customer-api/app/db/queries/customer.py`; adapter `services/customer-api/app/adapters/customer_adapter.py`; service `services/customer-api/app/services/customer_service.py`; SQL migrations in `services/customer-api/migrations/`.
- **Run GUI tests:** `python -m pytest tests/<file> -v`. **Run customer-api tests:** `cd services/customer-api && python -m pytest tests/<file> -v`.
- Branch for this work: `fix/customer-cache-never-holds` off `main` (do not commit on `main`).

---

## Phase 0 — Measurement spike (decides the Phase 3 approach). NO code change.

**Why:** The EXPLAIN of the vmname query shows an Index-Only Scan over the 7-day window with `vmname ~~* '%DEVUPS%'` as a **filter** (not an index cond), and `pg_trgm` is **not installed**. So the 104s could be dominated by one statement or spread across ~30. We must profile before choosing between: (a) `CREATE EXTENSION pg_trgm` + GIN trigram index, (b) anchored `LIKE 'name%'` + btree, (c) resolve-customer-to-exact-vmnames then `= ANY(...)`, (d) reduce/parallelize the ~30 statements, (e) a per-customer materialized rollup. Guessing here is how past weeks were lost.

### Task 0.1: Profile the `/resources` fetch end-to-end and per-statement

**Files:**
- Create: `docs/superpowers/plans/phase0-resources-profile.md` (findings, committed)
- (Scratch script may live under the scratchpad dir, not committed)

- [ ] **Step 1: Capture the total + per-endpoint latency** for one cold non-warmed customer, from inside the GUI container (mirrors the real network path):

```bash
docker exec datalake-platform-gui-app python3 - <<'PY'
import time, urllib.request, urllib.parse, json
name='DEVUPS BİLİŞİM TEKNOLOJİ DANIŞMANLIK VE OTOMOTİVTİCARET LİMİTED ŞİRKETİ'
enc=urllib.parse.quote(name)
for ep in ['resources','itsm/summary','sales/summary','sales/efficiency-by-category','s3/vaults']:
    url=f'http://customer-api:8000/api/v1/customers/{enc}/{ep}?preset=7d'
    t=time.time()
    try:
        r=urllib.request.urlopen(url, timeout=250); r.read()
        print(f'{ep:35s} {time.time()-t:6.1f}s HTTP {r.status}')
    except Exception as e:
        print(f'{ep:35s} {time.time()-t:6.1f}s ERR {e}')
PY
```
Expected: identifies whether `/resources` is the whole cost or several endpoints share it.

- [ ] **Step 2: EXPLAIN ANALYZE each statement** in `services/customer-api/app/db/queries/customer.py` against the live DB, using the customer-api container's own DB env. Run for the same customer/window. Record `actual time` per statement:

```bash
docker exec bulutistan-customer-api python3 - <<'PY'
import os, psycopg2
c=psycopg2.connect(host=os.getenv('DB_HOST'),port=os.getenv('DB_PORT'),dbname=os.getenv('DB_NAME'),user=os.getenv('DB_USER'),password=os.getenv('DB_PASS'))
c.autocommit=True; cur=c.cursor()
pat='%DEVUPS%'; s='2026-07-04'; e='2026-07-10'
sql="EXPLAIN (ANALYZE, TIMING, BUFFERS) SELECT DISTINCT ON (vmname) vmname FROM public.vm_metrics WHERE vmname ILIKE %s AND timestamp BETWEEN %s AND %s ORDER BY vmname, timestamp DESC"
cur.execute(sql,(pat,s,e))
for row in cur.fetchall(): print(row[0])
PY
```
Repeat for the LPAR query (`services/customer-api/app/db/queries/customer.py` power/lpar section) and the nutanix query. Note `Execution Time` on each.

- [ ] **Step 3: Test the pg_trgm hypothesis cheaply** — measure the ILIKE selectivity and whether a trigram index would convert the filter to an index cond. On a NON-production copy or with explicit approval, in a transaction you roll back:

```bash
docker exec bulutistan-customer-api python3 - <<'PY'
import os, psycopg2
c=psycopg2.connect(host=os.getenv('DB_HOST'),port=os.getenv('DB_PORT'),dbname=os.getenv('DB_NAME'),user=os.getenv('DB_USER'),password=os.getenv('DB_PASS'))
cur=c.cursor()
try:
    cur.execute("SELECT current_setting('is_superuser')"); print('superuser:', cur.fetchone())
    # Do NOT create the extension here if not superuser; just report capability.
finally:
    c.rollback(); c.close()
PY
```
Expected: tells us if we can `CREATE EXTENSION pg_trgm` (superuser) or must go the anchored/exact-id route.

- [ ] **Step 4: Write the decision** to `docs/superpowers/plans/phase0-resources-profile.md`: total latency, the 2-3 dominant statements, whether pg_trgm is feasible, and the chosen Phase 3 approach with the expected win. Commit:

```bash
git add docs/superpowers/plans/phase0-resources-profile.md
git commit -m "docs(cache): Phase 0 — /resources per-statement profile + Phase 3 decision"
```

---

## Phase 1 — Make the warm path effective (R4 + R5). GUI-only, low risk, deployable alone.

**Why:** `_warm_customer_view` (`src/services/app_background_warm.py:137-158`) fetches with the SHORT interactive timeout (no `warm_mode`), so a slow cold customer query times out during warm and is never cached — a silent false success (`warmed += 1`). It also warms only the non-anchor cache key, so a user with the browser `anchor_latest` toggle on always misses the warm. And no server-side timer calls it at all (the scheduler hook `warm_warmed_customer_caches` is a NO-OP; `warm_common` warms only home + SLA).

### Task 1: `_warm_customer_view` runs its fetches under `warm_mode()`

**Files:**
- Modify: `src/services/app_background_warm.py:137-158`
- Test: `tests/test_warm_customer_view.py`

**Interfaces:**
- Consumes: `src.services.api_client.warm_mode` (context manager, already exists at `api_client.py:223`), `api_client._WARM_MODE` (ContextVar, `:220`).
- Produces: `_warm_customer_view(customers, time_range)` unchanged signature; now executes getters with `_WARM_MODE` True.

- [ ] **Step 1: Write the failing test** (append to `tests/test_warm_customer_view.py`):

```python
def test_warm_customer_view_runs_under_warm_mode():
    from src.services import api_client
    seen = []
    def rec(*a, **k):
        seen.append(api_client._WARM_MODE.get())
        return {}
    with patch("src.services.api_client.get_customer_resources", side_effect=rec), \
         patch("src.services.api_client.get_customer_availability_bundle", side_effect=rec), \
         patch("src.services.api_client.get_customer_itsm_summary", side_effect=rec), \
         patch("src.services.api_client.get_customer_sales_summary", side_effect=rec), \
         patch("src.services.api_client.get_customer_efficiency_by_category", side_effect=rec), \
         patch("src.services.api_client.get_customer_s3_vaults", side_effect=rec):
        warm._warm_customer_view(["Acme"], {"preset": "7d"})
    assert seen and all(seen), "every customer getter must run inside warm_mode (long timeout)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_warm_customer_view.py::test_warm_customer_view_runs_under_warm_mode -v`
Expected: FAIL — `seen` holds `False` values (interactive mode).

- [ ] **Step 3: Wrap the loop body in `warm_mode()`** — edit `_warm_customer_view` so the per-customer getters run inside `with api.warm_mode():` (mirror `_warm_sellable_for_dcs` at `:48`):

```python
def _warm_customer_view(customers, time_range: dict | None) -> int:
    from src.services import api_client as api

    warmed = 0
    with api.warm_mode():
        for name in customers:
            name = (name or "").strip()
            if not name:
                continue
            try:
                api.get_customer_resources(name, time_range)
                api.get_customer_availability_bundle(name, time_range)
                api.get_customer_itsm_summary(name, time_range)
                api.get_customer_sales_summary(name)
                api.get_customer_efficiency_by_category(name, time_range)
                api.get_customer_s3_vaults(name, time_range)
                warmed += 1
            except Exception as exc:
                logger.warning("customer-view warm failed for %s: %s", name, exc)
    return warmed
```

- [ ] **Step 4: Run tests to verify pass** (both new and existing in the file)

Run: `python -m pytest tests/test_warm_customer_view.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/app_background_warm.py tests/test_warm_customer_view.py
git commit -m "fix(warm): run customer-view warm under warm_mode so slow cold fetches complete and cache"
```

### Task 2: `_warm_customer_view` warms BOTH anchor_latest variants (R5)

**Files:**
- Modify: `src/services/app_background_warm.py` (`_warm_customer_view`)
- Test: `tests/test_warm_customer_view.py`

**Interfaces:**
- Consumes: `_warm_tr_variants(tr)` (already at `app_background_warm.py:60-64`) → returns `[base, {**base, "anchor_latest": True}]`.
- Produces: each customer's resources/availability/itsm/efficiency/s3 getter is called once per anchor variant (sales has no `tr`, called once).

- [ ] **Step 1: Write the failing test**:

```python
def test_warm_customer_view_warms_both_anchor_variants():
    anchors = []
    def rec_res(name, tr):
        anchors.append(bool((tr or {}).get("anchor_latest")))
        return {}
    with patch("src.services.api_client.get_customer_resources", side_effect=rec_res), \
         patch("src.services.api_client.get_customer_availability_bundle", return_value={}), \
         patch("src.services.api_client.get_customer_itsm_summary", return_value={}), \
         patch("src.services.api_client.get_customer_sales_summary", return_value={}), \
         patch("src.services.api_client.get_customer_efficiency_by_category", return_value=[]), \
         patch("src.services.api_client.get_customer_s3_vaults", return_value={}):
        warm._warm_customer_view(["Acme"], {"preset": "7d", "start": "a", "end": "b"})
    assert set(anchors) == {True, False}, "resources must be warmed for both anchor and non-anchor keys"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_warm_customer_view.py::test_warm_customer_view_warms_both_anchor_variants -v`
Expected: FAIL — only `False` recorded.

- [ ] **Step 3: Iterate `_warm_tr_variants(time_range)`** for the `tr`-scoped getters (keep sales, which takes no `tr`, called once per customer):

```python
def _warm_customer_view(customers, time_range: dict | None) -> int:
    from src.services import api_client as api

    warmed = 0
    variants = _warm_tr_variants(time_range or {})
    with api.warm_mode():
        for name in customers:
            name = (name or "").strip()
            if not name:
                continue
            try:
                for t in variants:
                    api.get_customer_resources(name, t)
                    api.get_customer_availability_bundle(name, t)
                    api.get_customer_itsm_summary(name, t)
                    api.get_customer_efficiency_by_category(name, t)
                    api.get_customer_s3_vaults(name, t)
                api.get_customer_sales_summary(name)
                warmed += 1
            except Exception as exc:
                logger.warning("customer-view warm failed for %s: %s", name, exc)
    return warmed
```

- [ ] **Step 4: Run the whole file** (existing `test_warm_customer_view_calls_getters_per_customer` asserts `m_res.call_count == 2` for 2 customers with a bare `{"preset":"7d"}` tr; `_warm_tr_variants` of that base yields 2 variants → resources called 2×2=4. **Update that existing assertion** to `m_res.call_count == 4` and `m_it.call_count == 4`, `m_av.call_count == 4`, since we now warm both variants.)

Run: `python -m pytest tests/test_warm_customer_view.py -v`
Expected: PASS (4 tests) after updating the counts in the pre-existing test.

- [ ] **Step 5: Commit**

```bash
git add src/services/app_background_warm.py tests/test_warm_customer_view.py
git commit -m "fix(warm): warm both anchor_latest variants for customer-view (kills warm/request key mismatch)"
```

### Task 3: A server-side timer actually warms customer-view (R4)

**Files:**
- Modify: `src/services/app_background_warm.py` (`warm_common`, `:219-237`)
- Test: `tests/test_warm_common.py`

**Interfaces:**
- Consumes: `WARMED_CUSTOMERS` from `src.services.db_service`; `_warm_customer_view`.
- Produces: `warm_common(time_range)` additionally warms customer-view for `WARMED_CUSTOMERS` and reports `stats["customer_view"]`. `warm_common` is already invoked by the server-side `_periodic_common_warm` daemon every 240s (`app.py:177-193`), so this gives customer-view a real timer independent of browser events.

- [ ] **Step 1: Write the failing test** (append to `tests/test_warm_common.py`):

```python
def test_warm_common_warms_customer_view_for_warmed_customers():
    from src.services import app_background_warm as warm
    with patch("src.services.app_background_warm._warm_home_bundle"), \
         patch("src.services.app_background_warm._warm_dc_and_availability_sla", return_value=0), \
         patch("src.services.api_client.get_all_datacenters_summary", return_value=[]), \
         patch("src.services.db_service.WARMED_CUSTOMERS", ("Acme", "Globex")), \
         patch("src.services.app_background_warm._warm_customer_view", return_value=2) as m_cv:
        stats = warm.warm_common({"preset": "7d"})
    m_cv.assert_called_once()
    assert stats.get("customer_view") == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_warm_common.py::test_warm_common_warms_customer_view_for_warmed_customers -v`
Expected: FAIL — `_warm_customer_view` not called; no `customer_view` key.

- [ ] **Step 3: Add customer-view warm to `warm_common`** (after the SLA warm, guard on pause):

```python
def warm_common(time_range: dict | None = None) -> dict:
    from src.services import api_client as api
    from src.services.db_service import WARMED_CUSTOMERS
    from src.utils.time_range import default_time_range

    tr = time_range or default_time_range()
    stats: dict = {"home": False, "dc_avail_sla": 0, "customer_view": 0}
    if _should_pause():
        return stats
    _warm_home_bundle(tr)
    stats["home"] = True
    try:
        dc_rows = api.get_all_datacenters_summary(tr) or []
    except Exception:
        dc_rows = []
    stats["dc_avail_sla"] = _warm_dc_and_availability_sla(dc_rows, tr)
    if not _should_pause() and WARMED_CUSTOMERS:
        stats["customer_view"] = _warm_customer_view(WARMED_CUSTOMERS, tr)
    return stats
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_warm_common.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/app_background_warm.py tests/test_warm_common.py
git commit -m "fix(warm): warm_common seeds customer-view on the 240s server-side timer (not just browser events)"
```

### Task 4: Remove the misleading NO-OP scheduler jobs OR document why they stay

**Files:**
- Modify: `src/services/scheduler_service.py:30-37, 211-240`
- Test: `tests/test_scheduler_customer_warm.py` (create)

**Interfaces:**
- Produces: no scheduler job silently claims to "refresh warmed customers" while doing nothing. Either delete the two dead jobs (`customer_initial_warm`, `customer_warmed_refresh`) and the NO-OP `warm_warmed_customer_caches`, or repoint them at a real warm. Since Task 3 gives customer-view a real 240s timer, deleting the dead jobs is correct and reduces confusion.

- [ ] **Step 1: Write the failing test** (create `tests/test_scheduler_customer_warm.py`):

```python
import inspect
from src.services import scheduler_service


def test_no_noop_customer_warm_hook():
    # The legacy no-op must not exist as a live scheduler target; if it exists it must actually warm.
    assert not hasattr(scheduler_service, "warm_warmed_customer_caches"), \
        "delete the NO-OP customer warm hook; customer-view warm is owned by warm_common (Task 3)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scheduler_customer_warm.py -v`
Expected: FAIL — the function still exists.

- [ ] **Step 3: Delete the NO-OP and its two dead scheduler jobs.** Remove `warm_warmed_customer_caches` (`scheduler_service.py:30-37`) and the `customer_initial_warm` + `customer_warmed_refresh` `add_job` blocks (`:211-240`). Leave the availability-bundle jobs intact.

- [ ] **Step 4: Run tests to verify pass** (and the scheduler still imports/starts)

Run: `python -m pytest tests/test_scheduler_customer_warm.py tests/ -k "scheduler" -v`
Expected: PASS; no import errors.

- [ ] **Step 5: Commit**

```bash
git add src/services/scheduler_service.py tests/test_scheduler_customer_warm.py
git commit -m "chore(scheduler): remove NO-OP customer warm jobs (warm_common now owns customer-view)"
```

### Phase 1 verification (before moving on)

- [ ] Run the affected suites green: `python -m pytest tests/test_warm_customer_view.py tests/test_warm_common.py tests/test_scheduler_customer_warm.py tests/test_app_background_warm.py -v`
- [ ] Live smoke: bring the stack up, then confirm a warmed customer's second load is fast AND a warm cycle populates the anchor key:
  ```bash
  docker logs datalake-platform-gui-app 2>&1 | grep "app_background_warm done" | tail -3
  ```

---

## Phase 2 — Slow/timed-out fetch must not become a permanent empty (R2 + R3)

**Goal:** A cold customer that eventually computes should get served last-good instead of empty, and one slow statement must not throw away a whole computed payload. This is the safety net so that even before Phase 3, the cache "holds" once any success lands.

**Files (to be detailed to full TDD after Phase 0):**
- GUI: `src/services/api_client.py` — `_api_cache_get_with_stale` (`:537-594`), `_should_persist_api_cache` (`:512-521`). Decide the correct behavior on timeout: keep NOT caching empties (correct), but (a) return last-good if present, (b) surface a "degraded/loading" signal to the page instead of a silent empty so the UI can retry rather than render zeros.
- customer-api: `services/customer-api/app/services/customer_service.py` (`get_customer_resources` `:409-443`, `_stale_customer_resources` `:445-457`) and the cache backend `run_singleflight`/`cache_set` — evaluate incremental/last-good writes so a partial success seeds `last_good`.
- Timeout alignment: `.env` / docker-compose `API_INTERACTIVE_READ_TIMEOUT` (120) vs customer-api `DB_STATEMENT_TIMEOUT_MS` (120000) vs the per-endpoint budget — ensure a completing backend call is not abandoned by the caller a moment too early, and that the backend's own statement timeout doesn't 503 a query that Phase 3 will bring under budget.

**Test intent:** (1) on fetch timeout with a prior last-good present, the getter returns last-good (not empty) and does not overwrite it; (2) customer-api returns a cached/last-good payload on `QueryTimeoutError` when one exists; (3) the persist guard still refuses a genuinely-empty payload.

**Expand to full bite-sized TDD tasks once Phase 0 confirms whether the caller ever abandons a call the backend would have completed.**

---

## Phase 3 — Make `/resources` complete within budget (R1). Approach chosen by Phase 0.

**Goal:** Bring cold `/resources` from ~104s to within the interactive budget so the first (and warm) fetch actually completes and caches.

**Candidate approaches (Phase 0 picks one, with its measured win):**
- **A — pg_trgm GIN index** on `public.vm_metrics(vmname)`, `public.nutanix_vm_metrics(vm_name)`, and the LPAR name column: `CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE INDEX CONCURRENTLY ... USING gin (vmname gin_trgm_ops);`. Converts the `ILIKE '%name%'` filter into an index condition. Requires superuser for the extension; on TimescaleDB the index propagates to chunks. Add as a new SQL migration under `services/customer-api/migrations/` with a matching test that the migration file exists and is idempotent.
- **B — anchored pattern + existing btree** (`vm_metrics_vmname_idx`): only if customer VM names are reliably PREFIXED by the resolved token; Phase 0 must verify prefix-match recall vs the current substring match (must not drop VMs).
- **C — resolve customer → exact vmname set once** (cheap, cached) then `WHERE vmname = ANY(%s)`; removes ILIKE entirely. Highest recall risk if the resolver is incomplete.
- **D — reduce the ~30 sequential statements**: combine the per-metric CTEs into fewer round-trips, and/or run independent statements concurrently on separate pool connections.
- **E — per-customer materialized rollup** refreshed by the warm batch; the endpoint reads the rollup.

**Files:** `services/customer-api/app/db/queries/customer.py`, `services/customer-api/app/adapters/customer_adapter.py` (`_normalize_ilike_pattern` `:36-42`, `fetch` `:63+`), a new migration in `services/customer-api/migrations/`, and `services/customer-api/tests/` for query/plan assertions.

**Test intent:** the chosen query returns the SAME rows/totals as today for a known customer (DEVUPS: vms_total 14, cpu 92) but with an index-assisted plan; a regression test pins the totals so a perf rewrite can't silently change results.

**Expand to full bite-sized TDD tasks after Phase 0.**

---

## Phase 4 — Fleet cache-backend hardening (R7). k8s-only; independent.

**Goal:** A frontend pod that boots before Redis is reachable must not latch to a per-pod in-process cache for its whole life; a Redis restart must not silently wipe the fleet cache with no recovery.

**Files (to be detailed after Phases 1-3):**
- `src/services/cache_service.py` — `make_backend_from_env` / module-level `_backend` (`:192-221`): add a lazy re-selection / reconnect so an import-time Redis miss can recover (retry on first use, or a small background re-ping), instead of a permanent `InProcessBackend` latch. Same class of fix for `src/auth/permission_service.py:22-41`.
- `k8s/frontend/deployment.yaml` — add a readiness gate / init dependency on Redis so pods don't win the boot race against Redis.
- `k8s/redis/deployment.yaml` — add a PVC so a Redis restart doesn't flush the shared cache (or accept ephemerality and rely on fast re-warm from Phases 1-3).

**Test intent:** `make_backend_from_env` with an initially-unreachable Redis that later becomes reachable ends up on `RedisBackend` (not a permanent in-process latch); a `k8s` manifest test asserts the readiness/PVC wiring (mirror `tests/test_frontend_redis_wiring.py`).

**Expand to full bite-sized TDD tasks when reached.**

---

## Self-Review notes

- **Spec coverage:** R1→Phase 3, R2/R3→Phase 2, R4→Phase 1 (Tasks 1,3,4), R5→Phase 1 (Task 2), R6 ruled out (no task — mapping resolves correctly, confirmed live), R7→Phase 4. Phase 0 de-risks Phase 3.
- **Ordering rationale:** Phase 0 is cheap and decides Phase 3; Phase 1 is low-risk, GUI-only, and independently deployable for immediate relief on warmed customers; Phase 2 is the safety net; Phase 3 is the root but heaviest/riskiest (DB); Phase 4 is fleet-only.
- **Phases 2-4 are intentionally outlined, not fully expanded** — expanding them to bite-sized TDD before Phase 0's measurement would be speculative. Expand each when its predecessor completes.
