-- 005_panel_sellable_schema.sql
-- Adds tables for the C-level CRM Sellable Potential dashboard.
--
-- New tables:
--   gui_panel_definition       — registry of GUI panels (granular, e.g. virt_hyperconverged_ram)
--   gui_panel_infra_source     — datalake source binding per panel + DC
--   gui_panel_resource_ratio   — per-environment 1 CPU : N GB RAM : M GB Storage ratio
--   gui_unit_conversion        — runtime-editable unit conversions (e.g. GHz -> vCPU divide 8 ceil)
--   gui_metric_snapshot        — historical snapshots of computed metric tags (audit + trend)
--
-- Extends gui_crm_threshold_config and gui_crm_service_pages with a panel_key column.
--
-- Migration is idempotent (CREATE IF NOT EXISTS, ADD COLUMN IF NOT EXISTS).

BEGIN;

-- ---------------------------------------------------------------------------
-- Panel registry
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gui_panel_definition (
    panel_key       TEXT PRIMARY KEY,
    label           TEXT NOT NULL,
    family          TEXT NOT NULL,
    resource_kind   TEXT NOT NULL CHECK (resource_kind IN ('cpu','ram','storage','other')),
    display_unit    TEXT NOT NULL DEFAULT 'GB',
    sort_order      INT  NOT NULL DEFAULT 100,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    notes           TEXT,
    updated_by      TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_gui_panel_definition_family
    ON gui_panel_definition (family, sort_order);

-- ---------------------------------------------------------------------------
-- Per-panel datalake source binding (per DC override possible)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gui_panel_infra_source (
    panel_key        TEXT NOT NULL REFERENCES gui_panel_definition(panel_key) ON DELETE CASCADE,
    dc_code          TEXT NOT NULL DEFAULT '*',
    -- NULL = panel not yet bound to datalake (configure via Settings UI); see seed 007 placeholders.
    source_table     TEXT,
    total_column     TEXT,
    total_unit       TEXT,
    allocated_table  TEXT,
    allocated_column TEXT,
    allocated_unit   TEXT,
    filter_clause    TEXT,
    notes            TEXT,
    updated_by       TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (panel_key, dc_code)
);

-- ---------------------------------------------------------------------------
-- Per-environment resource ratio (1 CPU : N GB RAM : M GB Storage)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gui_panel_resource_ratio (
    family               TEXT NOT NULL,
    dc_code              TEXT NOT NULL DEFAULT '*',
    cpu_per_unit         DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    ram_gb_per_unit      DOUBLE PRECISION NOT NULL DEFAULT 8.0,
    storage_gb_per_unit  DOUBLE PRECISION NOT NULL DEFAULT 100.0,
    notes                TEXT,
    updated_by           TEXT,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (family, dc_code),
    CHECK (cpu_per_unit > 0 AND ram_gb_per_unit > 0 AND storage_gb_per_unit > 0)
);

-- ---------------------------------------------------------------------------
-- Unit conversion table (runtime editable)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gui_unit_conversion (
    from_unit    TEXT NOT NULL,
    to_unit      TEXT NOT NULL,
    factor       DOUBLE PRECISION NOT NULL,
    operation    TEXT NOT NULL DEFAULT 'divide' CHECK (operation IN ('multiply','divide')),
    ceil_result  BOOLEAN NOT NULL DEFAULT FALSE,
    notes        TEXT,
    updated_by   TEXT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (from_unit, to_unit),
    CHECK (factor > 0)
);

-- ---------------------------------------------------------------------------
-- Metric snapshot table (audit + trend) for tag-style metric_keys
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gui_metric_snapshot (
    metric_key   TEXT NOT NULL,
    scope_type   TEXT NOT NULL CHECK (scope_type IN ('global','dc','customer')),
    scope_id     TEXT NOT NULL DEFAULT '*',
    value        DOUBLE PRECISION NOT NULL,
    unit         TEXT NOT NULL,
    captured_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (metric_key, scope_type, scope_id, captured_at)
);
CREATE INDEX IF NOT EXISTS idx_metric_snapshot_lookup
    ON gui_metric_snapshot (metric_key, scope_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_metric_snapshot_scope
    ON gui_metric_snapshot (scope_type, scope_id, captured_at DESC);

-- ---------------------------------------------------------------------------
-- Extend existing tables: link to panel registry
-- ---------------------------------------------------------------------------
ALTER TABLE gui_crm_threshold_config
    ADD COLUMN IF NOT EXISTS panel_key TEXT REFERENCES gui_panel_definition(panel_key);
-- precedence in app code: per-panel > per-resource_type > '*'

ALTER TABLE gui_crm_service_pages
    ADD COLUMN IF NOT EXISTS panel_key TEXT REFERENCES gui_panel_definition(panel_key);
-- existing page_keys can be 1:1 mirrored; new granular page_keys point to a panel_key.

COMMIT;
