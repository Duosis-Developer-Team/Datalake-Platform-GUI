# IBM Storage query definitions
#
# Used by DatabaseService (dc_service.py) to build Power Mimari -> Storage
# capacity and performance sparkline widgets.
#
# DC scoping is handled in Python:
# - ibm_storage_system includes `storage_ip` and textual fields (`name`, `location`)
# - Association between storage_ip/name/location and a DC code is resolved via:
#   - regex extraction on textual fields
#   - fallback to NetBox discovery table using matching IPs


# --- Capacity (latest per storage_ip) ---
# Returns the latest capacity snapshot rows for the provided storage_ip list.
#
# Params:
#   - storage_ips: list[str]
STORAGE_SYSTEM_CAPACITY_LATEST = """
WITH latest AS (
    SELECT
        storage_ip,
        MAX("timestamp") AS max_ts
    FROM public.raw_ibm_storage_system
    WHERE storage_ip = ANY(%s)
    GROUP BY storage_ip
)
SELECT
    s.storage_ip,
    s.name,
    s.total_mdisk_capacity,
    s.total_used_capacity,
    s.total_free_space,
    s."timestamp"
FROM public.raw_ibm_storage_system s
JOIN latest l
  ON s.storage_ip = l.storage_ip
 AND s."timestamp" = l.max_ts;
"""


# --- Performance (time series; daily aggregation) ---
# Returns daily averages across the provided storage_ip list.
#
# Params:
#   - storage_ips: list[str]
#   - start_ts, end_ts: timestamps
STORAGE_SYSTEM_STATS_DAILY_AVG = """
SELECT
    DATE_TRUNC('day', "timestamp") AS ts,
    AVG(COALESCE(vdisk_io, 0))::double precision AS avg_iops,
    AVG(COALESCE(vdisk_mb, 0))::double precision AS avg_throughput_mb,
    AVG(COALESCE(vdisk_ms, 0))::double precision AS avg_latency_ms
FROM public.raw_ibm_storage_system_stats
WHERE
    storage_ip = ANY(%s)
  AND "timestamp" BETWEEN %s AND %s
GROUP BY 1
ORDER BY 1;
"""

