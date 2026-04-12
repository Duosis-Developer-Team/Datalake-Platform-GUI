"""HTTP client for the admin-api microservice.

When ADMIN_API_URL is set, all settings CRUD operations are routed through
the admin-api service instead of accessing the auth database directly.
If ADMIN_API_URL is not set, falls back to the local settings_crud module
so the app continues to work in single-service deployments.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_ADMIN_API_URL = (os.environ.get("ADMIN_API_URL") or "").rstrip("/")
_USE_API = bool(_ADMIN_API_URL)


def _get(path: str, params: dict | None = None) -> Any:
    import httpx

    url = f"{_ADMIN_API_URL}{path}"
    try:
        r = httpx.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.error("admin_client GET %s failed: %s", path, exc)
        raise


def _post(path: str, json: dict | None = None) -> Any:
    import httpx

    url = f"{_ADMIN_API_URL}{path}"
    try:
        r = httpx.post(url, json=json, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.error("admin_client POST %s failed: %s", path, exc)
        raise


def _put(path: str, json: dict | None = None) -> Any:
    import httpx

    url = f"{_ADMIN_API_URL}{path}"
    try:
        r = httpx.put(url, json=json, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.error("admin_client PUT %s failed: %s", path, exc)
        raise


def _delete(path: str) -> Any:
    import httpx

    url = f"{_ADMIN_API_URL}{path}"
    try:
        r = httpx.delete(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.error("admin_client DELETE %s failed: %s", path, exc)
        raise


# ---------------------------------------------------------------------------
# Public interface — mirrors src/auth/settings_crud.py signature exactly
# so callers can switch between implementations without code changes.
# ---------------------------------------------------------------------------

def list_users_with_roles() -> list[dict[str, Any]]:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.list_users_with_roles()
    return _get("/api/v1/users")


def list_roles() -> list[dict[str, Any]]:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.list_roles()
    return _get("/api/v1/roles")


def list_permissions_flat() -> list[dict[str, Any]]:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.list_permissions_flat()
    return _get("/api/v1/permissions", {"limit": 500})


def get_role_permission_rows(role_id: int) -> list[dict[str, Any]]:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.get_role_permission_rows(role_id)
    return _get(f"/api/v1/roles/{role_id}/permissions")


def bulk_set_role_matrix(role_id: int, triplets: list[tuple[int, bool, bool, bool]]) -> None:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.bulk_set_role_matrix(role_id, triplets)
    _post(f"/api/v1/roles/{role_id}/matrix", {"triplets": triplets})


def create_local_user(username: str, password: str, display_name: str | None) -> int:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.create_local_user(username, password, display_name)
    data = _post("/api/v1/users", {
        "username": username,
        "password": password,
        "display_name": display_name,
        "role_ids": [],
    })
    return int(data.get("id", 0))


def set_user_roles(user_id: int, role_ids: list[int]) -> None:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.set_user_roles(user_id, role_ids)
    _put(f"/api/v1/users/{user_id}/roles", {"role_ids": role_ids})


def set_user_active(user_id: int, active: bool) -> None:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.set_user_active(user_id, active)
    _put(f"/api/v1/users/{user_id}/active", {"is_active": active})


def list_ldap_configs() -> list[dict[str, Any]]:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.list_ldap_configs()
    return _get("/api/v1/ldap")


def upsert_ldap_config(
    ldap_id: int | str | None,
    name: str,
    server_primary: str,
    server_secondary: str | None,
    port: int,
    use_ssl: bool,
    bind_dn: str,
    bind_password_plain: str | None,
    search_base_dn: str,
    user_search_filter: str,
    is_active: bool,
) -> None:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.upsert_ldap_config(
            ldap_id, name, server_primary, server_secondary, port, use_ssl,
            bind_dn, bind_password_plain, search_base_dn, user_search_filter, is_active,
        )
    lid = None
    if ldap_id and str(ldap_id).strip().isdigit():
        lid = int(ldap_id)
    _post("/api/v1/ldap", {
        "ldap_id": lid,
        "name": name,
        "server_primary": server_primary,
        "server_secondary": server_secondary,
        "port": port,
        "use_ssl": use_ssl,
        "bind_dn": bind_dn,
        "bind_password": bind_password_plain,
        "search_base_dn": search_base_dn,
        "user_search_filter": user_search_filter,
        "is_active": is_active,
    })


def list_ldap_group_mappings(ldap_config_id: int) -> list[dict[str, Any]]:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.list_ldap_group_mappings(ldap_config_id)
    return _get(f"/api/v1/ldap/{ldap_config_id}/mappings")


def add_ldap_group_mapping(ldap_config_id: int, ldap_group_dn: str, role_id: int) -> None:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.add_ldap_group_mapping(ldap_config_id, ldap_group_dn, role_id)
    _post(f"/api/v1/ldap/{ldap_config_id}/mappings", {
        "ldap_group_dn": ldap_group_dn,
        "role_id": role_id,
    })


def delete_ldap_group_mapping(mapping_id: int) -> None:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.delete_ldap_group_mapping(mapping_id)
    _delete(f"/api/v1/ldap/mappings/{mapping_id}")


def list_teams() -> list[dict[str, Any]]:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.list_teams()
    return _get("/api/v1/teams")


def create_team(name: str, parent_id: int | None, created_by: int | None) -> None:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.create_team(name, parent_id, created_by)
    _post("/api/v1/teams", {"name": name, "parent_id": parent_id})


def list_audit_log(limit: int = 200) -> list[dict[str, Any]]:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.list_audit_log(limit)
    return _get("/api/v1/audit", {"limit": limit})


def insert_dynamic_permission(
    code: str,
    name: str,
    parent_code: str | None,
    resource_type: str,
    route_pattern: str | None,
) -> None:
    if not _USE_API:
        from src.auth import settings_crud
        return settings_crud.insert_dynamic_permission(code, name, parent_code, resource_type, route_pattern)
    _post("/api/v1/permissions", {
        "code": code,
        "name": name,
        "parent_code": parent_code,
        "resource_type": resource_type,
        "route_pattern": route_pattern,
    })
