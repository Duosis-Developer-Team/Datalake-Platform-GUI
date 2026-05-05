"""Operator endpoints for cache management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.core.cache_backend import cache_flush_pattern, cache_stats

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/admin/cache/refresh")
def refresh_cache(request: Request) -> dict:
    """Flush this service's Redis database and in-memory cache, then warm datacenter caches."""
    db = request.app.state.db
    logger.info("Admin cache refresh requested (datacenter-api).")
    cache_flush_pattern("*")
    db.warm_cache()
    db.warm_additional_ranges()
    db.warm_s3_cache()
    stats = cache_stats()
    logger.info(
        "Admin cache refresh complete (datacenter-api). redis_keys=%s memory_size=%s",
        stats.get("redis_keys"),
        stats.get("memory_size"),
    )
    return {"status": "ok", "cache": stats}
