"""MongoDB persistence for chat turn logs."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.models.schemas import ChatTurnLog

logger = logging.getLogger("chatbot-log-api.mongo")

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None
_indexes_ready = False


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_uri)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    global _db
    if _db is None:
        _db = get_client()[settings.mongo_db]
    return _db


async def close_client() -> None:
    global _client, _db, _indexes_ready
    if _client is not None:
        _client.close()
    _client = None
    _db = None
    _indexes_ready = False


async def ping() -> bool:
    try:
        await get_client().admin.command("ping")
        return True
    except Exception as exc:
        logger.warning("mongo ping failed: %s", exc)
        return False


async def ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    coll = get_db()[settings.mongo_collection]
    await coll.create_index("request_id", unique=True)
    await coll.create_index([("user_id", 1), ("created_at", -1)])
    await coll.create_index("created_at")
    await coll.create_index("expires_at", expireAfterSeconds=0)
    _indexes_ready = True


async def insert_turn(turn: ChatTurnLog) -> dict[str, Any]:
    await ensure_indexes()
    retention = turn.retention_days or settings.log_retention_days
    now = datetime.now(timezone.utc)
    doc = turn.model_dump(mode="json")
    doc["created_at"] = now
    doc["expires_at"] = now + timedelta(days=max(1, int(retention)))
    coll = get_db()[settings.mongo_collection]
    await coll.insert_one(doc)
    return {"request_id": turn.request_id, "stored": True}


def _build_turn_filter(
    *,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    status: Optional[str] = None,
    response_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> dict[str, Any]:
    filt: dict[str, Any] = {}
    if user_id:
        filt["user_id"] = user_id.strip()
    if username:
        filt["username"] = {"$regex": username.strip(), "$options": "i"}
    if status:
        filt["status"] = status.strip()
    if response_type:
        filt["response_type"] = response_type.strip()
    if date_from or date_to:
        created: dict[str, Any] = {}
        if date_from:
            created["$gte"] = datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
        if date_to:
            end = datetime.combine(date_to, datetime.max.time(), tzinfo=timezone.utc)
            created["$lte"] = end
        filt["created_at"] = created
    return filt


def _serialize_doc(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    out.pop("_id", None)
    return out


async def list_turns(
    *,
    skip: int = 0,
    limit: int = 50,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    status: Optional[str] = None,
    response_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> tuple[list[dict[str, Any]], int]:
    await ensure_indexes()
    filt = _build_turn_filter(
        user_id=user_id,
        username=username,
        status=status,
        response_type=response_type,
        date_from=date_from,
        date_to=date_to,
    )
    coll = get_db()[settings.mongo_collection]
    total = await coll.count_documents(filt)
    cursor = coll.find(filt).sort("created_at", -1).skip(max(0, skip)).limit(max(1, limit))
    items = [_serialize_doc(doc) async for doc in cursor]
    return items, total


async def get_turn_by_request_id(request_id: str) -> Optional[dict[str, Any]]:
    await ensure_indexes()
    coll = get_db()[settings.mongo_collection]
    doc = await coll.find_one({"request_id": request_id.strip()})
    if not doc:
        return None
    return _serialize_doc(doc)
