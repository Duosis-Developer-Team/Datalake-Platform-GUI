"""
routers/health.py

GET /health    → Public. Servis canlılık kontrolü (load-balancer / Docker healthcheck).
GET /db-status → Internal. asyncpg pool aracılığıyla gerçek DB bağlantı testi.
"""

import asyncpg
from fastapi import APIRouter, Depends

from src.database import get_pool
from src.dependencies import verify_internal_key

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Servis sağlık kontrolü — kimlik doğrulama gerekmez."""
    return {"status": "ok", "service": "db-service"}


@router.get("/db-status", dependencies=[Depends(verify_internal_key)])
async def db_status(pool: asyncpg.Pool = Depends(get_pool)) -> dict:
    """
    Gerçek DB bağlantı testi.
    Pool'dan bir connection alıp SELECT 1 çalıştırır.
    """
    try:
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
        return {
            "status":   "connected",
            "db_check": result == 1,
            "pool_size": pool.get_size(),
            "pool_free": pool.get_idle_size(),
        }
    except Exception as exc:
        return {
            "status":  "unreachable",
            "detail":  str(exc),
        }
