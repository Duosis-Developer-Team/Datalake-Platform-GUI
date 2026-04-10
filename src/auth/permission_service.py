"""Hierarchical permission resolution and helpers for UI."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from src.auth import db
from src.auth.config import AUTH_DISABLED

logger = logging.getLogger(__name__)

# In-process cache: user_id -> (computed_at_epoch, effective_map)
_CACHE: dict[int, tuple[float, dict[str, dict[str, bool]]]] = {}
_CACHE_TTL_SEC = float(os.environ.get("PERMISSION_MAP_CACHE_TTL_SEC", "300"))

_REDIS = None


def _redis_client():
    global _REDIS
    if _REDIS is False:
        return None
    if _REDIS is not None:
        return _REDIS
    url = (os.environ.get("REDIS_URL") or "").strip()
    if not url:
        _REDIS = False
        return None
    try:
        import redis

        _REDIS = redis.Redis.from_url(url, decode_responses=True)
        _REDIS.ping()
        return _REDIS
    except Exception as e:
        logger.warning("Redis unavailable for permission cache: %s", e)
        _REDIS = False
        return None


def _redis_key(uid: int) -> str:
    return f"dl:perm_map:{uid}"


def clear_user_cache(user_id: int | None = None) -> None:
    if user_id is None:
        _CACHE.clear()
        r = _redis_client()
        if r:
            try:
                for k in r.scan_iter(match="dl:perm_map:*"):
                    r.delete(k)
            except Exception:
                logger.exception("Redis clear permission keys failed")
    else:
        _CACHE.pop(user_id, None)
        r = _redis_client()
        if r:
            try:
                r.delete(_redis_key(user_id))
            except Exception:
                pass


def resolve_pathname_to_page_code(pathname: str | None) -> str | None:
    """Map URL path to the `page:*` permission code."""
    p = (pathname or "/").strip() or "/"
    if p in ("/", ""):
        return "page:overview"
    if p == "/datacenters":
        return "page:datacenters"
    if p.startswith("/datacenter/"):
        return "page:dc_view"
    if p.startswith("/dc-detail/"):
        return "page:dc_detail"
    if p == "/global-view":
        return "page:global_view"
    if p == "/region-drilldown":
        return "page:region_drilldown"
    if p == "/customer-view":
        return "page:customer_view"
    if p == "/query-explorer":
        return "page:query_explorer"
    if p == "/login":
        return None
    if p == "/settings" or p == "/settings/":
        return "grp:settings"
    if p.startswith("/settings/"):
        if p.startswith("/settings/users"):
            return "page:settings_users"
        if p.startswith("/settings/roles"):
            return "page:settings_roles"
        if p.startswith("/settings/permissions"):
            return "page:settings_permissions"
        if p.startswith("/settings/ldap"):
            return "page:settings_ldap"
        if p.startswith("/settings/teams"):
            return "page:settings_teams"
        if p.startswith("/settings/auth"):
            return "page:settings_auth"
        if p.startswith("/settings/audit"):
            return "page:settings_audit"
        return "grp:settings"
    return "page:overview"


def _user_role_ids(user_id: int) -> list[int]:
    rows = db.fetch_all(
        "SELECT role_id FROM user_roles WHERE user_id = %s",
        (user_id,),
    )
    return [int(r["role_id"]) for r in rows]


def _permission_row(code: str) -> dict[str, Any] | None:
    return db.fetch_one("SELECT * FROM permissions WHERE code = %s", (code,))


def _ancestors(perm_id: int) -> list[int]:
    out: list[int] = []
    cur = db.fetch_one("SELECT id, parent_id FROM permissions WHERE id = %s", (perm_id,))
    while cur:
        pid = int(cur["id"])
        out.append(pid)
        p = cur.get("parent_id")
        if not p:
            break
        cur = db.fetch_one("SELECT id, parent_id FROM permissions WHERE id = %s", (int(p),))
    return out


def _role_perm(role_id: int, perm_id: int) -> dict[str, Any] | None:
    return db.fetch_one(
        """
        SELECT can_view, can_edit, can_export FROM role_permissions
        WHERE role_id = %s AND permission_id = %s
        """,
        (role_id, perm_id),
    )


def _effective_triplet_for_role(role_id: int, perm_id: int) -> tuple[bool, bool, bool]:
    for aid in _ancestors(perm_id):
        rp = _role_perm(role_id, aid)
        if rp:
            return (
                bool(rp["can_view"]),
                bool(rp["can_edit"]),
                bool(rp["can_export"]),
            )
    return False, False, False


def effective_triplet(user_id: int | None, permission_code: str) -> tuple[bool, bool, bool]:
    """OR-merge across all roles for one permission code (inheritance-aware)."""
    if AUTH_DISABLED or user_id is None:
        return True, True, True
    prow = _permission_row(permission_code)
    if not prow:
        return False, False, False
    pid = int(prow["id"])
    roles = _user_role_ids(user_id)
    v = e = x = False
    for rid in roles:
        tv, te, tx = _effective_triplet_for_role(rid, pid)
        v, e, x = v or tv, e or te, x or tx
    return v, e, x


def can_view(user_id: int | None, permission_code: str) -> bool:
    return effective_triplet(user_id, permission_code)[0]


def can_edit(user_id: int | None, permission_code: str) -> bool:
    return effective_triplet(user_id, permission_code)[1]


def can_export(user_id: int | None, permission_code: str) -> bool:
    return effective_triplet(user_id, permission_code)[2]


def user_effective_map(user_id: int | None) -> dict[str, dict[str, bool]] | None:
    """All permission codes with effective triplets (for sidebar / stores). None = unrestricted UI."""
    if AUTH_DISABLED:
        return None
    if user_id is None:
        return {}
    uid = int(user_id)
    now = time.monotonic()
    hit = _CACHE.get(uid)
    if hit is not None:
        ts, cached = hit
        if now - ts < _CACHE_TTL_SEC:
            return cached

    r = _redis_client()
    if r:
        try:
            raw = r.get(_redis_key(uid))
            if raw:
                import json

                data = json.loads(raw)
                if isinstance(data, dict):
                    _CACHE[uid] = (now, data)
                    return data
        except Exception:
            logger.debug("Redis permission map read failed", exc_info=True)

    try:
        rows = db.fetch_all("SELECT code, id FROM permissions")
    except Exception:
        return None
    out: dict[str, dict[str, bool]] = {}
    for row in rows:
        code = str(row["code"])
        t = effective_triplet(uid, code)
        out[code] = {"view": t[0], "edit": t[1], "export": t[2]}
    _CACHE[uid] = (now, out)
    if r:
        try:
            import json

            from src.auth.config import SESSION_TTL_HOURS

            ttl = int(SESSION_TTL_HOURS) * 3600
            r.setex(_redis_key(uid), ttl, json.dumps(out))
        except Exception:
            pass
    return out


def subtree_codes(page_code: str) -> list[dict[str, Any]]:
    """All descendant rows under a page permission (recursive SQL)."""
    root = _permission_row(page_code)
    if not root:
        return []
    rid = int(root["id"])
    return db.fetch_all(
        """
        WITH RECURSIVE t AS (
            SELECT id, code, parent_id, resource_type FROM permissions WHERE id = %s
            UNION ALL
            SELECT p.id, p.code, p.parent_id, p.resource_type
            FROM permissions p
            INNER JOIN t ON p.parent_id = t.id
        )
        SELECT code, resource_type FROM t WHERE id <> %s
        """,
        (rid, rid),
    )


def get_visible_sections(user_id: int, page_code: str) -> set[str]:
    """
    Section / sub_section / action codes under page that user may use.
    For actions, requires can_export on that action node (or inherited).
    """
    vis: set[str] = set()
    for row in subtree_codes(page_code):
        code = str(row["code"])
        rt = str(row["resource_type"])
        if rt == "action":
            if can_export(user_id, code) or can_view(user_id, code):
                vis.add(code)
        elif rt in ("section", "sub_section", "widget"):
            if can_view(user_id, code):
                vis.add(code)
    return vis


def user_can_access_path(user_id: int, pathname: str | None) -> bool:
    code = resolve_pathname_to_page_code(pathname)
    if code is None:
        return True
    return can_view(user_id, code)
