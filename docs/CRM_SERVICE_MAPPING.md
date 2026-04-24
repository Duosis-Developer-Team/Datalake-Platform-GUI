# CRM service mapping

## Summary

Maps each `discovery_crm_products.productid` to a stable **`page_key`** (same semantics as the former `category_code`, e.g. `virt_classic`, `backup_veeam`) for:

- `/customers/{name}/sales/efficiency-by-category` (sold vs used)
- Datacenter CRM potential queries (`v_gui_crm_product_mapping` JOIN)

**GUI tab labels** (`gui_tab_binding`, e.g. `virtualization.classic`) are stored alongside each `page_key` in `gui_crm_service_pages`.

## Layers

1. **YAML** — [`config/crm_service_mapping.yaml`](../config/crm_service_mapping.yaml) documents the page registry for humans and release review.
2. **DB seed** — `gui_crm_service_mapping_seed` + `gui_crm_service_pages`, populated by [`datalake/SQL/CRM/migrations/2026-04-24-gui-crm-service-mapping.sql`](../../datalake/SQL/CRM/migrations/2026-04-24-gui-crm-service-mapping.sql) (regenerate via `shared/service_mapping/generate_seed_sql.py`).
3. **DB override** — `gui_crm_service_mapping_override`, edited from **Settings › CRM › Service mapping** (`/settings/crm/service-mapping`).

Effective mapping is exposed as view **`v_gui_crm_product_mapping`**.

## ADR

See [ADR-0011](../../datalake-platform-knowledge-base/adrs/ADR-0011-crm-service-mapping-yaml-db-override.md).
