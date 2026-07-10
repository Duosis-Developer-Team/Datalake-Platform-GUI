# Phase 0 — `/resources` profile & Phase 3 decision

**Date:** 2026-07-10. Measured live against `bulutlake` (10.134.16.6, TimescaleDB) from inside `bulutistan-customer-api`, customer pattern `%DEVUPS%`, window 2026-07-04..2026-07-10.

## Per-statement EXPLAIN ANALYZE (execution time)

| Statement (representative) | Table | Exec time |
|---|---|---|
| `DISTINCT ON (vmname) … number_of_cpus` | `public.vm_metrics` | **~2.1 s** |
| `DISTINCT ON (vm_name)` | `public.nutanix_vm_metrics` | **~1.5 s** |
| LPAR `GROUP BY lparname` (agg) | `public.ibm_lpar_general` | ~0.9 s |
| zabbix full-window `GROUP BY ibm_partition_name` | `raw_zabbix_hana_linux_host_metrics` | ~0.03 s |

Plan for the vm_metrics query: **Index-Only Scan** on `vm_metrics_vmname_idx`, timestamp as the Index Cond, `vmname ~~* '%DEVUPS%'` applied as a **Filter** over the whole 7-day (all-customer) slice. So each statement is index-assisted on the time window but still filters every row by the leading-wildcard ILIKE.

## Why cold `/resources` is ~104 s

`CustomerAdapter.fetch` runs **~30 statements sequentially on ONE connection**. The intel / classic / hyperconv / pure-nutanix / power sections each issue count + resource-totals + deleted + vm-list (≈4 statements) against the metric tables, each re-scanning the same window with the same `ILIKE %pattern%`. ~20 vm_metrics statements × ~2 s + nutanix + lpar + backup ≈ 100 s. **There is no single catastrophic query — the cost is the sheer number of ~2 s statements run serially.**

## Feasibility findings

- **`superuser: off`** on the app DB role → we **cannot** `CREATE EXTENSION pg_trgm` from an app migration. `pg_trgm` IS available to install (`pg_available_extensions` = 1), so a DBA/superuser can add it.
- Existing indexes: `vm_metrics_vmname_idx` (btree, used as index-only scan), `nutanix_vm_metrics_collection_time_idx`. No trigram index anywhere.

## Phase 3 decision

**Primary fix (in our control): reduce + parallelize the ~30 sequential statements.**
- Run the independent per-section statements concurrently across several pool connections (pool max = 16) instead of serially on one. Expected: ~104 s → roughly max-section-time + overhead (target < 20 s cold), bounded by DB CPU and pool size.
- Collapse redundant re-scans: sections that run count + totals + deleted + list as 4 separate window scans of the same table/pattern should be combined where the same scan can yield all of them.
- Guard pool pressure: cap concurrency so a burst of concurrent page loads (6 customer calls each fanning out) does not exhaust the 16-conn pool. Make the fan-out width configurable.

**Secondary fix (DBA-dependent, big multiplier): pg_trgm GIN indexes.**
- File a DBA request: `CREATE EXTENSION pg_trgm;` then `CREATE INDEX CONCURRENTLY … USING gin (vmname gin_trgm_ops)` on `vm_metrics`, `(vm_name)` on `nutanix_vm_metrics`, `(lparname)` on `ibm_lpar_general`. Converts each `ILIKE '%x%'` Filter into an index condition → each ~2 s statement → ~0.1 s. Cannot be done from our migrations (superuser required); track separately.

**Not pursued:** anchored `LIKE 'name%'` (would drop VMs whose name embeds the token mid-string — recall risk); per-customer materialized rollup (larger project; revisit if parallelization is insufficient).

## Impact on the rest of the plan

- **Phase 1 (warm under `warm_mode`)** already gives big relief: with the long warm timeout the ~104 s fetch completes and the backend caches it, so warmed customers are fast on first visit. Confirmed mechanism: once any call completes, the backend serves it in ~0.1 s.
- **Phase 3** brings *cold interactive* (non-warmed customers) under the caller budget for everyone.
- pg_trgm is the highest multiplier but is blocked on a DBA; parallelization is the highest *in-our-control* win.
