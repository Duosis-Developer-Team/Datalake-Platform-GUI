"""DB helpers for Settings UI (users, roles, LDAP, teams, audit)."""

from __future__ import annotations

from typing import Any

from src.auth import db
from src.auth.crypto import hash_password
from src.auth.permission_service import clear_user_cache


def list_users_with_roles() -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """
        SELECT u.id, u.username, u.display_name, u.email, u.source, u.is_active,
               COALESCE(string_agg(r.name, ', ' ORDER BY r.name), '') AS roles
        FROM users u
        LEFT JOIN user_roles ur ON ur.user_id = u.id
        LEFT JOIN roles r ON r.id = ur.role_id
        GROUP BY u.id, u.username, u.display_name, u.email, u.source, u.is_active
        ORDER BY u.username
        """
    )
    return rows


def list_roles() -> list[dict[str, Any]]:
    return db.fetch_all("SELECT id, name, description, is_system FROM roles ORDER BY name")


def list_permissions_flat() -> list[dict[str, Any]]:
    return db.fetch_all(
        "SELECT id, code, name, parent_id, resource_type, sort_order, is_dynamic FROM permissions ORDER BY code"
    )


def get_role_permission_rows(role_id: int) -> list[dict[str, Any]]:
    return db.fetch_all(
        """
        SELECT permission_id, can_view, can_edit, can_export
        FROM role_permissions WHERE role_id = %s
        """,
        (role_id,),
    )


def set_role_permission(
    role_id: int,
    permission_id: int,
    can_view: bool,
    can_edit: bool,
    can_export: bool,
    *,
    invalidate_cache: bool = True,
) -> None:
    db.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id, can_view, can_edit, can_export)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (role_id, permission_id) DO UPDATE SET
            can_view = EXCLUDED.can_view,
            can_edit = EXCLUDED.can_edit,
            can_export = EXCLUDED.can_export
        """,
        (role_id, permission_id, can_view, can_edit, can_export),
    )
    if invalidate_cache:
        clear_user_cache(None)


def bulk_set_role_matrix(
    role_id: int,
    triplets: list[tuple[int, bool, bool, bool]],
) -> None:
    """Replace matrix rows for one role in one pass; single cache invalidation."""
    from src.auth import db as dbmod

    with dbmod.connection() as conn:
        cur = conn.cursor()
        for pid, v, e, x in triplets:
            cur.execute(
                """
                INSERT INTO role_permissions (role_id, permission_id, can_view, can_edit, can_export)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (role_id, permission_id) DO UPDATE SET
                    can_view = EXCLUDED.can_view,
                    can_edit = EXCLUDED.can_edit,
                    can_export = EXCLUDED.can_export
                """,
                (role_id, pid, v, e, x),
            )
        cur.close()
    clear_user_cache(None)


def create_local_user(username: str, password: str, display_name: str | None) -> int:
    h = hash_password(password)
    db.execute(
        """
        INSERT INTO users (username, display_name, password_hash, source, is_active)
        VALUES (%s, %s, %s, 'local', TRUE)
        """,
        (username.strip(), display_name or username.strip(), h),
    )
    row = db.fetch_one("SELECT id FROM users WHERE lower(username) = lower(%s)", (username.strip(),))
    return int(row["id"]) if row else 0


def set_user_roles(user_id: int, role_ids: list[int]) -> None:
    db.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
    for rid in role_ids:
        db.execute(
            "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_id, rid),
        )
    clear_user_cache(user_id)


def set_user_active(user_id: int, active: bool) -> None:
    db.execute("UPDATE users SET is_active = %s, updated_at = NOW() WHERE id = %s", (active, user_id))
    clear_user_cache(user_id)


def list_ldap_configs() -> list[dict[str, Any]]:
    return db.fetch_all("SELECT * FROM ldap_config ORDER BY id")


def upsert_ldap_config(
    ldap_id: int | str | None,
    name: str,
    server_primary: str,
    server_secondary: str | None,
    port: int,
    use_ssl: bool,
    bind_dn: str,
    bind_password_plain: str | None,
    search_base_dn: str,
    user_search_filter: str,
    is_active: bool,
) -> None:
    from src.auth.crypto import fernet_encrypt

    if isinstance(ldap_id, str) and not str(ldap_id).strip():
        ldap_id = None
    elif isinstance(ldap_id, str) and str(ldap_id).strip().isdigit():
        ldap_id = int(ldap_id.strip())

    enc_pw: str | None = None
    if bind_password_plain and bind_password_plain.strip():
        enc_pw = fernet_encrypt(bind_password_plain.strip())
    if ldap_id:
        row = db.fetch_one("SELECT bind_password FROM ldap_config WHERE id = %s", (ldap_id,))
        existing_pw = str(row["bind_password"]) if row and row.get("bind_password") else ""
        if enc_pw is None:
            enc_pw = existing_pw
        db.execute(
            """
            UPDATE ldap_config SET
                name = %s, server_primary = %s, server_secondary = %s, port = %s, use_ssl = %s,
                bind_dn = %s, bind_password = %s, search_base_dn = %s,
                user_search_filter = %s, is_active = %s
            WHERE id = %s
            """,
            (
                name,
                server_primary,
                server_secondary,
                port,
                use_ssl,
                bind_dn,
                enc_pw or "",
                search_base_dn,
                user_search_filter,
                is_active,
                ldap_id,
            ),
        )
        return
    db.execute(
        """
        INSERT INTO ldap_config (
            name, server_primary, server_secondary, port, use_ssl, bind_dn, bind_password,
            search_base_dn, user_search_filter, is_active
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            name,
            server_primary,
            server_secondary,
            port,
            use_ssl,
            bind_dn,
            enc_pw or "",
            search_base_dn,
            user_search_filter,
            is_active,
        ),
    )


def list_ldap_group_mappings(ldap_config_id: int) -> list[dict[str, Any]]:
    return db.fetch_all(
        """
        SELECT m.id, m.ldap_group_dn, m.role_id, r.name AS role_name
        FROM ldap_group_role_mapping m
        JOIN roles r ON r.id = m.role_id
        WHERE m.ldap_config_id = %s
        ORDER BY m.ldap_group_dn
        """,
        (ldap_config_id,),
    )


def add_ldap_group_mapping(ldap_config_id: int, ldap_group_dn: str, role_id: int) -> None:
    db.execute(
        """
        INSERT INTO ldap_group_role_mapping (ldap_config_id, ldap_group_dn, role_id)
        VALUES (%s, %s, %s)
        ON CONFLICT (ldap_config_id, ldap_group_dn, role_id) DO NOTHING
        """,
        (ldap_config_id, ldap_group_dn.strip(), role_id),
    )


def delete_ldap_group_mapping(mapping_id: int) -> None:
    db.execute("DELETE FROM ldap_group_role_mapping WHERE id = %s", (mapping_id,))


def list_teams() -> list[dict[str, Any]]:
    return db.fetch_all(
        """
        SELECT t.id, t.name, t.parent_id, t.created_by,
               u.username AS created_by_name,
               (SELECT COUNT(*) FROM team_members tm WHERE tm.team_id = t.id) AS member_count
        FROM teams t
        LEFT JOIN users u ON u.id = t.created_by
        ORDER BY t.name
        """
    )


def create_team(name: str, parent_id: int | None, created_by: int | None) -> None:
    db.execute(
        "INSERT INTO teams (name, parent_id, created_by) VALUES (%s, %s, %s)",
        (name.strip(), parent_id, created_by),
    )


def list_audit_log(limit: int = 200) -> list[dict[str, Any]]:
    return db.fetch_all(
        """
        SELECT a.id, a.user_id, u.username, a.action, a.detail, a.ip_address, a.created_at
        FROM audit_log a
        LEFT JOIN users u ON u.id = a.user_id
        ORDER BY a.created_at DESC
        LIMIT %s
        """,
        (limit,),
    )


def insert_dynamic_permission(
    code: str,
    name: str,
    parent_code: str | None,
    resource_type: str,
    route_pattern: str | None,
) -> None:
    pid = None
    if parent_code:
        pr = db.fetch_one("SELECT id FROM permissions WHERE code = %s", (parent_code,))
        if pr:
            pid = int(pr["id"])
    db.execute(
        """
        INSERT INTO permissions (
            code, name, description, parent_id, resource_type, route_pattern,
            component_id, icon, sort_order, is_dynamic
        ) VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL, 0, TRUE)
        ON CONFLICT (code) DO NOTHING
        """,
        (code, name, None, pid, resource_type, route_pattern),
    )
    clear_user_cache(None)


def search_ldap_users(query: str) -> list[dict[str, Any]]:
    from src.auth import ldap_service

    rows = ldap_service.search_directory_users(query)
    return [
        {
            "username": r["username"],
            "display_name": r.get("display_name"),
            "email": r.get("email"),
            "distinguished_name": r["distinguished_name"],
        }
        for r in rows
    ]


def import_ldap_users(
    users: list[dict[str, Any]],
    role_ids: list[int],
    team_ids: list[int],
) -> list[int]:
    """Upsert LDAP users and assign roles / team memberships (same as admin-api)."""
    imported: list[int] = []
    for entry in users:
        uname = str(entry.get("username") or "").strip()
        if not uname:
            continue
        dn = str(entry.get("distinguished_name") or "").strip()
        if not dn:
            continue
        display_name = entry.get("display_name")
        email = entry.get("email")
        row = db.fetch_one("SELECT id FROM users WHERE lower(username) = lower(%s)", (uname,))
        if row:
            uid = int(row["id"])
            db.execute(
                """
                UPDATE users SET
                    display_name = COALESCE(%s, display_name),
                    email = COALESCE(%s, email),
                    ldap_dn = %s,
                    source = 'ldap',
                    updated_at = NOW()
                WHERE id = %s
                """,
                (display_name, email, dn, uid),
            )
        else:
            db.execute(
                """
                INSERT INTO users (username, display_name, email, password_hash, source, ldap_dn, is_active)
                VALUES (%s, %s, %s, NULL, 'ldap', %s, TRUE)
                """,
                (uname, display_name or uname, email, dn),
            )
            row2 = db.fetch_one("SELECT id FROM users WHERE lower(username) = lower(%s)", (uname,))
            uid = int(row2["id"]) if row2 else 0
        if not uid:
            continue
        imported.append(uid)

        db.execute("DELETE FROM user_roles WHERE user_id = %s", (uid,))
        for rid in role_ids:
            db.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (uid, rid),
            )

        db.execute("DELETE FROM team_members WHERE user_id = %s", (uid,))
        for tid in team_ids:
            db.execute(
                "INSERT INTO team_members (team_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (tid, uid),
            )
        clear_user_cache(uid)
    return imported


def get_user_detail(user_id: int) -> dict[str, Any] | None:
    u = db.fetch_one(
        """
        SELECT u.id, u.username, u.display_name, u.email, u.source, u.is_active,
               COALESCE(string_agg(r.name, ', ' ORDER BY r.name), '') AS roles
        FROM users u
        LEFT JOIN user_roles ur ON ur.user_id = u.id
        LEFT JOIN roles r ON r.id = ur.role_id
        WHERE u.id = %s
        GROUP BY u.id, u.username, u.display_name, u.email, u.source, u.is_active
        """,
        (user_id,),
    )
    if not u:
        return None
    role_rows = db.fetch_all(
        "SELECT role_id FROM user_roles WHERE user_id = %s ORDER BY role_id",
        (user_id,),
    )
    team_rows = db.fetch_all(
        "SELECT team_id FROM team_members WHERE user_id = %s ORDER BY team_id",
        (user_id,),
    )
    return {
        "id": int(u["id"]),
        "username": str(u["username"]),
        "display_name": u.get("display_name"),
        "email": u.get("email"),
        "source": str(u.get("source") or "local"),
        "is_active": bool(u.get("is_active")),
        "roles": str(u.get("roles") or ""),
        "role_ids": [int(r["role_id"]) for r in role_rows],
        "team_ids": [int(t["team_id"]) for t in team_rows],
    }


def update_user_profile(user_id: int, display_name: str | None, email: str | None) -> None:
    db.execute(
        """
        UPDATE users SET
            display_name = COALESCE(%s, display_name),
            email = COALESCE(%s, email),
            updated_at = NOW()
        WHERE id = %s
        """,
        (display_name, email, user_id),
    )
    clear_user_cache(user_id)


def set_user_teams_local(user_id: int, team_ids: list[int]) -> None:
    db.execute("DELETE FROM team_members WHERE user_id = %s", (user_id,))
    for tid in team_ids:
        db.execute(
            "INSERT INTO team_members (team_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (tid, user_id),
        )
    clear_user_cache(user_id)


def update_team_name(team_id: int, name: str) -> None:
    db.execute("UPDATE teams SET name = %s WHERE id = %s", (name.strip(), team_id))


def list_team_members(team_id: int) -> list[dict[str, Any]]:
    return db.fetch_all(
        """
        SELECT u.id AS user_id, u.username, u.display_name, u.email
        FROM team_members tm
        JOIN users u ON u.id = tm.user_id
        WHERE tm.team_id = %s
        ORDER BY u.username
        """,
        (team_id,),
    )


def add_team_members(team_id: int, user_ids: list[int]) -> None:
    for uid in user_ids:
        db.execute(
            "INSERT INTO team_members (team_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (team_id, uid),
        )
        clear_user_cache(uid)


def remove_team_member(team_id: int, user_id: int) -> None:
    db.execute(
        "DELETE FROM team_members WHERE team_id = %s AND user_id = %s",
        (team_id, user_id),
    )
    clear_user_cache(user_id)


def update_role_meta(role_id: int, name: str | None, description: str | None) -> None:
    row = db.fetch_one("SELECT id, name, description, is_system FROM roles WHERE id = %s", (role_id,))
    if not row or row.get("is_system"):
        raise ValueError("Cannot update system role")
    new_name = name.strip() if name is not None else str(row["name"])
    new_desc = description if description is not None else row.get("description")
    db.execute(
        "UPDATE roles SET name = %s, description = %s WHERE id = %s AND is_system IS FALSE",
        (new_name, new_desc, role_id),
    )
    clear_user_cache(None)


def delete_role_non_system(role_id: int) -> None:
    row = db.fetch_one("SELECT id, is_system FROM roles WHERE id = %s", (role_id,))
    if not row:
        raise ValueError("Role not found")
    if row.get("is_system"):
        raise ValueError("Cannot delete system role")
    db.execute("DELETE FROM roles WHERE id = %s AND is_system IS FALSE", (role_id,))
    clear_user_cache(None)
