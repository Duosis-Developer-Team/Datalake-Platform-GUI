"""Operator endpoints for cache management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.core.cache_backend import cache_flush_pattern, cache_stats
from app.services import cache_service as cache
from app.services.netbox_viz_filter import invalidate_exclusion_cache

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
    db.warm_network_cache()
    stats = cache_stats()
    logger.info(
        "Admin cache refresh complete (datacenter-api). redis_keys=%s memory_size=%s",
        stats.get("redis_keys"),
        stats.get("memory_size"),
    )
    return {"status": "ok", "cache": stats}


@router.post("/admin/cache/invalidate-netbox-viz")
def invalidate_netbox_viz_cache() -> dict:
    """Drop NetBox/Loki visualization caches after exclusion config changes."""
    invalidate_exclusion_cache()
    cache.delete_prefix("phys_inv:")
    cache.delete_prefix("dc_zabbix_net_")
    cache.delete_prefix("dc_zabbix_storage_")
    cache.delete("netbox:device_roles")
    return {"status": "ok"}
