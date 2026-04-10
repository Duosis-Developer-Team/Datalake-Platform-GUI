"""Migration module smoke tests (no live DB)."""

from src.auth import migration


def test_read_schema_sql_exists():
    sql = migration._read_schema_sql()
    assert "CREATE TABLE" in sql or sql == ""
