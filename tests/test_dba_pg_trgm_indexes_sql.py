"""Phase 3 root fix is a DBA-run pg_trgm index script (the app role is not superuser).
Lock its presence + the exact indexes so the DDL can't silently drift.
"""
from pathlib import Path

SQL = Path(__file__).resolve().parents[1] / "sql" / "dba" / "customer_resources_pg_trgm_indexes.sql"


def test_pg_trgm_index_script_exists_and_covers_all_three_tables():
    assert SQL.exists(), "DBA pg_trgm index script must exist for Phase 3"
    text = SQL.read_text()
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in text
    # GIN trigram index on each leading-wildcard-ILIKE column used by /resources.
    assert "public.vm_metrics USING gin (vmname gin_trgm_ops)" in text
    assert "public.nutanix_vm_metrics USING gin (vm_name gin_trgm_ops)" in text
    assert "public.ibm_lpar_general USING gin (lparname gin_trgm_ops)" in text
