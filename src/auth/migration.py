"""Startup migrations: ensure tables exist, version tracking."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from src.auth import db

logger = logging.getLogger(__name__)

_MIGRATION_RAN = False


def _read_schema_sql() -> str:
    root = Path(__file__).resolve().parents[2]
    p = root / "sql" / "auth_schema.sql"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def run_migrations() -> None:
    """Idempotent: create tables if missing, apply pending versions."""
    global _MIGRATION_RAN
    if _MIGRATION_RAN:
        return
    sql = _read_schema_sql()
    if not sql:
        logger.warning("auth_schema.sql not found; skipping auth migrations")
        return
    try:
        with db.connection() as conn:
            cur = conn.cursor()
            # Run DDL as one script (CREATE IF NOT EXISTS)
            cur.execute(sql)
            cur.execute(
                """
                INSERT INTO schema_migrations (version, description)
                VALUES (1, 'initial auth schema')
                ON CONFLICT (version) DO NOTHING
                """
            )
            cur.close()
        _MIGRATION_RAN = True
        logger.info("Auth DB migrations applied (v1)")
    except Exception as e:
        logger.warning("Auth migration failed (auth DB unavailable?): %s", e)
