VCENTER = """
SELECT COALESCE(AVG(vm.power_usage), 0)
FROM public.vmhost_metrics vm
WHERE vm.datacenter ILIKE ('%%' || %s || '%%')
AND vm."timestamp" BETWEEN %s AND %s
"""

IBM = """
SELECT COALESCE(AVG(power_watts), 0)
FROM public.ibm_server_power
WHERE server_name ILIKE %s AND "timestamp" BETWEEN %s AND %s
"""

VCENTER_KWH = """
SELECT COALESCE(SUM(total_watts) * (15.0 / 60.0) / 1000.0, 0)
FROM (
    SELECT vm."timestamp", SUM(vm.power_usage) AS total_watts
    FROM public.vmhost_metrics vm
    WHERE vm.datacenter ILIKE ('%%' || %s || '%%') AND vm."timestamp" BETWEEN %s AND %s
    GROUP BY vm."timestamp"
) sub
"""

IBM_KWH = """
SELECT COALESCE(SUM(total_watts) * (15.0 / 60.0) / 1000.0, 0)
FROM (
    SELECT "timestamp", SUM(power_watts) AS total_watts
    FROM public.ibm_server_power
    WHERE server_name ILIKE %s AND "timestamp" BETWEEN %s AND %s
    GROUP BY "timestamp"
) sub
"""

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
