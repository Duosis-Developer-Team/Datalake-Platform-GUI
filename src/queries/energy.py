# Energy SQL query definitions
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
