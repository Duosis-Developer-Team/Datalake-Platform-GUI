"""Team management endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app import database as db
from app.models import CreateTeamRequest, TeamOut

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/teams", response_model=list[TeamOut])
def list_teams():
    rows = db.fetch_all(
        """
        SELECT t.id, t.name, t.parent_id, t.created_by,
               u.username AS created_by_name,
               (SELECT COUNT(*) FROM team_members tm WHERE tm.team_id = t.id) AS member_count
        FROM teams t
        LEFT JOIN users u ON u.id = t.created_by
        ORDER BY t.name
        """
    )
    return [TeamOut(**r) for r in rows]


@router.post("/teams", response_model=dict)
def create_team(body: CreateTeamRequest, created_by: int | None = None):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Team name is required")
    try:
        db.execute(
            "INSERT INTO teams (name, parent_id, created_by) VALUES (%s, %s, %s)",
            (body.name.strip(), body.parent_id, created_by),
        )
        return {"ok": True, "name": body.name.strip()}
    except Exception as exc:
        logger.warning("create_team failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
