"""Startup migrations: ensure tables exist, version tracking."""

from __future__ import annotations

import logging
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


def _migration_v2_rename_settings(cur) -> None:
    """Rename legacy admin_* permission codes to settings_* and merge grp:admin into grp:settings."""
    renames = [
        ("page:admin_users", "page:settings_users"),
        ("page:admin_roles", "page:settings_roles"),
        ("page:admin_permissions", "page:settings_permissions"),
        ("page:admin_ldap", "page:settings_ldap"),
        ("page:admin_teams", "page:settings_teams"),
    ]
    for old, new in renames:
        cur.execute("SELECT id FROM permissions WHERE code = %s", (new,))
        has_new = cur.fetchone()
        cur.execute("SELECT id FROM permissions WHERE code = %s", (old,))
        has_old = cur.fetchone()
        if has_old and not has_new:
            cur.execute("UPDATE permissions SET code = %s WHERE code = %s", (new, old))

    cur.execute("SELECT id FROM permissions WHERE code = 'grp:settings' LIMIT 1")
    gs = cur.fetchone()
    cur.execute("SELECT id FROM permissions WHERE code = 'grp:admin' LIMIT 1")
    ga = cur.fetchone()
    if ga and gs:
        cur.execute("UPDATE permissions SET parent_id = %s WHERE parent_id = %s", (gs[0], ga[0]))
        cur.execute("DELETE FROM permissions WHERE id = %s", (ga[0],))
    elif ga and not gs:
        cur.execute("UPDATE permissions SET code = 'grp:settings' WHERE id = %s", (ga[0],))

    cur.execute("SELECT id FROM permissions WHERE code = 'grp:settings' LIMIT 1")
    row = cur.fetchone()
    if not row:
        return
    sid = row[0]
    cur.execute(
        """
        UPDATE permissions SET parent_id = %s
        WHERE code ~ '^page:settings_'
        """,
        (sid,),
    )


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
            cur.execute(sql)
            cur.execute(
                """
                INSERT INTO schema_migrations (version, description)
                VALUES (1, 'initial auth schema')
                ON CONFLICT (version) DO NOTHING
                """
            )
            cur.execute("SELECT 1 FROM schema_migrations WHERE version = 2")
            if not cur.fetchone():
                _migration_v2_rename_settings(cur)
                cur.execute(
                    """
                    INSERT INTO schema_migrations (version, description)
                    VALUES (2, 'rename admin permissions to settings paths')
                    ON CONFLICT (version) DO NOTHING
                    """
                )
                logger.info("Auth DB migration v2 applied (settings rename)")
            cur.close()
        _MIGRATION_RAN = True
        logger.info("Auth DB migrations applied")
    except Exception as e:
        logger.warning("Auth migration failed (auth DB unavailable?): %s", e)
