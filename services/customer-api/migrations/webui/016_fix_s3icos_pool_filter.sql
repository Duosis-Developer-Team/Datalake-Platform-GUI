-- 016_fix_s3icos_pool_filter.sql
-- raw_s3icos_pool_metrics has pool_name, not site_name.

BEGIN;

UPDATE gui_panel_infra_source
SET
    filter_clause = 'pool_name ILIKE :dc_pattern',
    notes = COALESCE(
        NULLIF(notes, ''),
        'S3ICOS filter: pool_name ILIKE :dc_pattern (not site_name).'
    ),
    updated_at = NOW()
WHERE panel_key IN ('storage_s3_ankara', 'storage_s3_istanbul')
  AND filter_clause ILIKE '%site_name%';

COMMIT;
