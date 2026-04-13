"""User management endpoints."""

from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, HTTPException

from app import database as db
from app.models import (
    CreateUserRequest,
    ImportLdapUsersRequest,
    SetUserActiveRequest,
    SetUserRolesRequest,
    SetUserTeamsRequest,
    UpdateUserRequest,
    UserDetailOut,
    UserOut,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _hash_password(password: str) -> str:
    """bcrypt-compatible hash — delegates to passlib if available, falls back to sha256."""
    try:
        from passlib.context import CryptContext

        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return ctx.hash(password)
    except ImportError:
        return hashlib.sha256(password.encode()).hexdigest()


@router.get("/users", response_model=list[UserOut])
def list_users():
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
    return [UserOut(**r) for r in rows]


@router.post("/users", response_model=dict)
def create_user(body: CreateUserRequest):
    h = _hash_password(body.password)
    try:
        db.execute(
            """
            INSERT INTO users (username, display_name, password_hash, source, is_active)
            VALUES (%s, %s, %s, 'local', TRUE)
            """,
            (body.username.strip(), body.display_name or body.username.strip(), h),
        )
        row = db.fetch_one(
            "SELECT id FROM users WHERE lower(username) = lower(%s)",
            (body.username.strip(),),
        )
        if not row:
            raise HTTPException(status_code=500, detail="User created but id not found")
        uid = int(row["id"])
        for rid in body.role_ids:
            db.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (uid, rid),
            )
        return {"id": uid, "username": body.username.strip()}
    except Exception as exc:
        logger.warning("create_user failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/users/{user_id}/roles", response_model=dict)
def set_user_roles(user_id: int, body: SetUserRolesRequest):
    db.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
    for rid in body.role_ids:
        db.execute(
            "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_id, rid),
        )
    return {"ok": True}


@router.put("/users/{user_id}/active", response_model=dict)
def set_user_active(user_id: int, body: SetUserActiveRequest):
    db.execute(
        "UPDATE users SET is_active = %s, updated_at = NOW() WHERE id = %s",
        (body.is_active, user_id),
    )
    return {"ok": True}


def _upsert_ldap_user_row(
    username: str,
    display_name: str | None,
    email: str | None,
    user_dn: str,
) -> int:
    row = db.fetch_one("SELECT id FROM users WHERE lower(username) = lower(%s)", (username.strip(),))
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
            (display_name, email, user_dn, uid),
        )
        return uid
    db.execute(
        """
        INSERT INTO users (username, display_name, email, password_hash, source, ldap_dn, is_active)
        VALUES (%s, %s, %s, NULL, 'ldap', %s, TRUE)
        """,
        (username.strip(), display_name or username.strip(), email, user_dn),
    )
    row2 = db.fetch_one("SELECT id FROM users WHERE lower(username) = lower(%s)", (username.strip(),))
    return int(row2["id"]) if row2 else 0


@router.post("/users/import-ldap", response_model=dict)
def import_ldap_users(body: ImportLdapUsersRequest):
    if not body.users:
        raise HTTPException(status_code=422, detail="No users to import")

    imported: list[int] = []
    for entry in body.users:
        if not entry.username.strip():
            continue
        uid = _upsert_ldap_user_row(
            entry.username.strip(),
            entry.display_name,
            entry.email,
            entry.distinguished_name.strip(),
        )
        if not uid:
            continue
        imported.append(uid)

        db.execute("DELETE FROM user_roles WHERE user_id = %s", (uid,))
        for rid in body.role_ids:
            db.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (uid, rid),
            )

        db.execute("DELETE FROM team_members WHERE user_id = %s", (uid,))
        for tid in body.team_ids:
            db.execute(
                "INSERT INTO team_members (team_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (tid, uid),
            )

    return {"ok": True, "user_ids": imported, "count": len(imported)}


@router.put("/users/{user_id}", response_model=dict)
def update_user(user_id: int, body: UpdateUserRequest):
    row = db.fetch_one("SELECT id FROM users WHERE id = %s", (user_id,))
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    db.execute(
        """
        UPDATE users SET
            display_name = COALESCE(%s, display_name),
            email = COALESCE(%s, email),
            updated_at = NOW()
        WHERE id = %s
        """,
        (body.display_name, body.email, user_id),
    )
    return {"ok": True}


@router.put("/users/{user_id}/teams", response_model=dict)
def set_user_teams(user_id: int, body: SetUserTeamsRequest):
    row = db.fetch_one("SELECT id FROM users WHERE id = %s", (user_id,))
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    db.execute("DELETE FROM team_members WHERE user_id = %s", (user_id,))
    for tid in body.team_ids:
        db.execute(
            "INSERT INTO team_members (team_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (tid, user_id),
        )
    return {"ok": True}


@router.get("/users/{user_id}", response_model=UserDetailOut)
def get_user_detail(user_id: int):
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
        raise HTTPException(status_code=404, detail="User not found")

    role_rows = db.fetch_all(
        "SELECT role_id FROM user_roles WHERE user_id = %s ORDER BY role_id",
        (user_id,),
    )
    team_rows = db.fetch_all(
        "SELECT team_id FROM team_members WHERE user_id = %s ORDER BY team_id",
        (user_id,),
    )
    return UserDetailOut(
        id=int(u["id"]),
        username=str(u["username"]),
        display_name=u.get("display_name"),
        email=u.get("email"),
        source=str(u.get("source") or "local"),
        is_active=bool(u.get("is_active")),
        roles=str(u.get("roles") or ""),
        role_ids=[int(r["role_id"]) for r in role_rows],
        team_ids=[int(t["team_id"]) for t in team_rows],
    )
