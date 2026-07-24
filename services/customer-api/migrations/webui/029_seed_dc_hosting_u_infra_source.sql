-- services/customer-api/migrations/webui/029_seed_dc_hosting_u_infra_source.sql
-- Colocation (TASK-62): make dc_hosting_u a computed sellable panel.
-- The occupancy math lives in code (SellableService._query_colocation_totals ->
-- shared/colocation/occupancy.py), keyed on panel_key. This row only needs to
-- make has_infra_source true; source_table is a documented sentinel, never
-- executed as SQL for this panel.
BEGIN;

INSERT INTO gui_panel_infra_source
    (panel_key, dc_code, source_table, total_column, total_unit,
     allocated_table, allocated_column, allocated_unit, filter_clause, notes, updated_by)
VALUES
    ('dc_hosting_u', '*',
        '__colocation_occupancy__', 'capacity_u', 'U',
        '__colocation_occupancy__', 'used_u',    'U',
        NULL,
        'Colocation free-U sellable. Totals computed in code via shared/colocation/occupancy.py (SellableService._query_colocation_totals); source_table is a sentinel, not a real relation.',
        'seed')
ON CONFLICT (panel_key, dc_code) DO UPDATE SET
    source_table     = EXCLUDED.source_table,
    total_column     = EXCLUDED.total_column,
    total_unit       = EXCLUDED.total_unit,
    allocated_table  = EXCLUDED.allocated_table,
    allocated_column = EXCLUDED.allocated_column,
    allocated_unit   = EXCLUDED.allocated_unit,
    filter_clause    = EXCLUDED.filter_clause,
    notes            = COALESCE(NULLIF(EXCLUDED.notes,''), gui_panel_infra_source.notes),
    updated_by       = 'seed',
    updated_at       = NOW();

COMMIT;
