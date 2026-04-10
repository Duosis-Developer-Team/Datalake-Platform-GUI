"""Flask before_request: session gate and public paths."""

from __future__ import annotations

import logging
from typing import Any

from flask import g, redirect, request, session

from src.auth import service
from src.auth.config import AUTH_DISABLED, SESSION_COOKIE_NAME

logger = logging.getLogger(__name__)


def _is_public_path(path: str) -> bool:
    if path in ("/login", "/favicon.ico"):
        return True
    if path.startswith("/assets/") or path.startswith("/_dash") or path.startswith("/static/"):
        return True
    if path.startswith("/auth/"):
        return True
    return False


def register_middleware(app) -> None:
    @app.before_request
    def _gate() -> Any:
        g.auth_user = None
        g.auth_user_id = None
        path = request.path or "/"

        if AUTH_DISABLED:
            row = service.get_user_by_username("admin")
            if row:
                g.auth_user = row
                g.auth_user_id = int(row["id"])
            return None

        # Logged-in users should not stay on /login
        if path == "/login":
            tok = session.get(SESSION_COOKIE_NAME)
            if service.get_session_user(tok):
                nxt = request.args.get("next") or "/"
                return redirect(nxt)
            return None

        if _is_public_path(path):
            return None

        tok = session.get(SESSION_COOKIE_NAME)
        urow = service.get_session_user(tok)
        if not urow:
            from urllib.parse import quote

            nxt = request.full_path if request.query_string else request.path
            return redirect(f"/login?next={quote(nxt, safe='/?&=')}")

        g.auth_user = urow
        g.auth_user_id = int(urow["id"])
        return None
