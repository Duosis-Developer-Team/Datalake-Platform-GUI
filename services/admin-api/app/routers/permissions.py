"""Permission catalog endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app import database as db
from app.models import CreatePermissionRequest, PermissionOut

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(limit: int = 150):
    rows = db.fetch_all(
        "SELECT id, code, name, parent_id, resource_type, sort_order, is_dynamic "
        "FROM permissions ORDER BY code LIMIT %s",
        (min(limit, 500),),
    )
    return [PermissionOut(**r) for r in rows]


@router.post("/permissions", response_model=dict)
def add_permission(body: CreatePermissionRequest):
    pid = None
    if body.parent_code:
        pr = db.fetch_one("SELECT id FROM permissions WHERE code = %s", (body.parent_code,))
        if pr:
            pid = int(pr["id"])
    try:
        db.execute(
            """
            INSERT INTO permissions (
                code, name, description, parent_id, resource_type, route_pattern,
                component_id, icon, sort_order, is_dynamic
            ) VALUES (%s, %s, NULL, %s, %s, %s, NULL, NULL, 0, TRUE)
            ON CONFLICT (code) DO NOTHING
            """,
            (body.code, body.name, pid, body.resource_type, body.route_pattern),
        )
        return {"ok": True, "code": body.code}
    except Exception as exc:
        logger.warning("add_permission failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
