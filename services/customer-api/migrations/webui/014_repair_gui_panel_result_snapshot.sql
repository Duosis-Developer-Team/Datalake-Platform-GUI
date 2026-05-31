-- 014_repair_gui_panel_result_snapshot.sql
-- Repair gui_panel_result_snapshot when 013 was recorded but CREATE TABLE IF NOT EXISTS
-- skipped because an older/partial table already existed (missing payload column).
--
-- Idempotent: safe to re-run.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   information_schema.tables
        WHERE  table_schema = 'public'
          AND  table_name = 'gui_panel_result_snapshot'
    ) THEN
        CREATE TABLE gui_panel_result_snapshot (
            dc_code       TEXT NOT NULL DEFAULT '*',
            family        TEXT NOT NULL DEFAULT '*',
            clusters_csv  TEXT NOT NULL DEFAULT '',
            payload       JSONB NOT NULL DEFAULT '[]'::jsonb,
            computed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (dc_code, family, clusters_csv)
        );
        RETURN;
    END IF;

    -- Legacy column names from early drafts (rename → payload)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_schema = 'public'
          AND  table_name = 'gui_panel_result_snapshot'
          AND  column_name = 'result_json'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_schema = 'public'
          AND  table_name = 'gui_panel_result_snapshot'
          AND  column_name = 'payload'
    ) THEN
        ALTER TABLE gui_panel_result_snapshot RENAME COLUMN result_json TO payload;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_schema = 'public'
          AND  table_name = 'gui_panel_result_snapshot'
          AND  column_name = 'panels_json'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_schema = 'public'
          AND  table_name = 'gui_panel_result_snapshot'
          AND  column_name = 'payload'
    ) THEN
        ALTER TABLE gui_panel_result_snapshot RENAME COLUMN panels_json TO payload;
    END IF;

    ALTER TABLE gui_panel_result_snapshot
        ADD COLUMN IF NOT EXISTS dc_code       TEXT NOT NULL DEFAULT '*',
        ADD COLUMN IF NOT EXISTS family        TEXT NOT NULL DEFAULT '*',
        ADD COLUMN IF NOT EXISTS clusters_csv  TEXT NOT NULL DEFAULT '',
        ADD COLUMN IF NOT EXISTS payload       JSONB DEFAULT '[]'::jsonb,
        ADD COLUMN IF NOT EXISTS computed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW();

    UPDATE gui_panel_result_snapshot
    SET    payload = '[]'::jsonb
    WHERE  payload IS NULL;

    BEGIN
        ALTER TABLE gui_panel_result_snapshot
            ALTER COLUMN payload SET NOT NULL;
    EXCEPTION
        WHEN others THEN
            RAISE NOTICE '014: payload NOT NULL constraint skipped (%)', SQLERRM;
    END;

    IF NOT EXISTS (
        SELECT 1
        FROM   pg_constraint c
        JOIN   pg_class t ON t.oid = c.conrelid
        WHERE  t.relname = 'gui_panel_result_snapshot'
          AND  c.contype = 'p'
    ) THEN
        BEGIN
            ALTER TABLE gui_panel_result_snapshot
                ADD PRIMARY KEY (dc_code, family, clusters_csv);
        EXCEPTION
            WHEN others THEN
                RAISE NOTICE '014: primary key add skipped (%)', SQLERRM;
        END;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_gui_panel_result_snapshot_computed
    ON gui_panel_result_snapshot (computed_at DESC);

COMMIT;
