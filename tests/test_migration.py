"""Migration module smoke tests (no live DB)."""

from src.auth import migration


def test_read_schema_sql_exists():
    sql = migration._read_schema_sql()
    assert "CREATE TABLE" in sql or sql == ""


def test_migration_002_sql_readable():
    from src.auth.auth_db_migrations import _read_migration_002_sql

    sql = _read_migration_002_sql()
    assert "team_roles" in sql
    assert "description" in sql
