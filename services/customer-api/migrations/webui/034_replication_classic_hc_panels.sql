-- 034: Classic / Hyperconverged split for Veeam & Zerto replication panels.
-- Adds architecture-specific panel definitions + ratios; keeps legacy panels
-- enabled as fallback until product mappings are remapped by name.

BEGIN;

INSERT INTO gui_panel_definition (
    panel_key, label, family, resource_kind, display_unit, sort_order, notes
) VALUES
    ('backup_veeam_replication_classic_cpu', 'Veeam Replication Classic — CPU',
     'backup_veeam_replication_classic', 'cpu', 'vCPU', 214, 'Klasik Mimari'),
    ('backup_veeam_replication_classic_ram', 'Veeam Replication Classic — RAM',
     'backup_veeam_replication_classic', 'ram', 'GB', 215, 'Klasik Mimari'),
    ('backup_veeam_replication_classic_storage', 'Veeam Replication Classic — Storage',
     'backup_veeam_replication_classic', 'storage', 'GB', 216, 'Klasik Mimari'),
    ('backup_veeam_replication_hyperconverged_cpu', 'Veeam Replication HC — CPU',
     'backup_veeam_replication_hyperconverged', 'cpu', 'vCPU', 217, 'Hyperconverged Mimari'),
    ('backup_veeam_replication_hyperconverged_ram', 'Veeam Replication HC — RAM',
     'backup_veeam_replication_hyperconverged', 'ram', 'GB', 218, 'Hyperconverged Mimari'),
    ('backup_veeam_replication_hyperconverged_storage', 'Veeam Replication HC — Storage',
     'backup_veeam_replication_hyperconverged', 'storage', 'GB', 219, 'Hyperconverged Mimari'),
    ('backup_zerto_replication_classic_cpu', 'Zerto Replication Classic — CPU',
     'backup_zerto_replication_classic', 'cpu', 'vCPU', 223, 'Klasik Mimari'),
    ('backup_zerto_replication_classic_ram', 'Zerto Replication Classic — RAM',
     'backup_zerto_replication_classic', 'ram', 'GB', 224, 'Klasik Mimari'),
    ('backup_zerto_replication_classic_storage', 'Zerto Replication Classic — Storage',
     'backup_zerto_replication_classic', 'storage', 'GB', 225, 'Klasik Mimari'),
    ('backup_zerto_replication_hyperconverged_cpu', 'Zerto Replication HC — CPU',
     'backup_zerto_replication_hyperconverged', 'cpu', 'vCPU', 226, 'Hyperconverged Mimari'),
    ('backup_zerto_replication_hyperconverged_ram', 'Zerto Replication HC — RAM',
     'backup_zerto_replication_hyperconverged', 'ram', 'GB', 227, 'Hyperconverged Mimari'),
    ('backup_zerto_replication_hyperconverged_storage', 'Zerto Replication HC — Storage',
     'backup_zerto_replication_hyperconverged', 'storage', 'GB', 228, 'Hyperconverged Mimari')
ON CONFLICT (panel_key) DO UPDATE SET
    label = EXCLUDED.label,
    family = EXCLUDED.family,
    resource_kind = EXCLUDED.resource_kind,
    display_unit = EXCLUDED.display_unit,
    sort_order = EXCLUDED.sort_order,
    notes = EXCLUDED.notes;

INSERT INTO gui_panel_resource_ratio (
    family, dc_code, cpu_per_unit, ram_gb_per_unit, storage_gb_per_unit, notes, updated_by
) VALUES
    ('backup_veeam_replication_classic', '*', 1.0, 4.0, 50.0,
     'Classic Veeam replication ratios', 'seed'),
    ('backup_veeam_replication_hyperconverged', '*', 1.0, 4.0, 50.0,
     'HC Veeam replication ratios', 'seed'),
    ('backup_zerto_replication_classic', '*', 1.0, 4.0, 50.0,
     'Classic Zerto replication ratios', 'seed'),
    ('backup_zerto_replication_hyperconverged', '*', 1.0, 4.0, 50.0,
     'HC Zerto replication ratios', 'seed')
ON CONFLICT (family, dc_code) DO UPDATE SET
    cpu_per_unit = CASE WHEN gui_panel_resource_ratio.updated_by = 'seed'
                        THEN EXCLUDED.cpu_per_unit
                        ELSE gui_panel_resource_ratio.cpu_per_unit END,
    ram_gb_per_unit = CASE WHEN gui_panel_resource_ratio.updated_by = 'seed'
                           THEN EXCLUDED.ram_gb_per_unit
                           ELSE gui_panel_resource_ratio.ram_gb_per_unit END,
    storage_gb_per_unit = CASE WHEN gui_panel_resource_ratio.updated_by = 'seed'
                               THEN EXCLUDED.storage_gb_per_unit
                               ELSE gui_panel_resource_ratio.storage_gb_per_unit END,
    notes = COALESCE(NULLIF(EXCLUDED.notes, ''), gui_panel_resource_ratio.notes),
    updated_at = NOW();

UPDATE gui_panel_definition
SET    inventory_visible = TRUE,
       updated_by        = 'seed',
       updated_at        = NOW()
WHERE  panel_key LIKE 'backup_veeam_replication_classic_%'
   OR  panel_key LIKE 'backup_veeam_replication_hyperconverged_%'
   OR  panel_key LIKE 'backup_zerto_replication_classic_%'
   OR  panel_key LIKE 'backup_zerto_replication_hyperconverged_%';

INSERT INTO gui_crm_service_pages (page_key, category_label, gui_tab_binding, resource_unit, panel_key) VALUES
    ('backup_veeam_replication_classic_cpu', 'Veeam Replication Classic — CPU', 'backup.veeam_replication', 'vCPU', 'backup_veeam_replication_classic_cpu'),
    ('backup_veeam_replication_classic_ram', 'Veeam Replication Classic — RAM', 'backup.veeam_replication', 'GB', 'backup_veeam_replication_classic_ram'),
    ('backup_veeam_replication_classic_storage', 'Veeam Replication Classic — Storage', 'backup.veeam_replication', 'GB', 'backup_veeam_replication_classic_storage'),
    ('backup_veeam_replication_hyperconverged_cpu', 'Veeam Replication HC — CPU', 'backup.veeam_replication', 'vCPU', 'backup_veeam_replication_hyperconverged_cpu'),
    ('backup_veeam_replication_hyperconverged_ram', 'Veeam Replication HC — RAM', 'backup.veeam_replication', 'GB', 'backup_veeam_replication_hyperconverged_ram'),
    ('backup_veeam_replication_hyperconverged_storage', 'Veeam Replication HC — Storage', 'backup.veeam_replication', 'GB', 'backup_veeam_replication_hyperconverged_storage'),
    ('backup_zerto_replication_classic_cpu', 'Zerto Replication Classic — CPU', 'backup.zerto_replication', 'vCPU', 'backup_zerto_replication_classic_cpu'),
    ('backup_zerto_replication_classic_ram', 'Zerto Replication Classic — RAM', 'backup.zerto_replication', 'GB', 'backup_zerto_replication_classic_ram'),
    ('backup_zerto_replication_classic_storage', 'Zerto Replication Classic — Storage', 'backup.zerto_replication', 'GB', 'backup_zerto_replication_classic_storage'),
    ('backup_zerto_replication_hyperconverged_cpu', 'Zerto Replication HC — CPU', 'backup.zerto_replication', 'vCPU', 'backup_zerto_replication_hyperconverged_cpu'),
    ('backup_zerto_replication_hyperconverged_ram', 'Zerto Replication HC — RAM', 'backup.zerto_replication', 'GB', 'backup_zerto_replication_hyperconverged_ram'),
    ('backup_zerto_replication_hyperconverged_storage', 'Zerto Replication HC — Storage', 'backup.zerto_replication', 'GB', 'backup_zerto_replication_hyperconverged_storage')
ON CONFLICT (page_key) DO UPDATE SET
    category_label = EXCLUDED.category_label,
    gui_tab_binding = EXCLUDED.gui_tab_binding,
    resource_unit = EXCLUDED.resource_unit,
    panel_key = EXCLUDED.panel_key;

COMMIT;
