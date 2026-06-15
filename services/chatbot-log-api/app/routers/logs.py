"""Chat turn log ingestion and read (internal)."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import verify_internal_api_key
from app.models.schemas import (
    ChatTurnListResponse,
    ChatTurnLog,
    ChatTurnLogResponse,
    ChatTurnStored,
)
from app.services import mongo_store

router = APIRouter()


@router.post("/turns", response_model=ChatTurnLogResponse)
async def create_turn(
    turn: ChatTurnLog,
    _: None = Depends(verify_internal_api_key),
) -> ChatTurnLogResponse:
    await mongo_store.insert_turn(turn)
    return ChatTurnLogResponse(request_id=turn.request_id, stored=True)


@router.get("/turns", response_model=ChatTurnListResponse)
async def list_turns(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    user_id: Optional[str] = Query(default=None),
    username: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    response_type: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    _: None = Depends(verify_internal_api_key),
) -> ChatTurnListResponse:
    items, total = await mongo_store.list_turns(
        skip=skip,
        limit=limit,
        user_id=user_id,
        username=username,
        status=status,
        response_type=response_type,
        date_from=date_from,
        date_to=date_to,
    )
    return ChatTurnListResponse(
        items=[ChatTurnStored.model_validate(item) for item in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/turns/{request_id}", response_model=ChatTurnStored)
async def get_turn(
    request_id: str,
    _: None = Depends(verify_internal_api_key),
) -> ChatTurnStored:
    doc = await mongo_store.get_turn_by_request_id(request_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="turn_not_found")
    return ChatTurnStored.model_validate(doc)
