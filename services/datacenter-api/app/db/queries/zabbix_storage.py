# Zabbix Storage query definitions (Intel Storage)
#
# Zabbix storage devices and disks are DC-scoped via NetBox inventory mapping:
#   zabbix_storage_device_metrics.loki_id (varchar/text)
#   -> discovery_netbox_inventory_device.id (int8)
#
# Then disk metrics are scoped via storage device "host" values.
#
# Performance notes:
# - KPIs use latest per host/device within the requested time range.
# - Trend uses time_bucket('1 day') to downsample before UI.


# --- Storage devices for DC (latest per loki_id) ---
# Returns one row per NetBox device (loki_id), with the latest Zabbix snapshot
# within the requested time range and only when health_status IS NOT NULL.
#
# Params:
#   - dc_code: str
#   - start_ts, end_ts: timestamps
STORAGE_DEVICES_FOR_DC_LATEST = """
WITH dc_map AS (
    SELECT
        name AS location_name,
        CASE
            WHEN parent_id IS NULL THEN name
            ELSE parent_name
        END AS dc_name
    FROM public.loki_locations
    WHERE
        CASE
            WHEN parent_id IS NULL THEN name
            ELSE parent_name
        END IS NOT NULL
),
latest AS (
    SELECT DISTINCT ON (sdm.loki_id)
        sdm.loki_id,
        sdm.host,
        sdm.total_capacity_bytes,
        sdm.used_capacity_bytes,
        sdm.free_capacity_bytes,
        sdm.health_status,
        sdm.collection_timestamp
    FROM public.zabbix_storage_device_metrics sdm
    WHERE
        sdm.health_status IS NOT NULL
        AND sdm.collection_timestamp BETWEEN %s AND %s
        AND sdm.loki_id ~ '^[0-9]+$'
    ORDER BY
        sdm.loki_id,
        sdm.collection_timestamp DESC
)
SELECT
    latest.loki_id,
    latest.host,
    dev.name AS storage_device_name,
    dev.manufacturer_name,
    dev.device_role_name,
    dev.location_name,
    dev.site_name,
    latest.total_capacity_bytes,
    latest.used_capacity_bytes,
    latest.free_capacity_bytes,
    latest.health_status,
    latest.collection_timestamp
FROM latest
JOIN public.discovery_netbox_inventory_device dev
    ON dev.id = latest.loki_id::bigint
JOIN dc_map m
    ON m.location_name IN (dev.location_name, dev.site_name, dev.name)
WHERE m.dc_name = %s
ORDER BY latest.host;
"""


# --- Capacity summary (latest per host) ---
# Params:
#   - hosts: list[str]
#   - start_ts, end_ts: timestamps
STORAGE_CAPACITY_SUMMARY_LATEST = """
WITH latest AS (
    SELECT DISTINCT ON (sdm.host)
        sdm.host,
        sdm.total_capacity_bytes,
        sdm.used_capacity_bytes,
        sdm.free_capacity_bytes,
        sdm.collection_timestamp
    FROM public.zabbix_storage_device_metrics sdm
    WHERE
        sdm.host = ANY(%s)
        AND sdm.health_status IS NOT NULL
        AND sdm.collection_timestamp BETWEEN %s AND %s
    ORDER BY
        sdm.host,
        sdm.collection_timestamp DESC
)
SELECT
    COUNT(*)::bigint AS storage_device_count,
    COALESCE(SUM(total_capacity_bytes), 0)::bigint AS total_capacity_bytes,
    COALESCE(SUM(used_capacity_bytes), 0)::bigint AS used_capacity_bytes,
    COALESCE(SUM(free_capacity_bytes), 0)::bigint AS free_capacity_bytes
FROM latest;
"""


# --- Capacity trend (time bucket) ---
# Params:
#   - hosts: list[str]
#   - start_ts, end_ts: timestamps
STORAGE_CAPACITY_TREND_DAILY = """
SELECT
    time_bucket('1 day', sdm.collection_timestamp) AS ts,
    COALESCE(SUM(sdm.used_capacity_bytes), 0)::bigint AS used_capacity_bytes,
    COALESCE(SUM(sdm.total_capacity_bytes), 0)::bigint AS total_capacity_bytes
FROM public.zabbix_storage_device_metrics sdm
WHERE
    sdm.host = ANY(%s)
    AND sdm.health_status IS NOT NULL
    AND sdm.collection_timestamp BETWEEN %s AND %s
GROUP BY 1
ORDER BY 1;
"""


# --- Disk health & performance summary ---
# Uses:
# - latest health_status per (host, disk_name)
# - average IOPS/latency/temperature across the time range per (host, disk_name)
#
# Params:
#   - hosts: list[str]
#   - start_ts, end_ts: timestamps
#   - limit (optional): int (default 500 in service)
DISK_HEALTH_PERFORMANCE = """
WITH latest_health AS (
    SELECT DISTINCT ON (sdm.host, sdm.disk_name)
        sdm.host,
        sdm.disk_name,
        sdm.health_status,
        sdm.running_status,
        sdm.collection_timestamp
    FROM public.zabbix_storage_disk_metrics sdm
    WHERE
        sdm.host = ANY(%s)
        AND sdm.collection_timestamp BETWEEN %s AND %s
        AND sdm.health_status IS NOT NULL
    ORDER BY
        sdm.host,
        sdm.disk_name,
        sdm.collection_timestamp DESC
),
stats AS (
    SELECT
        sdm.host,
        sdm.disk_name,
        AVG(COALESCE(sdm.total_iops, 0))::double precision AS avg_total_iops,
        AVG(COALESCE(sdm.latency_ms, 0))::double precision AS avg_latency_ms,
        AVG(COALESCE(sdm.temperature_c, 0))::double precision AS avg_temperature_c
    FROM public.zabbix_storage_disk_metrics sdm
    WHERE
        sdm.host = ANY(%s)
        AND sdm.collection_timestamp BETWEEN %s AND %s
    GROUP BY 1,2
)
SELECT
    stats.disk_name,
    latest_health.health_status,
    COALESCE(stats.avg_total_iops, 0)::double precision AS avg_total_iops,
    COALESCE(stats.avg_latency_ms, 0)::double precision AS avg_latency_ms,
    COALESCE(stats.avg_temperature_c, 0)::double precision AS avg_temperature_c,
    latest_health.running_status
FROM stats
JOIN latest_health
  ON latest_health.host = stats.host
 AND latest_health.disk_name = stats.disk_name
ORDER BY stats.avg_total_iops DESC, stats.avg_latency_ms DESC, stats.disk_name
LIMIT %s;
"""

