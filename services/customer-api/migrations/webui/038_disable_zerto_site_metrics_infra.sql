-- 038: Disable raw_zerto_site_metrics as Zerto storage infra source.
-- Blind SUM over history rows inflated Potential Sales to ~4B TL.
-- Sellable must use /compute/backup-zerto-storage only.

UPDATE gui_panel_infra_source
SET source_table = NULL,
    total_column = NULL,
    total_unit = NULL,
    allocated_table = NULL,
    allocated_column = NULL,
    allocated_unit = NULL,
    filter_column = NULL,
    filter_pattern = NULL,
    notes = COALESCE(notes, '') || CASE
        WHEN COALESCE(notes, '') = '' THEN 'disabled: use backup-zerto-storage compute (038)'
        WHEN notes LIKE '%backup-zerto-storage%' THEN ''
        ELSE '; disabled: use backup-zerto-storage compute (038)'
    END
WHERE panel_key IN (
    'backup_zerto_replication_storage',
    'backup_zerto_replication_classic_storage',
    'backup_zerto_replication_hyperconverged_storage'
)
AND LOWER(COALESCE(source_table, '')) = 'raw_zerto_site_metrics';
