# Energy SQL query definitions
# Sources: vmhost_metrics (vCenter), ibm_server_power (IBM HMC).
# Individual: params (dc_param or wildcard, start_ts, end_ts). Batch: (dc_list, start_ts, end_ts) or (start_ts, end_ts, dc_list).
#
# Power usage: AVG over all samples in [start_ts, end_ts]. Data is typically collected every 15 minutes
# (96 samples/day). AVG(power) gives the average power in watts over the period; displayed as "daily average"
# in the UI when the report period is one or more days. No extra scaling by interval count is needed.

# --- Individual queries ---

# vCenter: params (dc_code, start_ts, end_ts). Match by datacenter name containing DC code (ILIKE '%dc%').
VCENTER = """
SELECT COALESCE(AVG(vm.power_usage), 0)
FROM public.vmhost_metrics vm
WHERE vm.datacenter ILIKE ('%%' || %s || '%%')
AND vm."timestamp" BETWEEN %s AND %s
"""

# IBM: params (wildcard, start_ts, end_ts). Average power per server in range.
IBM = """
SELECT COALESCE(AVG(power_watts), 0)
FROM public.ibm_server_power
WHERE server_name ILIKE %s AND "timestamp" BETWEEN %s AND %s
"""

# --- Total energy (kWh) for billing: 15-min interval, total kWh = sum(total_watts per timestamp) * 0.25 / 1000 ---

# vCenter kWh: params (dc_code, start_ts, end_ts). One row per timestamp after GROUP BY; interval 15 min = 0.25 h.
VCENTER_KWH = """
SELECT COALESCE(SUM(total_watts) * (15.0 / 60.0) / 1000.0, 0)
FROM (
    SELECT vm."timestamp", SUM(vm.power_usage) AS total_watts
    FROM public.vmhost_metrics vm
    WHERE vm.datacenter ILIKE ('%%' || %s || '%%') AND vm."timestamp" BETWEEN %s AND %s
    GROUP BY vm."timestamp"
) sub
"""

# IBM kWh: params (wildcard, start_ts, end_ts).
IBM_KWH = """
SELECT COALESCE(SUM(total_watts) * (15.0 / 60.0) / 1000.0, 0)
FROM (
    SELECT "timestamp", SUM(power_watts) AS total_watts
    FROM public.ibm_server_power
    WHERE server_name ILIKE %s AND "timestamp" BETWEEN %s AND %s
    GROUP BY "timestamp"
) sub
"""

# --- Batch queries ---

# vCenter batch: params (dc_list, pattern_list, start_ts, end_ts). Returns (dc_code, avg_power_watts).
# Match vmhost_metrics.datacenter by ILIKE pattern; assign to dc_code by first matching pattern.
BATCH_VCENTER = """
WITH dc_map AS (
    SELECT DISTINCT ON (d.datacenter) d.datacenter, u.dc_code
    FROM public.datacenter_metrics d
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON d.datacenter ILIKE u.pattern
    ORDER BY d.datacenter, u.ord
)
SELECT dm.dc_code, AVG(vm.power_usage) AS avg_power_watts
FROM public.vmhost_metrics vm
JOIN dc_map dm ON vm.datacenter = dm.datacenter
WHERE vm."timestamp" BETWEEN %s AND %s
GROUP BY dm.dc_code
"""

# IBM batch: params (start_ts, end_ts, dc_list). DC extracted from server_name; returns (dc_code, avg_power_watts).
BATCH_IBM = """
WITH extracted AS (
    SELECT
        (regexp_matches(UPPER(server_name), 'DC[0-9]+|AZ[0-9]+|ICT[0-9]+'))[1] AS dc_code,
        power_watts
    FROM public.ibm_server_power
    WHERE "timestamp" BETWEEN %s AND %s
)
SELECT dc_code, AVG(power_watts) AS avg_power_watts
FROM extracted
WHERE dc_code = ANY(%s)
GROUP BY dc_code
"""

# Batch kWh (for billing): same param order as BATCH_VCENTER / BATCH_IBM; returns (dc_code, total_kwh).

BATCH_VCENTER_KWH = """
WITH dc_map AS (
    SELECT DISTINCT ON (d.datacenter) d.datacenter, u.dc_code
    FROM public.datacenter_metrics d
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON d.datacenter ILIKE u.pattern
    ORDER BY d.datacenter, u.ord
),
per_ts AS (
    SELECT dm.dc_code, vm."timestamp", SUM(vm.power_usage) AS total_watts
    FROM public.vmhost_metrics vm
    JOIN dc_map dm ON vm.datacenter = dm.datacenter
    WHERE vm."timestamp" BETWEEN %s AND %s
    GROUP BY dm.dc_code, vm."timestamp"
)
SELECT dc_code, SUM(total_watts) * (15.0 / 60.0) / 1000.0 AS total_kwh
FROM per_ts
GROUP BY dc_code
"""

BATCH_IBM_KWH = """
WITH extracted AS (
    SELECT
        (regexp_matches(UPPER(server_name), 'DC[0-9]+|AZ[0-9]+|ICT[0-9]+'))[1] AS dc_code,
        "timestamp",
        power_watts
    FROM public.ibm_server_power
    WHERE "timestamp" BETWEEN %s AND %s
),
per_ts AS (
    SELECT dc_code, "timestamp", SUM(power_watts) AS total_watts
    FROM extracted
    WHERE dc_code = ANY(%s)
    GROUP BY dc_code, "timestamp"
)
SELECT dc_code, SUM(total_watts) * (15.0 / 60.0) / 1000.0 AS total_kwh
FROM per_ts
GROUP BY dc_code
"""
