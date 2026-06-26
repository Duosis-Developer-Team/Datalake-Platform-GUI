-- 022_inventory_panel_visibility.sql
-- DB-driven inventory visibility and merge targets (sellable mappings unchanged).

BEGIN;

ALTER TABLE gui_panel_definition
    ADD COLUMN IF NOT EXISTS inventory_visible BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE gui_panel_definition
    ADD COLUMN IF NOT EXISTS inventory_merge_target TEXT NULL;

-- Replication families: hidden from inventory overview only.
UPDATE gui_panel_definition
SET    inventory_visible = FALSE,
       updated_at = NOW(),
       updated_by = 'seed'
WHERE  family IN ('backup_zerto_replication', 'backup_veeam_replication');

-- S3 site nodes merge into unified inventory row.
UPDATE gui_panel_definition
SET    inventory_merge_target = 'storage_s3',
       updated_at = NOW(),
       updated_by = 'seed'
WHERE  panel_key IN ('storage_s3_ankara', 'storage_s3_istanbul');

-- KM sub-family infra rows fold into Klasik Mimari (CRM merge in service layer).
UPDATE gui_panel_definition
SET    inventory_merge_target = 'virt_classic_cpu',
       updated_at = NOW(),
       updated_by = 'seed'
WHERE  panel_key = 'virt_km_cpu';

UPDATE gui_panel_definition
SET    inventory_merge_target = 'virt_classic_ram',
       updated_at = NOW(),
       updated_by = 'seed'
WHERE  panel_key = 'virt_km_ram';

UPDATE gui_panel_definition
SET    inventory_merge_target = 'virt_classic_storage',
       updated_at = NOW(),
       updated_by = 'seed'
WHERE  panel_key = 'virt_km_storage';

-- Unified S3 inventory panel (merged from site nodes).
INSERT INTO gui_panel_definition (
    panel_key, label, family, resource_kind, display_unit, sort_order, enabled, inventory_visible, notes
) VALUES (
    'storage_s3',
    'IBM ICOS S3',
    'storage_s3',
    'storage',
    'TB',
    309,
    TRUE,
    TRUE,
    'Merged inventory row for Ankara + Istanbul ICOS site nodes'
) ON CONFLICT (panel_key) DO UPDATE SET
    label = EXCLUDED.label,
    family = EXCLUDED.family,
    inventory_visible = EXCLUDED.inventory_visible,
    notes = COALESCE(NULLIF(EXCLUDED.notes, ''), gui_panel_definition.notes),
    updated_at = NOW(),
    updated_by = 'seed';

-- NetBackup CRM unit aligns with panel display_unit (TB).
UPDATE gui_crm_service_pages
SET    resource_unit = 'TB',
       updated_at = NOW()
WHERE  page_key = 'backup_netbackup_storage';

COMMIT;
