-- 029_netbackup_image_application_panels.sql
-- Split NetBackup CRM inventory into image (000BLT-203) and application (000BLT-142)
-- panels. Legacy backup_netbackup_storage remains for merge/registry but is hidden
-- from inventory (ADR-0030 / K-01 dual basis).

BEGIN;

-- Image + application panels (family backup_netbackup, storage, TB, inventory visible).
INSERT INTO gui_panel_definition (
    panel_key, label, family, resource_kind, display_unit, sort_order,
    enabled, inventory_visible, notes, updated_by, updated_at
) VALUES
    (
        'backup_netbackup_image',
        'NetBackup — Image',
        'backup_netbackup',
        'storage',
        'TB',
        231,
        TRUE,
        TRUE,
        'Veritas NetBackup image (000BLT-203) — pool capacity; used/sold PreDedup from finished BACKUP jobs (K-01)',
        'seed',
        NOW()
    ),
    (
        'backup_netbackup_application',
        'NetBackup — Application',
        'backup_netbackup',
        'storage',
        'TB',
        232,
        TRUE,
        TRUE,
        'Veritas NetBackup application (000BLT-142) — used/sold PreDedup from finished BACKUP jobs (K-01); pool capacity shared',
        'seed',
        NOW()
    )
ON CONFLICT (panel_key) DO UPDATE SET
    label             = EXCLUDED.label,
    family            = EXCLUDED.family,
    resource_kind     = EXCLUDED.resource_kind,
    display_unit      = EXCLUDED.display_unit,
    sort_order        = EXCLUDED.sort_order,
    inventory_visible = EXCLUDED.inventory_visible,
    notes             = COALESCE(NULLIF(EXCLUDED.notes, ''), gui_panel_definition.notes),
    updated_by        = 'seed',
    updated_at        = NOW();

-- Keep legacy storage panel as registry/merge parent; hide from inventory UI.
UPDATE gui_panel_definition
SET    inventory_visible = FALSE,
       notes             = COALESCE(
           NULLIF(notes, ''),
           'Legacy NetBackup storage panel — superseded by image/application; kept for merge/registry'
       ),
       updated_by        = 'seed',
       updated_at        = NOW()
WHERE  panel_key = 'backup_netbackup_storage';

-- CRM service pages for the split panels (004 / 010 patterns).
INSERT INTO gui_crm_service_pages (page_key, category_label, gui_tab_binding, resource_unit, panel_key)
VALUES
    ('backup_netbackup_image',       'NetBackup — Image',       'backup.netbackup', 'TB', 'backup_netbackup_image'),
    ('backup_netbackup_application', 'NetBackup — Application', 'backup.netbackup', 'TB', 'backup_netbackup_application')
ON CONFLICT (page_key) DO UPDATE SET
    category_label  = EXCLUDED.category_label,
    gui_tab_binding = EXCLUDED.gui_tab_binding,
    resource_unit   = EXCLUDED.resource_unit,
    panel_key       = EXCLUDED.panel_key;

-- Remap CRM products: 000BLT-203 → image, 000BLT-142 → application.
-- productid c87bff30 = 000BLT-203 (Image); d2635018 = 000BLT-142 (Application).
UPDATE gui_crm_service_mapping_seed
SET    page_key = 'backup_netbackup_image'
WHERE  productid = 'c87bff30-1dd0-f011-8544-7c1e52724e0e';

UPDATE gui_crm_service_mapping_seed
SET    page_key = 'backup_netbackup_application'
WHERE  productid = 'd2635018-5c6d-f011-b4cc-6045bd93381c';

-- Infra sources: used semantics from jobs (PreDedup); capacity from disk pools where applicable.
INSERT INTO gui_panel_infra_source
    (panel_key, dc_code, source_table, total_column, total_unit,
     allocated_table, allocated_column, allocated_unit, filter_clause, notes, updated_by)
VALUES
    (
        'backup_netbackup_image', '*',
        'raw_netbackup_disk_pools_metrics', 'usablesizebytes', 'bytes',
        'raw_netbackup_jobs_metrics', 'kilobytestransferred', 'KiB',
        NULL,
        'Total from disk pools; used/sold PreDedup from finished BACKUP jobs (image/VMWARE policy types). PostDedup is cost-only.',
        'seed'
    ),
    (
        'backup_netbackup_application', '*',
        'raw_netbackup_disk_pools_metrics', 'usablesizebytes', 'bytes',
        'raw_netbackup_jobs_metrics', 'kilobytestransferred', 'KiB',
        NULL,
        'Shared pool capacity; used/sold PreDedup from finished BACKUP jobs (non-image policy types). PostDedup is cost-only.',
        'seed'
    )
ON CONFLICT (panel_key, dc_code) DO UPDATE SET
    source_table     = EXCLUDED.source_table,
    total_column     = EXCLUDED.total_column,
    total_unit       = EXCLUDED.total_unit,
    allocated_table  = EXCLUDED.allocated_table,
    allocated_column = EXCLUDED.allocated_column,
    allocated_unit   = EXCLUDED.allocated_unit,
    filter_clause    = EXCLUDED.filter_clause,
    notes            = COALESCE(NULLIF(EXCLUDED.notes, ''), gui_panel_infra_source.notes),
    updated_by       = 'seed',
    updated_at       = NOW();

COMMIT;
