-- Customer /resources performance — pg_trgm GIN indexes for leading-wildcard ILIKE.
--
-- TARGET DB: the datalake metrics DB (bulutlake, e.g. 10.134.16.6) — NOT the webui DB.
-- This is a DBA action: it needs a SUPERUSER for CREATE EXTENSION (the app role is
-- not superuser). It is NOT run by the app migration runner (this repo does not own
-- the datalake schema).
--
-- WHY: customer /resources filters vm/lpar names with LEADING-wildcard ILIKE
-- ('%name%') across ~30 sequential statements. A leading wildcard cannot use the
-- existing btree (vm_metrics_vmname_idx), so each statement scans the whole time
-- window and applies the ILIKE as a FILTER (~2 s each → ~104 s cold). A pg_trgm GIN
-- index makes ILIKE '%x%' an index condition (~2 s → ~0.1 s), bringing the whole
-- endpoint well under the caller timeout — no application change required.
--
-- NOTE ON TIMESCALEDB: vm_metrics / nutanix_vm_metrics are hypertables. CREATE INDEX
-- propagates to existing and future chunks. CREATE INDEX CONCURRENTLY on a hypertable
-- requires running OUTSIDE a transaction block (psql default) and, on older TimescaleDB,
-- may need `SET timescaledb.transaction_per_chunk = on;`. If CONCURRENTLY errors on the
-- hypertable, drop the CONCURRENTLY keyword (locks writes briefly per chunk).
--
-- VERIFY AFTER: re-run EXPLAIN on the query below and confirm the plan shows a
-- "Bitmap Index Scan ... *_trgm" instead of "Filter: vmname ~~* '%...%'".

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX CONCURRENTLY IF NOT EXISTS vm_metrics_vmname_trgm
    ON public.vm_metrics USING gin (vmname gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS nutanix_vm_metrics_vm_name_trgm
    ON public.nutanix_vm_metrics USING gin (vm_name gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ibm_lpar_general_lparname_trgm
    ON public.ibm_lpar_general USING gin (lparname gin_trgm_ops);

-- Verification query (should use the trgm index after the above):
-- EXPLAIN SELECT DISTINCT ON (vmname) vmname FROM public.vm_metrics
--   WHERE vmname ILIKE '%DEVUPS%' AND timestamp BETWEEN '2026-07-04' AND '2026-07-10'
--   ORDER BY vmname, timestamp DESC;
--
-- ROLLBACK (if ever needed):
-- DROP INDEX CONCURRENTLY IF EXISTS public.vm_metrics_vmname_trgm;
-- DROP INDEX CONCURRENTLY IF EXISTS public.nutanix_vm_metrics_vm_name_trgm;
-- DROP INDEX CONCURRENTLY IF EXISTS public.ibm_lpar_general_lparname_trgm;
