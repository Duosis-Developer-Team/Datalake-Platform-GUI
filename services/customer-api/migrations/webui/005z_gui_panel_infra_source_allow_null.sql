-- Align legacy databases created before source_table was nullable in 005.
-- Idempotent: safe if NOT NULL already dropped (PostgreSQL notices, exits 0).

BEGIN;

ALTER TABLE gui_panel_infra_source
    ALTER COLUMN source_table DROP NOT NULL;

COMMIT;
