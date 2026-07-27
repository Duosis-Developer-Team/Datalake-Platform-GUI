-- services/customer-api/migrations/webui/030_licensed_os_panel_split.sql
-- Licensed OS: split the Windows guest-OS licence out of the SPLA bucket.
--
-- Why: `license_microsoft_spla` mixed three incompatible units —
--   * MS Windows Lisans .................... per VM   (1,294 qty live)  <- the OS licence
--   * SPLA - MS SQL Server 2 Core .......... per core (204 qty)
--   * SPLA - RDP Kullanıcı Lisans (RDS CAL)  per seat (612 qty)
-- Summing them produced a "sold Windows OS licences" figure that cannot be
-- compared with a detected Windows VM count. `license_windows_os` isolates the
-- per-VM OS SKU so detected-vs-sold reconciliation is unit-coherent.
--
-- Idempotent. Operator rows in gui_crm_service_mapping_override are untouched.
BEGIN;

-- 1) Panel definition (sellable/inventory registry).
INSERT INTO gui_panel_definition
    (panel_key, label, family, resource_kind, display_unit, sort_order,
     enabled, notes, updated_by, updated_at)
VALUES
    ('license_windows_os', 'MS Windows Lisans', 'license_os', 'other', 'per VM', 0,
     TRUE,
     'Windows guest-OS licence (per VM). Split from license_microsoft_spla so detected Windows VMs can be reconciled against sold licences.',
     'seed', NOW())
ON CONFLICT (panel_key) DO UPDATE SET
    label         = EXCLUDED.label,
    family        = EXCLUDED.family,
    resource_kind = EXCLUDED.resource_kind,
    display_unit  = EXCLUDED.display_unit,
    enabled       = EXCLUDED.enabled,
    notes         = COALESCE(NULLIF(EXCLUDED.notes, ''), gui_panel_definition.notes),
    updated_by    = 'seed',
    updated_at    = NOW();

UPDATE gui_panel_definition
SET    inventory_visible = TRUE,
       updated_by = 'seed',
       updated_at = NOW()
WHERE  panel_key = 'license_windows_os';

-- 2) Service page (CRM category the mapping seed points at).
INSERT INTO gui_crm_service_pages
    (page_key, category_label, gui_tab_binding, resource_unit, panel_key)
VALUES
    ('license_windows_os', 'MS Windows Lisans', 'licensing.os', 'per VM', 'license_windows_os')
ON CONFLICT (page_key) DO UPDATE SET
    category_label  = EXCLUDED.category_label,
    gui_tab_binding = EXCLUDED.gui_tab_binding,
    resource_unit   = EXCLUDED.resource_unit,
    panel_key       = EXCLUDED.panel_key;

-- 3) Re-point the MS Windows Lisans product at the new page.
--    discovery_crm_products lives in the datalake DB, so this migration cannot join
--    by name; the productid is pinned here (009LT-13, verified live 2026-07-27).
--    Re-running shared/sellable/generate_panel_mapping_sql.py against a fresh CSV
--    reclassifies it from panel_mapping.classify() and supersedes this row.
INSERT INTO gui_crm_service_mapping_seed (productid, page_key)
VALUES ('84625018-5c6d-f011-b4cc-6045bd93381c', 'license_windows_os')
ON CONFLICT (productid) DO UPDATE SET page_key = EXCLUDED.page_key;

COMMIT;
