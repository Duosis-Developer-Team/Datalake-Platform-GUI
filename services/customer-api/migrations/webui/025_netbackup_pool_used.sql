-- 025_netbackup_pool_used.sql
-- NetBackup inventory: Used from pool usedcapacitybytes (datacenter NetBackup tab semantics).

BEGIN;

UPDATE gui_panel_definition
SET    notes        = 'Veritas NetBackup — pool capacity (latest per host+name); used from pool usedcapacitybytes; pre-dedup from finished BACKUP jobs (display sub-lines)',
       updated_by   = 'seed',
       updated_at   = NOW()
WHERE  panel_key = 'backup_netbackup_storage';

COMMIT;
