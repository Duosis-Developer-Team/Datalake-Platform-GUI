# Nutanix SQL query definitions — source: nutanix_cluster_metrics
# Individual queries (single DC) and batch queries (all DCs at once)
# Params: (datacenter_name, start_ts, end_ts) for individual; (dc_list, start_ts, end_ts) for batch.
# No LIMIT 1: counts sum across all clusters per DC (latest per cluster); usage is AVG over time range.

# --- Individual queries (params: datacenter_name, start_ts, end_ts) ---

HOST_COUNT = """
SELECT COALESCE(SUM(num_nodes), 0)
FROM (
    SELECT DISTINCT ON (cluster_name) cluster_name, num_nodes
    FROM public.nutanix_cluster_metrics
    WHERE datacenter_name = %s AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
"""

VM_COUNT = """
SELECT COALESCE(SUM(total_vms), 0)
FROM (
    SELECT DISTINCT ON (cluster_name) cluster_name, total_vms
    FROM public.nutanix_cluster_metrics
    WHERE datacenter_name = %s AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
"""

MEMORY = """
SELECT
    AVG(total_memory_capacity),
    AVG(((memory_usage_avg / 1000) * total_memory_capacity) / 1000)
FROM public.nutanix_cluster_metrics
WHERE datacenter_name = %s AND collection_time BETWEEN %s AND %s
"""

STORAGE = """
SELECT
    AVG(storage_capacity / 2),
    AVG(storage_usage / 2)
FROM public.nutanix_cluster_metrics
WHERE datacenter_name = %s AND collection_time BETWEEN %s AND %s
"""

CPU = """
SELECT
    AVG(total_cpu_capacity),
    AVG((cpu_usage_avg * total_cpu_capacity) / 1000000)
FROM public.nutanix_cluster_metrics
WHERE datacenter_name = %s AND collection_time BETWEEN %s AND %s
"""

# --- Batch queries (params: dc_list, start_ts, end_ts) ---
# Counts: latest per cluster then SUM per DC. Usage: AVG over all rows per DC.

BATCH_HOST_COUNT = """
SELECT
    datacenter_name,
    SUM(num_nodes) AS num_nodes
FROM (
    SELECT DISTINCT ON (cluster_name)
        datacenter_name,
        cluster_name,
        num_nodes
    FROM public.nutanix_cluster_metrics
    WHERE datacenter_name = ANY(%s) AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
GROUP BY datacenter_name
"""

BATCH_MEMORY = """
SELECT
    datacenter_name,
    AVG(total_memory_capacity) AS total_memory_capacity,
    AVG(((memory_usage_avg / 1000) * total_memory_capacity) / 1000) AS used_memory
FROM public.nutanix_cluster_metrics
WHERE datacenter_name = ANY(%s) AND collection_time BETWEEN %s AND %s
GROUP BY datacenter_name
"""

BATCH_STORAGE = """
SELECT
    datacenter_name,
    AVG(storage_capacity / 2) AS storage_cap,
    AVG(storage_usage / 2)    AS storage_used
FROM public.nutanix_cluster_metrics
WHERE datacenter_name = ANY(%s) AND collection_time BETWEEN %s AND %s
GROUP BY datacenter_name
"""

BATCH_CPU = """
SELECT
    datacenter_name,
    AVG(total_cpu_capacity) AS total_cpu_capacity,
    AVG((cpu_usage_avg * total_cpu_capacity) / 1000000) AS cpu_used
FROM public.nutanix_cluster_metrics
WHERE datacenter_name = ANY(%s) AND collection_time BETWEEN %s AND %s
GROUP BY datacenter_name
"""

BATCH_VM_COUNT = """
SELECT
    datacenter_name,
    SUM(total_vms) AS total_vms
FROM (
    SELECT DISTINCT ON (cluster_name)
        datacenter_name,
        cluster_name,
        total_vms
    FROM public.nutanix_cluster_metrics
    WHERE datacenter_name = ANY(%s) AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
GROUP BY datacenter_name
"""
