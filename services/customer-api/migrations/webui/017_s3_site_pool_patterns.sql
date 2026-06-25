-- 017_s3_site_pool_patterns.sql
-- Document datalake pool_name ILIKE patterns for site-scoped S3 inventory panels.
-- Runtime mapping lives in SellableService._SITE_SCOPED_PANEL_PATTERNS.

BEGIN;

UPDATE gui_panel_infra_source
SET
    notes = 'pool_name ILIKE %DC14% (Ankara ICOS pool).',
    updated_at = NOW()
WHERE panel_key = 'storage_s3_ankara'
  AND dc_code = '*';

UPDATE gui_panel_infra_source
SET
    notes = 'pool_name ILIKE %DC13% (Istanbul ICOS pool).',
    updated_at = NOW()
WHERE panel_key = 'storage_s3_istanbul'
  AND dc_code = '*';

COMMIT;
