"""Operator endpoints for cache management (crm-engine overlay)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.core.cache_backend import cache_flush_pattern, cache_stats

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/admin/cache/refresh")
def refresh_cache(request: Request) -> dict:
    """Flush CRM Redis cache and rebuild sellable snapshots."""
    logger.info("Admin cache refresh requested (crm-engine).")
    cache_flush_pattern("*")
    sellable = getattr(request.app.state, "sellable", None)
    if sellable is None:
        raise HTTPException(status_code=503, detail="SellableService not available")
    metrics_emitted = sellable.snapshot_all()
    stats = cache_stats()
    logger.info(
        "Admin cache refresh complete (crm-engine). metrics_emitted=%s redis_keys=%s",
        metrics_emitted,
        stats.get("redis_keys"),
    )
    return {"status": "ok", "metrics_emitted": metrics_emitted, "cache": stats}
