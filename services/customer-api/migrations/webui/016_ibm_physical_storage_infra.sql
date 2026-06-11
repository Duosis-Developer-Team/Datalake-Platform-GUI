-- 016_ibm_physical_storage_infra.sql
-- Power storage sellable uses IBM physical capacity (not mdisk/datastore).

BEGIN;

UPDATE gui_panel_infra_source
SET
    total_column = 'physical_capacity',
    allocated_column = 'physical_free_capacity',
    notes = 'Latest row per storage_ip; physical capacity parsed to GB. Used = physical - free.'
WHERE panel_key = 'virt_power_storage'
  AND dc_code = '*'
  AND updated_by = 'seed';

COMMIT;
