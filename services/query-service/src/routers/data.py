"""
routers/data.py — Query-Service veri endpoint'leri

Tüm endpoint'ler X-Internal-Key ile korunur (router seviyesinde).
QueryService, httpx.AsyncClient'ı DI ile alır ve db-service'e proxy eder.

GET /datacenters/summary       → list[DCSummary]
GET /datacenters/{dc_code}     → DCDetail
GET /overview                  → GlobalOverview
"""

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Path

from shared.schemas.responses import DCDetail, DCSummary, GlobalOverview
from src.dependencies import get_db_client, get_redis, verify_internal_key
from src.services.query_service import QueryService

router = APIRouter(
    prefix="/datacenters",
    tags=["data"],
    dependencies=[Depends(verify_internal_key)],
)

overview_router = APIRouter(
    tags=["data"],
    dependencies=[Depends(verify_internal_key)],
)


def _get_service(
    client: httpx.AsyncClient = Depends(get_db_client),
    redis: aioredis.Redis = Depends(get_redis),
) -> QueryService:
    """Request başına QueryService instance'ı oluşturur (client ve redis paylaşılır)."""
    return QueryService(client, redis)


@router.get("/summary", response_model=list[DCSummary])
async def get_summary(
    service: QueryService = Depends(_get_service),
) -> list[DCSummary]:
    """Tüm aktif datacenter'lar için özet metrik listesi."""
    return await service.get_summary()


@router.get("/{dc_code}", response_model=DCDetail)
async def get_dc_detail(
    dc_code: str = Path(..., description="Datacenter kodu, örn: DC11"),
    service: QueryService = Depends(_get_service),
) -> DCDetail:
    """Tek bir datacenter'ın tam metrik profili."""
    return await service.get_dc_detail(dc_code)


@overview_router.get("/overview", response_model=GlobalOverview)
async def get_overview(
    service: QueryService = Depends(_get_service),
) -> GlobalOverview:
    """Platform geneli KPI özeti: toplam host, VM, DC sayısı ve enerji."""
    return await service.get_overview()
