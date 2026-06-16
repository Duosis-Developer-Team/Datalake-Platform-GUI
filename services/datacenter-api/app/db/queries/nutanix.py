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
    COALESCE(SUM(total_memory_capacity), 0) AS total_memory_capacity,
    COALESCE(SUM(used_memory), 0) AS used_memory
FROM (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        total_memory_capacity,
        ((memory_usage_avg / 1000.0) * total_memory_capacity) / 1000.0 AS used_memory
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
"""

STORAGE = """
SELECT
    COALESCE(SUM(storage_capacity) / 2, 0) AS storage_capacity,
    COALESCE(SUM(storage_usage) / 2, 0) AS storage_usage
FROM (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        storage_capacity,
        storage_usage
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
"""

CPU = """
SELECT
    COALESCE(SUM(total_cpu_capacity), 0) AS total_cpu_capacity,
    COALESCE(SUM(cpu_used), 0) AS cpu_used
FROM (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        total_cpu_capacity,
        (cpu_usage_avg * total_cpu_capacity) / 1000000.0 AS cpu_used
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
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
latest AS (
    SELECT DISTINCT ON (cluster_name) dc_code, total_memory_capacity, used_memory
    FROM matched
    ORDER BY cluster_name, ord, collection_time DESC
)
SELECT dc_code,
    COALESCE(SUM(total_memory_capacity), 0) AS total_memory_capacity,
    COALESCE(SUM(used_memory), 0) AS used_memory
FROM latest
GROUP BY dc_code
"""

BATCH_STORAGE = """
WITH matched AS (
    SELECT n.cluster_name, n.collection_time, n.storage_capacity, n.storage_usage, u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (cluster_name) dc_code, storage_capacity, storage_usage
    FROM matched
    ORDER BY cluster_name, ord, collection_time DESC
)
SELECT dc_code,
    COALESCE(SUM(storage_capacity) / 2, 0) AS storage_cap,
    COALESCE(SUM(storage_usage) / 2, 0) AS storage_used
FROM latest
GROUP BY dc_code
"""

BATCH_CPU = """
WITH matched AS (
    SELECT n.cluster_name, n.collection_time, n.total_cpu_capacity, n.cpu_usage_avg, u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (cluster_name) dc_code,
        total_cpu_capacity,
        (cpu_usage_avg * total_cpu_capacity) / 1000000.0 AS cpu_used
    FROM matched
    ORDER BY cluster_name, ord, collection_time DESC
)
SELECT dc_code,
    COALESCE(SUM(total_cpu_capacity), 0) AS total_cpu_capacity,
    COALESCE(SUM(cpu_used), 0) AS cpu_used
FROM latest
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

# =============================================================================
# Cluster list and filtered metrics (for DC view cluster selector)
# Params for CLUSTER_LIST: (dc_code, start_ts, end_ts)
# Params for *_FILTERED: (dc_code, cluster_array, start_ts, end_ts). cluster_array non-empty.
# =============================================================================

CLUSTER_LIST = """
SELECT DISTINCT cluster_name
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE ('%%' || %s || '%%') AND collection_time BETWEEN %s AND %s
ORDER BY cluster_name
"""

HOST_COUNT_FILTERED = """
SELECT COALESCE(SUM(num_nodes), 0)
FROM (
    SELECT DISTINCT ON (cluster_name) cluster_name, num_nodes
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND cluster_name = ANY(%s::text[])
      AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
"""

VM_COUNT_FILTERED = """
SELECT COALESCE(SUM(total_vms), 0)
FROM (
    SELECT DISTINCT ON (cluster_name) cluster_name, total_vms
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND cluster_name = ANY(%s::text[])
      AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
"""

MEMORY_FILTERED = """
SELECT
    COALESCE(SUM(total_memory_capacity), 0) AS total_memory_capacity,
    COALESCE(SUM(used_memory), 0) AS used_memory
FROM (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        total_memory_capacity,
        ((memory_usage_avg / 1000.0) * total_memory_capacity) / 1000.0 AS used_memory
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND cluster_name = ANY(%s::text[])
      AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
"""

STORAGE_FILTERED = """
SELECT
    COALESCE(SUM(storage_capacity) / 2, 0) AS storage_capacity,
    COALESCE(SUM(storage_usage) / 2, 0) AS storage_usage
FROM (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        storage_capacity,
        storage_usage
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND cluster_name = ANY(%s::text[])
      AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
"""

CPU_FILTERED = """
SELECT
    COALESCE(SUM(total_cpu_capacity), 0) AS total_cpu_capacity,
    COALESCE(SUM(cpu_used), 0) AS cpu_used
FROM (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        total_cpu_capacity,
        (cpu_usage_avg * total_cpu_capacity) / 1000000.0 AS cpu_used
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND cluster_name = ANY(%s::text[])
      AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
) latest
"""

# =============================================================================
# VM-level storage breakdown (provisioned disk vs actually used)
# Maps DC via cluster_name LIKE '%dc_code%' (same as HOST_COUNT / CPU / etc.).
# Params: (dc_code,) or (dc_code, cluster_array) for FILTERED variant.
# Returns: (provisioned_gb, used_gb, vcpu_count, mem_alloc_gb)
# =============================================================================

# =============================================================================
# Host-level compute rows (nutanix_host_metrics) — per-host capacity/usage for
# the DC view Hosts panel and the host-based sellable computation.
# Cluster names resolved via nutanix_cluster_metrics (cluster_uuid join);
# CPU values are in Hz, memory/storage in bytes (converted in Python).
# Params: (dc_code, cluster_filter[], cluster_filter[], start_ts, end_ts)
# Empty cluster_filter[] = all clusters in the DC.
# =============================================================================

NUTANIX_HOST_ROWS = """
WITH dc_clusters AS (
    SELECT DISTINCT ON (cluster_uuid)
        cluster_uuid::text AS cluster_uuid,
        cluster_name
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND (cardinality(%s::text[]) = 0 OR cluster_name = ANY(%s::text[]))
      AND collection_time >= NOW() - INTERVAL '7 days'
    ORDER BY cluster_uuid, collection_time DESC
)
SELECT DISTINCT ON (h.host_uuid)
    h.host_name,
    c.cluster_name,
    COALESCE(h.total_cpu_capacity, 0)     AS cpu_cap_hz,
    COALESCE(h.cpu_usage_avg, 0)          AS cpu_used_hz,
    COALESCE(h.total_memory_capacity, 0)  AS mem_cap_bytes,
    COALESCE(h.memory_usage_avg, 0)       AS mem_used_bytes,
    COALESCE(h.storage_capacity, 0)       AS stor_cap_bytes,
    COALESCE(h.storage_usage, 0)          AS stor_used_bytes,
    COALESCE(h.total_vms, 0)              AS vm_count
FROM public.nutanix_host_metrics h
JOIN dc_clusters c ON h.cluster_uuid::text = c.cluster_uuid
WHERE h.collectiontime BETWEEN %s AND %s
ORDER BY h.host_uuid, h.collectiontime DESC
"""

# Per-host RAM peak from nutanix_host_metrics (hyperconverged scope).
# Params: (dc_code, cluster_filter[], cluster_filter[], start_ts, end_ts)
NUTANIX_HOST_MEM_PEAK = """
WITH dc_clusters AS (
    SELECT DISTINCT ON (cluster_uuid)
        cluster_uuid::text AS cluster_uuid,
        cluster_name
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND (cardinality(%s::text[]) = 0 OR cluster_name = ANY(%s::text[]))
      AND collection_time >= NOW() - INTERVAL '7 days'
    ORDER BY cluster_uuid, collection_time DESC
),
ts_agg AS (
    SELECT h.host_name,
           h.collectiontime,
           COALESCE(h.memory_usage_avg, 0)      AS used_bytes,
           COALESCE(h.total_memory_capacity, 0) AS cap_bytes
    FROM public.nutanix_host_metrics h
    INNER JOIN dc_clusters c ON h.cluster_uuid::text = c.cluster_uuid
    WHERE h.collectiontime BETWEEN %s AND %s
)
SELECT DISTINCT ON (host_name)
    host_name,
    COALESCE(used_bytes / 1073741824.0, 0),
    COALESCE(cap_bytes / 1073741824.0, 0),
    COALESCE(100.0 * used_bytes / NULLIF(cap_bytes, 0), 0)
FROM ts_agg
WHERE cap_bytes > 0
ORDER BY host_name, used_bytes DESC, (used_bytes / NULLIF(cap_bytes, 0)) DESC
"""

# Per-host VM allocation aggregate (vCPU / RAM provisioned by Nutanix VMs on
# each host). Sales CPU rule: 1 vCPU = 1 GHz (applied in Python).
# Params: (dc_code, cluster_filter[], cluster_filter[], start_ts, end_ts)
NUTANIX_HOST_VM_ALLOCATION = """
WITH dc_clusters AS (
    SELECT DISTINCT cluster_uuid::text AS cluster_uuid
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND (cardinality(%s::text[]) = 0 OR cluster_name = ANY(%s::text[]))
      AND collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (vm_name)
        host_name,
        cpu_count,
        memory_capacity,
        disk_capacity,
        used_storage
    FROM public.nutanix_vm_metrics
    WHERE cluster_uuid::text IN (SELECT cluster_uuid FROM dc_clusters)
      AND collection_time BETWEEN %s AND %s
    ORDER BY vm_name, collection_time DESC
)
SELECT
    host_name,
    COUNT(*)                                              AS vm_count,
    COALESCE(SUM(cpu_count), 0)                           AS vcpu_total,
    COALESCE(SUM(memory_capacity / 1073741824.0), 0)      AS mem_alloc_gb,
    COALESCE(SUM(disk_capacity / 1073741824.0), 0)        AS stor_provisioned_gb,
    COALESCE(SUM(used_storage / 1073741824.0), 0)         AS stor_used_gb
FROM latest
GROUP BY host_name
"""

NUTANIX_VM_STORAGE = """
WITH dc_clusters AS (
    SELECT DISTINCT cluster_uuid::text AS cluster_uuid
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (vm_name)
        vm_name, disk_capacity, used_storage, cpu_count, memory_capacity
    FROM public.nutanix_vm_metrics
    WHERE cluster_uuid::text IN (SELECT cluster_uuid FROM dc_clusters)
      AND collection_time BETWEEN %s AND %s
    ORDER BY vm_name, collection_time DESC
)
SELECT
    COALESCE(SUM(disk_capacity / 1073741824.0), 0)     AS provisioned_gb,
    COALESCE(SUM(used_storage  / 1073741824.0), 0)     AS used_gb,
    COALESCE(SUM(cpu_count), 0)::bigint                AS vcpu_count,
    COALESCE(SUM(memory_capacity / 1073741824.0), 0)   AS mem_alloc_gb
FROM latest
"""

NUTANIX_VM_STORAGE_FILTERED = """
WITH dc_clusters AS (
    SELECT DISTINCT cluster_uuid::text AS cluster_uuid
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND cluster_name = ANY(%s::text[])
      AND collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (vm_name)
        vm_name, disk_capacity, used_storage, cpu_count, memory_capacity
    FROM public.nutanix_vm_metrics
    WHERE cluster_uuid::text IN (SELECT cluster_uuid FROM dc_clusters)
      AND collection_time BETWEEN %s AND %s
    ORDER BY vm_name, collection_time DESC
)
SELECT
    COALESCE(SUM(disk_capacity / 1073741824.0), 0)     AS provisioned_gb,
    COALESCE(SUM(used_storage  / 1073741824.0), 0)     AS used_gb,
    COALESCE(SUM(cpu_count), 0)::bigint                AS vcpu_count,
    COALESCE(SUM(memory_capacity / 1073741824.0), 0)   AS mem_alloc_gb
FROM latest
"""

# =============================================================================
# Per-VM allocation rows for Python host-GHz aggregation (same CTE as above).
# Params: (dc_code,) or (dc_code, cluster_array) for FILTERED variant.
# Returns rows: (host_name, cpu_count, mem_gb, prov_gb, used_gb)
# =============================================================================

NUTANIX_VM_ALLOCATION_ROWS = """
WITH dc_clusters AS (
    SELECT DISTINCT cluster_uuid::text AS cluster_uuid
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (vm_name)
        vm_name, host_name, disk_capacity, used_storage, cpu_count, memory_capacity
    FROM public.nutanix_vm_metrics
    WHERE cluster_uuid::text IN (SELECT cluster_uuid FROM dc_clusters)
      AND collection_time BETWEEN %s AND %s
    ORDER BY vm_name, collection_time DESC
)
SELECT
    host_name,
    COALESCE(cpu_count, 0)::int,
    COALESCE(memory_capacity / 1073741824.0, 0),
    COALESCE(disk_capacity / 1073741824.0, 0),
    COALESCE(used_storage / 1073741824.0, 0)
FROM latest
"""

NUTANIX_VM_ALLOCATION_ROWS_FILTERED = """
WITH dc_clusters AS (
    SELECT DISTINCT cluster_uuid::text AS cluster_uuid
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND cluster_name = ANY(%s::text[])
      AND collection_time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (vm_name)
        vm_name, host_name, disk_capacity, used_storage, cpu_count, memory_capacity
    FROM public.nutanix_vm_metrics
    WHERE cluster_uuid::text IN (SELECT cluster_uuid FROM dc_clusters)
      AND collection_time BETWEEN %s AND %s
    ORDER BY vm_name, collection_time DESC
)
SELECT
    host_name,
    COALESCE(cpu_count, 0)::int,
    COALESCE(memory_capacity / 1073741824.0, 0),
    COALESCE(disk_capacity / 1073741824.0, 0),
    COALESCE(used_storage / 1073741824.0, 0)
FROM latest
"""

# Memory peak from Nutanix cluster timestamp aggregates (hyperconverged scope).
NUTANIX_MEM_PEAK_RAW = """
WITH ts_agg AS (
    SELECT collection_time AS ts,
           SUM(COALESCE(memory_usage_avg, 0)) AS used_bytes,
           SUM(COALESCE(total_memory_capacity, 0)) AS cap_bytes
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND collection_time BETWEEN %s AND %s
    GROUP BY collection_time
)
SELECT COALESCE(used_bytes / 1073741824.0, 0),
       COALESCE(cap_bytes / 1073741824.0, 0),
       COALESCE(100.0 * used_bytes / NULLIF(cap_bytes, 0), 0)
FROM ts_agg
WHERE cap_bytes > 0
ORDER BY used_bytes DESC, (used_bytes / NULLIF(cap_bytes, 0)) DESC
LIMIT 1
"""

NUTANIX_MEM_PEAK_RAW_FILTERED = """
WITH ts_agg AS (
    SELECT collection_time AS ts,
           SUM(COALESCE(memory_usage_avg, 0)) AS used_bytes,
           SUM(COALESCE(total_memory_capacity, 0)) AS cap_bytes
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND cluster_name = ANY(%s::text[])
      AND collection_time BETWEEN %s AND %s
    GROUP BY collection_time
)
SELECT COALESCE(used_bytes / 1073741824.0, 0),
       COALESCE(cap_bytes / 1073741824.0, 0),
       COALESCE(100.0 * used_bytes / NULLIF(cap_bytes, 0), 0)
FROM ts_agg
WHERE cap_bytes > 0
ORDER BY used_bytes DESC, (used_bytes / NULLIF(cap_bytes, 0)) DESC
LIMIT 1
"""
