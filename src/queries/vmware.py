# VMware SQL query definitions — source: datacenter_metrics
# dc = datacenter code (e.g. DC13); datacenter = hypervisor name.
# Individual: params (dc_code, start_ts, end_ts). Batch: (dc_list, start_ts, end_ts).
# No LIMIT 1: counts sum across all hypervisors per DC; usage is AVG over time range.

# --- Individual queries ---

COUNTS = """
WITH latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc, datacenter)
        dc, datacenter, total_cluster_count, total_host_count, total_vm_count
    FROM public.datacenter_metrics
    WHERE dc = %s AND timestamp BETWEEN %s AND %s
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
WHERE dc = %s AND timestamp BETWEEN %s AND %s
"""

STORAGE = """
SELECT
    AVG(total_storage_capacity_gb) * (1024 * 1024),
    AVG(total_used_storage_gb) * (1024 * 1024)
FROM public.datacenter_metrics
WHERE dc = %s AND timestamp BETWEEN %s AND %s
"""

CPU = """
SELECT
    AVG(total_cpu_ghz_capacity) * 1000000000,
    AVG(total_cpu_ghz_used) * 1000000000
FROM public.datacenter_metrics
WHERE dc = %s AND timestamp BETWEEN %s AND %s
"""

# --- Batch queries (params: dc_list, start_ts, end_ts) ---

BATCH_COUNTS = """
WITH latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc, datacenter)
        dc, datacenter, total_cluster_count, total_host_count, total_vm_count
    FROM public.datacenter_metrics
    WHERE dc = ANY(%s) AND timestamp BETWEEN %s AND %s
    ORDER BY dc, datacenter, timestamp DESC
)
SELECT
    dc,
    COALESCE(SUM(total_cluster_count), 0) AS total_cluster_count,
    COALESCE(SUM(total_host_count), 0) AS total_host_count,
    COALESCE(SUM(total_vm_count), 0) AS total_vm_count
FROM latest_per_hypervisor
GROUP BY dc
"""

BATCH_MEMORY = """
SELECT
    dc,
    AVG(total_memory_capacity_gb) * 1024 * 1024 * 1024 AS mem_cap,
    AVG(total_memory_used_gb) * 1024 * 1024 * 1024     AS mem_used
FROM public.datacenter_metrics
WHERE dc = ANY(%s) AND timestamp BETWEEN %s AND %s
GROUP BY dc
"""

BATCH_STORAGE = """
SELECT
    dc,
    AVG(total_storage_capacity_gb) * (1024 * 1024) AS stor_cap,
    AVG(total_used_storage_gb) * (1024 * 1024)      AS stor_used
FROM public.datacenter_metrics
WHERE dc = ANY(%s) AND timestamp BETWEEN %s AND %s
GROUP BY dc
"""

BATCH_CPU = """
SELECT
    dc,
    AVG(total_cpu_ghz_capacity) * 1000000000 AS cpu_cap,
    AVG(total_cpu_ghz_used) * 1000000000     AS cpu_used
FROM public.datacenter_metrics
WHERE dc = ANY(%s) AND timestamp BETWEEN %s AND %s
GROUP BY dc
"""
