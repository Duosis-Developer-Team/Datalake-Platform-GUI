# Zabbix Network query definitions
#
# Network dashboard is DC-scoped using NetBox inventory mapped via:
#   zabbix_network_device_metrics.loki_id (varchar/text)
#   -> discovery_netbox_inventory_device.id (int8)
#
# DC scoping is derived by joining NetBox location/site/name to loki_locations
# and extracting the parent DC name (same approach as other DC mappings).
#
# Performance notes:
# - Device KPIs use "latest per loki_id" to avoid double counting.
# - Interface 95th percentile uses TimescaleDB time_bucket downsampling so we
#   don't compute percentile over every raw point.


# --- Devices for DC (latest per loki_id) ---
# Returns one row per NetBox device (loki_id), with the latest Zabbix snapshot
# within the requested time range and only when icmp_status IS NOT NULL.
#
# Params:
#   - dc_code: str
#   - start_ts, end_ts: timestamps
NETWORK_DEVICES_FOR_DC_LATEST = """
WITH dc_map AS (
    SELECT
        distinct name AS location_name,
        CASE
            WHEN parent_id IS NULL THEN name
            when parent_name = 'DH3' then 'DC13'
            ELSE parent_name
        END AS dc_name
    FROM public.loki_locations
    WHERE
        CASE
            WHEN parent_id IS NULL THEN name
            when parent_name = 'DH3' then 'DC13'
            ELSE parent_name
        END IS NOT NULL
),
latest AS (
    SELECT DISTINCT ON (ndm.loki_id)
        ndm.loki_id,
        ndm.host,
        ndm.total_ports_count,
        ndm.active_ports_count,
        ndm.icmp_loss_pct,
        ndm.collection_timestamp
    FROM public.zabbix_network_device_metrics ndm
    WHERE
        ndm.icmp_status IS NOT NULL
        AND ndm.collection_timestamp BETWEEN %s AND %s
        AND ndm.loki_id ~ '^[0-9]+$'
    ORDER BY
        ndm.loki_id,
        ndm.collection_timestamp DESC
)
SELECT
    ndm.loki_id,
    ndm.host,
    dev.name AS device_name,
    dev.manufacturer_name,
    dev.device_role_name,
    dev.location_name,
    dev.site_name,
    ndm.total_ports_count,
    ndm.active_ports_count,
    ndm.icmp_loss_pct,
    ndm.collection_timestamp
FROM latest ndm
JOIN public.discovery_netbox_inventory_device dev
    ON dev.id = ndm.loki_id::bigint
JOIN dc_map m
    ON m.location_name IN (dev.location_name, dev.site_name, dev.name)
WHERE m.dc_name = %s
ORDER BY dev.manufacturer_name NULLS LAST, dev.device_role_name NULLS LAST, dev.name NULLS LAST;
"""


# --- Port KPI summary (latest per loki_id) ---
# Params:
#   - dc_code: str
#   - start_ts, end_ts: timestamps
DEVICE_PORT_SUMMARY_LATEST = """
WITH devices AS (
    WITH dc_map AS (
    SELECT
        distinct name AS location_name,
        CASE
            WHEN parent_id IS NULL THEN name
            when parent_name = 'DH3' then 'DC13'
            ELSE parent_name
        END AS dc_name
    FROM public.loki_locations
    WHERE
        CASE
            WHEN parent_id IS NULL THEN name
            when parent_name = 'DH3' then 'DC13'
            ELSE parent_name
        END IS NOT NULL
    ),
    latest AS (
        SELECT DISTINCT ON (ndm.loki_id)
            ndm.loki_id,
            ndm.host,
            ndm.total_ports_count,
            ndm.active_ports_count,
            ndm.icmp_loss_pct,
            ndm.collection_timestamp
        FROM public.zabbix_network_device_metrics ndm
        WHERE
            ndm.icmp_status IS NOT NULL
            AND ndm.collection_timestamp BETWEEN %s AND %s
            AND ndm.loki_id ~ '^[0-9]+$'
        ORDER BY
            ndm.loki_id,
            ndm.collection_timestamp DESC
    )
    SELECT
        ndm.loki_id,
        ndm.host,
        ndm.total_ports_count,
        ndm.active_ports_count,
        ndm.icmp_loss_pct
    FROM latest ndm
    JOIN public.discovery_netbox_inventory_device dev
        ON dev.id = ndm.loki_id::bigint
    JOIN dc_map m
        ON m.location_name IN (dev.location_name, dev.site_name, dev.name)
    WHERE m.dc_name = %s
)
SELECT
    COUNT(*)::bigint AS device_count,
    COALESCE(SUM(total_ports_count), 0)::bigint AS total_ports,
    COALESCE(SUM(active_ports_count), 0)::bigint AS active_ports,
    COALESCE(AVG(COALESCE(icmp_loss_pct, 0)), 0)::double precision AS avg_icmp_loss_pct
FROM devices;
"""


# --- Device list for filters (latest per loki_id) ---
# Params:
#   - dc_code: str
#   - start_ts, end_ts: timestamps
#   - manufacturer_name (optional): str | None
#   - device_role_name (optional): str | None
#
# If optional params are NULL, the corresponding filter is ignored.
DEVICE_LIST_LATEST = """
WITH dc_map AS (
    SELECT
        distinct name AS location_name,
        CASE
            WHEN parent_id IS NULL THEN name
            when parent_name = 'DH3' then 'DC13'
            ELSE parent_name
        END AS dc_name
    FROM public.loki_locations
    WHERE
        CASE
            WHEN parent_id IS NULL THEN name
            when parent_name = 'DH3' then 'DC13'
            ELSE parent_name
        END IS NOT NULL
),
latest AS (
    SELECT DISTINCT ON (ndm.loki_id)
        ndm.loki_id,
        ndm.host,
        ndm.total_ports_count,
        ndm.active_ports_count,
        ndm.icmp_loss_pct,
        ndm.collection_timestamp
    FROM public.zabbix_network_device_metrics ndm
    WHERE
        ndm.icmp_status IS NOT NULL
        AND ndm.collection_timestamp BETWEEN %s AND %s
        AND ndm.loki_id ~ '^[0-9]+$'
    ORDER BY
        ndm.loki_id,
        ndm.collection_timestamp DESC
)
SELECT DISTINCT
    dev.manufacturer_name,
    dev.device_role_name,
    dev.name AS device_name
FROM latest ndm
JOIN public.discovery_netbox_inventory_device dev
    ON dev.id = ndm.loki_id::bigint
JOIN dc_map m
    ON m.location_name IN (dev.location_name, dev.site_name, dev.name)
WHERE
    m.dc_name = %s
    AND (%s IS NULL OR dev.manufacturer_name = %s)
    AND (%s IS NULL OR dev.device_role_name = %s)
ORDER BY
    dev.manufacturer_name NULLS LAST,
    dev.device_role_name NULLS LAST,
    dev.name NULLS LAST;
"""


# --- Interface list by host (latest per interface) ---
# Params:
#   - hosts: list[str]
#   - start_ts, end_ts: timestamps
INTERFACE_LIST_BY_HOST_LATEST = """
WITH latest_iface AS (
    SELECT DISTINCT ON (zndi.host, zndi.interface_name, COALESCE(zndi.interface_alias, ''))
        zndi.host,
        zndi.interface_name,
        zndi.interface_alias,
        zndi.operational_status,
        zndi.speed,
        zndi.collection_timestamp
    FROM public.zabbix_network_interface_metrics zndi
    WHERE
        zndi.host = ANY(%s)
        AND zndi.collection_timestamp BETWEEN %s AND %s
    ORDER BY
        zndi.host,
        zndi.interface_name,
        COALESCE(zndi.interface_alias, ''),
        zndi.collection_timestamp DESC
)
SELECT
    interface_name,
    interface_alias,
    operational_status,
    speed
FROM latest_iface
ORDER BY interface_name, interface_alias NULLS LAST;
"""


# --- 95th percentile interface bandwidth (downsampled) ---
# Uses time_bucket to downsample points into buckets, then computes percentile_cont
# across buckets per interface.
#
# Params:
#   - hosts: list[str]
#   - start_ts, end_ts: timestamps
INTERFACE_95TH_PERCENTILE = """
WITH deduped AS (
    SELECT DISTINCT ON (zndi.host, zndi.interface_name, COALESCE(zndi.interface_alias, ''), zndi.collection_timestamp)
        zndi.host,
        zndi.interface_name,
        zndi.interface_alias,
        zndi.speed,
        zndi.bits_received,
        zndi.bits_sent,
        zndi.collection_timestamp
    FROM public.zabbix_network_interface_metrics zndi
    WHERE
        zndi.host = ANY(%s)
        AND zndi.collection_timestamp BETWEEN %s AND %s
    ORDER BY
        zndi.host,
        zndi.interface_name,
        COALESCE(zndi.interface_alias, ''),
        zndi.collection_timestamp,
        zndi.id DESC
),
bucketed AS (
    SELECT
        time_bucket('1 hour', d.collection_timestamp) AS ts,
        d.host,
        d.interface_name,
        d.interface_alias,
        d.speed,
        AVG(COALESCE(d.bits_received, 0))::double precision AS avg_rx_bps,
        AVG(COALESCE(d.bits_sent, 0))::double precision AS avg_tx_bps
    FROM deduped d
    GROUP BY 1,2,3,4,5
),
ranked AS (
    SELECT
        interface_name,
        interface_alias,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_rx_bps) AS p95_rx_bps,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_tx_bps) AS p95_tx_bps,
        MAX(speed) AS max_speed_bps
    FROM bucketed
    GROUP BY interface_name, interface_alias
)
SELECT
    interface_name,
    interface_alias,
    COALESCE(p95_rx_bps, 0)::double precision AS p95_rx_bps,
    COALESCE(p95_tx_bps, 0)::double precision AS p95_tx_bps,
    COALESCE(p95_rx_bps, 0) + COALESCE(p95_tx_bps, 0) AS p95_total_bps,
    COALESCE(max_speed_bps, 0)::double precision AS speed_bps
FROM ranked
ORDER BY p95_total_bps DESC;
"""


# --- Interface bandwidth table (p95 based; supports search + pagination) ---
# Params:
#   - hosts: list[str]
#   - start_ts, end_ts: timestamps
#   - search: str (optional, may be empty string)
#   - limit, offset: int
INTERFACE_BANDWIDTH_TABLE_P95 = """
WITH deduped AS (
    SELECT DISTINCT ON (zndi.host, zndi.interface_name, COALESCE(zndi.interface_alias, ''), zndi.collection_timestamp)
        zndi.host,
        zndi.interface_name,
        zndi.interface_alias,
        zndi.speed,
        zndi.bits_received,
        zndi.bits_sent,
        zndi.collection_timestamp
    FROM public.zabbix_network_interface_metrics zndi
    WHERE
        zndi.host = ANY(%s)
        AND zndi.collection_timestamp BETWEEN %s AND %s
    ORDER BY
        zndi.host,
        zndi.interface_name,
        COALESCE(zndi.interface_alias, ''),
        zndi.collection_timestamp,
        zndi.id DESC
),
bucketed AS (
    SELECT
        time_bucket('1 hour', d.collection_timestamp) AS ts,
        d.host,
        d.interface_name,
        d.interface_alias,
        d.speed,
        AVG(COALESCE(d.bits_received, 0))::double precision AS avg_rx_bps,
        AVG(COALESCE(d.bits_sent, 0))::double precision AS avg_tx_bps
    FROM deduped d
    GROUP BY 1,2,3,4,5
),
p95 AS (
    SELECT
        interface_name,
        interface_alias,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_rx_bps) AS p95_rx_bps,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_tx_bps) AS p95_tx_bps,
        MAX(speed) AS max_speed_bps
    FROM bucketed
    GROUP BY interface_name, interface_alias
)
SELECT
    interface_name,
    interface_alias,
    COALESCE(p95_rx_bps, 0)::double precision AS p95_rx_bps,
    COALESCE(p95_tx_bps, 0)::double precision AS p95_tx_bps,
    (COALESCE(p95_rx_bps, 0) + COALESCE(p95_tx_bps, 0)) AS p95_total_bps,
    COALESCE(max_speed_bps, 0)::double precision AS speed_bps
FROM p95
WHERE
    (%s = '' OR interface_name ILIKE %s OR COALESCE(interface_alias, '') ILIKE %s)
ORDER BY p95_total_bps DESC, interface_name
LIMIT %s OFFSET %s;
"""

