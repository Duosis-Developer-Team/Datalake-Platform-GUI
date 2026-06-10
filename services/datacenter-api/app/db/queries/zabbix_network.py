from __future__ import annotations

# Zabbix Network query definitions
#
# Network dashboard is DC-scoped using NetBox inventory mapped via:
#   raw_zabbix_network_device_health_metrics.loki_id (varchar/text)
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
    FROM public.raw_zabbix_network_device_health_metrics ndm
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
    AND dev.status_value = 'active'
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
        FROM public.raw_zabbix_network_device_health_metrics ndm
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
        AND dev.status_value = 'active'
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
    FROM public.raw_zabbix_network_device_health_metrics ndm
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
    AND dev.status_value = 'active'
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
    FROM public.raw_zabbix_network_interface_metrics_v zndi
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
    FROM public.raw_zabbix_network_interface_metrics_v zndi
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
    FROM public.raw_zabbix_network_interface_metrics_v zndi
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


INTERFACE_SCOPE_TABLE_MAP: dict[str, str] = {
    "backbone": "raw_zabbix_network_backbone_interface_metrics",
    "leaf": "raw_zabbix_network_leaf_interface_metrics",
    "spine": "raw_zabbix_network_spine_interface_metrics",
    "management": "raw_zabbix_network_management_interface_metrics",
    "shared": "raw_zabbix_network_switch_shared_interface_metrics",
    "router_uplink": "raw_zabbix_network_router_uplink_metrics",
}

VALID_INTERFACE_SCOPES = frozenset(INTERFACE_SCOPE_TABLE_MAP.keys())


def resolve_interface_table(scope: str | None) -> str:
    """Return a whitelisted interface metrics table or the unified read view."""
    if not scope or scope == "overview":
        return "raw_zabbix_network_interface_metrics_v"
    if scope not in VALID_INTERFACE_SCOPES:
        raise ValueError(f"Invalid interface_scope: {scope}")
    return INTERFACE_SCOPE_TABLE_MAP[scope]


def _scope_overlap_filter(scope: str | None) -> str:
    if scope != "leaf":
        return ""
    return """
        AND NOT EXISTS (
            SELECT 1
            FROM public.raw_zabbix_network_switch_shared_interface_metrics s
            WHERE s.host = zndi.host
              AND s.interface_name = zndi.interface_name
              AND s.collection_timestamp = zndi.collection_timestamp
        )
    """


def build_interface_95th_percentile_sql(scope: str | None) -> str:
    table = resolve_interface_table(scope)
    overlap = _scope_overlap_filter(scope)
    return f"""
WITH deduped AS (
    SELECT DISTINCT ON (zndi.host, zndi.interface_name, COALESCE(zndi.interface_alias, ''), zndi.collection_timestamp)
        zndi.host,
        zndi.interface_name,
        zndi.interface_alias,
        zndi.speed,
        zndi.bits_received,
        zndi.bits_sent,
        zndi.collection_timestamp
    FROM public.{table} zndi
    WHERE
        zndi.host = ANY(%s)
        AND zndi.collection_timestamp BETWEEN %s AND %s
        {overlap}
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
    GROUP BY 1, 2, 3, 4, 5
),
ranked AS (
    SELECT
        host,
        interface_name,
        interface_alias,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_rx_bps) AS p95_rx_bps,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_tx_bps) AS p95_tx_bps,
        MAX(speed) AS max_speed_bps
    FROM bucketed
    GROUP BY host, interface_name, interface_alias
)
SELECT
    host,
    interface_name,
    interface_alias,
    COALESCE(p95_rx_bps, 0)::double precision AS p95_rx_bps,
    COALESCE(p95_tx_bps, 0)::double precision AS p95_tx_bps,
    COALESCE(p95_rx_bps, 0) + COALESCE(p95_tx_bps, 0) AS p95_total_bps,
    COALESCE(max_speed_bps, 0)::double precision AS speed_bps
FROM ranked
ORDER BY p95_total_bps DESC;
"""


def build_interface_bandwidth_table_p95_sql(scope: str | None) -> str:
    table = resolve_interface_table(scope)
    overlap = _scope_overlap_filter(scope)
    return f"""
WITH deduped AS (
    SELECT DISTINCT ON (zndi.host, zndi.interface_name, COALESCE(zndi.interface_alias, ''), zndi.collection_timestamp)
        zndi.host,
        zndi.interface_name,
        zndi.interface_alias,
        zndi.speed,
        zndi.bits_received,
        zndi.bits_sent,
        zndi.collection_timestamp
    FROM public.{table} zndi
    WHERE
        zndi.host = ANY(%s)
        AND zndi.collection_timestamp BETWEEN %s AND %s
        {overlap}
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
    GROUP BY 1, 2, 3, 4, 5
),
p95 AS (
    SELECT
        host,
        interface_name,
        interface_alias,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_rx_bps) AS p95_rx_bps,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY avg_tx_bps) AS p95_tx_bps,
        MAX(speed) AS max_speed_bps
    FROM bucketed
    GROUP BY host, interface_name, interface_alias
)
SELECT
    host,
    interface_name,
    interface_alias,
    COALESCE(p95_rx_bps, 0)::double precision AS p95_rx_bps,
    COALESCE(p95_tx_bps, 0)::double precision AS p95_tx_bps,
    (COALESCE(p95_rx_bps, 0) + COALESCE(p95_tx_bps, 0)) AS p95_total_bps,
    COALESCE(max_speed_bps, 0)::double precision AS speed_bps
FROM p95
WHERE
    (%s = '' OR host ILIKE %s OR interface_name ILIKE %s OR COALESCE(interface_alias, '') ILIKE %s)
ORDER BY p95_total_bps DESC, host, interface_name
LIMIT %s OFFSET %s;
"""


FIREWALL_SUMMARY_LATEST = """
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
    SELECT DISTINCT ON (fm.host)
        fm.host,
        fm.loki_id,
        fm.cpu_utilization_pct,
        fm.memory_utilization_pct,
        fm.active_sessions,
        fm.session_setup_rate,
        fm.intrusions_detected,
        fm.intrusions_blocked,
        fm.ha_mode,
        fm.ha_cluster_name,
        fm.icmp_status,
        fm.icmp_loss_pct,
        fm.collection_timestamp
    FROM public.raw_zabbix_network_firewall_metrics fm
    WHERE fm.collection_timestamp BETWEEN %s AND %s
    ORDER BY fm.host, fm.collection_timestamp DESC
)
SELECT
    latest.host,
    dev.name AS device_name,
    dev.manufacturer_name,
    latest.cpu_utilization_pct,
    latest.memory_utilization_pct,
    latest.active_sessions,
    latest.session_setup_rate,
    latest.intrusions_detected,
    latest.intrusions_blocked,
    latest.ha_mode,
    latest.ha_cluster_name,
    latest.icmp_status,
    latest.icmp_loss_pct
FROM latest
JOIN public.discovery_netbox_inventory_device dev
    ON dev.id = latest.loki_id::bigint
    AND dev.status_value = 'active'
JOIN dc_map m
    ON m.location_name IN (dev.location_name, dev.site_name, dev.name)
WHERE m.dc_name = %s
ORDER BY latest.host;
"""


_DC_MAP_CTE = """
dc_map AS (
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
)
"""


def build_scoped_hosts_for_dc_sql(scope: str | None) -> str:
    """Hosts with interface rows in the scoped table for a DC and time window."""
    table = resolve_interface_table(scope)
    overlap = _scope_overlap_filter(scope)
    return f"""
WITH {_DC_MAP_CTE},
scoped AS (
    SELECT DISTINCT
        zndi.host,
        dev.manufacturer_name,
        dev.name AS device_name,
        dev.device_role_name
    FROM public.{table} zndi
    JOIN public.discovery_netbox_inventory_device dev
        ON dev.id = zndi.loki_id::bigint
        AND dev.status_value = 'active'
        AND zndi.loki_id ~ '^[0-9]+$'
    JOIN dc_map m
        ON m.location_name IN (dev.location_name, dev.site_name, dev.name)
    WHERE
        m.dc_name = %s
        AND zndi.collection_timestamp BETWEEN %s AND %s
        {overlap}
)
SELECT
    host,
    manufacturer_name,
    device_name,
    device_role_name
FROM scoped
WHERE host IS NOT NULL
ORDER BY manufacturer_name NULLS LAST, device_name NULLS LAST;
"""


def build_scoped_port_summary_sql(scope: str | None) -> str:
    """KPI counts from latest-per-interface rows in the scoped table."""
    table = resolve_interface_table(scope)
    overlap = _scope_overlap_filter(scope)
    return f"""
WITH latest_iface AS (
    SELECT DISTINCT ON (zndi.host, zndi.interface_name, COALESCE(zndi.interface_alias, ''))
        zndi.host,
        zndi.interface_name,
        zndi.operational_status
    FROM public.{table} zndi
    WHERE
        zndi.host = ANY(%s)
        AND zndi.collection_timestamp BETWEEN %s AND %s
        {overlap}
    ORDER BY
        zndi.host,
        zndi.interface_name,
        COALESCE(zndi.interface_alias, ''),
        zndi.collection_timestamp DESC
),
health AS (
    SELECT DISTINCT ON (ndm.host)
        ndm.host,
        ndm.icmp_loss_pct
    FROM public.raw_zabbix_network_device_health_metrics ndm
    WHERE
        ndm.host = ANY(%s)
        AND ndm.collection_timestamp BETWEEN %s AND %s
    ORDER BY ndm.host, ndm.collection_timestamp DESC
)
SELECT
    COUNT(DISTINCT li.host)::bigint AS device_count,
    COUNT(*)::bigint AS total_ports,
    COUNT(*) FILTER (WHERE COALESCE(li.operational_status, 0) = 1)::bigint AS active_ports,
    COALESCE(AVG(COALESCE(h.icmp_loss_pct, 0)), 0)::double precision AS avg_icmp_loss_pct
FROM latest_iface li
LEFT JOIN health h ON h.host = li.host;
"""


LOAD_BALANCER_SUMMARY_LATEST = """
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
    SELECT DISTINCT ON (dh.host)
        dh.host,
        dh.loki_id,
        dh.icmp_status,
        dh.icmp_loss_pct,
        dh.icmp_response_time_ms,
        dh.cpu_utilization_pct,
        dh.memory_utilization_pct,
        dh.uptime_seconds,
        dh.total_ports_count,
        dh.active_ports_count,
        dh.collection_timestamp
    FROM public.raw_zabbix_network_device_health_metrics dh
    WHERE
        dh.collection_timestamp BETWEEN %s AND %s
        AND (
            lower(COALESCE(dh.device_type_category, '')) LIKE '%load balancer%'
            OR lower(COALESCE(dh.applied_templates, '')) LIKE '%citrix%'
            OR lower(COALESCE(dh.applied_templates, '')) LIKE '%load balancer%'
        )
    ORDER BY dh.host, dh.collection_timestamp DESC
)
SELECT
    latest.host,
    dev.name AS device_name,
    dev.manufacturer_name,
    latest.icmp_status,
    latest.icmp_loss_pct,
    latest.icmp_response_time_ms,
    latest.cpu_utilization_pct,
    latest.memory_utilization_pct,
    latest.uptime_seconds,
    latest.total_ports_count,
    latest.active_ports_count
FROM latest
JOIN public.discovery_netbox_inventory_device dev
    ON dev.id = latest.loki_id::bigint
    AND dev.status_value = 'active'
JOIN dc_map m
    ON m.location_name IN (dev.location_name, dev.site_name, dev.name)
WHERE m.dc_name = %s
ORDER BY latest.host;
"""

