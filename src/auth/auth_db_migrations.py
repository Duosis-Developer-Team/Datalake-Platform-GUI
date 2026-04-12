"""Shared auth database migrations (GUI app.py and admin-api lifespan).

Locates sql/ by walking up from this file until sql/auth_schema.sql exists.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _sql_dir() -> Path:
    env = os.environ.get("AUTH_SQL_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = ancestor / "sql" / "auth_schema.sql"
        if candidate.is_file():
            return ancestor / "sql"
    raise FileNotFoundError(
        "Cannot find sql/auth_schema.sql; set AUTH_SQL_DIR or run from repo with sql/ present."
    )


def _read_schema_sql() -> str:
    p = _sql_dir() / "auth_schema.sql"
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return ""


def _read_migration_002_sql() -> str:
    p = _sql_dir() / "migrations" / "002_team_description_and_team_roles.sql"
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return ""


def _exec_sql_statements(cur: Any, sql: str) -> None:
    """Run semicolon-separated statements (002 script has no string literals with ;)."""

    cleaned = re.sub(r"--[^\n]*", "", sql)
    for part in cleaned.split(";"):
        stmt = part.strip()
        if stmt:
            cur.execute(stmt)


def _migration_v2_rename_settings(cur: Any) -> None:
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


def run_auth_db_migrations(conn: Any) -> None:
    """Idempotent: create tables if missing, apply pending schema_migrations versions."""

    sql = _read_schema_sql()
    if not sql:
        logger.warning("auth_schema.sql not found; skipping auth migrations")
        return
    cur = conn.cursor()
    try:
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
        cur.execute("SELECT 1 FROM schema_migrations WHERE version = 3")
        if not cur.fetchone():
            m002 = _read_migration_002_sql()
            if m002.strip():
                _exec_sql_statements(cur, m002)
                cur.execute(
                    """
                    INSERT INTO schema_migrations (version, description)
                    VALUES (3, 'teams description and team_roles')
                    ON CONFLICT (version) DO NOTHING
                    """
                )
                logger.info("Auth DB migration v3 applied (teams extended)")
            else:
                logger.warning("002 migration SQL missing; v3 not recorded")
    finally:
        cur.close()
