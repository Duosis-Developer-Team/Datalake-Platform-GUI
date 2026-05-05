-- 012_power_crm_panels.sql
-- IBM Power: proc-unit to Core (x8) for CRM sellable, virt_power_cpu infra units,
-- raw_ibm_storage_system binding for virt_power_storage (parsed in SellableService).

BEGIN;

-- CRM CPU prices are per Core; datalake holds IBM proc units (1 PU = 8 cores).
INSERT INTO gui_unit_conversion (from_unit, to_unit, factor, operation, ceil_result, notes, updated_by)
VALUES (
    'procunit', 'Core', 8.0, 'multiply', FALSE,
    '1 IBM processor entitlement unit = 8 cores; CRM list prices use Core.',
    'seed'
)
ON CONFLICT (from_unit, to_unit) DO UPDATE SET
    factor      = CASE WHEN gui_unit_conversion.updated_by = 'seed' THEN EXCLUDED.factor      ELSE gui_unit_conversion.factor END,
    operation   = CASE WHEN gui_unit_conversion.updated_by = 'seed' THEN EXCLUDED.operation   ELSE gui_unit_conversion.operation END,
    ceil_result = CASE WHEN gui_unit_conversion.updated_by = 'seed' THEN EXCLUDED.ceil_result ELSE gui_unit_conversion.ceil_result END,
    notes       = COALESCE(NULLIF(EXCLUDED.notes,''), gui_unit_conversion.notes),
    updated_at  = NOW();

UPDATE gui_panel_infra_source
SET
    total_unit = 'procunit',
    allocated_unit = 'procunit',
    notes = 'IBM HMC proc units (SUM DISTINCT-on-latest server rows); 1 PU = 8 cores for CRM Core pricing.'
WHERE panel_key = 'virt_power_cpu'
  AND dc_code = '*'
  AND updated_by = 'seed';

UPDATE gui_panel_infra_source
SET
    source_table = 'public.raw_ibm_storage_system',
    total_column = 'total_mdisk_capacity',
    total_unit = 'GB',
    allocated_table = 'public.raw_ibm_storage_system',
    allocated_column = 'total_used_capacity',
    allocated_unit = 'GB',
    filter_clause = '(COALESCE(location, '''') || '' '' || COALESCE(name, '''')) ILIKE :dc_pattern',
    notes = 'Latest row per storage_ip; varchar capacities parsed to GB in SellableService. Match NVMi SKUs via gui_crm_service_mapping_seed.'
WHERE panel_key = 'virt_power_storage'
  AND dc_code = '*'
  AND updated_by = 'seed';

INSERT INTO gui_crm_service_pages (page_key, category_label, gui_tab_binding, resource_unit, panel_key)
VALUES
    ('virt_power_cpu',     'Power Mimari — CPU',     'virtualization.power', 'Core', 'virt_power_cpu'),
    ('virt_power_ram',     'Power Mimari — RAM',     'virtualization.power', 'GB',   'virt_power_ram'),
    ('virt_power_storage', 'Power Mimari — Storage', 'virtualization.power', 'GB',   'virt_power_storage')
ON CONFLICT (page_key) DO UPDATE SET
    category_label   = EXCLUDED.category_label,
    gui_tab_binding  = EXCLUDED.gui_tab_binding,
    resource_unit    = EXCLUDED.resource_unit,
    panel_key        = EXCLUDED.panel_key;

COMMIT;
