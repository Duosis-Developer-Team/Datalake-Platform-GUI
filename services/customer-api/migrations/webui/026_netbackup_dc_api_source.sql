-- 026_netbackup_dc_api_source.sql
-- NetBackup inventory pool metrics sourced via datacenter-api (DC View parity).

BEGIN;

UPDATE gui_panel_definition
SET    notes        = 'Veritas NetBackup — pool total/used/free via datacenter-api per DC (7d); pre-dedup from finished BACKUP jobs (7d sub-lines)',
       updated_by   = 'seed',
       updated_at   = NOW()
WHERE  panel_key = 'backup_netbackup_storage';

COMMIT;
