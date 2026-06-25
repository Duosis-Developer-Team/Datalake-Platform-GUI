-- 018_fix_allocated_units.sql
-- Redis stor_provisioned_gb fields are GB; allocated_unit must not be TB (×1024 bug).

BEGIN;

UPDATE gui_panel_infra_source
SET
    allocated_unit = 'GB',
    notes = COALESCE(NULLIF(notes, ''), '') || ' [018: allocated_unit=GB for stor_provisioned_gb]',
    updated_at = NOW()
WHERE allocated_column IN ('provisioned_space_gb', 'disk_capacity');

COMMIT;
