# Energy SQL query definitions
# Sources: vmhost_metrics (vCenter), ibm_server_power (IBM HMC). Loki/racks not used.
# Individual: params (dc_param or wildcard, start_ts, end_ts). Batch: (dc_list, start_ts, end_ts) or (start_ts, end_ts, dc_list).
# All energy values as AVG over time range (daily average).

# --- Individual queries ---

# vCenter: params (dc_code, start_ts, end_ts). Map DC to datacenter(s) via datacenter_metrics.
VCENTER = """
SELECT COALESCE(AVG(vm.power_usage), 0)
FROM public.vmhost_metrics vm
WHERE vm.datacenter IN (
    SELECT DISTINCT datacenter FROM public.datacenter_metrics WHERE dc = %s
)
AND vm."timestamp" BETWEEN %s AND %s
"""

# IBM: params (wildcard, start_ts, end_ts). Average power per server in range.
IBM = """
SELECT COALESCE(AVG(power_watts), 0)
FROM public.ibm_server_power
WHERE server_name ILIKE %s AND "timestamp" BETWEEN %s AND %s
"""

# --- Batch queries ---

# vCenter batch: params (dc_list, start_ts, end_ts). Returns (dc, avg_power_watts).
BATCH_VCENTER = """
WITH dc_map AS (
    SELECT DISTINCT dc, datacenter
    FROM public.datacenter_metrics
    WHERE dc = ANY(%s)
)
SELECT dm.dc, AVG(vm.power_usage) AS avg_power_watts
FROM public.vmhost_metrics vm
JOIN dc_map dm ON vm.datacenter = dm.datacenter
WHERE vm."timestamp" BETWEEN %s AND %s
GROUP BY dm.dc
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
