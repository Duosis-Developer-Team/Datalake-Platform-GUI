-- 008_seed_resource_ratios.sql
-- Seeds per-environment CPU : RAM : Storage ratios used to compute the
-- "constrained sellable" projection. Each ratio answers:
--   "1 CPU unit can be paired with N GB RAM and M GB Storage."
--
-- For environments without a CPU/RAM/Storage triplet (e.g. backup-only,
-- license-only families) the row is informational and used by the
-- SellableService only when all three resource_kinds exist.
--
-- Operators can override these from the Settings UI; updated_by tracks
-- the source so seed re-runs do not clobber manual changes
-- (the SellableService applies seed-only updates conditionally).

BEGIN;

INSERT INTO gui_panel_resource_ratio
    (family, dc_code, cpu_per_unit, ram_gb_per_unit, storage_gb_per_unit, notes, updated_by)
VALUES
    ('virt_hyperconverged',       '*', 1.0,  8.0, 100.0, 'Hyperconverged: 1 vCPU paired with 8 GB RAM, 100 GB SSD.', 'seed'),
    ('virt_classic',              '*', 1.0,  4.0, 100.0, 'Klasik Mimari: lower memory ratio for general workloads.', 'seed'),
    ('virt_power',                '*', 1.0, 16.0, 200.0, 'IBM Power LPAR: higher memory per core.',                  'seed'),
    ('virt_intel_hana',           '*', 1.0, 16.0, 150.0, 'SAP Intel HANA in-memory profile.',                        'seed'),
    ('virt_power_hana',           '*', 1.0, 32.0, 200.0, 'SAP Power HANA in-memory profile.',                        'seed'),
    ('backup_veeam_replication',  '*', 1.0,  4.0,  50.0, 'Replication compute is small; storage dominates.',         'seed'),
    ('backup_zerto_replication',  '*', 1.0,  4.0,  50.0, '',                                                         'seed')
ON CONFLICT (family, dc_code) DO UPDATE SET
    cpu_per_unit        = CASE WHEN gui_panel_resource_ratio.updated_by = 'seed' THEN EXCLUDED.cpu_per_unit        ELSE gui_panel_resource_ratio.cpu_per_unit END,
    ram_gb_per_unit     = CASE WHEN gui_panel_resource_ratio.updated_by = 'seed' THEN EXCLUDED.ram_gb_per_unit     ELSE gui_panel_resource_ratio.ram_gb_per_unit END,
    storage_gb_per_unit = CASE WHEN gui_panel_resource_ratio.updated_by = 'seed' THEN EXCLUDED.storage_gb_per_unit ELSE gui_panel_resource_ratio.storage_gb_per_unit END,
    notes               = COALESCE(NULLIF(EXCLUDED.notes,''), gui_panel_resource_ratio.notes),
    updated_at          = NOW();

COMMIT;
