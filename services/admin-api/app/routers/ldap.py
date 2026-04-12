"""LDAP configuration endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app import database as db
from app.ldap_ops import search_directory_users
from app.models import (
    AddLdapMappingRequest,
    LdapConfigOut,
    LdapGroupMappingOut,
    LdapSearchResultUser,
    UpsertLdapRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _fernet_encrypt(plain: str) -> str:
    """Encrypt plain text using FERNET_KEY; returns plain if key not set."""
    from app import config

    if not config.FERNET_KEY:
        return plain
    try:
        from cryptography.fernet import Fernet

        f = Fernet(config.FERNET_KEY.encode())
        return f.encrypt(plain.encode()).decode()
    except Exception as exc:
        logger.warning("Fernet encrypt failed: %s", exc)
        return plain


@router.get("/ldap/search", response_model=list[LdapSearchResultUser])
def ldap_search_users(q: str | None = None):
    """Search Active Directory / LDAP for users using the active ldap_config."""
    query = (q or "").strip()
    if len(query) < 2:
        raise HTTPException(status_code=422, detail="Query must be at least 2 characters")

    row = db.fetch_one(
        "SELECT * FROM ldap_config WHERE is_active IS TRUE ORDER BY id ASC LIMIT 1"
    )
    if not row:
        raise HTTPException(status_code=400, detail="No active LDAP configuration")

    try:
        rows = search_directory_users(dict(row), query)
        return [LdapSearchResultUser(**r) for r in rows]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("ldap_search_users failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/ldap", response_model=list[LdapConfigOut])
def list_ldap_configs():
    rows = db.fetch_all(
        "SELECT id, name, server_primary, server_secondary, port, use_ssl, "
        "bind_dn, search_base_dn, user_search_filter, is_active FROM ldap_config ORDER BY id"
    )
    return [LdapConfigOut(**r) for r in rows]


@router.post("/ldap", response_model=dict)
def upsert_ldap_config(body: UpsertLdapRequest):
    enc_pw: str | None = None
    if body.bind_password and body.bind_password.strip():
        enc_pw = _fernet_encrypt(body.bind_password.strip())

    if body.ldap_id:
        row = db.fetch_one("SELECT bind_password FROM ldap_config WHERE id = %s", (body.ldap_id,))
        if enc_pw is None and row:
            enc_pw = str(row.get("bind_password") or "")
        try:
            db.execute(
                """
                UPDATE ldap_config SET
                    name = %s, server_primary = %s, server_secondary = %s, port = %s, use_ssl = %s,
                    bind_dn = %s, bind_password = %s, search_base_dn = %s,
                    user_search_filter = %s, is_active = %s
                WHERE id = %s
                """,
                (
                    body.name, body.server_primary, body.server_secondary, body.port, body.use_ssl,
                    body.bind_dn, enc_pw or "", body.search_base_dn, body.user_search_filter,
                    body.is_active, body.ldap_id,
                ),
            )
            return {"ok": True, "id": body.ldap_id}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        db.execute(
            """
            INSERT INTO ldap_config (
                name, server_primary, server_secondary, port, use_ssl, bind_dn, bind_password,
                search_base_dn, user_search_filter, is_active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                body.name, body.server_primary, body.server_secondary, body.port, body.use_ssl,
                body.bind_dn, enc_pw or "", body.search_base_dn, body.user_search_filter,
                body.is_active,
            ),
        )
        row = db.fetch_one("SELECT id FROM ldap_config ORDER BY id DESC LIMIT 1")
        return {"ok": True, "id": int(row["id"]) if row else None}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/ldap/{ldap_id}/mappings", response_model=list[LdapGroupMappingOut])
def list_ldap_mappings(ldap_id: int):
    rows = db.fetch_all(
        """
        SELECT m.id, m.ldap_group_dn, m.role_id, r.name AS role_name
        FROM ldap_group_role_mapping m
        JOIN roles r ON r.id = m.role_id
        WHERE m.ldap_config_id = %s
        ORDER BY m.ldap_group_dn
        """,
        (ldap_id,),
    )
    return [LdapGroupMappingOut(**r) for r in rows]


@router.post("/ldap/{ldap_id}/mappings", response_model=dict)
def add_ldap_mapping(ldap_id: int, body: AddLdapMappingRequest):
    if not body.ldap_group_dn.strip():
        raise HTTPException(status_code=422, detail="ldap_group_dn is required")
    try:
        db.execute(
            """
            INSERT INTO ldap_group_role_mapping (ldap_config_id, ldap_group_dn, role_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (ldap_config_id, ldap_group_dn, role_id) DO NOTHING
            """,
            (ldap_id, body.ldap_group_dn.strip(), body.role_id),
        )
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/ldap/mappings/{mapping_id}", response_model=dict)
def delete_ldap_mapping(mapping_id: int):
    db.execute("DELETE FROM ldap_group_role_mapping WHERE id = %s", (mapping_id,))
    return {"ok": True}
