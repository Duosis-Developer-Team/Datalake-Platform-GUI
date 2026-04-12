"""Role and permission matrix endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app import database as db
from app.models import RoleMatrixRequest, RoleOut, RolePermissionRow

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/roles", response_model=list[RoleOut])
def list_roles():
    rows = db.fetch_all("SELECT id, name, description, is_system FROM roles ORDER BY name")
    return [RoleOut(**r) for r in rows]


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
