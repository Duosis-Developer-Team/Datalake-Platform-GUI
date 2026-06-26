"""Operator endpoints for cache management (crm-engine overlay)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.core.cache_backend import cache_stats

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/admin/cache/refresh")
def refresh_cache(request: Request) -> dict:
    """Recompute sellable snapshots and publish in place (zero-downtime refresh).

    Does not flush Redis up front; ``snapshot_all`` overwrites successful scopes
    while leaving prior values visible until new results are ready.
    """
    logger.info("Admin cache refresh requested (crm-engine).")
    sellable = getattr(request.app.state, "sellable", None)
    if sellable is None:
        raise HTTPException(status_code=503, detail="SellableService not available")
    metrics_emitted = sellable.snapshot_all()
    inventory = getattr(request.app.state, "inventory", None)
    inventory_warmed = False
    if inventory is not None:
        try:
            inventory.warm_inventory_cache(dc_code="*")
            inventory_warmed = True
        except Exception:  # noqa: BLE001
            logger.exception("Inventory overview warm failed during admin refresh")
    stats = cache_stats()
    logger.info(
        "Admin cache refresh complete (crm-engine). metrics_emitted=%s inventory_warmed=%s redis_keys=%s",
        metrics_emitted,
        inventory_warmed,
        stats.get("redis_keys"),
    )
    return {
        "status": "ok",
        "metrics_emitted": metrics_emitted,
        "inventory_warmed": inventory_warmed,
        "cache": stats,
    }
