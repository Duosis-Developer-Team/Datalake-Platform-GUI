# Nutanix SQL query definitions — source: nutanix_cluster_metrics
# Match DC by cluster_name containing DC code (e.g. cluster_name LIKE '%AZ11%').
# Params: (dc_code, start_ts, end_ts) for individual; (dc_list, pattern_list, start_ts, end_ts) for batch.
# pattern_list = ['%' || dc || '%' for each dc in dc_list], same order.

# --- Individual queries (params: dc_code, start_ts, end_ts) ---

HOST_COUNT = """
SELECT COALESCE(SUM(num_nodes), 0)
FROM (
    SELECT DISTINCT ON (cluster_name) cluster_name, num_nodes
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
"""

VM_COUNT = """
SELECT COALESCE(SUM(total_vms), 0)
FROM (
    SELECT DISTINCT ON (cluster_name) cluster_name, total_vms
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
"""

MEMORY = """
SELECT
    AVG(total_memory_capacity),
    AVG(((memory_usage_avg / 1000) * total_memory_capacity) / 1000)
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
"""

STORAGE = """
SELECT
    AVG(storage_capacity / 2),
    AVG(storage_usage / 2)
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
"""

CPU = """
SELECT
    AVG(total_cpu_capacity),
    AVG((cpu_usage_avg * total_cpu_capacity) / 1000000)
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
"""

# --- Batch queries (params: dc_list, pattern_list, start_ts, end_ts) ---
# pattern_list[i] = '%' || dc_list[i] || '%'. Each cluster is assigned to first matching DC (by dc_list order).

BATCH_HOST_COUNT = """
WITH matched AS (
    SELECT n.cluster_name, n.num_nodes, n.collection_time, u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (cluster_name) dc_code, num_nodes
    FROM matched
    ORDER BY cluster_name, ord, collection_time DESC
)
SELECT dc_code, SUM(num_nodes) AS num_nodes
FROM latest
GROUP BY dc_code
"""

BATCH_MEMORY = """
WITH matched AS (
    SELECT n.cluster_name, n.collection_time, n.total_memory_capacity,
        ((n.memory_usage_avg / 1000.0) * n.total_memory_capacity) / 1000.0 AS used_memory,
        u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.collection_time BETWEEN %s AND %s
),
one_dc_per_row AS (
    SELECT DISTINCT ON (cluster_name, collection_time) dc_code, total_memory_capacity, used_memory
    FROM matched
    ORDER BY cluster_name, collection_time, ord
)
SELECT dc_code,
    AVG(total_memory_capacity) AS total_memory_capacity,
    AVG(used_memory) AS used_memory
FROM one_dc_per_row
GROUP BY dc_code
"""

BATCH_STORAGE = """
WITH latest_host AS (
    SELECT DISTINCT ON (host_uuid)
        host_uuid,
        cluster_uuid,
        storage_capacity,
        storage_usage
    FROM public.nutanix_host_metrics
    WHERE collectiontime BETWEEN %s AND %s
    ORDER BY host_uuid, collectiontime DESC
),
dc_map AS (
    SELECT DISTINCT ON (cluster_uuid)
        cluster_uuid,
        cluster_name
    FROM public.nutanix_cluster_metrics
    ORDER BY cluster_uuid, collection_time DESC
)
SELECT
    u.dc_code,
    SUM(h.storage_capacity) / (1024.0 * 1024.0 * 1024.0 * 1024.0) AS storage_cap,
    SUM(h.storage_usage)    / (1024.0 * 1024.0 * 1024.0 * 1024.0) AS storage_used
FROM latest_host h
JOIN dc_map d ON h.cluster_uuid = d.cluster_uuid
INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
    ON d.cluster_name LIKE u.pattern
GROUP BY u.dc_code
"""

BATCH_CPU = """
WITH matched AS (
    SELECT n.cluster_name, n.collection_time, n.total_cpu_capacity, n.cpu_usage_avg, u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.collection_time BETWEEN %s AND %s
),
one_dc_per_row AS (
    SELECT DISTINCT ON (cluster_name, collection_time) dc_code,
        total_cpu_capacity,
        (cpu_usage_avg * total_cpu_capacity) / 1000000.0 AS cpu_used
    FROM matched
    ORDER BY cluster_name, collection_time, ord
)
SELECT dc_code,
    AVG(total_cpu_capacity) AS total_cpu_capacity,
    AVG(cpu_used) AS cpu_used
FROM one_dc_per_row
GROUP BY dc_code
"""

BATCH_VM_COUNT = """
WITH matched AS (
    SELECT n.cluster_name, n.total_vms, n.collection_time, u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (cluster_name) dc_code, total_vms
    FROM matched
    ORDER BY cluster_name, ord, collection_time DESC
)
SELECT dc_code, SUM(total_vms) AS total_vms
FROM latest
GROUP BY dc_code
"""

# Number of distinct clusters per DC in time range — for platform count
BATCH_PLATFORM_COUNT = """
WITH matched AS (
    SELECT n.cluster_name, n.collection_time, u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (cluster_name) dc_code
    FROM matched
    ORDER BY cluster_name, ord, collection_time DESC
)
SELECT dc_code, COUNT(*) AS platform_count
FROM latest
GROUP BY dc_code
"""
