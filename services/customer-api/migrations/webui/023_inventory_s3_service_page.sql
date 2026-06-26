-- 023_inventory_s3_service_page.sql
-- Align legacy storage_s3 CRM page with merged IBM ICOS S3 inventory row.

BEGIN;

UPDATE gui_crm_service_pages
SET    category_label = 'IBM ICOS S3',
       resource_unit = 'TB',
       panel_key = 'storage_s3'
WHERE  page_key = 'storage_s3';

COMMIT;
