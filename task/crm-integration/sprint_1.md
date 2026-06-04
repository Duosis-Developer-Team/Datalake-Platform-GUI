# CRM integration — Sprint 1 (realized sales scope + GUI)

## Scope (ADR-0010)

- Collectors / DB: **realized sales only** (sales orders fulfilled/invoiced), customer + product category aliases.
- **customer-api**: sales summary, items, efficiency, **efficiency-by-category**, CRM service mapping CRUD on `gui_crm_service_mapping_override` + view `v_gui_crm_product_mapping`.
- **datacenter-api**: **GET `/datacenters/{dc}/sales-potential/v2`** (80% sellable rule, Nutanix capacity proxy).
- **GUI**: remove standalone Sales tab; Billing + category tabs show **Sold vs Used**; DC list/detail show CRM potential; settings links for CRM aliases + product categories.

## Phases & status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Collector + SQL + docs (datalake repo) | Done (prior) |
| 2 | Category rules + alias DDL/seed | Done (prior) |
| 2c | Product category settings UI + customer-api routes | Done |
| 3 | customer-api efficiency-by-category + customer_view | Done |
| 4 | DC sales-potential v2 + datacenters/dc_view | Done |
| 5 | Tests + this doc | Done |

## Test checklist

- [x] `services/customer-api`: `pytest tests/test_efficiency_usage.py tests/test_sales_service_realized_only.py`
- [x] `services/datacenter-api`: `pytest tests/test_crm_potential_v2.py`
- [x] GUI root: `pytest tests/test_customer_view_sold_vs_used.py tests/test_datacenters_potential_ribbon.py`
- [ ] Manual: open Customer View → Billing KPI + category tabs panels; DC list ribbon; DC Summary CRM card; Settings → CRM product categories save.

## Branching (repo policy)

1. `feature/crm-scope-cleanup` (Phase 1 — datalake)
2. `feature/crm-product-category-alias` (Phase 2)
3. `feature/gui-customer-efficiency-by-category` (Phase 3)
4. `feature/gui-dc-sales-potential-v2` (Phase 4)

Merge each into `development`, then `development` → `main` after approval.

## Follow-ups

- NiFi flow XML update (ops).
- S3 usage telemetry for `storage_s3` category.
- DC v2: extend `per_resource` beyond Nutanix CPU/RAM proxy (NetBox rack, power meters).

## crm-engine bugfix (2026-06-04)

- **Redis-first totals**: `SellableService._query_total_allocated` reads `cpu_cap` / `mem_cap` / `power.*` from datacenter-api Redis (`dc_details` / `global_dashboard`) before datalake SQL (fixes 887s IBM LPAR scans).
- **SQL**: `filter_clause` `%` escaping for psycopg2 (`%KM%` panels).
- **Cross-DB**: `_count_unmapped_products` uses webui mapping IDs + datalake `discovery_crm_products` count.
- **Migration**: `016_fix_s3icos_pool_filter.sql` (`site_name` → `pool_name` on S3 panels).
- **Tests**: `pytest services/customer-api/tests/test_sellable_service.py` (51 passed).

## crm-engine startup fix (2026-06-04)

- **Non-blocking lifespan**: initial `snapshot_all` runs via APScheduler (`next_run_time=now`); `CRM_ENGINE_SYNC_SNAPSHOT_ON_STARTUP` defaults false so `/health` is available immediately.
- **Redis preload**: `compute_all_panels` loads `dc_payload` when any panel uses `_infra_uses_dc_redis_payload` (IBM/classic/hyperconv totals, not only VM allocated).
- **Tests**: `services/crm-engine/tests/test_main_startup.py`, `test_compute_all_panels_preloads_redis_for_ibm_power_infra`.

## crm zero-downtime cache (2026-06-04)

- **snapshot_all**: no upfront `invalidate_result_cache()`; successful scopes overwrite Tier-1/Tier-2 in place.
- **admin cache refresh**: crm-engine no longer `flush *` before recompute.
- **Data Centers virt warm**: `datacenters_virt_sellable.py` stale-while-refresh + partial publish merge.
- **GUI api_client**: empty sellable fetch falls back to last LRU entry instead of caching zeros.

## crm dc-wide redis key fix (2026-06-04)

- **Root cause**: `_dc_redis_key` used `today-7` while datacenter-api writes `today-6:today` (7d inclusive) → 100% Redis miss on Data Centers list.
- **Fix**: UTC dates, `start = today - (span_days - 1)`, alternate legacy keys, boundary logs, `summary?preset=7d` prewarm + Redis scan fallback.
- **Recompute bypass**: scheduler/admin refresh now uses `force_recompute=True`, bypassing stale Tier-1/Tier-2 zeros and overwriting only after successful compute.
- **Redis unit normalization**: datacenter-api Redis fields (`cpu_cap` GHz, `mem_cap` GB, `stor_cap` TB) are converted back to configured infra units before existing sellable conversions run.
- **DC-13 verification**: `virt_classic=1,396,549.49 TL`, `virt_hyperconverged=570,081.47 TL`, GUI helper total `1,966,630.958 TL`.
