# VMware SQL query definitions — source: datacenter_metrics
# Match DC by datacenter (vCenter/hypervisor name) containing DC code (e.g. datacenter ILIKE '%AZ11%').
# Individual: params (dc_code, start_ts, end_ts). Batch: (dc_list, pattern_list, start_ts, end_ts).
# pattern_list = ['%' || dc || '%' for each dc in dc_list], same order.

# --- Individual queries ---

COUNTS = """
WITH latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc, datacenter)
        dc, datacenter, total_cluster_count, total_host_count, total_vm_count
    FROM public.datacenter_metrics
    WHERE datacenter ILIKE ('%%' || %s || '%%') AND timestamp BETWEEN %s AND %s
    ORDER BY dc, datacenter, timestamp DESC
)
SELECT
    COALESCE(SUM(total_cluster_count), 0),
    COALESCE(SUM(total_host_count), 0),
    COALESCE(SUM(total_vm_count), 0)
FROM latest_per_hypervisor
"""

MEMORY = """
SELECT
    AVG(total_memory_capacity_gb) * 1024 * 1024 * 1024,
    AVG(total_memory_used_gb) * 1024 * 1024 * 1024
FROM public.datacenter_metrics
WHERE datacenter ILIKE ('%%' || %s || '%%') AND timestamp BETWEEN %s AND %s
"""

STORAGE = """
SELECT
    AVG(total_storage_capacity_gb) * (1024 * 1024),
    AVG(total_used_storage_gb) * (1024 * 1024)
FROM public.datacenter_metrics
WHERE datacenter ILIKE ('%%' || %s || '%%') AND timestamp BETWEEN %s AND %s
"""

CPU = """
SELECT
    AVG(total_cpu_ghz_capacity) * 1000000000,
    AVG(total_cpu_ghz_used) * 1000000000
FROM public.datacenter_metrics
WHERE datacenter ILIKE ('%%' || %s || '%%') AND timestamp BETWEEN %s AND %s
"""

# --- Batch queries (params: dc_list, pattern_list, start_ts, end_ts) ---

BATCH_COUNTS = """
WITH matched AS (
    SELECT d.dc, d.datacenter, d.total_cluster_count, d.total_host_count, d.total_vm_count,
        d.timestamp, u.dc_code, u.ord
    FROM public.datacenter_metrics d
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON d.datacenter ILIKE u.pattern
    WHERE d.timestamp BETWEEN %s AND %s
),
latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc, datacenter) dc_code, total_cluster_count, total_host_count, total_vm_count
    FROM matched
    ORDER BY dc, datacenter, ord, timestamp DESC
)
SELECT
    dc_code,
    COALESCE(SUM(total_cluster_count), 0) AS total_cluster_count,
    COALESCE(SUM(total_host_count), 0) AS total_host_count,
    COALESCE(SUM(total_vm_count), 0) AS total_vm_count
FROM latest_per_hypervisor
GROUP BY dc_code
"""

BATCH_MEMORY = """
WITH matched AS (
    SELECT d.datacenter, d.timestamp, d.total_memory_capacity_gb, d.total_memory_used_gb, u.dc_code, u.ord
    FROM public.datacenter_metrics d
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON d.datacenter ILIKE u.pattern
    WHERE d.timestamp BETWEEN %s AND %s
),
one_dc_per_row AS (
    SELECT DISTINCT ON (datacenter, timestamp) dc_code,
        total_memory_capacity_gb * 1024 * 1024 * 1024 AS mem_cap,
        total_memory_used_gb * 1024 * 1024 * 1024 AS mem_used
    FROM matched
    ORDER BY datacenter, timestamp, ord
)
SELECT dc_code,
    AVG(mem_cap) AS mem_cap,
    AVG(mem_used) AS mem_used
FROM one_dc_per_row
GROUP BY dc_code
"""

BATCH_STORAGE = """
WITH matched AS (
    SELECT d.datacenter, d.timestamp, d.total_storage_capacity_gb, d.total_used_storage_gb, u.dc_code, u.ord
    FROM public.datacenter_metrics d
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON d.datacenter ILIKE u.pattern
    WHERE d.timestamp BETWEEN %s AND %s
),
one_dc_per_row AS (
    SELECT DISTINCT ON (datacenter, timestamp) dc_code,
        total_storage_capacity_gb * (1024 * 1024) AS stor_cap,
        total_used_storage_gb * (1024 * 1024) AS stor_used
    FROM matched
    ORDER BY datacenter, timestamp, ord
)
SELECT dc_code,
    AVG(stor_cap) AS stor_cap,
    AVG(stor_used) AS stor_used
FROM one_dc_per_row
GROUP BY dc_code
"""

BATCH_CPU = """
WITH matched AS (
    SELECT d.datacenter, d.timestamp, d.total_cpu_ghz_capacity, d.total_cpu_ghz_used, u.dc_code, u.ord
    FROM public.datacenter_metrics d
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON d.datacenter ILIKE u.pattern
    WHERE d.timestamp BETWEEN %s AND %s
),
one_dc_per_row AS (
    SELECT DISTINCT ON (datacenter, timestamp) dc_code,
        total_cpu_ghz_capacity * 1000000000 AS cpu_cap,
        total_cpu_ghz_used * 1000000000 AS cpu_used
    FROM matched
    ORDER BY datacenter, timestamp, ord
)
SELECT dc_code,
    AVG(cpu_cap) AS cpu_cap,
    AVG(cpu_used) AS cpu_used
FROM one_dc_per_row
GROUP BY dc_code
"""

# Number of distinct hypervisors (datacenter) per DC in time range — for platform count
BATCH_PLATFORM_COUNT = """
WITH matched AS (
    SELECT d.dc, d.datacenter, d.timestamp, u.dc_code, u.ord
    FROM public.datacenter_metrics d
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON d.datacenter ILIKE u.pattern
    WHERE d.timestamp BETWEEN %s AND %s
),
latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc, datacenter) dc_code
    FROM matched
    ORDER BY dc, datacenter, ord, timestamp DESC
)
SELECT dc_code, COUNT(*) AS platform_count
FROM latest_per_hypervisor
GROUP BY dc_code
"""
