-- 040: Seed DR replication / offsite panels and remap DR virt CRM products
-- into Replication inventory group (Image | Application | Replication IA).

BEGIN;

INSERT INTO gui_panel_definition (
    panel_key, label, family, resource_kind, display_unit, sort_order,
    enabled, inventory_visible, notes, updated_by, updated_at
) VALUES
    ('backup_replication_cpu', 'Replication — DR CPU', 'backup_replication', 'cpu', 'vCPU', 260, TRUE, TRUE,
     'HC Intel CPU - DR (000BLT-47); CRM Inventory under Replication', 'seed', NOW()),
    ('backup_replication_ram', 'Replication — DR RAM', 'backup_replication', 'ram', 'GB', 261, TRUE, TRUE,
     'HC Intel RAM - DR (000BLT-53)', 'seed', NOW()),
    ('backup_replication_storage', 'Replication — DR Disk', 'backup_replication', 'storage', 'GB', 262, TRUE, TRUE,
     'HC Intel Disk - DR (000BLT-51)', 'seed', NOW())
ON CONFLICT (panel_key) DO UPDATE SET
    label = EXCLUDED.label,
    family = EXCLUDED.family,
    resource_kind = EXCLUDED.resource_kind,
    display_unit = EXCLUDED.display_unit,
    inventory_visible = TRUE,
    notes = COALESCE(NULLIF(EXCLUDED.notes, ''), gui_panel_definition.notes),
    updated_by = 'seed',
    updated_at = NOW();

INSERT INTO gui_crm_service_pages (page_key, category_label, gui_tab_binding, resource_unit, panel_key)
VALUES
    ('backup_replication_cpu', 'Replication — DR CPU', 'backup.replication', 'vCPU', 'backup_replication_cpu'),
    ('backup_replication_ram', 'Replication — DR RAM', 'backup.replication', 'GB', 'backup_replication_ram'),
    ('backup_replication_storage', 'Replication — DR Disk', 'backup.replication', 'GB', 'backup_replication_storage')
ON CONFLICT (page_key) DO UPDATE SET
    category_label = EXCLUDED.category_label,
    gui_tab_binding = EXCLUDED.gui_tab_binding,
    resource_unit = EXCLUDED.resource_unit,
    panel_key = EXCLUDED.panel_key;

-- Remap DR virt products from virt_* page_keys via price_override names
UPDATE gui_crm_service_mapping_seed s
SET    page_key = 'backup_replication_cpu'
FROM   gui_crm_price_override p
WHERE  s.productid = p.productid
  AND  p.product_name ILIKE '%Intel CPU%'
  AND  p.product_name ILIKE '%DR%'
  AND  s.page_key LIKE 'virt_%';

UPDATE gui_crm_service_mapping_seed s
SET    page_key = 'backup_replication_ram'
FROM   gui_crm_price_override p
WHERE  s.productid = p.productid
  AND  p.product_name ILIKE '%Intel RAM%'
  AND  p.product_name ILIKE '%DR%'
  AND  s.page_key LIKE 'virt_%';

UPDATE gui_crm_service_mapping_seed s
SET    page_key = 'backup_replication_storage'
FROM   gui_crm_price_override p
WHERE  s.productid = p.productid
  AND  p.product_name ILIKE '%Intel Disk%'
  AND  p.product_name ILIKE '%DR%'
  AND  s.page_key LIKE 'virt_%';

-- Ensure Image Backup panels stay inventory-visible
UPDATE gui_panel_definition
SET inventory_visible = TRUE,
    updated_at = NOW()
WHERE panel_key IN (
    'backup_image_hyperconverged',
    'backup_remote_nutanix',
    'backup_offsite_veeam',
    'backup_offsite_s3',
    'backup_netbackup_image',
    'backup_netbackup_application'
);

COMMIT;
