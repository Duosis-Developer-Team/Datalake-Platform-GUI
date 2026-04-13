"""LDAP directory search using ldap3 (Active Directory compatible)."""

from __future__ import annotations

import logging
import re
from typing import Any

from ldap3 import ALL_ATTRIBUTES, NONE, Connection, Server
from ldap3.core.exceptions import LDAPException

from app.fernet_util import fernet_decrypt

logger = logging.getLogger(__name__)

_MAX_RESULTS = 50


def _servers(cfg: dict[str, Any]) -> list[Server]:
    hosts = [cfg["server_primary"]]
    if cfg.get("server_secondary"):
        hosts.append(cfg["server_secondary"])
    use_ssl = bool(cfg.get("use_ssl"))
    port = int(cfg.get("port") or (636 if use_ssl else 389))
    return [Server(h, port=port, use_ssl=use_ssl, get_info=NONE) for h in hosts]


def _bind_password(cfg: dict[str, Any]) -> str:
    bind_pw = cfg.get("bind_password") or ""
    try:
        return fernet_decrypt(str(bind_pw))
    except Exception:
        return str(bind_pw)


def _escape_ldap_filter_value(value: str) -> str:
    """RFC 4515 escape for assertion value (substring search)."""
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


def _sanitize_query(q: str) -> str:
    q = (q or "").strip()
    q = re.sub(r"\s+", " ", q)
    return q[:200]


def _user_dict_from_entry(e: Any) -> dict[str, Any] | None:
    """Build API user row from ldap3 Entry; DN from entry_dn only (never request distinguishedName)."""
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


def search_directory_users(
    cfg: dict[str, Any], query: str, *, size_limit: int | None = None
) -> list[dict[str, Any]]:
    """Search AD/LDAP for user objects matching query. Returns dicts with keys for LdapSearchResultUser."""
    lim = int(size_limit) if size_limit is not None else _MAX_RESULTS
    if lim < 1:
        lim = 1
    q = _sanitize_query(query)
    if len(q) < 2:
        raise ValueError("Query must be at least 2 characters")

    esc = _escape_ldap_filter_value(q)
    # AD: person + user + match on account name, mail, CN, displayName
    search_filter = (
        "(&(&(objectCategory=person)(objectClass=user))"
        f"(|(sAMAccountName=*{esc}*)(mail=*{esc}*)(cn=*{esc}*)(displayName=*{esc}*)))"
    )
    search_base = str(cfg.get("search_base_dn") or "")
    if not search_base:
        raise ValueError("search_base_dn is not configured")

    bind_pw = _bind_password(cfg)
    # With get_info=NONE the Server has no schema; requesting named attributes can trigger
    # "attribute type not present" on some directories. Return all attributes and map in code.
    for srv in _servers(cfg):
        try:
            conn = Connection(
                srv,
                user=str(cfg["bind_dn"]),
                password=bind_pw,
                auto_bind=True,
            )
            conn.search(
                search_base,
                search_filter,
                attributes=ALL_ATTRIBUTES,
                size_limit=lim,
            )
            out: list[dict[str, Any]] = []
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
