"""Permission registry: catalog sync to database."""

from __future__ import annotations

import logging
from typing import Any

from src.auth import db
from src.auth.models import PermissionNode
from src.auth.permission_catalog import build_default_permission_roots

logger = logging.getLogger(__name__)


def _flatten_nodes(
    nodes: list[PermissionNode],
    parent_code: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for n in nodes:
        rows.append(
            {
                "code": n.code,
                "name": n.name,
                "parent_code": parent_code,
                "resource_type": n.resource_type,
                "route_pattern": n.route_pattern,
                "component_id": n.component_id,
                "icon": n.icon,
                "sort_order": n.sort_order,
                "is_dynamic": False,
            }
        )
        if n.children:
            rows.extend(_flatten_nodes(list(n.children), n.code))
    return rows


def sync_permissions_from_catalog() -> None:
    """Upsert static permission nodes from code catalog (non-dynamic rows)."""
    roots = build_default_permission_roots()
    flat = _flatten_nodes(roots, None)
    # Insert parents before children: sort by depth (parent first)
    code_to_row = {r["code"]: r for r in flat}
    ordered: list[dict[str, Any]] = []

    def depth(code: str) -> int:
        d = 0
        cur = code_to_row.get(code)
        while cur and cur["parent_code"]:
            d += 1
            cur = code_to_row.get(cur["parent_code"])
        return d

    flat_sorted = sorted(flat, key=lambda r: (depth(r["code"]), r["code"]))
    with db.connection() as conn:
        cur = conn.cursor()
        id_by_code: dict[str, int] = {}
        cur.execute("SELECT id, code FROM permissions")
        for rid, code in cur.fetchall():
            id_by_code[str(code)] = int(rid)

        for r in flat_sorted:
            pid = None
            if r["parent_code"]:
                pid = id_by_code.get(r["parent_code"])
            cur.execute(
                """
                INSERT INTO permissions (
                    code, name, description, parent_id, resource_type,
                    route_pattern, component_id, icon, sort_order, is_dynamic
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    parent_id = EXCLUDED.parent_id,
                    resource_type = EXCLUDED.resource_type,
                    route_pattern = EXCLUDED.route_pattern,
                    component_id = EXCLUDED.component_id,
                    icon = EXCLUDED.icon,
                    sort_order = EXCLUDED.sort_order
                WHERE permissions.is_dynamic IS NOT TRUE
                """,
                (
                    r["code"],
                    r["name"],
                    None,
                    pid,
                    r["resource_type"],
                    r["route_pattern"],
                    r["component_id"],
                    r["icon"],
                    r["sort_order"],
                    False,
                ),
            )
            cur.execute("SELECT id FROM permissions WHERE code = %s", (r["code"],))
            one = cur.fetchone()
            if one:
                id_by_code[r["code"]] = int(one[0])
        cur.close()
    logger.info("Permission catalog synced (%d nodes)", len(flat_sorted))


def sync_permissions_from_catalog_safe() -> None:
    try:
        sync_permissions_from_catalog()
    except Exception:
        logger.exception("sync_permissions_from_catalog failed")
