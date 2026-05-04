-- 007_seed_panel_infra_sources.sql
-- Maps each panel_key to the datalake table/column that supplies its
-- "total" capacity and "allocated" (provisioned) value, plus the unit those
-- values are stored in. SellableService uses these descriptors to:
--   1) execute the SQL against the datalake DB,
--   2) convert raw units to display_unit via gui_unit_conversion,
--   3) apply threshold and ratio constraints.
--
-- filter_clause is interpolated with :dc_pattern (named placeholder, %% escaped
-- in psycopg). For dc_code='*' the binding is the global default; per-DC rows
-- override the global one (precedence: dc_code = current > '*').

BEGIN;

INSERT INTO gui_panel_infra_source
    (panel_key, dc_code, source_table, total_column, total_unit,
     allocated_table, allocated_column, allocated_unit, filter_clause, notes, updated_by)
VALUES
    -- Hyperconverged Mimari (Nutanix backed)
    ('virt_hyperconverged_cpu', '*',
        'nutanix_cluster_metrics',  'total_cpu_capacity',    'Hz',
        'nutanix_vm_metrics',       'cpu_count',             'vCPU',
        'datacenter_name ILIKE :dc_pattern',
        'Nutanix cluster CPU (Hz at collector level, see nutanix_cluster_dyn.py).', 'seed'),
    ('virt_hyperconverged_ram', '*',
        'nutanix_cluster_metrics',  'total_memory_capacity', 'bytes',
        'nutanix_vm_metrics',       'memory_capacity',       'bytes',
        'datacenter_name ILIKE :dc_pattern',
        'Nutanix cluster + VM memory in bytes.', 'seed'),
    ('virt_hyperconverged_storage', '*',
        'nutanix_cluster_metrics',  'storage_capacity',      'bytes',
        'nutanix_vm_metrics',       'disk_capacity',         'bytes',
        'datacenter_name ILIKE :dc_pattern',
        '', 'seed'),

    -- Klasik Mimari (VMware) — same lineage as datacenter-api vmware.py (datacenter_metrics latest per dc,name)
    ('virt_classic_cpu', '*',
        'v_crm_datacenter_metrics_latest', 'total_cpu_ghz_capacity', 'GHz',
        'vm_metrics',                      'number_of_cpus',        'vCPU',
        'datacenter ILIKE :dc_pattern',
        'Totals from v_crm_datacenter_metrics_latest ( DISTINCT ON dc,datacenter from datacenter_metrics ).', 'seed'),
    ('virt_classic_ram', '*',
        'v_crm_datacenter_metrics_latest', 'total_memory_capacity_gb', 'GB',
        'vm_metrics',                      'total_memory_capacity_gb', 'GB',
        'datacenter ILIKE :dc_pattern',
        '', 'seed'),
    ('virt_classic_storage', '*',
        'v_crm_datacenter_metrics_latest', 'total_storage_capacity_gb', 'GB',
        'vm_metrics',                      'provisioned_space_gb', 'GB',
        'datacenter ILIKE :dc_pattern',
        'Totals from datacenter_metrics rollup view; allocated from vm_metrics.', 'seed'),

    -- Classic KM clusters only — same lineage as vmware.py CLASSIC_METRICS (cluster_metrics)
    ('virt_km_cpu', '*',
        'v_crm_cluster_metrics_latest', 'cpu_ghz_capacity', 'GHz',
        'vm_metrics',                   'number_of_cpus',   'vCPU',
        'datacenter ILIKE :dc_pattern AND cluster ILIKE ''%KM%''',
        'KM clusters: cluster_metrics latest-per-cluster view + KM filter.', 'seed'),
    ('virt_km_ram', '*',
        'v_crm_cluster_metrics_latest', 'memory_capacity_gb', 'GB',
        'vm_metrics',                   'total_memory_capacity_gb', 'GB',
        'datacenter ILIKE :dc_pattern AND cluster ILIKE ''%KM%''',
        '', 'seed'),
    ('virt_km_storage', '*',
        'v_crm_cluster_metrics_latest', 'total_capacity_gb', 'GB',
        'vm_metrics',                   'provisioned_space_gb', 'GB',
        'datacenter ILIKE :dc_pattern AND cluster ILIKE ''%KM%''',
        '', 'seed'),

    -- IBM Power LPAR
    ('virt_power_cpu', '*',
        'ibm_server_general',          'server_processor_totalprocunits', 'Core',
        'ibm_lpar_general',            'lpar_processor_entitledprocunits', 'Core',
        'site_name ILIKE :dc_pattern',
        'IBM HMC server / LPAR processor units.', 'seed'),
    ('virt_power_ram', '*',
        'ibm_server_general',          'server_memory_totalmem',          'MB',
        'ibm_lpar_general',            'lpar_memory_logicalmem',          'MB',
        'site_name ILIKE :dc_pattern',
        'IBM HMC memory in MB.', 'seed'),
    ('virt_power_storage', '*',
        NULL, NULL, NULL, NULL, NULL, NULL, NULL,
        'IBM Power dedicated storage source TBD; configure per-DC via UI.', 'seed'),

    -- SAP Intel HANA / SAP Power HANA share underlying infrastructure with virt_classic / virt_power
    -- but operators may want dedicated panels with manually-set caps.
    ('virt_intel_hana_cpu', '*',     NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Configure per-DC.', 'seed'),
    ('virt_intel_hana_ram', '*',     NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Configure per-DC.', 'seed'),
    ('virt_intel_hana_storage', '*', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Configure per-DC.', 'seed'),
    ('virt_power_hana_cpu', '*',     NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Configure per-DC.', 'seed'),
    ('virt_power_hana_ram', '*',     NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Configure per-DC.', 'seed'),
    ('virt_power_hana_storage', '*', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Configure per-DC.', 'seed'),

    -- Backup repositories
    ('backup_veeam_replication_storage', '*',
        'raw_veeam_repositories_states', 'capacity_gb', 'GB',
        'raw_veeam_repositories_states', 'used_space_gb', 'GB',
        NULL,
        'Veeam repo capacity vs used (no per-DC filter at MVP).', 'seed'),
    ('backup_zerto_replication_storage', '*',
        'raw_zerto_site_metrics', 'provisioned_storage_mb', 'MB',
        'raw_zerto_site_metrics', 'used_storage_mb', 'MB',
        NULL, '', 'seed'),
    ('backup_netbackup_storage', '*',
        'raw_netbackup_disk_pools_metrics', 'usablesizebytes', 'bytes',
        'raw_netbackup_disk_pools_metrics', 'usedcapacitybytes', 'bytes',
        NULL, '', 'seed'),

    -- Object storage (S3 ICOS)
    ('storage_s3_ankara', '*',
        'raw_s3icos_pool_metrics', 'total_capacity_bytes', 'bytes',
        'raw_s3icos_pool_metrics', 'used_capacity_bytes',  'bytes',
        'site_name ILIKE :dc_pattern',
        'Filter expects site=Ankara.', 'seed'),
    ('storage_s3_istanbul', '*',
        'raw_s3icos_pool_metrics', 'total_capacity_bytes', 'bytes',
        'raw_s3icos_pool_metrics', 'used_capacity_bytes',  'bytes',
        'site_name ILIKE :dc_pattern',
        'Filter expects site=Istanbul.', 'seed')
ON CONFLICT (panel_key, dc_code) DO UPDATE SET
    source_table     = EXCLUDED.source_table,
    total_column     = EXCLUDED.total_column,
    total_unit       = EXCLUDED.total_unit,
    allocated_table  = EXCLUDED.allocated_table,
    allocated_column = EXCLUDED.allocated_column,
    allocated_unit   = EXCLUDED.allocated_unit,
    filter_clause    = EXCLUDED.filter_clause,
    notes            = COALESCE(NULLIF(EXCLUDED.notes,''), gui_panel_infra_source.notes),
    updated_by       = 'seed',
    updated_at       = NOW();

COMMIT;
