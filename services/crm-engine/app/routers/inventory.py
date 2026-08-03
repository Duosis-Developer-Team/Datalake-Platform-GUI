"""CRM global inventory overview REST endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response

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


def _attach_product_matching(
    payload: dict,
    *,
    matching: Optional[ProductMatchingService],
    force_recompute: bool,
) -> dict:
    """Embed product matching into payload; skip when already cached unless forced."""
    if (
        not force_recompute
        and isinstance(payload.get("product_matching"), dict)
        and "products" in (payload.get("product_matching") or {})
    ):
        return payload

    if matching is None:
        payload["product_matching"] = {
            "products": [],
            "summary": {},
            "error": "product_matching_unavailable",
        }
        return payload

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


@router.get("/crm/inventory-overview", response_model=dict)
def get_inventory_overview(
    response: Response,
    dc_code: str = "*",
    force_recompute: bool = False,
    include_product_matching: bool = True,
    svc: InventoryOverviewService = Depends(_inventory),
    matching: Optional[ProductMatchingService] = Depends(_product_matching_optional),
):
    """Global capacity vs CRM entitled vs infra used, aggregated across all DCs."""
    payload = svc.compute_inventory_overview(dc_code=dc_code, force_recompute=force_recompute)
    cache_status = str(payload.get("cache_status") or "miss")
    had_pm = isinstance(payload.get("product_matching"), dict) and "products" in (
        payload.get("product_matching") or {}
    )

    if include_product_matching:
        payload = _attach_product_matching(
            payload,
            matching=matching,
            force_recompute=force_recompute,
        )
        if force_recompute or cache_status == "miss" or not had_pm:
            if payload.get("error") != "inventory_warming":
                try:
                    to_store = {
                        k: v
                        for k, v in payload.items()
                        if k not in {"cache_status", "stale"}
                    }
                    svc.write_inventory_cache(dc_code or "*", to_store)
                except Exception:  # noqa: BLE001
                    pass
    elif "product_matching" in payload:
        payload = {k: v for k, v in payload.items() if k != "product_matching"}

    response.headers["X-Cache"] = "stale" if payload.get("stale") else cache_status
    return payload


@router.get("/crm/inventory-matching", response_model=dict)
def get_inventory_matching(
    force_recompute: bool = False,
    matching: ProductMatchingService = Depends(_product_matching),
):
    """CRM product ↔ infrastructure matching rows (ADR-0024 registry + sold)."""
    return matching.compute_product_matching(force_recompute=force_recompute)


@router.get("/crm/netbackup/jobs-disk-footprint", response_model=dict)
def get_netbackup_jobs_disk_footprint(
    request: Request,
    limit: int = 500,
):
    """Per finished BACKUP job: transfer, dedupratio, estimated on-disk footprint.

    Retention filter deferred — currently percentcomplete=100 only.
    """
    sellable = getattr(request.app.state, "sellable", None)
    if sellable is None or not getattr(sellable, "is_available", False):
        raise HTTPException(status_code=503, detail="SellableService not available")
    rows = sellable.list_netbackup_jobs_disk_footprint(limit=limit)
    return {
        "jobs": rows,
        "count": len(rows),
        "note": "footprint_kb = kilobytestransferred / dedupratio; retention filter deferred",
    }
