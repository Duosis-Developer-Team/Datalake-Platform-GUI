"""Team management endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app import database as db
from app.models import AddTeamMembersRequest, CreateTeamRequest, TeamMemberOut, TeamOut, UpdateTeamRequest

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


@router.put("/teams/{team_id}", response_model=dict)
def update_team(team_id: int, body: UpdateTeamRequest):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Team name is required")
    row = db.fetch_one("SELECT id FROM teams WHERE id = %s", (team_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Team not found")
    try:
        db.execute(
            "UPDATE teams SET name = %s WHERE id = %s",
            (body.name.strip(), team_id),
        )
        return {"ok": True}
    except Exception as exc:
        logger.warning("update_team failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/teams/{team_id}/members", response_model=list[TeamMemberOut])
def list_team_members(team_id: int):
    row = db.fetch_one("SELECT id FROM teams WHERE id = %s", (team_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Team not found")
    rows = db.fetch_all(
        """
        SELECT u.id AS user_id, u.username, u.display_name, u.email
        FROM team_members tm
        JOIN users u ON u.id = tm.user_id
        WHERE tm.team_id = %s
        ORDER BY u.username
        """,
        (team_id,),
    )
    return [TeamMemberOut(**r) for r in rows]


@router.post("/teams/{team_id}/members", response_model=dict)
def add_team_members(team_id: int, body: AddTeamMembersRequest):
    row = db.fetch_one("SELECT id FROM teams WHERE id = %s", (team_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Team not found")
    if not body.user_ids:
        raise HTTPException(status_code=422, detail="user_ids is required")
    for uid in body.user_ids:
        db.execute(
            "INSERT INTO team_members (team_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (team_id, uid),
        )
    return {"ok": True}


@router.delete("/teams/{team_id}/members/{user_id}", response_model=dict)
def remove_team_member(team_id: int, user_id: int):
    row = db.fetch_one("SELECT id FROM teams WHERE id = %s", (team_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Team not found")
    db.execute(
        "DELETE FROM team_members WHERE team_id = %s AND user_id = %s",
        (team_id, user_id),
    )
    return {"ok": True}
