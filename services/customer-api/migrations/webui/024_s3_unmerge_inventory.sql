-- 024_s3_unmerge_inventory.sql
-- Show S3 Ankara and Istanbul as separate inventory rows; hide merged synthetic storage_s3 row.

BEGIN;

-- Site nodes visible in inventory (no merge into storage_s3).
UPDATE gui_panel_definition
SET    inventory_merge_target = NULL,
       updated_at = NOW(),
       updated_by = 'seed'
WHERE  panel_key IN ('storage_s3_ankara', 'storage_s3_istanbul');

-- Synthetic merged row kept for registry/CRM legacy only — not shown in inventory UI.
UPDATE gui_panel_definition
SET    inventory_visible = FALSE,
       updated_at = NOW(),
       updated_by = 'seed'
WHERE  panel_key = 'storage_s3';

COMMIT;
