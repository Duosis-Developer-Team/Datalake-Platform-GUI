-- 039: NetBackup allocated_unit must match pool query units (bytes).
-- Migration 032 set allocated_unit=KiB (jobs column metadata) but
-- _query_netbackup_storage_totals returns pool usedcapacitybytes as bytes.
-- Missing KiB→TB conversion caused false-positive unit_conversion_missing.

UPDATE gui_panel_infra_source
SET allocated_table = 'raw_netbackup_disk_pools_metrics',
    allocated_column = 'usedcapacitybytes',
    allocated_unit = 'bytes',
    notes = CASE
        WHEN COALESCE(notes, '') LIKE '%allocated matches pool bytes%' THEN notes
        WHEN COALESCE(notes, '') = '' THEN 'Total/allocated from disk pools (bytes); PreDedup used overlay from jobs in inventory'
        ELSE notes || '; allocated matches pool bytes (039)'
    END,
    updated_by = 'seed',
    updated_at = NOW()
WHERE panel_key IN ('backup_netbackup_image', 'backup_netbackup_application')
  AND dc_code = '*';
