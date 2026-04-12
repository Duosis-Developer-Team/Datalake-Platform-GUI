"""User management endpoints."""

from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, HTTPException

from app import database as db
from app.models import CreateUserRequest, SetUserActiveRequest, SetUserRolesRequest, UserOut

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
