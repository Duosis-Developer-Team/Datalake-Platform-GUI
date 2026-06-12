"""Chat turn log ingestion (internal)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import verify_internal_api_key
from app.models.schemas import ChatTurnLog, ChatTurnLogResponse
from app.services import mongo_store

router = APIRouter()


@router.post("/turns", response_model=ChatTurnLogResponse)
async def create_turn(
    turn: ChatTurnLog,
    _: None = Depends(verify_internal_api_key),
) -> ChatTurnLogResponse:
    await mongo_store.insert_turn(turn)
    return ChatTurnLogResponse(request_id=turn.request_id, stored=True)
