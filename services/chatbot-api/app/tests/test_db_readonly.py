import pytest

from app.config import settings
from app.services.db_readonly import ReadOnlyDB, ReadOnlyViolation, assert_read_only


def test_select_accepted():
    assert_read_only("SELECT 1")
    assert_read_only("WITH t AS (SELECT 1) SELECT * FROM t")


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE users",
        "UPDATE users SET active=false",
        "DELETE FROM customers",
        "TRUNCATE audit",
        "ALTER TABLE x ADD COLUMN y int",
        "CREATE TABLE z (a int)",
        "GRANT SELECT ON x TO y",
    ],
)
def test_write_and_ddl_rejected(sql):
    with pytest.raises(ReadOnlyViolation):
        assert_read_only(sql)


def test_multiple_statements_rejected():
    with pytest.raises(ReadOnlyViolation):
        assert_read_only("SELECT 1; SELECT 2")


def test_sensitive_column_rejected():
    with pytest.raises(ReadOnlyViolation):
        assert_read_only("SELECT password_hash FROM auth_users")


def test_non_select_rejected():
    with pytest.raises(ReadOnlyViolation):
        assert_read_only("EXPLAIN ANALYZE SELECT 1")


def test_db_disabled_by_default():
    db = ReadOnlyDB()
    assert db.enabled is False
    with pytest.raises(ReadOnlyViolation):
        db.run_template("SELECT 1")


def test_row_cap_and_timeout_defaults():
    assert settings.db_max_rows == 50
    assert settings.db_statement_timeout_ms == 10000


def test_generic_db_env_does_not_leak_into_chatbot_tuning(monkeypatch):
    """The main stack's generic DB_* (shared via .env) must not override the
    chatbot's stricter read-only tuning — only CHATBOT_DB_* is honoured."""
    from app.config import Settings

    monkeypatch.setenv("DB_STATEMENT_TIMEOUT_MS", "60000")
    monkeypatch.setenv("DB_MAX_ROWS", "9999")
    fresh = Settings()
    assert fresh.db_statement_timeout_ms == 10000
    assert fresh.db_max_rows == 50


def test_registry_templates_validate_at_import():
    # Importing the registry runs assert_read_only on every template.
    from app.services import db_query_registry

    assert db_query_registry.list_enabled_keys() == []  # all disabled by default
