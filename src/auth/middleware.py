"""Flask before_request: session gate and public paths."""

from __future__ import annotations

import logging
import os
from typing import Any

from flask import g, jsonify, redirect, request, session
from opentelemetry import trace

from src.auth import dash_gate, service
from src.auth.config import AUTH_DISABLED, SESSION_COOKIE_NAME

logger = logging.getLogger(__name__)

# Only the callback transport carries data. The rest of /_dash* is shell
# plumbing (layout skeleton, dependency graph, component bundles) and must stay
# reachable or the browser cannot boot far enough to show the login form.
DASH_CALLBACK_PATH = "/_dash-update-component"


def _hydrate_g_from_session() -> None:
    """Set g.auth_user / g.auth_user_id when a valid session token exists."""
    tok = session.get(SESSION_COOKIE_NAME)
    urow = service.get_session_user(tok)
    if urow:
        g.auth_user = urow
        g.auth_user_id = int(urow["id"])


def _is_public_path(path: str) -> bool:
    if path in ("/login", "/favicon.ico"):
        return True
    if path.startswith("/assets/") or path.startswith("/_dash") or path.startswith("/static/"):
        return True
    if path.startswith("/auth/"):
        return True
    if path.startswith("/telemetry/"):
        return True
    # Release-ingest routes authenticate with a shared token, not a session.
    # Scoped to this prefix on purpose: a blanket /internal/ rule would make
    # every future blueprint mounted there session-public by accident.
    if path == "/internal/platform/releases" or path.startswith("/internal/platform/releases/"):
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

        # Dash internal routes (e.g. POST /_dash-update-component) are "public" for
        # redirect purposes but must still populate g from the session cookie so
        # callbacks (render_main_content, sidebar, etc.) see auth_user_id.
        if path.startswith("/_dash"):
            _hydrate_g_from_session()
            if getattr(g, "auth_user_id", None) is not None:
                logger.debug(
                    "dash path session hydrated user_id=%s request_path=%s",
                    g.auth_user_id,
                    path,
                )
                return None
            if path.startswith(DASH_CALLBACK_PATH):
                # No session: the shell may still boot and render the login
                # form, but page callbacks must not serve data. See
                # src/auth/dash_gate.py for why the output id is the key.
                body = request.get_json(silent=True)
                if not dash_gate.is_public_callback_request(body):
                    output = body.get("output") if isinstance(body, dict) else None
                    logger.warning(
                        "dash callback denied without session output=%s remote=%s",
                        output,
                        request.remote_addr,
                    )
                    return jsonify({"error": "session_expired"}), 401
            return None

        if _is_public_path(path):
            return None

        _hydrate_g_from_session()
        urow = getattr(g, "auth_user", None)
        if not urow:
            from urllib.parse import quote

            nxt = request.full_path if request.query_string else request.path
            return redirect(f"/login?next={quote(nxt, safe='/?&=')}")

        return None

    @app.after_request
    def _otel_enduser_attributes(response):  # type: ignore[no-untyped-def]
        """Attach enduser.* attributes to the active HTTP server span for trace correlation."""
        if os.environ.get("OTEL_ENABLED", "").strip().lower() not in ("1", "true", "yes", "on"):
            return response
        try:
            span = trace.get_current_span()
            if span is None or not span.is_recording():
                return response
            uid = getattr(g, "auth_user_id", None)
            if uid is not None:
                span.set_attribute("enduser.id", str(uid))
            urow = getattr(g, "auth_user", None)
            if isinstance(urow, dict) and urow.get("username"):
                span.set_attribute("enduser.name", str(urow["username"])[:256])
        except Exception:
            pass
        return response
