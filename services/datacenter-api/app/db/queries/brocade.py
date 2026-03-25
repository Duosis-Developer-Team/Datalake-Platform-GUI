# Brocade SAN query definitions
#
# Used by DatabaseService (dc_service.py) to build DC-scoped
# Network > SAN executive views.
#
# Notes on DC scoping:
# - raw_brocade_port_status and raw_brocade_port_statistics include `switch_host`.
# - DC association for a given `switch_host` is resolved in Python via regex
#   and (fallback) NetBox discovery data.
# - raw_brocade_san_fcport_1 does NOT include `switch_host` in the current DDL;
#   bottleneck association is therefore handled in Python from `portname`.


# --- Port usage (gauges) ---
# Returns aggregated counts across all provided switches, using each
# switch_host's latest collection_timestamp.
#
# Params:
#   - switch_hosts: list[str]
PORT_USAGE_LATEST = """
WITH latest AS (
    SELECT
        switch_host,
        MAX(collection_timestamp) AS max_ts
    FROM public.raw_brocade_port_status
    WHERE switch_host = ANY(%s)
    GROUP BY switch_host
)
SELECT
    COUNT(*)::bigint AS total_ports,
    COUNT(*) FILTER (WHERE pod_license_status = true) AS licensed_ports,
    COUNT(*) FILTER (WHERE operational_status = 2 AND is_enabled_state = true) AS active_ports,
    COUNT(*) FILTER (WHERE COALESCE(is_enabled_state, false) = true) AS enabled_ports,
    COUNT(*) FILTER (WHERE COALESCE(is_enabled_state, false) = false) AS disabled_ports
FROM public.raw_brocade_port_status ps
JOIN latest l
  ON ps.switch_host = l.switch_host
 AND ps.collection_timestamp = l.max_ts;
"""


# --- SAN health alerts (delta-based) ---
# Returns per-port delta counters for each switch's latest stats row,
# filtered to rows with any delta > 0.
#
# Params:
#   - switch_hosts: list[str]
HEALTH_ALERTS_LATEST = """
WITH latest AS (
    SELECT
        switch_host,
        MAX(collection_timestamp) AS max_ts
    FROM public.raw_brocade_port_statistics
    WHERE switch_host = ANY(%s)
    GROUP BY switch_host
)
SELECT
    ps.switch_host,
    ps.name AS port_name,
    COALESCE(ps.crc_errors_delta, 0) AS crc_errors_delta,
    COALESCE(ps.link_failures_delta, 0) AS link_failures_delta,
    COALESCE(ps.loss_of_sync_delta, 0) AS loss_of_sync_delta,
    COALESCE(ps.loss_of_signal_delta, 0) AS loss_of_signal_delta
FROM public.raw_brocade_port_statistics ps
JOIN latest l
  ON ps.switch_host = l.switch_host
 AND ps.collection_timestamp = l.max_ts
WHERE
    COALESCE(ps.crc_errors_delta, 0) > 0
 OR COALESCE(ps.link_failures_delta, 0) > 0
 OR COALESCE(ps.loss_of_sync_delta, 0) > 0
 OR COALESCE(ps.loss_of_signal_delta, 0) > 0
ORDER BY
    (COALESCE(ps.crc_errors_delta, 0)
   + COALESCE(ps.link_failures_delta, 0)
   + COALESCE(ps.loss_of_sync_delta, 0)
   + COALESCE(ps.loss_of_signal_delta, 0)) DESC;
"""


# --- Traffic trend ---
# Hourly aggregated in/out rate over the requested time range.
#
# Params:
#   - switch_hosts: list[str]
#   - start_ts, end_ts: timestamps
TRAFFIC_TREND_HOURLY = """
SELECT
    DATE_TRUNC('hour', collection_timestamp) AS ts,
    SUM(COALESCE(in_rate, 0))::bigint AS total_in_rate,
    SUM(COALESCE(out_rate, 0))::bigint AS total_out_rate
FROM public.raw_brocade_port_statistics
WHERE
    switch_host = ANY(%s)
  AND collection_timestamp BETWEEN %s AND %s
GROUP BY 1
ORDER BY 1;
"""


# --- Switch list discovery for a given time range ---
# Returns switch_hosts that reported port status within the time range.
#
# Params:
#   - start_ts, end_ts: timestamps
SWITCH_HOSTS_IN_RANGE = """
SELECT DISTINCT switch_host
FROM public.raw_brocade_port_status
WHERE collection_timestamp BETWEEN %s AND %s
ORDER BY 1;
"""


# --- SAN bottleneck (raw_brocade_san_fcport_1) ---
# This table does not have switch_host/DC fields in the current DDL.
# We fetch the latest snapshot rows and filter by DC in Python using `portname`.
#
# Params:
#   - limit: int
SAN_FCPORT_LATEST = """
SELECT
    portname,
    COALESCE(swfcportnotxcredits, 0) AS swfcportnotxcredits,
    COALESCE(swfcporttoomanyrdys, 0) AS swfcporttoomanyrdys,
    "timestamp" AS ts
FROM public.raw_brocade_san_fcport_1
WHERE "timestamp" = (SELECT MAX("timestamp") FROM public.raw_brocade_san_fcport_1)
  AND (
        COALESCE(swfcportnotxcredits, 0) > 0
     OR COALESCE(swfcporttoomanyrdys, 0) > 0
  )
ORDER BY
    swfcportnotxcredits DESC,
    swfcporttoomanyrdys DESC
LIMIT %s;
"""

