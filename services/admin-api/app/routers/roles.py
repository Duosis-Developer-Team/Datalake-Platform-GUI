"""Role and permission matrix endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app import database as db
from app.models import RoleMatrixRequest, RoleOut, RolePermissionRow, UpdateRoleRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/roles", response_model=list[RoleOut])
def list_roles():
    rows = db.fetch_all("SELECT id, name, description, is_system FROM roles ORDER BY name")
    return [RoleOut(**r) for r in rows]


@router.put("/roles/{role_id}", response_model=dict)
def update_role(role_id: int, body: UpdateRoleRequest):
    row = db.fetch_one("SELECT id, name, description, is_system FROM roles WHERE id = %s", (role_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Role not found")
    if row.get("is_system"):
        raise HTTPException(status_code=403, detail="System roles cannot be renamed")

    name = body.name.strip() if body.name is not None else str(row["name"])
    description = body.description if body.description is not None else row.get("description")
    if not name:
        raise HTTPException(status_code=422, detail="Name is required")

    try:
        db.execute(
            "UPDATE roles SET name = %s, description = %s WHERE id = %s AND is_system IS FALSE",
            (name, description, role_id),
        )
        return {"ok": True}
    except Exception as exc:
        logger.warning("update_role failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/roles/{role_id}", response_model=dict)
def delete_role(role_id: int):
    """Remove a non-system role (hard delete). Fails if still referenced."""
    row = db.fetch_one("SELECT id, is_system FROM roles WHERE id = %s", (role_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Role not found")
    if row.get("is_system"):
        raise HTTPException(status_code=403, detail="System roles cannot be deleted")
    try:
        db.execute("DELETE FROM roles WHERE id = %s AND is_system IS FALSE", (role_id,))
        return {"ok": True}
    except Exception as exc:
        logger.warning("delete_role failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/roles/{role_id}/permissions", response_model=list[RolePermissionRow])
def get_role_permissions(role_id: int):
    rows = db.fetch_all(
        "SELECT permission_id, can_view, can_edit, can_export FROM role_permissions WHERE role_id = %s",
        (role_id,),
    )
    return [RolePermissionRow(**r) for r in rows]


@router.post("/roles/{role_id}/matrix", response_model=dict)
def set_role_matrix(role_id: int, body: RoleMatrixRequest):
    try:
        with db.connection() as conn:
            cur = conn.cursor()
            for pid, v, e, x in body.triplets:
                cur.execute(
                    """
                    INSERT INTO role_permissions (role_id, permission_id, can_view, can_edit, can_export)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (role_id, permission_id) DO UPDATE SET
                        can_view = EXCLUDED.can_view,
                        can_edit = EXCLUDED.can_edit,
                        can_export = EXCLUDED.can_export
                    """,
                    (role_id, pid, v, e, x),
                )
            cur.close()
        logger.info("Role matrix updated for role_id=%s (%d rows)", role_id, len(body.triplets))
        return {"ok": True, "rows": len(body.triplets)}
    except Exception as exc:
        logger.error("set_role_matrix failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
