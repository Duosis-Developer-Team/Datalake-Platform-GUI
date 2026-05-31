-- 013_panel_result_snapshot_and_manual_override.sql
-- ADR-0015 Tier-2 durable cache for compute_all_panels results + manual infra overrides.
--
-- Idempotent: CREATE IF NOT EXISTS, ADD COLUMN IF NOT EXISTS.

BEGIN;

-- ---------------------------------------------------------------------------
-- Tier-2 durable panel result snapshots (survives Redis cold start / restart)
-- ---------------------------------------------------------------------------
-- NOTE: IF NOT EXISTS alone cannot repair a pre-existing partial table; see 014_repair_*.
CREATE TABLE IF NOT EXISTS gui_panel_result_snapshot (
    dc_code       TEXT NOT NULL DEFAULT '*',
    family        TEXT NOT NULL DEFAULT '*',
    clusters_csv  TEXT NOT NULL DEFAULT '',
    payload       JSONB NOT NULL DEFAULT '[]'::jsonb,
    computed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (dc_code, family, clusters_csv)
);
CREATE INDEX IF NOT EXISTS idx_gui_panel_result_snapshot_computed
    ON gui_panel_result_snapshot (computed_at DESC);

-- ---------------------------------------------------------------------------
-- Manual capacity override (bypass datalake SUM when manual_total is set)
-- ---------------------------------------------------------------------------
ALTER TABLE gui_panel_infra_source
    ADD COLUMN IF NOT EXISTS manual_total     DOUBLE PRECISION NULL,
    ADD COLUMN IF NOT EXISTS manual_allocated DOUBLE PRECISION NULL;

COMMIT;
