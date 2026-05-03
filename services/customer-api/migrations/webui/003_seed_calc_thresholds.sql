-- Seed default calculation variables and resource ceiling thresholds.
-- Operators can edit any of these from Settings > Integrations > CRM > Calc / Thresholds.

BEGIN;

INSERT INTO gui_crm_calc_config (config_key, config_value, value_type, description) VALUES
    ('efficiency.under_pct', '80.0', 'float',
     'Sold/used ratio below this percentage marks a customer category as under-utilised.'),
    ('efficiency.over_pct', '110.0', 'float',
     'Sold/used ratio above this percentage marks a customer category as over-utilised.'),
    ('efficiency.alloc_cap_pct', '150.0', 'float',
     'Hard ceiling for allocated_vs_sold display (prevents misleading off-chart values).'),
    ('price.method', 'override_first', 'enum',
     'Catalog price source order. override_first = use gui_crm_price_override before discovery_crm_productpricelevels.'),
    ('price.fallback_factor', '1.0', 'float',
     'Multiplier applied to fallback prices when neither override nor catalog row exists.'),
    ('cache.product_mapping_ttl_seconds', '900', 'int',
     'TTL for product-mapping dict cached in Redis (lookup table for application-layer joins).'),
    ('cache.alias_ttl_seconds', '900', 'int',
     'TTL for customer alias resolution cache in Redis.')
ON CONFLICT (config_key) DO NOTHING;

INSERT INTO gui_crm_threshold_config (resource_type, dc_code, sellable_limit_pct, notes) VALUES
    ('cpu',       '*', 80.0, 'Global default sellable ceiling for vCPU capacity.'),
    ('ram',       '*', 80.0, 'Global default sellable ceiling for memory (GB).'),
    ('storage',   '*', 85.0, 'Global default sellable ceiling for storage capacity.'),
    ('backup',    '*', 90.0, 'Global default sellable ceiling for backup repository capacity.'),
    ('rack_u',    '*', 80.0, 'Global default sellable ceiling for rack U slots.'),
    ('power_kw',  '*', 75.0, 'Global default sellable ceiling for available kW per DC.')
ON CONFLICT (resource_type, dc_code) DO NOTHING;

COMMIT;
