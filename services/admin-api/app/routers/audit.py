"""Audit log read endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app import database as db
from app.models import AuditRow

router = APIRouter()


@router.get("/audit", response_model=list[AuditRow])
def list_audit(limit: int = 200):
    rows = db.fetch_all(
        """
        SELECT a.id, a.user_id, u.username, a.action, a.detail, a.ip_address,
               a.created_at::text AS created_at
        FROM audit_log a
        LEFT JOIN users u ON u.id = a.user_id
        ORDER BY a.created_at DESC
        LIMIT %s
        """,
        (min(limit, 500),),
    )
    return [AuditRow(**r) for r in rows]
