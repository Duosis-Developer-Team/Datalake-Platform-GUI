"""Operator endpoints for cache management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.core.cache_backend import cache_flush_pattern, cache_stats

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/admin/cache/refresh")
def refresh_cache(request: Request) -> dict:
    """Flush this service's Redis database and in-memory cache, then warm customer caches."""
    svc = request.app.state.db
    logger.info("Admin cache refresh requested (customer-api).")
    cache_flush_pattern("*")
    svc.warm_cache()
    stats = cache_stats()
    logger.info(
        "Admin cache refresh complete (customer-api). redis_keys=%s memory_size=%s",
        stats.get("redis_keys"),
        stats.get("memory_size"),
    )
    return {"status": "ok", "cache": stats}
