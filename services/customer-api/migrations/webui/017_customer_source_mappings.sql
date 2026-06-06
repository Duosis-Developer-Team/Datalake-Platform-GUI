-- CRM customer source mappings: per-data-source match rules for infra correlation.
-- Replaces single-row alias semantics for resource queries; legacy gui_crm_customer_alias
-- remains for backward-compatible sales alias resolution.

CREATE TABLE IF NOT EXISTS gui_crm_customer_source_mapping (
    id BIGSERIAL PRIMARY KEY,
    crm_accountid TEXT NOT NULL,
    crm_account_name TEXT NOT NULL,
    data_source TEXT NOT NULL,
    match_method TEXT NOT NULL,
    match_value TEXT NOT NULL,
    display_label TEXT,
    priority INTEGER NOT NULL DEFAULT 100,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (crm_accountid, data_source, match_method, match_value)
);

CREATE INDEX IF NOT EXISTS idx_gui_crm_customer_source_mapping_account
    ON gui_crm_customer_source_mapping (crm_accountid);

CREATE INDEX IF NOT EXISTS idx_gui_crm_customer_source_mapping_source
    ON gui_crm_customer_source_mapping (crm_accountid, data_source, enabled);
