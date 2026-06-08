-- NetBox/Loki visualization exclusions (device role and future dimensions).
-- Operators exclude roles per view scope (datacenter vs customer).
-- Example: exclude "Patch Panel" from datacenter physical inventory and network charts.

CREATE TABLE IF NOT EXISTS gui_netbox_viz_exclusion (
    id              SERIAL PRIMARY KEY,
    view_scope      TEXT NOT NULL CHECK (view_scope IN ('datacenter', 'customer')),
    dimension       TEXT NOT NULL DEFAULT 'device_role',
    dimension_value TEXT NOT NULL,
    notes           TEXT,
    updated_by      TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (view_scope, dimension, dimension_value)
);

CREATE INDEX IF NOT EXISTS idx_gui_netbox_viz_exclusion_scope
    ON gui_netbox_viz_exclusion (view_scope, dimension);
