"""The 029 migration seeds a dc_hosting_u infra-source row with the sentinel
source_table and U units, wrapped in a transaction with ON CONFLICT upsert."""
import os

_MIG = os.path.join(
    os.path.dirname(__file__), "..", "migrations", "webui",
    "029_seed_dc_hosting_u_infra_source.sql",
)


def test_migration_file_exists_and_is_transactional():
    with open(_MIG, encoding="utf-8") as fh:
        sql = fh.read()
    assert "BEGIN;" in sql and "COMMIT;" in sql
    assert "INSERT INTO gui_panel_infra_source" in sql
    assert "'dc_hosting_u'" in sql
    assert "__colocation_occupancy__" in sql          # sentinel source_table
    assert "'capacity_u'" in sql and "'used_u'" in sql
    assert "'U'" in sql                                # units
    assert "ON CONFLICT (panel_key, dc_code) DO UPDATE" in sql
