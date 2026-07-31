-- 033_backup_replication_inventory_visible.sql
-- Show Veeam/Zerto replication, image, and remote backup panels on CRM
-- inventory. Keep legacy NetBackup storage panel hidden (image/application
-- split from 032 remains the inventory surface).

BEGIN;

UPDATE gui_panel_definition
SET    inventory_visible = TRUE,
       updated_by        = 'seed',
       updated_at        = NOW()
WHERE  panel_key LIKE 'backup_veeam_replication_%'
   OR  panel_key LIKE 'backup_zerto_replication_%'
   OR  panel_key IN ('backup_image_hyperconverged', 'backup_remote_nutanix');

UPDATE gui_panel_definition
SET    inventory_visible = FALSE,
       updated_by        = 'seed',
       updated_at        = NOW()
WHERE  panel_key = 'backup_netbackup_storage';

COMMIT;
