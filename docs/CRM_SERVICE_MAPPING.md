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

## Resource unit semantics (per-product / line-level)

- **`gui_crm_service_pages.resource_unit`**: default label for a `page_key` (e.g. `virt_classic` → `vCPU`) — used in **Settings** and as `page_resource_unit` in the view.
- **View `v_gui_crm_product_mapping`**: exposes `resource_unit` as **NULL** so joins prefer **`salesorderdetails.uomid_name`** for sold quantity bucketing (vCPU vs GB). List API maps `page_resource_unit` → `resource_unit` for the Settings table.
- **Migrations**: apply [`2026-04-25-gui-crm-service-mapping-units-and-replication.sql`](../../datalake/SQL/CRM/migrations/2026-04-25-gui-crm-service-mapping-units-and-replication.sql) after `2026-04-24-*` on databases that were created from the older view definition.

## Default name rules (Klasik / replication)

Embedded rule pack ([`shared/service_mapping/embedded_rules.json`](../shared/service_mapping/embedded_rules.json)) — higher priority wins:

1. **Klasik Mimari Zerto Replication** → `backup_zerto`
2. **Klasik Mimari Veeam Replication** → `backup_veeam`
3. **Klasik Mimari Intel (CPU|RAM|Disk)** → `virt_classic`

Regenerate seed SQL with `shared/service_mapping/generate_seed_sql.py` after changing rules; migration `2026-04-25` also updates existing seed rows for replication names.

## Audit queries

See [`datalake/SQL/CRM/audit_crm_service_mapping_gaps.sql`](../../datalake/SQL/CRM/audit_crm_service_mapping_gaps.sql).

## ADR

See [ADR-0011](../../datalake-platform-knowledge-base/adrs/ADR-0011-crm-service-mapping-yaml-db-override.md).
