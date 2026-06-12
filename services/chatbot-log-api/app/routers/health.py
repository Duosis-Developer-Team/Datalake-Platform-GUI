from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.models.schemas import HealthResponse, ReadyResponse
from app.services import mongo_store

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    mongo_ok = await mongo_store.ping()
    return ReadyResponse(
        status="ready" if mongo_ok else "degraded",
        checks={
            "mongo": "ok" if mongo_ok else "unavailable",
            "mongo_db": settings.mongo_db,
            "collection": settings.mongo_collection,
        },
    )
