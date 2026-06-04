"""Liveness/readiness endpoints (CTO pack 03).

``/ready`` reports configuration *presence* only — it never calls the external
LLM and never echoes secret values.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.models.schemas import HealthResponse, ReadyResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.service_name)


@router.get("/ready", response_model=ReadyResponse)
def ready() -> ReadyResponse:
    return ReadyResponse(
        status="ready",
        checks={
            "llm_configured": settings.llm_configured,
            "db_enabled": settings.chatbot_db_enabled,
            "datacenter_api_url": "configured" if settings.datacenter_api_url else "missing",
            "customer_api_url": "configured" if settings.customer_api_url else "missing",
            "query_api_url": "configured" if settings.query_api_url else "missing",
            "crm_engine_url": "configured" if settings.crm_engine_url else "missing",
        },
    )
