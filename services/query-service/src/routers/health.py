"""
routers/health.py — Query-Service sağlık endpoint'leri

GET /health         → Public; kimlik doğrulama yok.
GET /service-status → Internal key korumalı; db-service bağlantısını test eder.
"""

import httpx
from fastapi import APIRouter, Depends

from src.dependencies import get_db_client, verify_internal_key

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Servis sağlık kontrolü — kimlik doğrulama gerekmez."""
    return {"status": "ok", "service": "query-service"}


@router.get("/service-status", dependencies=[Depends(verify_internal_key)])
async def service_status(
    client: httpx.AsyncClient = Depends(get_db_client),
) -> dict:
    """
    db-service bağlantısını aktif olarak test eder.
    Sonuç: query-service ve db-service'in birlikte sağlıklı olup olmadığını raporlar.
    """
    try:
        resp = await client.get("/health")
        db_reachable = resp.status_code == 200
        db_detail = resp.json() if db_reachable else {"error": resp.status_code}
    except httpx.RequestError as exc:
        db_reachable = False
        db_detail = {"error": str(exc)}

    return {
        "status": "ok",
        "service": "query-service",
        "db_service": "reachable" if db_reachable else "unreachable",
        "db_detail": db_detail,
    }
