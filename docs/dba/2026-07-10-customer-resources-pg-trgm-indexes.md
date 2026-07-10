# DBA Runbook — Customer `/resources` pg_trgm indexes (Phase 3 root fix)

**Owner action:** a DBA/superuser on the **datalake metrics DB** (`bulutlake`, e.g. `10.134.16.6`).
**App change required:** none. This is a pure DB index addition.
**SQL:** `sql/dba/customer_resources_pg_trgm_indexes.sql`

## Why this is the fix (evidence, 2026-07-10)

- Cold `/resources` for a non-warmed customer = **~104 s**, HTTP 200 with real data. It runs ~30 statements sequentially, each ~2 s.
- Each statement filters names with **leading-wildcard ILIKE** (`vmname ILIKE '%name%'`). Leading `%` cannot use the existing btree `vm_metrics_vmname_idx`, so the planner does an index-only scan of the whole time window and applies the ILIKE as a **Filter** (measured ~2.1 s for vm_metrics, ~1.5 s nutanix, ~0.9 s lpar).
- A **pg_trgm GIN index** turns `ILIKE '%x%'` into an index condition → each statement ~2 s → **~0.1 s**. 30 × 0.1 s ≈ 3 s total — well under the 45–120 s caller timeout. **No application change needed.**

## Why we did NOT change application code for this

- Measured serial→parallel of the section queries: only **1.6×** (DB CPU serializes them). A 500-line threading refactor of `CustomerAdapter.fetch` for ~1.6–2.5× is high-risk and, more importantly, **redundant once the index lands** (3 s serial needs no parallelism). So the correct fix is the index, not code.
- The app DB role is **not superuser** (`current_setting('is_superuser') = off`), so the app migration runner cannot `CREATE EXTENSION pg_trgm`. Hence this runbook.

## Steps

1. Connect to the datalake DB as a superuser (psql), NOT inside a transaction block:
   ```
   psql "host=10.134.16.6 dbname=bulutlake user=<superuser>"
   ```
2. Run the script:
   ```
   \i sql/dba/customer_resources_pg_trgm_indexes.sql
   ```
   `vm_metrics` / `nutanix_vm_metrics` are TimescaleDB hypertables — `CREATE INDEX` propagates to all chunks. If `CONCURRENTLY` errors on the hypertable, either `SET timescaledb.transaction_per_chunk = on;` first, or remove the `CONCURRENTLY` keyword (brief per-chunk write lock).
3. Verify the plan now uses the trgm index:
   ```sql
   EXPLAIN SELECT DISTINCT ON (vmname) vmname FROM public.vm_metrics
     WHERE vmname ILIKE '%DEVUPS%' AND timestamp BETWEEN '2026-07-04' AND '2026-07-10'
     ORDER BY vmname, timestamp DESC;
   ```
   Expect a `Bitmap Index Scan ... vm_metrics_vmname_trgm` instead of `Filter: vmname ~~* '%DEVUPS%'`.
4. Re-time the endpoint end-to-end (from the GUI container):
   ```
   docker exec datalake-platform-gui-app python3 -c "import time,urllib.request,urllib.parse; \
   n=urllib.parse.quote('DEVUPS BİLİŞİM TEKNOLOJİ DANIŞMANLIK VE OTOMOTİVTİCARET LİMİTED ŞİRKETİ'); \
   t=time.time(); urllib.request.urlopen('http://customer-api:8000/api/v1/customers/%s/resources?preset=7d'%n,timeout=200).read(); \
   print('%.1fs'%(time.time()-t))"
   ```
   Expect a large drop from ~104 s toward a few seconds cold.

## Rollback

See the `DROP INDEX CONCURRENTLY` lines at the bottom of the SQL file. Dropping the indexes returns to the prior (slow) behavior; it does not affect correctness.

## Interaction with Phases 1–2

Phases 1–2 (already shipped on this branch) make warm effective and self-healing so *warmed* customers are fast regardless. This index is what makes *cold, non-warmed* customers fast on first visit — the remaining gap.
