"""Load NiFi proxy catalog from HMDL sync registry (hmdl.proxy_node)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from app.config import settings

_logger = logging.getLogger(__name__)


def _proxy_row_to_entry(row: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(row["proxy_id"]),
        "proxy_nifi_host": str(row.get("proxy_nifi_host") or ""),
        "ssh_user": str(row.get("ssh_user") or "root"),
        "conf_path": str(row.get("conf_path") or "/Datalake_Project/configuration_file.json"),
        "gitea_audit_path": str(row.get("gitea_audit_path") or ""),
    }


def build_catalog_from_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return {dc_code: {dc_code, proxies: [...]}} from proxy_node rows."""
    catalog: dict[str, dict[str, Any]] = {}
    for row in rows:
        dc_code = str(row.get("dc_code") or "").upper()
        if not dc_code:
            continue
        block = catalog.setdefault(
            dc_code,
            {"dc_code": dc_code, "catalog_key": dc_code, "proxies": []},
        )
        block["proxies"].append(_proxy_row_to_entry(row))
    return catalog


def _load_proxy_catalog_from_yaml() -> dict[str, dict[str, Any]]:
    """Legacy fallback when proxy_node table is empty or unavailable."""
    path = Path(settings.proxy_assignment_path)
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    catalog: dict[str, dict[str, Any]] = {}
    for key, block in raw.items():
        if not isinstance(block, dict):
            continue
        dc_code = str(block.get("dc_code") or key).upper()
        proxies = block.get("proxies") or []
        catalog[dc_code] = {
            "dc_code": dc_code,
            "catalog_key": str(key),
            "proxies": [
                {
                    "id": str(p.get("id", "")),
                    "proxy_nifi_host": str(p.get("proxy_nifi_host", "")),
                    "ssh_user": str(p.get("ssh_user", "")),
                    "conf_path": str(p.get("conf_path", "")),
                    "gitea_audit_path": str(p.get("gitea_audit_path", "")),
                }
                for p in proxies
                if isinstance(p, dict) and p.get("id")
            ],
        }
    return catalog


def _fetch_sync_proxy_nodes() -> list[dict[str, Any]]:
    """Proxies registered during collector sync with at least one prod run."""
    from app.db import pool

    schema = settings.hmdl_schema
    try:
        return pool.fetch_all(
            f"""
            SELECT
                pn.proxy_id,
                pn.dc_code,
                pn.proxy_nifi_host,
                pn.ssh_user,
                pn.conf_path,
                pn.gitea_audit_path
            FROM {schema}.proxy_node pn
            WHERE EXISTS (
                SELECT 1
                FROM {schema}.collector_sync_log s
                WHERE s.proxy_id = pn.proxy_id
                  AND s.dry_run = FALSE
            )
            ORDER BY pn.dc_code, pn.proxy_id
            """
        )
    except Exception as exc:
        _logger.debug("proxy_node query failed, using YAML fallback: %s", exc)
        return []


def load_proxy_catalog() -> dict[str, dict[str, Any]]:
    """Return {dc_code: {dc_code, proxies: [{id, proxy_nifi_host, ...}]}}."""
    rows = _fetch_sync_proxy_nodes()
    if rows:
        return build_catalog_from_rows(rows)
    fallback = _load_proxy_catalog_from_yaml()
    if fallback:
        _logger.warning(
            "proxy_node registry empty; falling back to %s",
            settings.proxy_assignment_path,
        )
    return fallback


def list_dc_codes() -> list[str]:
    catalog = load_proxy_catalog()
    return sorted(catalog.keys())


def proxies_for_dc(dc_code: str) -> list[dict[str, Any]]:
    block = load_proxy_catalog().get(dc_code.upper(), {})
    return list(block.get("proxies") or [])


def all_proxy_ids() -> list[str]:
    ids: list[str] = []
    for block in load_proxy_catalog().values():
        for p in block.get("proxies") or []:
            pid = p.get("id")
            if pid:
                ids.append(str(pid))
    return ids


def proxy_to_dc_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for dc_code, block in load_proxy_catalog().items():
        for p in block.get("proxies") or []:
            mapping[str(p["id"])] = dc_code
    return mapping


def find_proxy_entry(proxy_id: str) -> tuple[str | None, dict[str, Any] | None]:
    """Return (dc_code, proxy_entry) for a proxy id."""
    for dc_code, block in load_proxy_catalog().items():
        for p in block.get("proxies") or []:
            if str(p.get("id")) == proxy_id:
                return dc_code, p
    return None, None
