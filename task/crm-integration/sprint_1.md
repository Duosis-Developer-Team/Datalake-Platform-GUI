# CRM integration — Sprint 1 (realized sales scope + GUI)

## Scope (ADR-0010)

- Collectors / DB: **realized sales only** (sales orders fulfilled/invoiced), customer + product category aliases.
- **customer-api**: sales summary, items, efficiency, **efficiency-by-category**, product category CRUD on `discovery_crm_product_category_alias`.
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
