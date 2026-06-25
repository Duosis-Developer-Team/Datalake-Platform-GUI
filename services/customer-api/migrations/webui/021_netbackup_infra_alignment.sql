-- 021_netbackup_infra_alignment.sql
-- NetBackup inventory panel: display TB (not GB) and document jobs-based used semantics.

BEGIN;

UPDATE gui_panel_definition
SET    display_unit = 'TB',
       notes        = 'Veritas NetBackup — pool capacity (latest per host+name); used from jobs post-dedup',
       updated_by   = 'seed',
       updated_at   = NOW()
WHERE  panel_key = 'backup_netbackup_storage';

COMMIT;
