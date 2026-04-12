"""Team management endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app import database as db
from app.models import AddTeamMembersRequest, CreateTeamRequest, TeamMemberOut, TeamOut, UpdateTeamRequest

logger = logging.getLogger(__name__)

router = APIRouter()

# None = not yet probed; avoids 500 when migration 002 is not applied on auth DB.
_teams_extended_schema: bool | None = None


def _reset_teams_schema_cache_for_tests() -> None:
    """Clear cached information_schema result (tests only)."""

    global _teams_extended_schema
    _teams_extended_schema = None


def _teams_extended_schema_ready() -> bool:
    """True when teams.description and team_roles exist (migration 002 applied)."""

    global _teams_extended_schema
    if _teams_extended_schema is not None:
        return _teams_extended_schema
    try:
        row = db.fetch_one(
            """
            SELECT
              EXISTS (
                SELECT 1 FROM information_schema.columns c
                WHERE c.table_schema = 'public' AND c.table_name = 'teams' AND c.column_name = 'description'
              )
              AND EXISTS (
                SELECT 1 FROM information_schema.tables t
                WHERE t.table_schema = 'public' AND t.table_name = 'team_roles'
              ) AS ok
            """
        )
        _teams_extended_schema = bool(row and row.get("ok"))
    except Exception as exc:
        logger.warning("teams extended schema probe failed: %s", exc)
        _teams_extended_schema = False
    return _teams_extended_schema


def _list_teams_extended() -> list[TeamOut]:
    rows = db.fetch_all(
        """
        SELECT t.id, t.name, t.description, t.parent_id, t.created_by,
               u.username AS created_by_name,
               (SELECT COUNT(*) FROM team_members tm WHERE tm.team_id = t.id) AS member_count
        FROM teams t
        LEFT JOIN users u ON u.id = t.created_by
        ORDER BY t.name
        """
    )
    tr_rows = db.fetch_all("SELECT team_id, role_id FROM team_roles")
    by_team: dict[int, list[int]] = {}
    for r in tr_rows:
        tid = int(r["team_id"])
        by_team.setdefault(tid, []).append(int(r["role_id"]))
    role_names = {int(r["id"]): str(r["name"]) for r in db.fetch_all("SELECT id, name FROM roles")}
    out: list[TeamOut] = []
    for raw in rows:
        tid = int(raw["id"])
        rids = sorted(by_team.get(tid, []))
        row = dict(raw)
        row["role_ids"] = rids
        row["roles"] = ", ".join(role_names.get(rid, str(rid)) for rid in rids)
        out.append(TeamOut(**row))
    return out


def _list_teams_legacy() -> list[TeamOut]:
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
    out: list[TeamOut] = []
    for raw in rows:
        row = dict(raw)
        row["description"] = None
        row["role_ids"] = []
        row["roles"] = ""
        out.append(TeamOut(**row))
    return out


@router.get("/teams", response_model=list[TeamOut])
def list_teams():
    if _teams_extended_schema_ready():
        return _list_teams_extended()
    return _list_teams_legacy()


@router.post("/teams", response_model=dict)
def create_team(body: CreateTeamRequest, created_by: int | None = None):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Team name is required")
    if _teams_extended_schema_ready():
        try:
            desc = (body.description or "").strip() or None
            row = db.fetch_one(
                """
                INSERT INTO teams (name, parent_id, created_by, description)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (body.name.strip(), body.parent_id, created_by, desc),
            )
            tid = int(row["id"]) if row else 0
            for rid in body.role_ids or []:
                db.execute(
                    "INSERT INTO team_roles (team_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (tid, rid),
                )
            return {"ok": True, "name": body.name.strip(), "id": tid}
        except Exception as exc:
            logger.warning("create_team failed: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        row = db.fetch_one(
            """
            INSERT INTO teams (name, parent_id, created_by)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (body.name.strip(), body.parent_id, created_by),
        )
        tid = int(row["id"]) if row else 0
        return {"ok": True, "name": body.name.strip(), "id": tid}
    except Exception as exc:
        logger.warning("create_team (legacy schema) failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/teams/{team_id}", response_model=dict)
def update_team(team_id: int, body: UpdateTeamRequest):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Team name is required")
    row = db.fetch_one("SELECT id FROM teams WHERE id = %s", (team_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Team not found")
    if _teams_extended_schema_ready():
        try:
            if body.description is not None:
                db.execute(
                    "UPDATE teams SET name = %s, description = %s WHERE id = %s",
                    (body.name.strip(), (body.description or "").strip() or None, team_id),
                )
            else:
                db.execute(
                    "UPDATE teams SET name = %s WHERE id = %s",
                    (body.name.strip(), team_id),
                )
            if body.role_ids is not None:
                db.execute("DELETE FROM team_roles WHERE team_id = %s", (team_id,))
                for rid in body.role_ids:
                    db.execute(
                        "INSERT INTO team_roles (team_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (team_id, rid),
                    )
            return {"ok": True}
        except Exception as exc:
            logger.warning("update_team failed: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        db.execute(
            "UPDATE teams SET name = %s WHERE id = %s",
            (body.name.strip(), team_id),
        )
        return {"ok": True}
    except Exception as exc:
        logger.warning("update_team (legacy schema) failed: %s", exc)
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
