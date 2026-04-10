"""Flask routes for login/logout and auth API."""

from __future__ import annotations

import logging
from urllib.parse import quote

from flask import Blueprint, redirect, request, session, url_for

from src.auth import service
from src.auth.config import SESSION_COOKIE_NAME
from src.auth.ldap_service import (
    apply_ldap_role_mappings,
    get_active_ldap_config,
    list_user_groups,
    map_ldap_groups_to_roles,
    try_bind_user,
    upsert_ldap_user,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth_routes", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["POST"])
def login_post():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    nxt = request.form.get("next") or "/"
    user = service.authenticate_local(username, password)
    if not user:
        cfg = get_active_ldap_config()
        if cfg:
            ok, user_dn = try_bind_user(username, password, cfg)
            if ok and user_dn:
                uid = upsert_ldap_user(username, None, user_dn)
                groups = list_user_groups(user_dn, cfg)
                role_ids = map_ldap_groups_to_roles(int(cfg["id"]), groups)
                apply_ldap_role_mappings(uid, role_ids)
                user = service.get_user_by_id(uid)
    if not user:
        return redirect(f"/login?error=1&next={quote(nxt)}")
    token = service.create_session(
        int(user["id"]),
        request.remote_addr,
        request.headers.get("User-Agent"),
    )
    session[SESSION_COOKIE_NAME] = token
    service.audit(int(user["id"]), "login", None, request.remote_addr)
    return redirect(nxt or "/")


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    tok = session.get(SESSION_COOKIE_NAME)
    service.delete_session(tok)
    session.pop(SESSION_COOKIE_NAME, None)
    return redirect("/login")

