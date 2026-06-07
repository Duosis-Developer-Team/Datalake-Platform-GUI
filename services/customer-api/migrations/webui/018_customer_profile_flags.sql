-- GUI-owned VIP and cache-pinned flags for CRM project customers.

CREATE TABLE IF NOT EXISTS gui_crm_customer_profile_flags (
    crm_accountid  TEXT PRIMARY KEY,
    is_vip         BOOLEAN NOT NULL DEFAULT FALSE,
    cache_pinned   BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by     TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gui_crm_customer_profile_flags_vip
    ON gui_crm_customer_profile_flags (is_vip)
    WHERE is_vip = TRUE;

CREATE INDEX IF NOT EXISTS idx_gui_crm_customer_profile_flags_cache_pinned
    ON gui_crm_customer_profile_flags (cache_pinned)
    WHERE cache_pinned = TRUE;
