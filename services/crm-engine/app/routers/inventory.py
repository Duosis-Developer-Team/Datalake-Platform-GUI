"""CRM global inventory overview REST endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.services.inventory_overview_service import InventoryOverviewService

router = APIRouter()


def _inventory(request: Request) -> InventoryOverviewService:
    svc: InventoryOverviewService = getattr(request.app.state, "inventory", None)
    if svc is None or not svc.is_available():
        raise HTTPException(status_code=503, detail="InventoryOverviewService not available")
    return svc


@router.get("/crm/inventory-overview", response_model=dict)
def get_inventory_overview(
    dc_code: str = "*",
    force_recompute: bool = False,
    svc: InventoryOverviewService = Depends(_inventory),
):
    """Global capacity vs CRM entitled vs infra used, aggregated across all DCs."""
    return svc.compute_inventory_overview(dc_code=dc_code, force_recompute=force_recompute)
