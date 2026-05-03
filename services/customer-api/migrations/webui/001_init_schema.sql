-- WebUI App DB initial schema
-- Owns GUI configuration tables: service mapping, customer aliases, thresholds,
-- price overrides, calculation variables.
--
-- Datalake DB stays read-only for raw vendor data (discovery_crm_*, NetBox, etc.).
-- Application-layer joins enrich datalake rows with mappings from this DB.

BEGIN;

CREATE TABLE IF NOT EXISTS gui_crm_service_pages (
    page_key          TEXT PRIMARY KEY,
    category_label    TEXT NOT NULL,
    gui_tab_binding   TEXT NOT NULL,
    resource_unit     TEXT NOT NULL DEFAULT 'Adet',
    icon              TEXT,
    route_hint        TEXT,
    tab_hint          TEXT,
    sub_tab_hint      TEXT
);

CREATE TABLE IF NOT EXISTS gui_crm_service_mapping_seed (
    productid TEXT PRIMARY KEY,
    page_key  TEXT NOT NULL REFERENCES gui_crm_service_pages(page_key)
);

CREATE TABLE IF NOT EXISTS gui_crm_service_mapping_override (
    productid    TEXT PRIMARY KEY,
    page_key     TEXT NOT NULL REFERENCES gui_crm_service_pages(page_key),
    notes        TEXT,
    updated_by   TEXT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Customer alias: replaces empty discovery_crm_customer_alias from datalake DB.
-- Operator-managed mapping between CRM accountid and platform/NetBox identifiers.
CREATE TABLE IF NOT EXISTS gui_crm_customer_alias (
    crm_accountid          TEXT PRIMARY KEY,
    crm_account_name       TEXT NOT NULL,
    canonical_customer_key TEXT,
    netbox_musteri_value   TEXT,
    notes                  TEXT,
    source                 TEXT NOT NULL DEFAULT 'manual',
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gui_crm_customer_alias_canonical
    ON gui_crm_customer_alias (canonical_customer_key);
CREATE INDEX IF NOT EXISTS idx_gui_crm_customer_alias_name
    ON gui_crm_customer_alias (crm_account_name);

-- Resource ceiling configuration. dc_code='*' = global default, otherwise per-DC override.
CREATE TABLE IF NOT EXISTS gui_crm_threshold_config (
    id                  SERIAL PRIMARY KEY,
    resource_type       TEXT NOT NULL,
    dc_code             TEXT NOT NULL DEFAULT '*',
    sellable_limit_pct  DOUBLE PRECISION NOT NULL DEFAULT 80.0,
    notes               TEXT,
    updated_by          TEXT,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (resource_type, dc_code),
    CHECK (sellable_limit_pct >= 0 AND sellable_limit_pct <= 100)
);

-- Per-product unit price override. Required while discovery_crm_productpricelevels
-- arrives empty from CRM; also lets operators override stale catalog prices.
CREATE TABLE IF NOT EXISTS gui_crm_price_override (
    productid       TEXT PRIMARY KEY,
    product_name    TEXT,
    unit_price_tl   DOUBLE PRECISION NOT NULL,
    resource_unit   TEXT,
    currency        TEXT NOT NULL DEFAULT 'TL',
    notes           TEXT,
    updated_by      TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (unit_price_tl >= 0)
);

-- Generic calculation variables (efficiency thresholds, fallback factors, etc.).
CREATE TABLE IF NOT EXISTS gui_crm_calc_config (
    config_key   TEXT PRIMARY KEY,
    config_value TEXT NOT NULL,
    value_type   TEXT NOT NULL DEFAULT 'float',
    description  TEXT,
    updated_by   TEXT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (value_type IN ('float', 'int', 'string', 'enum', 'bool'))
);

COMMIT;
