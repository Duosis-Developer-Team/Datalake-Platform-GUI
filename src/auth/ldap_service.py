"""LDAP authentication and group discovery (ldap3)."""

from __future__ import annotations

import logging
import re
from typing import Any

from ldap3 import ALL, ALL_ATTRIBUTES, Connection, Server
from ldap3.core.exceptions import LDAPException

from src.auth import db
from src.auth.crypto import fernet_decrypt, fernet_encrypt

logger = logging.getLogger(__name__)


def _servers(cfg: dict[str, Any]) -> list[Server]:
    hosts = [cfg["server_primary"]]
    if cfg.get("server_secondary"):
        hosts.append(cfg["server_secondary"])
    use_ssl = bool(cfg.get("use_ssl"))
    port = int(cfg.get("port") or (636 if use_ssl else 389))
    servers = []
    for h in hosts:
        servers.append(Server(h, port=port, use_ssl=use_ssl, get_info=ALL))
    return servers


def get_active_ldap_config() -> dict[str, Any] | None:
    return db.fetch_one(
        "SELECT * FROM ldap_config WHERE is_active IS TRUE ORDER BY id ASC LIMIT 1"
    )


_MAX_SEARCH_RESULTS = 50


def _escape_ldap_filter_value(value: str) -> str:
    out: list[str] = []
    for ch in value:
        if ch == "\\":
            out.append("\\5c")
        elif ch == "*":
            out.append("\\2a")
        elif ch == "(":
            out.append("\\28")
        elif ch == ")":
            out.append("\\29")
        elif ch == "\x00":
            out.append("\\00")
        else:
            out.append(ch)
    return "".join(out)


def _sanitize_search_query(q: str) -> str:
    q = (q or "").strip()
    q = re.sub(r"\s+", " ", q)
    return q[:200]


def _user_dict_from_entry(e: Any) -> dict[str, Any] | None:
    """Map ldap3 Entry to API row; DN from entry_dn only."""
    dn = str(e.entry_dn)
    sam = getattr(e, "sAMAccountName", None)
    uid = getattr(e, "uid", None)
    cn = getattr(e, "cn", None)
    username = ""
    if sam is not None and sam.value is not None:
        username = str(sam.value).strip()
    elif uid is not None and uid.value is not None:
        username = str(uid.value).strip()
    elif cn is not None and cn.value is not None:
        username = str(cn.value).strip()
    if not username:
        return None
    disp = getattr(e, "displayName", None)
    display_name = str(disp.value) if disp is not None and disp.value is not None else None
    mail_attr = getattr(e, "mail", None)
    email = str(mail_attr.value) if mail_attr is not None and mail_attr.value is not None else None
    return {
        "username": username,
        "display_name": display_name,
        "email": email,
        "distinguished_name": dn,
    }


def _search_directory_users_with_cfg(
    cfg: dict[str, Any], query: str, *, size_limit: int | None = None
) -> list[dict[str, Any]]:
    """Run user search against arbitrary LDAP config (same filter as admin-api)."""
    lim = int(size_limit) if size_limit is not None else _MAX_SEARCH_RESULTS
    if lim < 1:
        lim = 1
    q = _sanitize_search_query(query)
    if len(q) < 2:
        raise ValueError("Query must be at least 2 characters")

    search_base = str(cfg.get("search_base_dn") or "")
    if not search_base:
        raise ValueError("search_base_dn is not configured")

    q_stripped = q.strip()
    if q_stripped.upper().startswith("OU="):
        # OU path: search all user objects under this subtree (relative or full DN).
        if "," in q_stripped[3:]:
            effective_base = q_stripped
        else:
            effective_base = f"{q_stripped},{search_base}"
        search_filter = "(&(objectCategory=person)(objectClass=user))"
    else:
        esc = _escape_ldap_filter_value(q)
        effective_base = search_base
        search_filter = (
            "(&(&(objectCategory=person)(objectClass=user))"
            f"(|(sAMAccountName=*{esc}*)(mail=*{esc}*)(cn=*{esc}*)(displayName=*{esc}*)))"
        )

    bind_pw = cfg.get("bind_password") or ""
    try:
        bind_pw = fernet_decrypt(str(bind_pw))
    except Exception:
        bind_pw = str(bind_pw)

    out: list[dict[str, Any]] = []

    for srv in _servers(cfg):
        try:
            conn = Connection(
                srv,
                user=str(cfg["bind_dn"]),
                password=bind_pw,
                auto_bind=True,
            )
            conn.search(effective_base, search_filter, attributes=ALL_ATTRIBUTES, size_limit=lim)
            for e in conn.entries:
                try:
                    row = _user_dict_from_entry(e)
                    if row:
                        out.append(row)
                except Exception as ex:
                    logger.debug("Skip malformed LDAP entry: %s", ex)
                    continue
            conn.unbind()
            return out
        except LDAPException as ex:
            logger.warning("LDAP search failed on %s: %s", srv, ex)
            continue
        except Exception as ex:
            logger.warning("LDAP error on %s: %s", srv, ex)
            continue

    raise RuntimeError("Could not connect to LDAP or search failed on all servers")


def search_directory_users(query: str) -> list[dict[str, Any]]:
    """Search AD/LDAP for user objects (admin UI). Same semantics as admin-api /ldap/search."""
    cfg = get_active_ldap_config()
    if not cfg:
        raise ValueError("No active LDAP configuration")
    return _search_directory_users_with_cfg(dict(cfg), query)


def test_ldap_connection(
    server_primary: str,
    server_secondary: str | None,
    port: int,
    use_ssl: bool,
    bind_dn: str,
    bind_password_plain: str | None,
    search_base_dn: str,
    user_search_filter: str,
    ldap_id: int | None,
    test_query: str = "test",
) -> dict[str, Any]:
    """Bind + sample user search for Settings 'Test connection' (no ADMIN_API_URL)."""
    pw = bind_password_plain
    if (not pw or not str(pw).strip()) and ldap_id:
        row = db.fetch_one("SELECT bind_password FROM ldap_config WHERE id = %s", (ldap_id,))
        if row:
            pw = row.get("bind_password")
    cfg = {
        "server_primary": server_primary,
        "server_secondary": server_secondary,
        "port": port,
        "use_ssl": use_ssl,
        "bind_dn": bind_dn,
        "bind_password": pw or "",
        "search_base_dn": search_base_dn,
        "user_search_filter": user_search_filter,
    }
    q = _sanitize_search_query(test_query or "test")
    if len(q) < 2:
        q = "te"
    try:
        rows = _search_directory_users_with_cfg(cfg, q, size_limit=3)
        return {
            "ok": True,
            "bind": True,
            "search_count": len(rows),
            "message": f"Bind OK, {len(rows)} user(s) found for query {q!r}.",
        }
    except ValueError as exc:
        return {"ok": False, "bind": False, "search_count": 0, "error": str(exc)}
    except RuntimeError as exc:
        return {"ok": False, "bind": False, "search_count": 0, "error": str(exc)}


def try_bind_user(username: str, password: str, cfg: dict[str, Any]) -> tuple[bool, str | None]:
    """Try user bind using search to resolve DN. Returns (ok, user_dn)."""
    bind_pw = cfg.get("bind_password") or ""
    try:
        bind_pw = fernet_decrypt(str(bind_pw))
    except Exception:
        bind_pw = str(bind_pw)

    user_filter = (cfg.get("user_search_filter") or "(sAMAccountName={username})").replace(
        "{username}", username
    )
    search_base = cfg.get("search_base_dn") or ""

    for srv in _servers(cfg):
        try:
            conn = Connection(
                srv,
                user=str(cfg["bind_dn"]),
                password=bind_pw,
                auto_bind=True,
            )
            conn.search(search_base, user_filter, attributes=["distinguishedName", "cn"])
            if not conn.entries:
                conn.unbind()
                continue
            user_dn = str(conn.entries[0].distinguishedName)
            conn.unbind()
            uconn = Connection(srv, user=user_dn, password=password, auto_bind=True)
            uconn.unbind()
            return True, user_dn
        except LDAPException as e:
            logger.info("LDAP bind attempt failed on %s: %s", srv, e)
            continue
        except Exception as e:
            logger.warning("LDAP error: %s", e)
            continue
    return False, None


def list_user_groups(user_dn: str, cfg: dict[str, Any]) -> list[str]:
    """Return group DNs for user (best-effort)."""
    bind_pw = cfg.get("bind_password") or ""
    try:
        bind_pw = fernet_decrypt(str(bind_pw))
    except Exception:
        bind_pw = str(bind_pw)
    search_base = cfg.get("search_base_dn") or ""
    filt = f"(&(objectClass=group)(member={user_dn}))"
    groups: list[str] = []
    for srv in _servers(cfg):
        try:
            conn = Connection(
                srv,
                user=str(cfg["bind_dn"]),
                password=bind_pw,
                auto_bind=True,
            )
            conn.search(search_base, filt, attributes=["distinguishedName"])
            for e in conn.entries:
                groups.append(str(e.distinguishedName))
            conn.unbind()
            return groups
        except Exception:
            continue
    return groups


def encrypt_bind_password_for_storage(plain: str) -> str:
    return fernet_encrypt(plain)


def map_ldap_groups_to_roles(ldap_config_id: int, group_dns: list[str]) -> list[int]:
    if not group_dns:
        return []
    rows = db.fetch_all(
        """
        SELECT role_id FROM ldap_group_role_mapping
        WHERE ldap_config_id = %s AND ldap_group_dn = ANY(%s)
        """,
        (ldap_config_id, group_dns),
    )
    return [int(r["role_id"]) for r in rows]


def upsert_ldap_user(username: str, display_name: str | None, user_dn: str) -> int:
    row = db.fetch_one("SELECT id FROM users WHERE lower(username) = lower(%s)", (username,))
    if row:
        db.execute(
            """
            UPDATE users SET display_name = COALESCE(%s, display_name), ldap_dn = %s, source = 'ldap', updated_at = NOW()
            WHERE id = %s
            """,
            (display_name, user_dn, int(row["id"])),
        )
        return int(row["id"])
    db.execute(
        """
        INSERT INTO users (username, display_name, password_hash, source, ldap_dn, is_active)
        VALUES (%s, %s, NULL, 'ldap', %s, TRUE)
        """,
        (username, display_name or username, user_dn),
    )
    row2 = db.fetch_one("SELECT id FROM users WHERE lower(username) = lower(%s)", (username,))
    return int(row2["id"]) if row2 else 0


def apply_ldap_role_mappings(user_id: int, role_ids: list[int]) -> None:
    """Replace user roles from LDAP mapping (additive merge with existing local roles optional)."""
    if not role_ids:
        return
    for rid in set(role_ids):
        db.execute(
            """
            INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (user_id, rid),
        )
