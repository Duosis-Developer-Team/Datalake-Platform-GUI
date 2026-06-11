-- Dual CPU sellable calculation variables (physical GHz vs effective sales units).
BEGIN;

INSERT INTO gui_crm_calc_config (config_key, config_value, value_type, description) VALUES
    ('sellable.cpu.effective_ghz_per_unit', '1.0', 'float',
     'Effective sellable rule: one sales unit (vCPU/Core) equals this many GHz.'),
    ('sellable.cpu.physical_use_netbox_ghz', 'true', 'bool',
     'When true, physical CPU sellable uses NetBox host GHz per core (fallback: vmware.default_host_cpu_ghz).'),
    ('sellable.cpu.physical_price_unit', 'GHz', 'enum',
     'Price unit for the physical CPU sellable track (typically GHz).'),
    ('power.core_to_ghz_factor', '3.3', 'float',
     'Power architecture: approximate GHz per Core for revenue estimation.')
ON CONFLICT (config_key) DO NOTHING;

COMMIT;
