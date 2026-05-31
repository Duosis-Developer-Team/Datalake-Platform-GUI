-- 015_fix_ibm_power_infra_filter.sql
-- Remove invalid site_name filter on IBM HMC tables (column does not exist).
-- SellableService applies DC scoping via server_details_servername / lpar_details_servername ILIKE.

BEGIN;

UPDATE gui_panel_infra_source
SET
    filter_clause = NULL,
    notes = COALESCE(
        NULLIF(notes, ''),
        'IBM HMC DC filter applied in SellableService (server_details_servername / lpar_details_servername ILIKE).'
    ),
    updated_by = 'seed',
    updated_at = NOW()
WHERE panel_key IN ('virt_power_cpu', 'virt_power_ram')
  AND dc_code = '*'
  AND filter_clause ILIKE '%site_name%';

COMMIT;
