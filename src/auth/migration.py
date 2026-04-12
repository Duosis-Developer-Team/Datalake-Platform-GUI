"""Startup migrations: ensure tables exist, version tracking."""

from __future__ import annotations

import logging

from src.auth import db
from src.auth.auth_db_migrations import run_auth_db_migrations

logger = logging.getLogger(__name__)

_MIGRATION_RAN = False


def _read_schema_sql() -> str:
    """Re-export for tests that assert on schema content."""

    from src.auth.auth_db_migrations import _read_schema_sql as _rs

    return _rs()


def run_migrations() -> None:
    """Idempotent: create tables if missing, apply pending versions."""

    global _MIGRATION_RAN
    if _MIGRATION_RAN:
        return
    try:
        with db.connection() as conn:
            run_auth_db_migrations(conn)
        _MIGRATION_RAN = True
        logger.info("Auth DB migrations applied")
    except Exception as e:
        logger.warning("Auth migration failed (auth DB unavailable?): %s", e)
