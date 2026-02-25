# Energy SQL query definitions
# Sources: loki_racks, ibm_server_power, vmhost_metrics
# Racks: include child locations via loki_locations parent_name hierarchy

# --- Individual queries ---

# loki_racks: DC + child locations (parent_name in loki_locations)
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
WHERE (location_name = %s OR location_name IN (SELECT name FROM public.loki_locations WHERE parent_name = %s))
  AND id IN (SELECT DISTINCT id FROM public.loki_racks)
"""

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
# Racks: aggregate by DC including child locations, return (dc_code, total_watts)
BATCH_RACKS = r"""
WITH dc_list AS (SELECT unnest(%s::text[]) AS dc_code),
     rack_totals AS (
         SELECT location_name,
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
         WHERE (location_name = ANY(%s) OR location_name IN (SELECT name FROM public.loki_locations WHERE parent_name = ANY(%s)))
           AND id IN (SELECT DISTINCT id FROM public.loki_racks)
         GROUP BY location_name
     ),
     with_dc AS (
         SELECT r.location_name, r.total_watts, COALESCE(l.parent_name, l.name) AS dc_code
         FROM rack_totals r
         JOIN public.loki_locations l ON r.location_name = l.name
     )
SELECT dc_code, SUM(total_watts) AS total_watts
FROM with_dc
WHERE dc_code = ANY(%s)
GROUP BY dc_code
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
