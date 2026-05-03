"""SQL for the GUI CRM configuration tables (webui-db)."""

# ---------------------------------------------------------------------------
# Threshold config — sellable ceiling % per resource type, optionally per DC
# ---------------------------------------------------------------------------

LIST_THRESHOLDS = """
SELECT id,
       panel_key,
       resource_type,
       dc_code,
       sellable_limit_pct,
       notes,
       updated_by,
       updated_at
FROM   gui_crm_threshold_config
ORDER BY (panel_key IS NULL), panel_key, resource_type, dc_code;
"""

GET_THRESHOLD_FOR = """
SELECT sellable_limit_pct
FROM   gui_crm_threshold_config
WHERE  resource_type = %s
   AND (dc_code = %s OR dc_code = '*')
ORDER BY (dc_code = '*') ASC
LIMIT 1;
"""

UPSERT_THRESHOLD = """
INSERT INTO gui_crm_threshold_config
    (panel_key, resource_type, dc_code, sellable_limit_pct, notes, updated_by, updated_at)
VALUES (%s, %s, %s, %s, %s, %s, NOW())
ON CONFLICT (resource_type, dc_code) DO UPDATE SET
    panel_key          = EXCLUDED.panel_key,
    sellable_limit_pct = EXCLUDED.sellable_limit_pct,
    notes              = COALESCE(EXCLUDED.notes, gui_crm_threshold_config.notes),
    updated_by         = EXCLUDED.updated_by,
    updated_at         = NOW();
"""

DELETE_THRESHOLD_BY_ID = """
DELETE FROM gui_crm_threshold_config WHERE id = %s;
"""

# ---------------------------------------------------------------------------
# Price overrides — operator-managed unit prices, primary fallback while
# discovery_crm_productpricelevels stays empty
# ---------------------------------------------------------------------------

LIST_PRICE_OVERRIDES = """
SELECT productid,
       product_name,
       unit_price_tl,
       resource_unit,
       currency,
       notes,
       updated_by,
       updated_at
FROM   gui_crm_price_override
ORDER BY product_name NULLS LAST, productid;
"""

UPSERT_PRICE_OVERRIDE = """
INSERT INTO gui_crm_price_override
    (productid, product_name, unit_price_tl, resource_unit, currency, notes, updated_by, updated_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
ON CONFLICT (productid) DO UPDATE SET
    product_name  = COALESCE(EXCLUDED.product_name, gui_crm_price_override.product_name),
    unit_price_tl = EXCLUDED.unit_price_tl,
    resource_unit = COALESCE(EXCLUDED.resource_unit, gui_crm_price_override.resource_unit),
    currency      = COALESCE(EXCLUDED.currency, gui_crm_price_override.currency),
    notes         = COALESCE(EXCLUDED.notes, gui_crm_price_override.notes),
    updated_by    = EXCLUDED.updated_by,
    updated_at    = NOW();
"""

DELETE_PRICE_OVERRIDE = """
DELETE FROM gui_crm_price_override WHERE productid = %s;
"""

# ---------------------------------------------------------------------------
# Calc config — generic numeric/string variables consumed by the calculation layer
# ---------------------------------------------------------------------------

LIST_CALC_CONFIG = """
SELECT config_key,
       config_value,
       value_type,
       description,
       updated_by,
       updated_at
FROM   gui_crm_calc_config
ORDER BY config_key;
"""

UPSERT_CALC_CONFIG = """
INSERT INTO gui_crm_calc_config (config_key, config_value, value_type, description, updated_by, updated_at)
VALUES (%s, %s, %s, %s, %s, NOW())
ON CONFLICT (config_key) DO UPDATE SET
    config_value = EXCLUDED.config_value,
    value_type   = COALESCE(EXCLUDED.value_type, gui_crm_calc_config.value_type),
    description  = COALESCE(EXCLUDED.description, gui_crm_calc_config.description),
    updated_by   = EXCLUDED.updated_by,
    updated_at   = NOW();
"""
