-- 046_fix_netbackup_image_app_product_map.sql
-- Migration 032 swapped NetBackup Image/Application product GUIDs.
-- Live bulutlake mapping:
--   c87bff30-… = 000BLT-203 Klasik Mimari İmaj Yedekleme → backup_netbackup_image
--   d2635018-… = 000BLT-142 Uygulama Yedekleme Hizmeti   → backup_netbackup_application

BEGIN;

UPDATE gui_crm_service_mapping_seed
SET    page_key = 'backup_netbackup_image'
WHERE  productid = 'c87bff30-1dd0-f011-8544-7c1e52724e0e';

UPDATE gui_crm_service_mapping_seed
SET    page_key = 'backup_netbackup_application'
WHERE  productid = 'd2635018-5c6d-f011-b4cc-6045bd93381c';

-- Keep override table in sync when operators remapped the same productids.
UPDATE gui_crm_service_mapping_override
SET    page_key = 'backup_netbackup_image'
WHERE  productid = 'c87bff30-1dd0-f011-8544-7c1e52724e0e';

UPDATE gui_crm_service_mapping_override
SET    page_key = 'backup_netbackup_application'
WHERE  productid = 'd2635018-5c6d-f011-b4cc-6045bd93381c';

COMMIT;
