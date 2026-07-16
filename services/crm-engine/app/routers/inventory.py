"""CRM global inventory overview REST endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from app.services.inventory_overview_service import InventoryOverviewService
from app.services.product_matching_service import ProductMatchingService

router = APIRouter()


def _inventory(request: Request) -> InventoryOverviewService:
    svc: InventoryOverviewService = getattr(request.app.state, "inventory", None)
    if svc is None or not svc.is_available():
        raise HTTPException(status_code=503, detail="InventoryOverviewService not available")
    return svc


def _product_matching_optional(request: Request) -> Optional[ProductMatchingService]:
    svc: ProductMatchingService | None = getattr(request.app.state, "product_matching", None)
    if svc is None or not svc.is_available():
        return None
    return svc


def _product_matching(request: Request) -> ProductMatchingService:
    svc = _product_matching_optional(request)
    if svc is None:
        raise HTTPException(status_code=503, detail="ProductMatchingService not available")
    return svc


@router.get("/crm/inventory-overview", response_model=dict)
def get_inventory_overview(
    dc_code: str = "*",
    force_recompute: bool = False,
    include_product_matching: bool = True,
    svc: InventoryOverviewService = Depends(_inventory),
    matching: Optional[ProductMatchingService] = Depends(_product_matching_optional),
):
    """Global capacity vs CRM entitled vs infra used, aggregated across all DCs."""
    payload = svc.compute_inventory_overview(dc_code=dc_code, force_recompute=force_recompute)
    if include_product_matching:
        if matching is None:
            payload["product_matching"] = {
                "products": [],
                "summary": {},
                "error": "product_matching_unavailable",
            }
        else:
            try:
                panel_by_key = {
                    str(r.get("panel_key")): r
                    for r in (payload.get("panels") or [])
                    if r.get("panel_key")
                }
                payload["product_matching"] = matching.compute_product_matching(
                    force_recompute=False,
                    panel_by_key=panel_by_key,
                )
            except Exception:
                payload["product_matching"] = {
                    "products": [],
                    "summary": {},
                    "error": "product_matching_unavailable",
                }
    return payload


@router.get("/crm/inventory-matching", response_model=dict)
def get_inventory_matching(
    force_recompute: bool = False,
    matching: ProductMatchingService = Depends(_product_matching),
):
    """CRM product ↔ infrastructure matching rows (ADR-0024 registry + sold)."""
    return matching.compute_product_matching(force_recompute=force_recompute)
