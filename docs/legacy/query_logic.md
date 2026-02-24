# Legacy Query & Processing Logic Reference

Bu dosya, farklı veri kaynaklarından (VMware, Nutanix, IBM, Loki vb.) veri toplama, işleme ve cacheleme mantığını içerir. Senior Dev (Claude), bu mantığı `query-service` içerisine asenkron olarak taşımalıdır.

## Query Logic
*Kaynak: queries/vmware.py*
*Kaynak: queries/nutanix.py*
*Kaynak: queries/ibm.py veya queries/energy.py*
*Kaynak: queries/loki.py*
*Kaynak: services/cache_service.py Not: Eski yapıda Redis veya Memory cache nasıl yönetiliyorsa o mantığı buraya ekle.*
*Kaynak: queries/registry.py*
```python
[# VMware SQL query definitions — source: datacenter_metrics
# Individual queries (single DC) and batch queries (all DCs at once)

# --- Individual queries (parameterized with ILIKE %s wildcard) ---

COUNTS = """
SELECT total_cluster_count, total_host_count, total_vm_count
FROM public.datacenter_metrics
WHERE datacenter ILIKE %s
ORDER BY timestamp DESC
LIMIT 1
"""

MEMORY = """
SELECT
    total_memory_capacity_gb * 1024 * 1024 * 1024,
    total_memory_used_gb * 1024 * 1024 * 1024
FROM public.datacenter_metrics
WHERE datacenter ILIKE %s
ORDER BY timestamp DESC
LIMIT 1
"""

STORAGE = """
SELECT
    total_storage_capacity_gb * (1024 * 1024),
    total_used_storage_gb * (1024 * 1024)
FROM public.datacenter_metrics
WHERE datacenter ILIKE %s
ORDER BY timestamp DESC
LIMIT 1
"""

CPU = """
SELECT
    total_cpu_ghz_capacity * 1000000000,
    total_cpu_ghz_used * 1000000000
FROM public.datacenter_metrics
WHERE datacenter ILIKE %s
ORDER BY timestamp DESC
LIMIT 1
"""

# --- Batch queries (all DCs in a single roundtrip) ---
# Uses ILIKE with pattern matching via LIKE ANY(...)
# PostgreSQL supports: WHERE col ILIKE ANY(ARRAY['%AZ11%', '%DC11%', ...])

BATCH_COUNTS = """
SELECT DISTINCT ON (datacenter)
    datacenter,
    total_cluster_count,
    total_host_count,
    total_vm_count
FROM public.datacenter_metrics
WHERE datacenter ILIKE ANY(%s)
ORDER BY datacenter, timestamp DESC
"""

BATCH_MEMORY = """
SELECT DISTINCT ON (datacenter)
    datacenter,
    total_memory_capacity_gb * 1024 * 1024 * 1024 AS mem_cap,
    total_memory_used_gb * 1024 * 1024 * 1024     AS mem_used
FROM public.datacenter_metrics
WHERE datacenter ILIKE ANY(%s)
ORDER BY datacenter, timestamp DESC
"""

BATCH_STORAGE = """
SELECT DISTINCT ON (datacenter)
    datacenter,
    total_storage_capacity_gb * (1024 * 1024) AS stor_cap,
    total_used_storage_gb * (1024 * 1024)      AS stor_used
FROM public.datacenter_metrics
WHERE datacenter ILIKE ANY(%s)
ORDER BY datacenter, timestamp DESC
"""

BATCH_CPU = """
SELECT DISTINCT ON (datacenter)
    datacenter,
    total_cpu_ghz_capacity * 1000000000 AS cpu_cap,
    total_cpu_ghz_used * 1000000000     AS cpu_used
FROM public.datacenter_metrics
WHERE datacenter ILIKE ANY(%s)
ORDER BY datacenter, timestamp DESC
"""
]

[# Nutanix SQL query definitions — source: nutanix_cluster_metrics
# Individual queries (single DC) and batch queries (all DCs at once)

# --- Individual queries (parameterized with LIKE %s wildcard) ---

HOST_COUNT = """
SELECT num_nodes
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE %s
ORDER BY collection_time DESC
LIMIT 1
"""

MEMORY = """
SELECT
    total_memory_capacity,
    ((memory_usage_avg / 1000) * total_memory_capacity) / 1000
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE %s
ORDER BY collection_time DESC
LIMIT 1
"""

STORAGE = """
SELECT
    storage_capacity / 2,
    storage_usage / 2
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE %s
ORDER BY collection_time DESC
LIMIT 1
"""

CPU = """
SELECT
    total_cpu_capacity,
    (cpu_usage_avg * total_cpu_capacity) / 1000000
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE %s
ORDER BY collection_time DESC
LIMIT 1
"""

# --- Batch queries (all DCs in a single roundtrip) ---
# Uses `datacenter_name` column (exact DC code) instead of cluster_name LIKE wildcard.
# `datacenter_name` is a direct column in nutanix_cluster_metrics → exact match is safe and fast.
# When multiple clusters exist per DC, we SUM metrics across all clusters per DC.

BATCH_HOST_COUNT = """
SELECT
    datacenter_name,
    SUM(num_nodes) AS num_nodes
FROM (
    SELECT DISTINCT ON (cluster_name)
        datacenter_name,
        cluster_name,
        num_nodes
    FROM public.nutanix_cluster_metrics
    WHERE datacenter_name = ANY(%s)
    ORDER BY cluster_name, collection_time DESC
) latest
GROUP BY datacenter_name
"""

BATCH_MEMORY = """
SELECT
    datacenter_name,
    SUM(total_memory_capacity) AS total_memory_capacity,
    SUM(((memory_usage_avg / 1000) * total_memory_capacity) / 1000) AS used_memory
FROM (
    SELECT DISTINCT ON (cluster_name)
        datacenter_name,
        cluster_name,
        total_memory_capacity,
        memory_usage_avg
    FROM public.nutanix_cluster_metrics
    WHERE datacenter_name = ANY(%s)
    ORDER BY cluster_name, collection_time DESC
) latest
GROUP BY datacenter_name
"""

BATCH_STORAGE = """
SELECT
    datacenter_name,
    SUM(storage_capacity / 2) AS storage_cap,
    SUM(storage_usage / 2)    AS storage_used
FROM (
    SELECT DISTINCT ON (cluster_name)
        datacenter_name,
        cluster_name,
        storage_capacity,
        storage_usage
    FROM public.nutanix_cluster_metrics
    WHERE datacenter_name = ANY(%s)
    ORDER BY cluster_name, collection_time DESC
) latest
GROUP BY datacenter_name
"""

BATCH_CPU = """
SELECT
    datacenter_name,
    SUM(total_cpu_capacity) AS total_cpu_capacity,
    SUM((cpu_usage_avg * total_cpu_capacity) / 1000000) AS cpu_used
FROM (
    SELECT DISTINCT ON (cluster_name)
        datacenter_name,
        cluster_name,
        total_cpu_capacity,
        cpu_usage_avg
    FROM public.nutanix_cluster_metrics
    WHERE datacenter_name = ANY(%s)
    ORDER BY cluster_name, collection_time DESC
) latest
GROUP BY datacenter_name
"""
]

[# IBM Power (HMC) SQL query definitions — source: ibm_server_general

# --- Individual queries ---

HOST_COUNT = """
SELECT COUNT(DISTINCT server_details_servername)
FROM public.ibm_server_general
WHERE server_details_servername LIKE %s
"""

# --- Batch queries ---
# Groups by DC code prefix so the caller can map results back to DC codes.
# Pattern list passed as ARRAY via psycopg2 for LIKE ANY(...)

BATCH_HOST_COUNT = """
SELECT
    server_details_servername,
    COUNT(DISTINCT server_details_servername) AS host_count
FROM public.ibm_server_general
WHERE server_details_servername LIKE ANY(%s)
GROUP BY server_details_servername
"""
]

[# Energy SQL query definitions
# Sources: loki_racks, ibm_server_power (NOT ibm_server_power_sum), vmhost_metrics

# --- Individual queries ---

# loki_racks: exact match (=) on location_name — loki_locations hierarchy determines DC name
RACKS = r"""
SELECT SUM(
    CASE
        WHEN kabin_enerji ~ '^[0-9]+(\.[0-9]+)?$' THEN kabin_enerji::float
        ELSE NULLIF(
            regexp_replace(replace(kabin_enerji, ',', '.'), '[^0-9.]', '', 'g'),
            ''
        )::float
    END * 1000
)
FROM public.loki_racks
WHERE location_name = %s
  AND id IN (SELECT DISTINCT id FROM public.loki_racks)
"""

# ibm_server_power — ibm_server_power_sum does not exist in the schema
IBM = """
SELECT SUM(power_watts)
FROM public.ibm_server_power
WHERE server_name ILIKE %s
"""

VCENTER = """
WITH latest_per_host AS (
    SELECT DISTINCT ON (vm.vmhost) vm.power_usage
    FROM public.vmhost_metrics vm
    WHERE vm.vmhost ILIKE %s
    ORDER BY vm.vmhost, vm."timestamp" DESC
)
SELECT SUM(power_usage)
FROM latest_per_host
"""

# --- Batch queries ---

BATCH_RACKS = r"""
SELECT
    location_name,
    SUM(
        CASE
            WHEN kabin_enerji ~ '^[0-9]+(\.[0-9]+)?$' THEN kabin_enerji::float
            ELSE NULLIF(
                regexp_replace(replace(kabin_enerji, ',', '.'), '[^0-9.]', '', 'g'),
                ''
            )::float
        END * 1000
    ) AS total_watts
FROM public.loki_racks
WHERE location_name = ANY(%s)
  AND id IN (SELECT DISTINCT id FROM public.loki_racks)
GROUP BY location_name
"""

# ibm_server_power — corrected table name
BATCH_IBM = """
SELECT
    server_name,
    SUM(power_watts) AS total_watts
FROM public.ibm_server_power
WHERE server_name ILIKE ANY(%s)
GROUP BY server_name
"""

BATCH_VCENTER = """
WITH latest_per_host AS (
    SELECT DISTINCT ON (vm.vmhost)
        vm.vmhost,
        vm.power_usage
    FROM public.vmhost_metrics vm
    WHERE vm.vmhost ILIKE ANY(%s)
    ORDER BY vm.vmhost, vm."timestamp" DESC
)
SELECT
    vmhost,
    SUM(power_usage) AS total_watts
FROM latest_per_host
GROUP BY vmhost
"""
]

[# Loki (NetBox) SQL query definitions — source: loki_locations
# Used to dynamically resolve the list of active data centers.

# Returns distinct datacenter names using the parent/child hierarchy:
#   - If parent_id IS NULL  → the row itself IS a datacenter (name = dc_name)
#   - If parent_id IS NOT NULL → the row is a sub-location; parent_name = dc_name
DC_LIST = """
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
    AND status_value = 'active'
ORDER BY 1
"""

# Same query without status filter (fallback if status_value is not populated)
DC_LIST_NO_STATUS = """
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
ORDER BY 1
"""
]

[# Module-level TTL cache service.
# Replaces the broken instance-level lru_cache pattern.
# Uses cachetools.TTLCache so entries expire automatically after TTL seconds.

import threading
import logging
from typing import Any, Callable, Optional
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Default TTL for all cache entries (seconds).
# Background scheduler refreshes data every 15 minutes; TTL is set slightly higher
# (20 min) so stale data is never served between refresh cycles.
DEFAULT_TTL = 1200  # 20 minutes — scheduler refreshes every 15 min

# Module-level cache — shared across all instances of DatabaseService.
# maxsize=100 covers many DCs + global overview + dc_details per DC + headroom.
_cache: TTLCache = TTLCache(maxsize=100, ttl=DEFAULT_TTL)
_lock = threading.Lock()


def get(key: str) -> Optional[Any]:
    """Return cached value or None if the key is missing / expired."""
    with _lock:
        return _cache.get(key)


def set(key: str, value: Any) -> None:
    """Store a value in the cache under the given key."""
    with _lock:
        _cache[key] = value
    logger.debug("Cache SET: %s", key)


def delete(key: str) -> None:
    """Explicitly evict a single key."""
    with _lock:
        _cache.pop(key, None)
    logger.debug("Cache DELETE: %s", key)


def clear() -> None:
    """Flush the entire cache (e.g. on config reload or forced refresh)."""
    with _lock:
        _cache.clear()
    logger.info("Cache cleared.")


def cached(key_fn: Callable[..., str]):
    """
    Decorator factory for caching function results.

    Usage:
        @cached(lambda dc_code: f"dc_details:{dc_code}")
        def get_dc_details(self, dc_code):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            cache_key = key_fn(*args, **kwargs)
            hit = get(cache_key)
            if hit is not None:
                logger.debug("Cache HIT: %s", cache_key)
                return hit
            logger.debug("Cache MISS: %s", cache_key)
            result = fn(*args, **kwargs)
            if result is not None:
                set(cache_key, result)
            return result
        wrapper.__wrapped__ = fn
        return wrapper
    return decorator


def stats() -> dict:
    """Return cache statistics for observability / debugging."""
    with _lock:
        return {
            "current_size": len(_cache),
            "max_size": _cache.maxsize,
            "ttl_seconds": _cache.ttl,
            "keys": list(_cache.keys()),
        }
]

[# Query Registry — central catalog of all available SQL queries.
# To add a new query for a future dashboard, register it here.
# The db_service uses this registry for dynamic query execution.

from src.queries import nutanix, vmware, ibm, energy

# Schema for each entry:
#   sql           : SQL string (from the provider module)
#   source        : DB table name (informational)
#   result_type   : "value" | "row" | "rows"
#   params_style  : "wildcard"  → caller passes f"%{dc_code}%"
#                   "exact"     → caller passes dc_code as-is
#                   "array_wildcard" → caller passes list of wildcard patterns
#                   "array_exact"    → caller passes list of exact DC codes
#   provider      : "nutanix" | "vmware" | "ibm" | "energy"
#   batch_key     : column name to map rows back to DC code (batch queries only)

QUERY_REGISTRY: dict[str, dict] = {
    # --- Nutanix (individual) ---
    "nutanix_host_count": {
        "sql": nutanix.HOST_COUNT,
        "source": "nutanix_cluster_metrics",
        "result_type": "value",
        "params_style": "wildcard",
        "provider": "nutanix",
    },
    "nutanix_memory": {
        "sql": nutanix.MEMORY,
        "source": "nutanix_cluster_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "nutanix",
    },
    "nutanix_storage": {
        "sql": nutanix.STORAGE,
        "source": "nutanix_cluster_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "nutanix",
    },
    "nutanix_cpu": {
        "sql": nutanix.CPU,
        "source": "nutanix_cluster_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "nutanix",
    },
    # --- Nutanix (batch) ---
    "nutanix_batch_host_count": {
        "sql": nutanix.BATCH_HOST_COUNT,
        "source": "nutanix_cluster_metrics",
        "result_type": "rows",
        "params_style": "array_exact",
        "provider": "nutanix",
        "batch_key": "cluster_name",
    },
    "nutanix_batch_memory": {
        "sql": nutanix.BATCH_MEMORY,
        "source": "nutanix_cluster_metrics",
        "result_type": "rows",
        "params_style": "array_exact",
        "provider": "nutanix",
        "batch_key": "cluster_name",
    },
    "nutanix_batch_storage": {
        "sql": nutanix.BATCH_STORAGE,
        "source": "nutanix_cluster_metrics",
        "result_type": "rows",
        "params_style": "array_exact",
        "provider": "nutanix",
        "batch_key": "cluster_name",
    },
    "nutanix_batch_cpu": {
        "sql": nutanix.BATCH_CPU,
        "source": "nutanix_cluster_metrics",
        "result_type": "rows",
        "params_style": "array_exact",
        "provider": "nutanix",
        "batch_key": "cluster_name",
    },
    # --- VMware (individual) ---
    "vmware_counts": {
        "sql": vmware.COUNTS,
        "source": "datacenter_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "vmware",
    },
    "vmware_memory": {
        "sql": vmware.MEMORY,
        "source": "datacenter_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "vmware",
    },
    "vmware_storage": {
        "sql": vmware.STORAGE,
        "source": "datacenter_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "vmware",
    },
    "vmware_cpu": {
        "sql": vmware.CPU,
        "source": "datacenter_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "vmware",
    },
    # --- VMware (batch) ---
    "vmware_batch_counts": {
        "sql": vmware.BATCH_COUNTS,
        "source": "datacenter_metrics",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "vmware",
        "batch_key": "datacenter",
    },
    "vmware_batch_memory": {
        "sql": vmware.BATCH_MEMORY,
        "source": "datacenter_metrics",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "vmware",
        "batch_key": "datacenter",
    },
    "vmware_batch_storage": {
        "sql": vmware.BATCH_STORAGE,
        "source": "datacenter_metrics",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "vmware",
        "batch_key": "datacenter",
    },
    "vmware_batch_cpu": {
        "sql": vmware.BATCH_CPU,
        "source": "datacenter_metrics",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "vmware",
        "batch_key": "datacenter",
    },
    # --- IBM Power (individual) ---
    "ibm_host_count": {
        "sql": ibm.HOST_COUNT,
        "source": "ibm_server_general",
        "result_type": "value",
        "params_style": "wildcard",
        "provider": "ibm",
    },
    # --- IBM Power (batch) ---
    "ibm_batch_host_count": {
        "sql": ibm.BATCH_HOST_COUNT,
        "source": "ibm_server_general",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "ibm",
        "batch_key": "server_details_servername",
    },
    # --- Energy (individual) ---
    "energy_racks": {
        "sql": energy.RACKS,
        "source": "loki_racks",
        "result_type": "value",
        "params_style": "exact",
        "provider": "energy",
    },
    "energy_ibm": {
        "sql": energy.IBM,
        "source": "ibm_server_power_sum",
        "result_type": "value",
        "params_style": "wildcard",
        "provider": "energy",
    },
    "energy_vcenter": {
        "sql": energy.VCENTER,
        "source": "vmhost_metrics",
        "result_type": "value",
        "params_style": "wildcard",
        "provider": "energy",
    },
    # --- Energy (batch) ---
    "energy_batch_racks": {
        "sql": energy.BATCH_RACKS,
        "source": "loki_racks",
        "result_type": "rows",
        "params_style": "array_exact",
        "provider": "energy",
        "batch_key": "location_name",
    },
    "energy_batch_ibm": {
        "sql": energy.BATCH_IBM,
        "source": "ibm_server_power_sum",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "energy",
        "batch_key": "server_name",
    },
    "energy_batch_vcenter": {
        "sql": energy.BATCH_VCENTER,
        "source": "vmhost_metrics",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "energy",
        "batch_key": "vmhost",
    },
}
]
