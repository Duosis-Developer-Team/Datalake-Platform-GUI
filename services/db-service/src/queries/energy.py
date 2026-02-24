# Energy SQL query definitions
# Sources: loki_racks, ibm_server_power, vmhost_metrics
# asyncpg placeholder syntax: $1  (NOT %s)

# ── Individual queries ────────────────────────────────────────────────────────

# loki_racks: exact match (=) on location_name — DC name as stored in loki_locations.
# kabin_enerji is a dirty text field; regex normalises it to a numeric kW value × 1000 → Watts.
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
WHERE location_name = $1
"""

IBM = """
SELECT SUM(power_watts)
FROM public.ibm_server_power
WHERE server_name ILIKE $1
"""

VCENTER = """
WITH latest_per_host AS (
    SELECT DISTINCT ON (vm.vmhost) vm.power_usage
    FROM public.vmhost_metrics vm
    WHERE vm.vmhost ILIKE $1
      AND vm."timestamp" >= NOW() - INTERVAL '4 hours'
    ORDER BY vm.vmhost, vm."timestamp" DESC
)
SELECT SUM(power_usage)
FROM latest_per_host
"""

# ── Batch queries ─────────────────────────────────────────────────────────────

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
WHERE location_name = ANY($1::text[])
GROUP BY location_name
"""

BATCH_IBM = """
SELECT
    server_name,
    SUM(power_watts) AS total_watts
FROM public.ibm_server_power
WHERE server_name ILIKE ANY($1::text[])
GROUP BY server_name
"""

BATCH_VCENTER = """
WITH latest_per_host AS (
    SELECT DISTINCT ON (vm.vmhost)
        vm.vmhost,
        vm.power_usage
    FROM public.vmhost_metrics vm
    WHERE vm.vmhost ILIKE ANY($1::text[])
      AND vm."timestamp" >= NOW() - INTERVAL '4 hours'
    ORDER BY vm.vmhost, vm."timestamp" DESC
)
SELECT
    vmhost,
    SUM(power_usage) AS total_watts
FROM latest_per_host
GROUP BY vmhost
"""
