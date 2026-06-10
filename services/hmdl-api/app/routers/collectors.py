"""HMDL collector read API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.db.queries import collectors as q
from app.models.schemas import (
    DcSummaryResponse,
    ProxyDetailResponse,
    RunsResponse,
    SyncSummaryResponse,
    TargetsResponse,
    TopologyResponse,
)

router = APIRouter(prefix="/collectors", tags=["collectors"])


@router.get("/topology", response_model=TopologyResponse)
def get_topology():
    return q.build_topology(settings.hub_dc_code)


@router.get("/sync-summary", response_model=SyncSummaryResponse)
def get_sync_summary():
    return q.build_sync_summary()


@router.get("/proxies/{proxy_id}", response_model=ProxyDetailResponse)
def get_proxy(proxy_id: str):
    data = q.get_proxy_detail(proxy_id)
    if not data:
        raise HTTPException(status_code=404, detail="Proxy not found")
    return data


@router.get("/dc/{dc_code}", response_model=DcSummaryResponse)
def get_dc(dc_code: str):
    data = q.get_dc_summary(dc_code)
    if not data:
        raise HTTPException(status_code=404, detail="Datacenter not found")
    return data


@router.get("/dc/{dc_code}/targets", response_model=TargetsResponse)
def get_dc_targets(
    dc_code: str,
    category: str | None = Query(default=None),
    entity_name: str | None = Query(default=None),
    ip: str | None = Query(default=None),
):
    data = q.get_dc_targets(
        dc_code,
        category=category,
        entity_name=entity_name,
        ip=ip,
    )
    if not data:
        raise HTTPException(status_code=404, detail="Datacenter not found")
    return data


@router.get("/runs", response_model=RunsResponse)
def get_runs(limit: int = Query(default=20, ge=1, le=100)):
    return {"items": q.list_recent_runs(limit)}
