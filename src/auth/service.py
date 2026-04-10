"""Authentication, sessions, and user helpers."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.auth import db
from src.auth.config import SESSION_TTL_HOURS
from src.auth.crypto import new_session_token, verify_password
from src.auth.models import UserPublic
from src.auth.permission_service import clear_user_cache

logger = logging.getLogger(__name__)


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    return db.fetch_one("SELECT * FROM users WHERE id = %s AND is_active IS TRUE", (user_id,))


def get_user_by_username(username: str) -> dict[str, Any] | None:
    return db.fetch_one("SELECT * FROM users WHERE lower(username) = lower(%s)", (username,))


def authenticate_local(username: str, password: str) -> dict[str, Any] | None:
    u = get_user_by_username(username.strip())
    if not u or not u.get("password_hash"):
        return None
    if not verify_password(password, str(u["password_hash"])):
        return None
    return u


def create_session(user_id: int, ip: str | None, ua: str | None) -> str:
    token = new_session_token()
    exp = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
    db.execute(
        """
        INSERT INTO sessions (id, user_id, expires_at, ip_address, user_agent)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (token, user_id, exp, ip, ua),
    )
    clear_user_cache(user_id)
    return token


def delete_session(token: str | None) -> None:
    if not token:
        return
    row = db.fetch_one("SELECT user_id FROM sessions WHERE id = %s", (token,))
    db.execute("DELETE FROM sessions WHERE id = %s", (token,))
    if row:
        clear_user_cache(int(row["user_id"]))


def get_session_user(session_token: str | None) -> dict[str, Any] | None:
    if not session_token:
        return None
    row = db.fetch_one(
        """
        SELECT s.id AS sid, s.user_id, s.expires_at, u.*
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.id = %s AND u.is_active IS TRUE
        """,
        (session_token,),
    )
    if not row:
        return None
    exp = row.get("expires_at")
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and datetime.now(timezone.utc) > exp:
        delete_session(session_token)
        return None
    return row


def to_public_user(row: dict[str, Any]) -> UserPublic:
    return UserPublic(
        id=int(row["id"]),
        username=str(row["username"]),
        display_name=row.get("display_name"),
        email=row.get("email"),
        source=str(row.get("source") or "local"),
        is_active=bool(row.get("is_active", True)),
    )


def audit(user_id: int | None, action: str, detail: str | None, ip: str | None) -> None:
    try:
        db.execute(
            "INSERT INTO audit_log (user_id, action, detail, ip_address) VALUES (%s, %s, %s, %s)",
            (user_id, action, detail, ip),
        )
    except Exception:
        logger.exception("audit_log insert failed")
