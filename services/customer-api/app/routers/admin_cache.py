"""Operator endpoints for cache management."""

from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, Request

from app.core.cache_backend import cache_stats

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/admin/cache/refresh")
def refresh_cache(request: Request) -> dict:
    """
    Rebuild customer caches without flushing Redis (stale-until-overwrite).

    Hot tier (VIP/pinned) runs synchronously; warm tier (mapped non-VIP) runs in a
    background thread so deploy hooks return before long sequential SQL completes.
    """
    svc = request.app.state.db
    logger.info("Admin cache refresh requested (customer-api).")
    svc.warm_cache()
    threading.Thread(
        target=svc.refresh_warm_tier_caches,
        name="admin-warm-tier-refresh",
        daemon=True,
    ).start()
    stats = cache_stats()
    logger.info(
        "Admin cache refresh accepted (customer-api). redis_keys=%s memory_size=%s warm_tier=background",
        stats.get("redis_keys"),
        stats.get("memory_size"),
    )
    return {
        "status": "ok",
        "cache": stats,
        "warm_tier": "background",
    }
