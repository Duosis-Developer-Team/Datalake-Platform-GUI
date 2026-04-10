"""Seed default roles, role-permission defaults, and admin user."""

from __future__ import annotations

import logging

from src.auth import db
from src.auth.config import ADMIN_DEFAULT_PASSWORD, ADMIN_DEFAULT_USERNAME
from src.auth.crypto import hash_password
from src.auth.registry import sync_permissions_from_catalog

logger = logging.getLogger(__name__)

DEFAULT_ROLES: list[tuple[str, str, bool]] = [
    ("Admin", "Full application access (default system user).", True),
    ("App Admin", "Application administrator (LDAP or local).", True),
    ("Executive", "Executive dashboards and reporting.", True),
    ("Operation Lead", "Operations dashboards, reporting, team delegation.", True),
    ("Operation Team", "Operations dashboards (view).", True),
    ("Guest", "No default permissions; assign in UI.", True),
]


def _ensure_roles() -> dict[str, int]:
    name_to_id: dict[str, int] = {}
    with db.connection() as conn:
        cur = conn.cursor()
        for name, desc, is_sys in DEFAULT_ROLES:
            cur.execute(
                """
                INSERT INTO roles (name, description, is_system)
                VALUES (%s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description
                RETURNING id
                """,
                (name, desc, is_sys),
            )
            row = cur.fetchone()
            if row:
                name_to_id[name] = int(row[0])
            else:
                cur.execute("SELECT id FROM roles WHERE name = %s", (name,))
                r2 = cur.fetchone()
                if r2:
                    name_to_id[name] = int(r2[0])
        cur.close()
    return name_to_id


def _all_permission_ids() -> list[int]:
    rows = db.fetch_all("SELECT id FROM permissions ORDER BY id")
    return [int(r["id"]) for r in rows]


def _code_to_id_map() -> dict[str, int]:
    rows = db.fetch_all("SELECT id, code FROM permissions")
    return {str(r["code"]): int(r["id"]) for r in rows}


def _seed_role_permissions(name_to_id: dict[str, int], cmap: dict[str, int]) -> None:
    """Default grants: Admin/App Admin full; others per plan (group-level + overrides)."""

    def grant(role: str, codes: list[str], view: bool, edit: bool, export: bool) -> None:
        rid = name_to_id.get(role)
        if not rid:
            return
        for code in codes:
            pid = cmap.get(code)
            if not pid:
                continue
            db.execute(
                """
                INSERT INTO role_permissions (role_id, permission_id, can_view, can_edit, can_export)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (role_id, permission_id) DO UPDATE SET
                    can_view = EXCLUDED.can_view,
                    can_edit = EXCLUDED.can_edit,
                    can_export = EXCLUDED.can_export
                """,
                (rid, pid, view, edit, export),
            )

    all_ids = _all_permission_ids()
    admin_id = name_to_id.get("Admin")
    app_admin_id = name_to_id.get("App Admin")
    if admin_id:
        for pid in all_ids:
            db.execute(
                """
                INSERT INTO role_permissions (role_id, permission_id, can_view, can_edit, can_export)
                VALUES (%s, %s, TRUE, TRUE, TRUE)
                ON CONFLICT (role_id, permission_id) DO UPDATE SET
                    can_view = TRUE, can_edit = TRUE, can_export = TRUE
                """,
                (admin_id, pid),
            )
    if app_admin_id:
        for pid in all_ids:
            db.execute(
                """
                INSERT INTO role_permissions (role_id, permission_id, can_view, can_edit, can_export)
                VALUES (%s, %s, TRUE, TRUE, TRUE)
                ON CONFLICT (role_id, permission_id) DO UPDATE SET
                    can_view = TRUE, can_edit = TRUE, can_export = TRUE
                """,
                (app_admin_id, pid),
            )

    # Executive: Dashboard + Global + Customer (view + export), no admin
    executive_codes = [
        "grp:dashboard",
        "grp:global",
        "grp:customer",
    ]
    for c in executive_codes:
        grant("Executive", [c], True, False, True)

    # Operation Lead: Dashboard + Global full-ish; teams admin
    grant("Operation Lead", ["grp:dashboard"], True, True, True)
    grant("Operation Lead", ["grp:global"], True, True, True)
    grant("Operation Lead", ["page:settings_teams"], True, True, False)

    # Operation Team: Dashboard + Global view only
    grant("Operation Team", ["grp:dashboard"], True, False, False)
    grant("Operation Team", ["grp:global"], True, False, False)

    # Guest: intentionally no group grants


def _ensure_admin_user(admin_role_id: int) -> None:
    row = db.fetch_one("SELECT id FROM users WHERE username = %s", (ADMIN_DEFAULT_USERNAME,))
    if row:
        return
    pwd_hash = hash_password(ADMIN_DEFAULT_PASSWORD)
    db.execute(
        """
        INSERT INTO users (username, display_name, password_hash, source, is_active)
        VALUES (%s, %s, %s, 'local', TRUE)
        """,
        (ADMIN_DEFAULT_USERNAME, "Administrator", pwd_hash),
    )
    u = db.fetch_one("SELECT id FROM users WHERE username = %s", (ADMIN_DEFAULT_USERNAME,))
    if not u:
        return
    uid = int(u["id"])
    db.execute(
        """
        INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)
        ON CONFLICT (user_id, role_id) DO NOTHING
        """,
        (uid, admin_role_id),
    )
    logger.info("Seeded default admin user %s", ADMIN_DEFAULT_USERNAME)


def seed_all() -> None:
    sync_permissions_from_catalog()
    name_to_id = _ensure_roles()
    cmap = _code_to_id_map()
    _seed_role_permissions(name_to_id, cmap)
    admin_rid = name_to_id.get("Admin", 0)
    if admin_rid:
        _ensure_admin_user(admin_rid)
