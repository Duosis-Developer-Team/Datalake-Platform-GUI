-- Default base GHz per core for VMware hosts when NetBox CPU string is missing.
-- Operators can edit from Settings > Integrations > CRM > Calc / Thresholds.

BEGIN;

INSERT INTO gui_crm_calc_config (config_key, config_value, value_type, description, updated_by)
VALUES (
    'vmware.default_host_cpu_ghz',
    '2.0',
    'float',
    'Fallback base GHz per vCPU for VMware CPU allocation when NetBox host CPU model is unavailable.',
    'seed'
)
ON CONFLICT (config_key) DO UPDATE SET
    description = EXCLUDED.description,
    value_type  = CASE WHEN gui_crm_calc_config.updated_by = 'seed' THEN EXCLUDED.value_type ELSE gui_crm_calc_config.value_type END;

COMMIT;
