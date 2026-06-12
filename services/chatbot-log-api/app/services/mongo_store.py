"""MongoDB persistence for chat turn logs."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
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
