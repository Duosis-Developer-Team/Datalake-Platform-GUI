"""
routers/data.py

Tüm veri endpoint'leri — INTERNAL_API_KEY ile korunur.
FastAPI, response_model annotasyonlarını kullanarak:
  - Gelen Pydantic nesnelerini otomatik JSON'a serialize eder.
  - OpenAPI şemasını shared.schemas modellerinden otomatik üretir.
  - Fazla alanları filtreler (model_config ile kontrol edilir).

GET /datacenters/summary      → list[DCSummary]
GET /datacenters/{dc_code}    → DCDetail
GET /overview                 → GlobalOverview
"""

import asyncpg
from fastapi import APIRouter, Depends, Path

from shared.schemas.responses import DCDetail, DCSummary, GlobalOverview
from src.database import get_pool
from src.dependencies import verify_internal_key
from src.services.database_service import DatabaseService

router = APIRouter(
    prefix="/datacenters",
    tags=["data"],
    dependencies=[Depends(verify_internal_key)],
)

overview_router = APIRouter(
    tags=["data"],
    dependencies=[Depends(verify_internal_key)],
)


def _get_service(pool: asyncpg.Pool = Depends(get_pool)) -> DatabaseService:
    """Request başına DatabaseService instance'ı oluşturur (pool paylaşılır)."""
    return DatabaseService(pool)


@router.get("/summary", response_model=list[DCSummary])
async def get_summary(
    service: DatabaseService = Depends(_get_service),
) -> list[DCSummary]:
    """Tüm aktif datacenters'lar için özet metrik listesi."""
    return await service.get_all_datacenters_summary()


@router.get("/{dc_code}", response_model=DCDetail)
async def get_dc_details(
    dc_code: str = Path(..., description="Datacenter kodu, örn: DC11"),
    service: DatabaseService = Depends(_get_service),
) -> DCDetail:
    """Belirtilen datacenter için tam metrik modeli."""
    return await service.get_dc_details(dc_code.upper())


@overview_router.get("/overview", response_model=GlobalOverview)
async def get_overview(
    service: DatabaseService = Depends(_get_service),
) -> GlobalOverview:
    """Platform geneli toplam host/VM/enerji metrikleri."""
    return await service.get_global_overview()
