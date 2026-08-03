"""Operator endpoints for cache management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.core.cache_backend import cache_stats
from app.services import cache_service as cache
from app.services.netbox_viz_filter import invalidate_exclusion_cache

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/admin/cache/refresh")
def refresh_cache(request: Request) -> dict:
    """Warm datacenter caches in place, overwriting the previous values.

    Deliberately does not flush first, matching customer-api and crm-engine.
    The flush this used to start with cost nothing in data — every write here
    goes through cache_set, which always applies settings.cache_ttl_seconds, so
    it only removed entries that were about to expire anyway. What it did cost
    was availability: from the DELETE until the last warm finished, minutes
    later, every read was a miss. Callers either blocked on the database or gave
    up and rendered empty, so an operator pressing "refresh cache" made the UI
    worse for as long as the refresh ran. Warming over the top reaches the same
    end state with the old values readable throughout.
    """
    db = request.app.state.db
    logger.info("Admin cache refresh requested (datacenter-api).")
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
