# VMware SQL query definitions.
# Two source tables:
#   datacenter_metrics  — DC-level aggregated VMware metrics (legacy, kept for energy & overview)
#   cluster_metrics     — Per-cluster VMware metrics; used to split Classic (KM) vs Hyperconverged
#
# datacenter_metrics match: datacenter ILIKE '%<DC_CODE>%'
# cluster_metrics match:    datacenter ILIKE '%<DC_CODE>%'
#   Classic:       cluster LIKE '%KM%'
#   Hyperconverged: cluster NOT LIKE '%KM%'
#
# Individual params: (dc_code, start_ts, end_ts)
# Batch params:      (dc_list[], pattern_list[], start_ts, end_ts)
# pattern_list = ['%' + dc + '%' for each dc in dc_list], same order.

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
WITH latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc, datacenter)
        dc,
        datacenter,
        total_memory_capacity_gb * 1024 * 1024 * 1024 AS mem_cap,
        total_memory_used_gb * 1024 * 1024 * 1024 AS mem_used
    FROM public.datacenter_metrics
    WHERE datacenter ILIKE ('%%' || %s || '%%') AND timestamp BETWEEN %s AND %s
    ORDER BY dc, datacenter, timestamp DESC
)
SELECT
    COALESCE(SUM(mem_cap), 0),
    COALESCE(SUM(mem_used), 0)
FROM latest_per_hypervisor
"""

STORAGE = """
WITH latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc, datacenter)
        dc,
        datacenter,
        total_storage_capacity_gb * (1024 * 1024) AS stor_cap,
        total_used_storage_gb * (1024 * 1024) AS stor_used
    FROM public.datacenter_metrics
    WHERE datacenter ILIKE ('%%' || %s || '%%') AND timestamp BETWEEN %s AND %s
    ORDER BY dc, datacenter, timestamp DESC
)
SELECT
    COALESCE(SUM(stor_cap), 0),
    COALESCE(SUM(stor_used), 0)
FROM latest_per_hypervisor
"""

CPU = """
WITH latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc, datacenter)
        dc,
        datacenter,
        total_cpu_ghz_capacity * 1000000000 AS cpu_cap,
        total_cpu_ghz_used * 1000000000 AS cpu_used
    FROM public.datacenter_metrics
    WHERE datacenter ILIKE ('%%' || %s || '%%') AND timestamp BETWEEN %s AND %s
    ORDER BY dc, datacenter, timestamp DESC
)
SELECT
    COALESCE(SUM(cpu_cap), 0),
    COALESCE(SUM(cpu_used), 0)
FROM latest_per_hypervisor
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
latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc_code, datacenter)
        dc_code,
        total_memory_capacity_gb * 1024 * 1024 * 1024 AS mem_cap,
        total_memory_used_gb * 1024 * 1024 * 1024 AS mem_used
    FROM matched
    ORDER BY dc_code, datacenter, ord, timestamp DESC
)
SELECT dc_code,
    COALESCE(SUM(mem_cap), 0) AS mem_cap,
    COALESCE(SUM(mem_used), 0) AS mem_used
FROM latest_per_hypervisor
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
latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc_code, datacenter)
        dc_code,
        total_storage_capacity_gb * (1024 * 1024) AS stor_cap,
        total_used_storage_gb * (1024 * 1024) AS stor_used
    FROM matched
    ORDER BY dc_code, datacenter, ord, timestamp DESC
)
SELECT dc_code,
    COALESCE(SUM(stor_cap), 0) AS stor_cap,
    COALESCE(SUM(stor_used), 0) AS stor_used
FROM latest_per_hypervisor
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
latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc_code, datacenter)
        dc_code,
        total_cpu_ghz_capacity * 1000000000 AS cpu_cap,
        total_cpu_ghz_used * 1000000000 AS cpu_used
    FROM matched
    ORDER BY dc_code, datacenter, ord, timestamp DESC
)
SELECT dc_code,
    COALESCE(SUM(cpu_cap), 0) AS cpu_cap,
    COALESCE(SUM(cpu_used), 0) AS cpu_used
FROM latest_per_hypervisor
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

# =============================================================================
# cluster_metrics — Classic (KM) vs Hyperconverged (non-KM) split
# Params for individual queries: (dc_pattern, start_ts, end_ts)
# cluster_metrics columns used:
#   vhost_count, vm_count, cpu_ghz_capacity, cpu_ghz_used,
#   memory_capacity_gb, memory_used_gb,
#   total_capacity_gb, total_freespace_gb,
#   cpu_usage_avg_perc, memory_usage_avg_perc
# =============================================================================

# --- Classic Compute (cluster LIKE '%KM%') individual query ---
CLASSIC_METRICS = """
WITH latest_per_cluster AS (
    SELECT DISTINCT ON (cluster)
        vhost_count, vm_count,
        cpu_ghz_capacity, cpu_ghz_used,
        memory_capacity_gb, memory_used_gb,
        total_capacity_gb, total_freespace_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC
)
SELECT
    COALESCE(SUM(vhost_count), 0)                                   AS hosts,
    COALESCE(SUM(vm_count), 0)                                      AS vms,
    COALESCE(SUM(cpu_ghz_capacity), 0)                              AS cpu_cap_ghz,
    COALESCE(SUM(cpu_ghz_used), 0)                                  AS cpu_used_ghz,
    COALESCE(SUM(memory_capacity_gb), 0)                            AS mem_cap_gb,
    COALESCE(SUM(memory_used_gb), 0)                                AS mem_used_gb,
    COALESCE(SUM(total_capacity_gb), 0)                             AS stor_cap_gb,
    COALESCE(SUM(total_capacity_gb - total_freespace_gb), 0)        AS stor_used_gb
FROM latest_per_cluster
"""

# --- Classic Compute utilization stats (used/capacity ratio over time range) ---
CLASSIC_AVG30 = """
SELECT
    COALESCE(AVG(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_avg_pct,
    COALESCE(AVG(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_avg_pct,
    COALESCE(MAX(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_max_pct,
    COALESCE(MAX(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_max_pct,
    COALESCE(MIN(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_min_pct,
    COALESCE(MIN(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_min_pct
FROM public.cluster_metrics
WHERE datacenter ILIKE %s
  AND cluster ILIKE '%%KM%%'
  AND timestamp BETWEEN %s AND %s
"""

# --- Hyperconverged Compute (cluster NOT LIKE '%KM%') individual query ---
HYPERCONV_METRICS = """
WITH latest_per_cluster AS (
    SELECT DISTINCT ON (cluster)
        vhost_count, vm_count,
        cpu_ghz_capacity, cpu_ghz_used,
        memory_capacity_gb, memory_used_gb,
        total_capacity_gb, total_freespace_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster NOT ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC
)
SELECT
    COALESCE(SUM(vhost_count), 0)                                   AS hosts,
    COALESCE(SUM(vm_count), 0)                                      AS vms,
    COALESCE(SUM(cpu_ghz_capacity), 0)                              AS cpu_cap_ghz,
    COALESCE(SUM(cpu_ghz_used), 0)                                  AS cpu_used_ghz,
    COALESCE(SUM(memory_capacity_gb), 0)                            AS mem_cap_gb,
    COALESCE(SUM(memory_used_gb), 0)                                AS mem_used_gb,
    COALESCE(SUM(total_capacity_gb), 0)                             AS stor_cap_gb,
    COALESCE(SUM(total_capacity_gb - total_freespace_gb), 0)        AS stor_used_gb
FROM latest_per_cluster
"""

# --- Hyperconverged Compute utilization stats (VMware non-KM clusters) ---
HYPERCONV_AVG30 = """
SELECT
    COALESCE(AVG(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_avg_pct,
    COALESCE(AVG(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_avg_pct,
    COALESCE(MAX(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_max_pct,
    COALESCE(MAX(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_max_pct,
    COALESCE(MIN(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_min_pct,
    COALESCE(MIN(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_min_pct
FROM public.cluster_metrics
WHERE datacenter ILIKE %s
  AND cluster NOT ILIKE '%%KM%%'
  AND timestamp BETWEEN %s AND %s
"""

# --- Batch Classic Metrics (all DCs in one query) ---
# Params: (dc_list[], pattern_list[], start_ts, end_ts)
BATCH_CLASSIC_METRICS = """
WITH matched AS (
    SELECT c.datacenter, c.cluster, c.timestamp,
           c.vhost_count, c.vm_count,
           c.cpu_ghz_capacity, c.cpu_ghz_used,
           c.memory_capacity_gb, c.memory_used_gb,
           c.total_capacity_gb, c.total_freespace_gb,
           u.dc_code, u.ord
    FROM public.cluster_metrics c
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON c.datacenter ILIKE u.pattern
    WHERE c.cluster ILIKE '%%KM%%'
      AND c.timestamp BETWEEN %s AND %s
),
latest_per_cluster AS (
    SELECT DISTINCT ON (datacenter, cluster) dc_code,
        vhost_count, vm_count,
        cpu_ghz_capacity, cpu_ghz_used,
        memory_capacity_gb, memory_used_gb,
        total_capacity_gb, total_freespace_gb
    FROM matched
    ORDER BY datacenter, cluster, ord, timestamp DESC
)
SELECT
    dc_code,
    COALESCE(SUM(vhost_count), 0)                            AS hosts,
    COALESCE(SUM(vm_count), 0)                               AS vms,
    COALESCE(SUM(cpu_ghz_capacity), 0)                       AS cpu_cap_ghz,
    COALESCE(SUM(cpu_ghz_used), 0)                           AS cpu_used_ghz,
    COALESCE(SUM(memory_capacity_gb), 0)                     AS mem_cap_gb,
    COALESCE(SUM(memory_used_gb), 0)                         AS mem_used_gb,
    COALESCE(SUM(total_capacity_gb), 0)                      AS stor_cap_gb,
    COALESCE(SUM(total_capacity_gb - total_freespace_gb), 0) AS stor_used_gb
FROM latest_per_cluster
GROUP BY dc_code
"""

# --- Batch Hyperconverged Metrics (all DCs in one query) ---
BATCH_HYPERCONV_METRICS = """
WITH matched AS (
    SELECT c.datacenter, c.cluster, c.timestamp,
           c.vhost_count, c.vm_count,
           c.cpu_ghz_capacity, c.cpu_ghz_used,
           c.memory_capacity_gb, c.memory_used_gb,
           c.total_capacity_gb, c.total_freespace_gb,
           u.dc_code, u.ord
    FROM public.cluster_metrics c
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON c.datacenter ILIKE u.pattern
    WHERE c.cluster NOT ILIKE '%%KM%%'
      AND c.timestamp BETWEEN %s AND %s
),
latest_per_cluster AS (
    SELECT DISTINCT ON (datacenter, cluster) dc_code,
        vhost_count, vm_count,
        cpu_ghz_capacity, cpu_ghz_used,
        memory_capacity_gb, memory_used_gb,
        total_capacity_gb, total_freespace_gb
    FROM matched
    ORDER BY datacenter, cluster, ord, timestamp DESC
)
SELECT
    dc_code,
    COALESCE(SUM(vhost_count), 0)                            AS hosts,
    COALESCE(SUM(vm_count), 0)                               AS vms,
    COALESCE(SUM(cpu_ghz_capacity), 0)                       AS cpu_cap_ghz,
    COALESCE(SUM(cpu_ghz_used), 0)                           AS cpu_used_ghz,
    COALESCE(SUM(memory_capacity_gb), 0)                     AS mem_cap_gb,
    COALESCE(SUM(memory_used_gb), 0)                         AS mem_used_gb,
    COALESCE(SUM(total_capacity_gb), 0)                      AS stor_cap_gb,
    COALESCE(SUM(total_capacity_gb - total_freespace_gb), 0) AS stor_used_gb
FROM latest_per_cluster
GROUP BY dc_code
"""

# --- Batch utilization stats for Classic ---
BATCH_CLASSIC_AVG30 = """
WITH matched AS (
    SELECT c.datacenter, c.timestamp,
           c.cpu_ghz_capacity, c.cpu_ghz_used,
           c.memory_capacity_gb, c.memory_used_gb,
           u.dc_code
    FROM public.cluster_metrics c
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON c.datacenter ILIKE u.pattern
    WHERE c.cluster ILIKE '%%KM%%'
      AND c.timestamp BETWEEN %s AND %s
)
SELECT
    dc_code,
    COALESCE(AVG(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_avg_pct,
    COALESCE(AVG(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_avg_pct,
    COALESCE(MAX(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_max_pct,
    COALESCE(MAX(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_max_pct,
    COALESCE(MIN(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_min_pct,
    COALESCE(MIN(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_min_pct
FROM matched
GROUP BY dc_code
"""

# --- Batch utilization stats for Hyperconverged ---
BATCH_HYPERCONV_AVG30 = """
WITH matched AS (
    SELECT c.datacenter, c.timestamp,
           c.cpu_ghz_capacity, c.cpu_ghz_used,
           c.memory_capacity_gb, c.memory_used_gb,
           u.dc_code
    FROM public.cluster_metrics c
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON c.datacenter ILIKE u.pattern
    WHERE c.cluster NOT ILIKE '%%KM%%'
      AND c.timestamp BETWEEN %s AND %s
)
SELECT
    dc_code,
    COALESCE(AVG(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_avg_pct,
    COALESCE(AVG(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_avg_pct,
    COALESCE(MAX(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_max_pct,
    COALESCE(MAX(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_max_pct,
    COALESCE(MIN(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_min_pct,
    COALESCE(MIN(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_min_pct
FROM matched
GROUP BY dc_code
"""

# =============================================================================
# Cluster list and filtered metrics (for DC view cluster selector)
# Params: (dc_pattern, start_ts, end_ts) for list; (dc_pattern, cluster_array, start_ts, end_ts) for filtered
# =============================================================================

CLASSIC_CLUSTER_LIST = """
SELECT DISTINCT cluster
FROM public.cluster_metrics
WHERE datacenter ILIKE %s
  AND cluster ILIKE '%%KM%%'
  AND timestamp BETWEEN %s AND %s
ORDER BY cluster
"""

HYPERCONV_CLUSTER_LIST = """
SELECT DISTINCT cluster
FROM public.cluster_metrics
WHERE datacenter ILIKE %s
  AND cluster NOT ILIKE '%%KM%%'
  AND timestamp BETWEEN %s AND %s
ORDER BY cluster
"""

# Params: (dc_pattern, cluster_array, start_ts, end_ts). cluster_array must be non-empty.
CLASSIC_METRICS_FILTERED = """
WITH latest_per_cluster AS (
    SELECT DISTINCT ON (cluster)
        vhost_count, vm_count,
        cpu_ghz_capacity, cpu_ghz_used,
        memory_capacity_gb, memory_used_gb,
        total_capacity_gb, total_freespace_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster = ANY(%s::text[])
      AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC
)
SELECT
    COALESCE(SUM(vhost_count), 0)                                   AS hosts,
    COALESCE(SUM(vm_count), 0)                                      AS vms,
    COALESCE(SUM(cpu_ghz_capacity), 0)                              AS cpu_cap_ghz,
    COALESCE(SUM(cpu_ghz_used), 0)                                  AS cpu_used_ghz,
    COALESCE(SUM(memory_capacity_gb), 0)                            AS mem_cap_gb,
    COALESCE(SUM(memory_used_gb), 0)                                AS mem_used_gb,
    COALESCE(SUM(total_capacity_gb), 0)                             AS stor_cap_gb,
    COALESCE(SUM(total_capacity_gb - total_freespace_gb), 0)        AS stor_used_gb
FROM latest_per_cluster
"""

CLASSIC_AVG30_FILTERED = """
SELECT
    COALESCE(AVG(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_avg_pct,
    COALESCE(AVG(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_avg_pct,
    COALESCE(MAX(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_max_pct,
    COALESCE(MAX(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_max_pct,
    COALESCE(MIN(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_min_pct,
    COALESCE(MIN(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_min_pct
FROM public.cluster_metrics
WHERE datacenter ILIKE %s
  AND cluster = ANY(%s::text[])
  AND timestamp BETWEEN %s AND %s
"""

HYPERCONV_METRICS_FILTERED = """
WITH latest_per_cluster AS (
    SELECT DISTINCT ON (cluster)
        vhost_count, vm_count,
        cpu_ghz_capacity, cpu_ghz_used,
        memory_capacity_gb, memory_used_gb,
        total_capacity_gb, total_freespace_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster = ANY(%s::text[])
      AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC
)
SELECT
    COALESCE(SUM(vhost_count), 0)                                   AS hosts,
    COALESCE(SUM(vm_count), 0)                                      AS vms,
    COALESCE(SUM(cpu_ghz_capacity), 0)                              AS cpu_cap_ghz,
    COALESCE(SUM(cpu_ghz_used), 0)                                  AS cpu_used_ghz,
    COALESCE(SUM(memory_capacity_gb), 0)                            AS mem_cap_gb,
    COALESCE(SUM(memory_used_gb), 0)                                AS mem_used_gb,
    COALESCE(SUM(total_capacity_gb), 0)                             AS stor_cap_gb,
    COALESCE(SUM(total_capacity_gb - total_freespace_gb), 0)        AS stor_used_gb
FROM latest_per_cluster
"""

HYPERCONV_AVG30_FILTERED = """
SELECT
    COALESCE(AVG(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_avg_pct,
    COALESCE(AVG(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_avg_pct,
    COALESCE(MAX(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_max_pct,
    COALESCE(MAX(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_max_pct,
    COALESCE(MIN(CASE WHEN cpu_ghz_capacity > 0
        THEN 100.0 * cpu_ghz_used / cpu_ghz_capacity END), 0)    AS cpu_min_pct,
    COALESCE(MIN(CASE WHEN memory_capacity_gb > 0
        THEN 100.0 * memory_used_gb / memory_capacity_gb END), 0) AS mem_min_pct
FROM public.cluster_metrics
WHERE datacenter ILIKE %s
  AND cluster = ANY(%s::text[])
  AND timestamp BETWEEN %s AND %s
"""

# --- Memory peak from raw GB sums per timestamp (Capacity Planning max column) ---
CLASSIC_MEM_PEAK_RAW = """
WITH ts_agg AS (
    SELECT timestamp,
           SUM(memory_used_gb) AS used_gb,
           SUM(memory_capacity_gb) AS cap_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    GROUP BY timestamp
)
SELECT COALESCE(used_gb, 0), COALESCE(cap_gb, 0),
       COALESCE(100.0 * used_gb / NULLIF(cap_gb, 0), 0)
FROM ts_agg
WHERE cap_gb > 0
ORDER BY (used_gb / NULLIF(cap_gb, 0)) DESC, used_gb DESC
LIMIT 1
"""

CLASSIC_MEM_PEAK_RAW_FILTERED = """
WITH ts_agg AS (
    SELECT timestamp,
           SUM(memory_used_gb) AS used_gb,
           SUM(memory_capacity_gb) AS cap_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster = ANY(%s::text[])
      AND timestamp BETWEEN %s AND %s
    GROUP BY timestamp
)
SELECT COALESCE(used_gb, 0), COALESCE(cap_gb, 0),
       COALESCE(100.0 * used_gb / NULLIF(cap_gb, 0), 0)
FROM ts_agg
WHERE cap_gb > 0
ORDER BY (used_gb / NULLIF(cap_gb, 0)) DESC, used_gb DESC
LIMIT 1
"""

# Time-series memory average: same ts_agg as peak, AVG(used/cap) across timestamps.
CLASSIC_MEM_AVG_TS_RAW = """
WITH ts_agg AS (
    SELECT timestamp,
           SUM(memory_used_gb) AS used_gb,
           SUM(memory_capacity_gb) AS cap_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    GROUP BY timestamp
)
SELECT COALESCE(AVG(100.0 * used_gb / NULLIF(cap_gb, 0)), 0)
FROM ts_agg
WHERE cap_gb > 0
"""

CLASSIC_MEM_AVG_TS_RAW_FILTERED = """
WITH ts_agg AS (
    SELECT timestamp,
           SUM(memory_used_gb) AS used_gb,
           SUM(memory_capacity_gb) AS cap_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster = ANY(%s::text[])
      AND timestamp BETWEEN %s AND %s
    GROUP BY timestamp
)
SELECT COALESCE(AVG(100.0 * used_gb / NULLIF(cap_gb, 0)), 0)
FROM ts_agg
WHERE cap_gb > 0
"""

HYPERCONV_MEM_PEAK_RAW = """
WITH ts_agg AS (
    SELECT timestamp,
           SUM(memory_used_gb) AS used_gb,
           SUM(memory_capacity_gb) AS cap_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster NOT ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    GROUP BY timestamp
)
SELECT COALESCE(used_gb, 0), COALESCE(cap_gb, 0),
       COALESCE(100.0 * used_gb / NULLIF(cap_gb, 0), 0)
FROM ts_agg
WHERE cap_gb > 0
ORDER BY (used_gb / NULLIF(cap_gb, 0)) DESC, used_gb DESC
LIMIT 1
"""

HYPERCONV_MEM_PEAK_RAW_FILTERED = """
WITH ts_agg AS (
    SELECT timestamp,
           SUM(memory_used_gb) AS used_gb,
           SUM(memory_capacity_gb) AS cap_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster = ANY(%s::text[])
      AND timestamp BETWEEN %s AND %s
    GROUP BY timestamp
)
SELECT COALESCE(used_gb, 0), COALESCE(cap_gb, 0),
       COALESCE(100.0 * used_gb / NULLIF(cap_gb, 0), 0)
FROM ts_agg
WHERE cap_gb > 0
ORDER BY (used_gb / NULLIF(cap_gb, 0)) DESC, used_gb DESC
LIMIT 1
"""

HYPERCONV_MEM_AVG_TS_RAW = """
WITH ts_agg AS (
    SELECT timestamp,
           SUM(memory_used_gb) AS used_gb,
           SUM(memory_capacity_gb) AS cap_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster NOT ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    GROUP BY timestamp
)
SELECT COALESCE(AVG(100.0 * used_gb / NULLIF(cap_gb, 0)), 0)
FROM ts_agg
WHERE cap_gb > 0
"""

HYPERCONV_MEM_AVG_TS_RAW_FILTERED = """
WITH ts_agg AS (
    SELECT timestamp,
           SUM(memory_used_gb) AS used_gb,
           SUM(memory_capacity_gb) AS cap_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster = ANY(%s::text[])
      AND timestamp BETWEEN %s AND %s
    GROUP BY timestamp
)
SELECT COALESCE(AVG(100.0 * used_gb / NULLIF(cap_gb, 0)), 0)
FROM ts_agg
WHERE cap_gb > 0
"""

# =============================================================================
# VM-level storage breakdown (thin-provisioned vs actually used)
# Params: (dc_pattern,)
# Returns: (provisioned_gb, used_gb)
# =============================================================================

CLASSIC_STORAGE_VM = """
WITH latest AS (
    SELECT DISTINCT ON (vmname)
        vmname, provisioned_space_gb, used_space_gb,
        total_cpu_capacity_mhz, total_memory_capacity_gb
    FROM public.vm_metrics
    WHERE datacenter ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY vmname, timestamp DESC
)
SELECT
    COALESCE(SUM(provisioned_space_gb), 0)              AS provisioned_gb,
    COALESCE(SUM(used_space_gb), 0)                     AS used_gb,
    COALESCE(SUM(total_cpu_capacity_mhz / 1000.0), 0)   AS cpu_alloc_ghz,
    COALESCE(SUM(total_memory_capacity_gb), 0)          AS mem_alloc_gb
FROM latest
"""

HYPERCONV_VMWARE_STORAGE_VM = """
WITH latest AS (
    SELECT DISTINCT ON (vmname)
        vmname, provisioned_space_gb, used_space_gb,
        total_cpu_capacity_mhz, total_memory_capacity_gb
    FROM public.vm_metrics
    WHERE datacenter ILIKE %s
      AND cluster NOT ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY vmname, timestamp DESC
)
SELECT
    COALESCE(SUM(provisioned_space_gb), 0)              AS provisioned_gb,
    COALESCE(SUM(used_space_gb), 0)                     AS used_gb,
    COALESCE(SUM(total_cpu_capacity_mhz / 1000.0), 0)   AS cpu_alloc_ghz,
    COALESCE(SUM(total_memory_capacity_gb), 0)          AS mem_alloc_gb
FROM latest
"""

# =============================================================================
# NetBox host CPU strings + VM allocation rows (Python-side GHz conversion)
# =============================================================================

NETBOX_HOST_CPU_STRINGS = """
SELECT DISTINCT ON (name)
    name,
    custom_fields->'CPU'->>0 AS cpu_cf,
    cpu AS cpu_col
FROM public.discovery_netbox_inventory_device
WHERE status_value = 'active'
ORDER BY name, collection_time DESC NULLS LAST
"""

# Params: (dc_pattern, start_ts, end_ts, cluster_filter[], cluster_filter[])
# Empty cluster_filter[] = all clusters in scope.
CLASSIC_VM_ALLOCATION_ROWS = """
WITH latest AS (
    SELECT DISTINCT ON (vmname)
        vmhost,
        number_of_cpus,
        total_memory_capacity_gb,
        provisioned_space_gb,
        used_space_gb
    FROM public.vm_metrics
    WHERE datacenter ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND LEFT(vmname, 1) <> '_'
      AND timestamp BETWEEN %s AND %s
      AND (cardinality(%s::text[]) = 0 OR cluster = ANY(%s::text[]))
    ORDER BY vmname, timestamp DESC
)
SELECT
    vmhost,
    COALESCE(number_of_cpus, 0),
    COALESCE(total_memory_capacity_gb, 0),
    COALESCE(provisioned_space_gb, 0),
    COALESCE(used_space_gb, 0)
FROM latest
"""

HYPERCONV_VMWARE_VM_ALLOCATION_ROWS = """
WITH latest AS (
    SELECT DISTINCT ON (vmname)
        vmhost,
        number_of_cpus,
        total_memory_capacity_gb,
        provisioned_space_gb,
        used_space_gb
    FROM public.vm_metrics
    WHERE datacenter ILIKE %s
      AND cluster NOT ILIKE '%%KM%%'
      AND LEFT(vmname, 1) <> '_'
      AND timestamp BETWEEN %s AND %s
      AND (cardinality(%s::text[]) = 0 OR cluster = ANY(%s::text[]))
    ORDER BY vmname, timestamp DESC
)
SELECT
    vmhost,
    COALESCE(number_of_cpus, 0),
    COALESCE(total_memory_capacity_gb, 0),
    COALESCE(provisioned_space_gb, 0),
    COALESCE(used_space_gb, 0)
FROM latest
"""

# =============================================================================
# Host-level compute rows (vmhost_metrics) — per-host capacity/usage for the
# DC view Hosts panel and the host-based sellable computation (ADR: host-based
# CRM calculation). Latest snapshot per host within the time range.
# Params: (dc_pattern, cluster_filter[], cluster_filter[], start_ts, end_ts)
# Empty cluster_filter[] = all KM clusters in scope.
# =============================================================================

CLASSIC_HOST_ROWS = """
SELECT DISTINCT ON (vmhost)
    vmhost,
    cluster,
    COALESCE(cpu_ghz_capacity, 0)   AS cpu_cap_ghz,
    COALESCE(cpu_ghz_used, 0)       AS cpu_used_ghz,
    COALESCE(memory_capacity_gb, 0) AS mem_cap_gb,
    COALESCE(memory_used_gb, 0)     AS mem_used_gb
FROM public.vmhost_metrics
WHERE datacenter ILIKE %s
  AND cluster ILIKE '%%KM%%'
  AND (cardinality(%s::text[]) = 0 OR cluster = ANY(%s::text[]))
  AND "timestamp" BETWEEN %s AND %s
ORDER BY vmhost, "timestamp" DESC
"""

# Per-host RAM peak within time range (classic KM).
# Params: (dc_pattern, cluster_filter[], cluster_filter[], start_ts, end_ts)
CLASSIC_HOST_MEM_PEAK = """
WITH ts_agg AS (
    SELECT vmhost,
           "timestamp",
           COALESCE(memory_used_gb, 0)     AS used_gb,
           COALESCE(memory_capacity_gb, 0) AS cap_gb
    FROM public.vmhost_metrics
    WHERE datacenter ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND (cardinality(%s::text[]) = 0 OR cluster = ANY(%s::text[]))
      AND "timestamp" BETWEEN %s AND %s
)
SELECT DISTINCT ON (vmhost)
    vmhost,
    used_gb,
    cap_gb,
    COALESCE(100.0 * used_gb / NULLIF(cap_gb, 0), 0) AS util_pct
FROM ts_agg
WHERE cap_gb > 0
ORDER BY vmhost, (used_gb / NULLIF(cap_gb, 0)) DESC, used_gb DESC
"""

# Per-host VM allocation aggregate (vCPU / RAM / storage provisioned by VMs on
# each host). Sales CPU rule: 1 vCPU = 1 GHz (applied in Python).
# Params: (dc_pattern, start_ts, end_ts, cluster_filter[], cluster_filter[])
CLASSIC_HOST_VM_ALLOCATION = """
WITH latest AS (
    SELECT DISTINCT ON (vmname)
        vmhost,
        number_of_cpus,
        total_memory_capacity_gb,
        provisioned_space_gb,
        used_space_gb
    FROM public.vm_metrics
    WHERE datacenter ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND LEFT(vmname, 1) <> '_'
      AND timestamp BETWEEN %s AND %s
      AND (cardinality(%s::text[]) = 0 OR cluster = ANY(%s::text[]))
    ORDER BY vmname, timestamp DESC
)
SELECT
    vmhost,
    COUNT(*)                                    AS vm_count,
    COALESCE(SUM(number_of_cpus), 0)            AS vcpu_total,
    COALESCE(SUM(total_memory_capacity_gb), 0)  AS mem_alloc_gb,
    COALESCE(SUM(provisioned_space_gb), 0)      AS stor_provisioned_gb,
    COALESCE(SUM(used_space_gb), 0)             AS stor_used_gb
FROM latest
GROUP BY vmhost
"""
