# VMware-primary, Nutanix-fallback CPU/RAM merge for Classic (KM) and Hyperconverged.
#
# Per cluster: use VMware cluster_metrics when a row exists AND
# (cpu_ghz_capacity > 0 OR memory_capacity_gb > 0); otherwise Nutanix nutanix_cluster_metrics.
# hosts/vms/stor slots in metrics rows come from VMware only (storage patched separately).
#
# Nutanix unit conversions (match dc_service.get_hyperconv_metrics_filtered):
#   CPU cap: total_cpu_capacity Hz -> GHz (/ 1e9)
#   CPU used: (cpu_usage_avg * total_cpu_capacity) / 1e6 Hz -> GHz (/ 1e9)
#   RAM cap/used: bytes -> GB (/ 1024^3)

_VMWARE_PRIORITY = """
    (COALESCE(v.cpu_ghz_capacity, 0) > 0 OR COALESCE(v.memory_capacity_gb, 0) > 0)
"""

_NUTANIX_LATEST_CORE = """
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        total_cpu_capacity,
        (cpu_usage_avg * total_cpu_capacity) / 1000000.0 AS cpu_used_hz,
        total_memory_capacity,
        ((memory_usage_avg / 1000.0) * total_memory_capacity) / 1000.0 AS used_memory_bytes
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      {nutanix_extra_filter}
      AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
"""

_NUTANIX_LATEST_SELECT = """
    SELECT
        cluster_name,
        total_cpu_capacity / 1000000000.0 AS cpu_cap_ghz,
        cpu_used_hz / 1000000000.0 AS cpu_used_ghz,
        total_memory_capacity / 1073741824.0 AS mem_cap_gb,
        used_memory_bytes / 1073741824.0 AS mem_used_gb
    FROM nutanix_latest_raw
"""

# --- Individual: Classic (KM) ---

CLASSIC_CPU_MEM_MERGED = f"""
WITH vmware_latest AS (
    SELECT DISTINCT ON (cluster)
        cluster AS cluster_name,
        vhost_count,
        vm_count,
        cpu_ghz_capacity,
        cpu_ghz_used,
        memory_capacity_gb,
        memory_used_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC
),
nutanix_latest_raw AS (
{_NUTANIX_LATEST_CORE.format(nutanix_extra_filter="AND cluster_name ILIKE '%%KM%%'")}
),
nutanix_latest AS (
{_NUTANIX_LATEST_SELECT}
),
all_clusters AS (
    SELECT cluster_name FROM vmware_latest
    UNION
    SELECT cluster_name FROM nutanix_latest
),
merged AS (
    SELECT
        ac.cluster_name,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_capacity, 0) ELSE COALESCE(n.cpu_cap_ghz, 0) END AS cpu_cap_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_used, 0) ELSE COALESCE(n.cpu_used_ghz, 0) END AS cpu_used_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_capacity_gb, 0) ELSE COALESCE(n.mem_cap_gb, 0) END AS mem_cap_gb,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_used_gb, 0) ELSE COALESCE(n.mem_used_gb, 0) END AS mem_used_gb
    FROM all_clusters ac
    LEFT JOIN vmware_latest v ON v.cluster_name = ac.cluster_name
    LEFT JOIN nutanix_latest n ON n.cluster_name = ac.cluster_name
)
SELECT
    COALESCE((SELECT SUM(vhost_count) FROM vmware_latest), 0) AS hosts,
    COALESCE((SELECT SUM(vm_count) FROM vmware_latest), 0) AS vms,
    COALESCE(SUM(cpu_cap_ghz), 0) AS cpu_cap_ghz,
    COALESCE(SUM(cpu_used_ghz), 0) AS cpu_used_ghz,
    COALESCE(SUM(mem_cap_gb), 0) AS mem_cap_gb,
    COALESCE(SUM(mem_used_gb), 0) AS mem_used_gb,
    0::numeric AS stor_cap_gb,
    0::numeric AS stor_used_gb
FROM merged
"""

CLASSIC_AVG30_MERGED = f"""
WITH vmware_latest AS (
    SELECT DISTINCT ON (cluster)
        cluster AS cluster_name,
        cpu_ghz_capacity,
        cpu_ghz_used,
        memory_capacity_gb,
        memory_used_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC
),
nutanix_latest_raw AS (
{_NUTANIX_LATEST_CORE.format(nutanix_extra_filter="AND cluster_name ILIKE '%%KM%%'")}
),
nutanix_latest AS (
{_NUTANIX_LATEST_SELECT}
),
all_clusters AS (
    SELECT cluster_name FROM vmware_latest
    UNION
    SELECT cluster_name FROM nutanix_latest
),
merged AS (
    SELECT
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_capacity, 0) ELSE COALESCE(n.cpu_cap_ghz, 0) END AS cpu_cap_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_used, 0) ELSE COALESCE(n.cpu_used_ghz, 0) END AS cpu_used_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_capacity_gb, 0) ELSE COALESCE(n.mem_cap_gb, 0) END AS mem_cap_gb,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_used_gb, 0) ELSE COALESCE(n.mem_used_gb, 0) END AS mem_used_gb
    FROM all_clusters ac
    LEFT JOIN vmware_latest v ON v.cluster_name = ac.cluster_name
    LEFT JOIN nutanix_latest n ON n.cluster_name = ac.cluster_name
)
SELECT
    COALESCE(AVG(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_avg_pct,
    COALESCE(AVG(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_avg_pct,
    COALESCE(MAX(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_max_pct,
    COALESCE(MAX(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_max_pct,
    COALESCE(MIN(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_min_pct,
    COALESCE(MIN(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_min_pct
FROM merged
"""

# --- Individual: Hyperconverged (non-KM VMware + Nutanix fallback) ---

HYPERCONV_CPU_MEM_MERGED = f"""
WITH vmware_latest AS (
    SELECT DISTINCT ON (cluster)
        cluster AS cluster_name,
        vhost_count,
        vm_count,
        cpu_ghz_capacity,
        cpu_ghz_used,
        memory_capacity_gb,
        memory_used_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster NOT ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC
),
nutanix_latest_raw AS (
{_NUTANIX_LATEST_CORE.format(nutanix_extra_filter="")}
),
nutanix_latest AS (
{_NUTANIX_LATEST_SELECT}
),
all_clusters AS (
    SELECT cluster_name FROM vmware_latest
    UNION
    SELECT cluster_name FROM nutanix_latest
),
merged AS (
    SELECT
        ac.cluster_name,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_capacity, 0) ELSE COALESCE(n.cpu_cap_ghz, 0) END AS cpu_cap_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_used, 0) ELSE COALESCE(n.cpu_used_ghz, 0) END AS cpu_used_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_capacity_gb, 0) ELSE COALESCE(n.mem_cap_gb, 0) END AS mem_cap_gb,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_used_gb, 0) ELSE COALESCE(n.mem_used_gb, 0) END AS mem_used_gb
    FROM all_clusters ac
    LEFT JOIN vmware_latest v ON v.cluster_name = ac.cluster_name
    LEFT JOIN nutanix_latest n ON n.cluster_name = ac.cluster_name
)
SELECT
    COALESCE((SELECT SUM(vhost_count) FROM vmware_latest), 0) AS hosts,
    COALESCE((SELECT SUM(vm_count) FROM vmware_latest), 0) AS vms,
    COALESCE(SUM(cpu_cap_ghz), 0) AS cpu_cap_ghz,
    COALESCE(SUM(cpu_used_ghz), 0) AS cpu_used_ghz,
    COALESCE(SUM(mem_cap_gb), 0) AS mem_cap_gb,
    COALESCE(SUM(mem_used_gb), 0) AS mem_used_gb,
    0::numeric AS stor_cap_gb,
    0::numeric AS stor_used_gb
FROM merged
"""

HYPERCONV_AVG30_MERGED = f"""
WITH vmware_latest AS (
    SELECT DISTINCT ON (cluster)
        cluster AS cluster_name,
        cpu_ghz_capacity,
        cpu_ghz_used,
        memory_capacity_gb,
        memory_used_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster NOT ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC
),
nutanix_latest_raw AS (
{_NUTANIX_LATEST_CORE.format(nutanix_extra_filter="")}
),
nutanix_latest AS (
{_NUTANIX_LATEST_SELECT}
),
all_clusters AS (
    SELECT cluster_name FROM vmware_latest
    UNION
    SELECT cluster_name FROM nutanix_latest
),
merged AS (
    SELECT
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_capacity, 0) ELSE COALESCE(n.cpu_cap_ghz, 0) END AS cpu_cap_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_used, 0) ELSE COALESCE(n.cpu_used_ghz, 0) END AS cpu_used_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_capacity_gb, 0) ELSE COALESCE(n.mem_cap_gb, 0) END AS mem_cap_gb,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_used_gb, 0) ELSE COALESCE(n.mem_used_gb, 0) END AS mem_used_gb
    FROM all_clusters ac
    LEFT JOIN vmware_latest v ON v.cluster_name = ac.cluster_name
    LEFT JOIN nutanix_latest n ON n.cluster_name = ac.cluster_name
)
SELECT
    COALESCE(AVG(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_avg_pct,
    COALESCE(AVG(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_avg_pct,
    COALESCE(MAX(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_max_pct,
    COALESCE(MAX(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_max_pct,
    COALESCE(MIN(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_min_pct,
    COALESCE(MIN(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_min_pct
FROM merged
"""

# --- Filtered: Classic (selected VMware KM clusters + Nutanix fallback) ---
# Params: (dc_wc, cluster_array, dc_code, cluster_array, start_ts, end_ts)

CLASSIC_CPU_MEM_MERGED_FILTERED = f"""
WITH vmware_latest AS (
    SELECT DISTINCT ON (cluster)
        cluster AS cluster_name,
        vhost_count,
        vm_count,
        cpu_ghz_capacity,
        cpu_ghz_used,
        memory_capacity_gb,
        memory_used_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster = ANY(%s::text[])
      AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC
),
nutanix_latest_raw AS (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        total_cpu_capacity,
        (cpu_usage_avg * total_cpu_capacity) / 1000000.0 AS cpu_used_hz,
        total_memory_capacity,
        ((memory_usage_avg / 1000.0) * total_memory_capacity) / 1000.0 AS used_memory_bytes
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND cluster_name = ANY(%s::text[])
      AND cluster_name ILIKE '%%KM%%'
      AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
),
nutanix_latest AS (
{_NUTANIX_LATEST_SELECT}
),
all_clusters AS (
    SELECT unnest(%s::text[]) AS cluster_name
),
merged AS (
    SELECT
        ac.cluster_name,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_capacity, 0) ELSE COALESCE(n.cpu_cap_ghz, 0) END AS cpu_cap_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_used, 0) ELSE COALESCE(n.cpu_used_ghz, 0) END AS cpu_used_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_capacity_gb, 0) ELSE COALESCE(n.mem_cap_gb, 0) END AS mem_cap_gb,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_used_gb, 0) ELSE COALESCE(n.mem_used_gb, 0) END AS mem_used_gb
    FROM all_clusters ac
    LEFT JOIN vmware_latest v ON v.cluster_name = ac.cluster_name
    LEFT JOIN nutanix_latest n ON n.cluster_name = ac.cluster_name
)
SELECT
    COALESCE((SELECT SUM(vhost_count) FROM vmware_latest), 0) AS hosts,
    COALESCE((SELECT SUM(vm_count) FROM vmware_latest), 0) AS vms,
    COALESCE(SUM(cpu_cap_ghz), 0) AS cpu_cap_ghz,
    COALESCE(SUM(cpu_used_ghz), 0) AS cpu_used_ghz,
    COALESCE(SUM(mem_cap_gb), 0) AS mem_cap_gb,
    COALESCE(SUM(mem_used_gb), 0) AS mem_used_gb,
    0::numeric AS stor_cap_gb,
    0::numeric AS stor_used_gb
FROM merged
"""

CLASSIC_AVG30_MERGED_FILTERED = f"""
WITH vmware_latest AS (
    SELECT DISTINCT ON (cluster)
        cluster AS cluster_name,
        cpu_ghz_capacity,
        cpu_ghz_used,
        memory_capacity_gb,
        memory_used_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster = ANY(%s::text[])
      AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC
),
nutanix_latest_raw AS (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        total_cpu_capacity,
        (cpu_usage_avg * total_cpu_capacity) / 1000000.0 AS cpu_used_hz,
        total_memory_capacity,
        ((memory_usage_avg / 1000.0) * total_memory_capacity) / 1000.0 AS used_memory_bytes
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND cluster_name = ANY(%s::text[])
      AND cluster_name ILIKE '%%KM%%'
      AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
),
nutanix_latest AS (
{_NUTANIX_LATEST_SELECT}
),
all_clusters AS (
    SELECT unnest(%s::text[]) AS cluster_name
),
merged AS (
    SELECT
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_capacity, 0) ELSE COALESCE(n.cpu_cap_ghz, 0) END AS cpu_cap_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_used, 0) ELSE COALESCE(n.cpu_used_ghz, 0) END AS cpu_used_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_capacity_gb, 0) ELSE COALESCE(n.mem_cap_gb, 0) END AS mem_cap_gb,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_used_gb, 0) ELSE COALESCE(n.mem_used_gb, 0) END AS mem_used_gb
    FROM all_clusters ac
    LEFT JOIN vmware_latest v ON v.cluster_name = ac.cluster_name
    LEFT JOIN nutanix_latest n ON n.cluster_name = ac.cluster_name
)
SELECT
    COALESCE(AVG(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_avg_pct,
    COALESCE(AVG(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_avg_pct,
    COALESCE(MAX(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_max_pct,
    COALESCE(MAX(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_max_pct,
    COALESCE(MIN(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_min_pct,
    COALESCE(MIN(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_min_pct
FROM merged
"""

# --- Filtered: Hyperconverged (Nutanix cluster names; VMware fallback when present) ---
# Params: (dc_wc, cluster_array, dc_code, cluster_array, start_ts, end_ts, cluster_array)

HYPERCONV_CPU_MEM_MERGED_FILTERED = f"""
WITH vmware_latest AS (
    SELECT DISTINCT ON (cluster)
        cluster AS cluster_name,
        vhost_count,
        vm_count,
        cpu_ghz_capacity,
        cpu_ghz_used,
        memory_capacity_gb,
        memory_used_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster = ANY(%s::text[])
      AND cluster NOT ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC
),
nutanix_latest_raw AS (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        total_cpu_capacity,
        (cpu_usage_avg * total_cpu_capacity) / 1000000.0 AS cpu_used_hz,
        total_memory_capacity,
        ((memory_usage_avg / 1000.0) * total_memory_capacity) / 1000.0 AS used_memory_bytes
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND cluster_name = ANY(%s::text[])
      AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
),
nutanix_latest AS (
{_NUTANIX_LATEST_SELECT}
),
all_clusters AS (
    SELECT unnest(%s::text[]) AS cluster_name
),
merged AS (
    SELECT
        ac.cluster_name,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_capacity, 0) ELSE COALESCE(n.cpu_cap_ghz, 0) END AS cpu_cap_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_used, 0) ELSE COALESCE(n.cpu_used_ghz, 0) END AS cpu_used_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_capacity_gb, 0) ELSE COALESCE(n.mem_cap_gb, 0) END AS mem_cap_gb,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_used_gb, 0) ELSE COALESCE(n.mem_used_gb, 0) END AS mem_used_gb
    FROM all_clusters ac
    LEFT JOIN vmware_latest v ON v.cluster_name = ac.cluster_name
    LEFT JOIN nutanix_latest n ON n.cluster_name = ac.cluster_name
)
SELECT
    COALESCE((SELECT SUM(vhost_count) FROM vmware_latest), 0) AS hosts,
    COALESCE((SELECT SUM(vm_count) FROM vmware_latest), 0) AS vms,
    COALESCE(SUM(cpu_cap_ghz), 0) AS cpu_cap_ghz,
    COALESCE(SUM(cpu_used_ghz), 0) AS cpu_used_ghz,
    COALESCE(SUM(mem_cap_gb), 0) AS mem_cap_gb,
    COALESCE(SUM(mem_used_gb), 0) AS mem_used_gb,
    0::numeric AS stor_cap_gb,
    0::numeric AS stor_used_gb
FROM merged
"""

HYPERCONV_AVG30_MERGED_FILTERED = f"""
WITH vmware_latest AS (
    SELECT DISTINCT ON (cluster)
        cluster AS cluster_name,
        cpu_ghz_capacity,
        cpu_ghz_used,
        memory_capacity_gb,
        memory_used_gb
    FROM public.cluster_metrics
    WHERE datacenter ILIKE %s
      AND cluster = ANY(%s::text[])
      AND cluster NOT ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY cluster, timestamp DESC
),
nutanix_latest_raw AS (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        total_cpu_capacity,
        (cpu_usage_avg * total_cpu_capacity) / 1000000.0 AS cpu_used_hz,
        total_memory_capacity,
        ((memory_usage_avg / 1000.0) * total_memory_capacity) / 1000.0 AS used_memory_bytes
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name LIKE ('%%' || %s || '%%')
      AND cluster_name = ANY(%s::text[])
      AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
),
nutanix_latest AS (
{_NUTANIX_LATEST_SELECT}
),
all_clusters AS (
    SELECT unnest(%s::text[]) AS cluster_name
),
merged AS (
    SELECT
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_capacity, 0) ELSE COALESCE(n.cpu_cap_ghz, 0) END AS cpu_cap_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_used, 0) ELSE COALESCE(n.cpu_used_ghz, 0) END AS cpu_used_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_capacity_gb, 0) ELSE COALESCE(n.mem_cap_gb, 0) END AS mem_cap_gb,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_used_gb, 0) ELSE COALESCE(n.mem_used_gb, 0) END AS mem_used_gb
    FROM all_clusters ac
    LEFT JOIN vmware_latest v ON v.cluster_name = ac.cluster_name
    LEFT JOIN nutanix_latest n ON n.cluster_name = ac.cluster_name
)
SELECT
    COALESCE(AVG(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_avg_pct,
    COALESCE(AVG(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_avg_pct,
    COALESCE(MAX(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_max_pct,
    COALESCE(MAX(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_max_pct,
    COALESCE(MIN(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_min_pct,
    COALESCE(MIN(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_min_pct
FROM merged
"""

# --- Batch queries (params: dc_list[], pattern_list[], start_ts, end_ts) ---

BATCH_CLASSIC_CPU_MEM_MERGED = f"""
WITH vmware_matched AS (
    SELECT c.datacenter, c.cluster, c.timestamp,
           c.vhost_count, c.vm_count,
           c.cpu_ghz_capacity, c.cpu_ghz_used,
           c.memory_capacity_gb, c.memory_used_gb,
           u.dc_code, u.ord
    FROM public.cluster_metrics c
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON c.datacenter ILIKE u.pattern
    WHERE c.cluster ILIKE '%%KM%%'
      AND c.timestamp BETWEEN %s AND %s
),
vmware_latest AS (
    SELECT DISTINCT ON (dc_code, cluster)
        dc_code, cluster AS cluster_name,
        vhost_count, vm_count,
        cpu_ghz_capacity, cpu_ghz_used,
        memory_capacity_gb, memory_used_gb
    FROM vmware_matched
    ORDER BY dc_code, cluster, ord, timestamp DESC
),
nutanix_matched AS (
    SELECT n.cluster_name, n.collection_time,
           n.total_cpu_capacity,
           (n.cpu_usage_avg * n.total_cpu_capacity) / 1000000.0 AS cpu_used_hz,
           n.total_memory_capacity,
           ((n.memory_usage_avg / 1000.0) * n.total_memory_capacity) / 1000.0 AS used_memory_bytes,
           u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.cluster_name ILIKE '%%KM%%'
      AND n.collection_time BETWEEN %s AND %s
),
nutanix_latest AS (
    SELECT DISTINCT ON (dc_code, cluster_name)
        dc_code, cluster_name,
        total_cpu_capacity / 1000000000.0 AS cpu_cap_ghz,
        cpu_used_hz / 1000000000.0 AS cpu_used_ghz,
        total_memory_capacity / 1073741824.0 AS mem_cap_gb,
        used_memory_bytes / 1073741824.0 AS mem_used_gb
    FROM nutanix_matched
    ORDER BY dc_code, cluster_name, ord, collection_time DESC
),
all_clusters AS (
    SELECT dc_code, cluster_name FROM vmware_latest
    UNION
    SELECT dc_code, cluster_name FROM nutanix_latest
),
merged AS (
    SELECT
        ac.dc_code,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_capacity, 0) ELSE COALESCE(n.cpu_cap_ghz, 0) END AS cpu_cap_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_used, 0) ELSE COALESCE(n.cpu_used_ghz, 0) END AS cpu_used_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_capacity_gb, 0) ELSE COALESCE(n.mem_cap_gb, 0) END AS mem_cap_gb,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_used_gb, 0) ELSE COALESCE(n.mem_used_gb, 0) END AS mem_used_gb
    FROM all_clusters ac
    LEFT JOIN vmware_latest v ON v.dc_code = ac.dc_code AND v.cluster_name = ac.cluster_name
    LEFT JOIN nutanix_latest n ON n.dc_code = ac.dc_code AND n.cluster_name = ac.cluster_name
),
vmware_totals AS (
    SELECT dc_code,
        COALESCE(SUM(vhost_count), 0) AS hosts,
        COALESCE(SUM(vm_count), 0) AS vms
    FROM vmware_latest
    GROUP BY dc_code
)
SELECT
    m.dc_code,
    COALESCE(wt.hosts, 0) AS hosts,
    COALESCE(wt.vms, 0) AS vms,
    COALESCE(SUM(m.cpu_cap_ghz), 0) AS cpu_cap_ghz,
    COALESCE(SUM(m.cpu_used_ghz), 0) AS cpu_used_ghz,
    COALESCE(SUM(m.mem_cap_gb), 0) AS mem_cap_gb,
    COALESCE(SUM(m.mem_used_gb), 0) AS mem_used_gb,
    0::numeric AS stor_cap_gb,
    0::numeric AS stor_used_gb
FROM merged m
LEFT JOIN vmware_totals wt ON wt.dc_code = m.dc_code
GROUP BY m.dc_code, wt.hosts, wt.vms
"""

BATCH_CLASSIC_AVG30_MERGED = f"""
WITH vmware_matched AS (
    SELECT c.cluster, c.timestamp,
           c.cpu_ghz_capacity, c.cpu_ghz_used,
           c.memory_capacity_gb, c.memory_used_gb,
           u.dc_code, u.ord
    FROM public.cluster_metrics c
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON c.datacenter ILIKE u.pattern
    WHERE c.cluster ILIKE '%%KM%%'
      AND c.timestamp BETWEEN %s AND %s
),
vmware_latest AS (
    SELECT DISTINCT ON (dc_code, cluster)
        dc_code, cluster AS cluster_name,
        cpu_ghz_capacity, cpu_ghz_used,
        memory_capacity_gb, memory_used_gb
    FROM vmware_matched
    ORDER BY dc_code, cluster, ord, timestamp DESC
),
nutanix_matched AS (
    SELECT n.cluster_name, n.collection_time,
           n.total_cpu_capacity,
           (n.cpu_usage_avg * n.total_cpu_capacity) / 1000000.0 AS cpu_used_hz,
           n.total_memory_capacity,
           ((n.memory_usage_avg / 1000.0) * n.total_memory_capacity) / 1000.0 AS used_memory_bytes,
           u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.cluster_name ILIKE '%%KM%%'
      AND n.collection_time BETWEEN %s AND %s
),
nutanix_latest AS (
    SELECT DISTINCT ON (dc_code, cluster_name)
        dc_code, cluster_name,
        total_cpu_capacity / 1000000000.0 AS cpu_cap_ghz,
        cpu_used_hz / 1000000000.0 AS cpu_used_ghz,
        total_memory_capacity / 1073741824.0 AS mem_cap_gb,
        used_memory_bytes / 1073741824.0 AS mem_used_gb
    FROM nutanix_matched
    ORDER BY dc_code, cluster_name, ord, collection_time DESC
),
all_clusters AS (
    SELECT dc_code, cluster_name FROM vmware_latest
    UNION
    SELECT dc_code, cluster_name FROM nutanix_latest
),
merged AS (
    SELECT
        ac.dc_code,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_capacity, 0) ELSE COALESCE(n.cpu_cap_ghz, 0) END AS cpu_cap_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_used, 0) ELSE COALESCE(n.cpu_used_ghz, 0) END AS cpu_used_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_capacity_gb, 0) ELSE COALESCE(n.mem_cap_gb, 0) END AS mem_cap_gb,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_used_gb, 0) ELSE COALESCE(n.mem_used_gb, 0) END AS mem_used_gb
    FROM all_clusters ac
    LEFT JOIN vmware_latest v ON v.dc_code = ac.dc_code AND v.cluster_name = ac.cluster_name
    LEFT JOIN nutanix_latest n ON n.dc_code = ac.dc_code AND n.cluster_name = ac.cluster_name
)
SELECT
    dc_code,
    COALESCE(AVG(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_avg_pct,
    COALESCE(AVG(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_avg_pct,
    COALESCE(MAX(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_max_pct,
    COALESCE(MAX(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_max_pct,
    COALESCE(MIN(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_min_pct,
    COALESCE(MIN(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_min_pct
FROM merged
GROUP BY dc_code
"""

BATCH_HYPERCONV_CPU_MEM_MERGED = f"""
WITH vmware_matched AS (
    SELECT c.datacenter, c.cluster, c.timestamp,
           c.vhost_count, c.vm_count,
           c.cpu_ghz_capacity, c.cpu_ghz_used,
           c.memory_capacity_gb, c.memory_used_gb,
           u.dc_code, u.ord
    FROM public.cluster_metrics c
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON c.datacenter ILIKE u.pattern
    WHERE c.cluster NOT ILIKE '%%KM%%'
      AND c.timestamp BETWEEN %s AND %s
),
vmware_latest AS (
    SELECT DISTINCT ON (dc_code, cluster)
        dc_code, cluster AS cluster_name,
        vhost_count, vm_count,
        cpu_ghz_capacity, cpu_ghz_used,
        memory_capacity_gb, memory_used_gb
    FROM vmware_matched
    ORDER BY dc_code, cluster, ord, timestamp DESC
),
nutanix_matched AS (
    SELECT n.cluster_name, n.collection_time,
           n.total_cpu_capacity,
           (n.cpu_usage_avg * n.total_cpu_capacity) / 1000000.0 AS cpu_used_hz,
           n.total_memory_capacity,
           ((n.memory_usage_avg / 1000.0) * n.total_memory_capacity) / 1000.0 AS used_memory_bytes,
           u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.collection_time BETWEEN %s AND %s
),
nutanix_latest AS (
    SELECT DISTINCT ON (dc_code, cluster_name)
        dc_code, cluster_name,
        total_cpu_capacity / 1000000000.0 AS cpu_cap_ghz,
        cpu_used_hz / 1000000000.0 AS cpu_used_ghz,
        total_memory_capacity / 1073741824.0 AS mem_cap_gb,
        used_memory_bytes / 1073741824.0 AS mem_used_gb
    FROM nutanix_matched
    ORDER BY dc_code, cluster_name, ord, collection_time DESC
),
all_clusters AS (
    SELECT dc_code, cluster_name FROM vmware_latest
    UNION
    SELECT dc_code, cluster_name FROM nutanix_latest
),
merged AS (
    SELECT
        ac.dc_code,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_capacity, 0) ELSE COALESCE(n.cpu_cap_ghz, 0) END AS cpu_cap_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_used, 0) ELSE COALESCE(n.cpu_used_ghz, 0) END AS cpu_used_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_capacity_gb, 0) ELSE COALESCE(n.mem_cap_gb, 0) END AS mem_cap_gb,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_used_gb, 0) ELSE COALESCE(n.mem_used_gb, 0) END AS mem_used_gb
    FROM all_clusters ac
    LEFT JOIN vmware_latest v ON v.dc_code = ac.dc_code AND v.cluster_name = ac.cluster_name
    LEFT JOIN nutanix_latest n ON n.dc_code = ac.dc_code AND n.cluster_name = ac.cluster_name
),
vmware_totals AS (
    SELECT dc_code,
        COALESCE(SUM(vhost_count), 0) AS hosts,
        COALESCE(SUM(vm_count), 0) AS vms
    FROM vmware_latest
    GROUP BY dc_code
)
SELECT
    m.dc_code,
    COALESCE(wt.hosts, 0) AS hosts,
    COALESCE(wt.vms, 0) AS vms,
    COALESCE(SUM(m.cpu_cap_ghz), 0) AS cpu_cap_ghz,
    COALESCE(SUM(m.cpu_used_ghz), 0) AS cpu_used_ghz,
    COALESCE(SUM(m.mem_cap_gb), 0) AS mem_cap_gb,
    COALESCE(SUM(m.mem_used_gb), 0) AS mem_used_gb,
    0::numeric AS stor_cap_gb,
    0::numeric AS stor_used_gb
FROM merged m
LEFT JOIN vmware_totals wt ON wt.dc_code = m.dc_code
GROUP BY m.dc_code, wt.hosts, wt.vms
"""

BATCH_HYPERCONV_AVG30_MERGED = f"""
WITH vmware_matched AS (
    SELECT c.cluster, c.timestamp,
           c.cpu_ghz_capacity, c.cpu_ghz_used,
           c.memory_capacity_gb, c.memory_used_gb,
           u.dc_code, u.ord
    FROM public.cluster_metrics c
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON c.datacenter ILIKE u.pattern
    WHERE c.cluster NOT ILIKE '%%KM%%'
      AND c.timestamp BETWEEN %s AND %s
),
vmware_latest AS (
    SELECT DISTINCT ON (dc_code, cluster)
        dc_code, cluster AS cluster_name,
        cpu_ghz_capacity, cpu_ghz_used,
        memory_capacity_gb, memory_used_gb
    FROM vmware_matched
    ORDER BY dc_code, cluster, ord, timestamp DESC
),
nutanix_matched AS (
    SELECT n.cluster_name, n.collection_time,
           n.total_cpu_capacity,
           (n.cpu_usage_avg * n.total_cpu_capacity) / 1000000.0 AS cpu_used_hz,
           n.total_memory_capacity,
           ((n.memory_usage_avg / 1000.0) * n.total_memory_capacity) / 1000.0 AS used_memory_bytes,
           u.dc_code, u.ord
    FROM public.nutanix_cluster_metrics n
    INNER JOIN unnest(%s::text[], %s::text[]) WITH ORDINALITY AS u(dc_code, pattern, ord)
        ON n.cluster_name LIKE u.pattern
    WHERE n.collection_time BETWEEN %s AND %s
),
nutanix_latest AS (
    SELECT DISTINCT ON (dc_code, cluster_name)
        dc_code, cluster_name,
        total_cpu_capacity / 1000000000.0 AS cpu_cap_ghz,
        cpu_used_hz / 1000000000.0 AS cpu_used_ghz,
        total_memory_capacity / 1073741824.0 AS mem_cap_gb,
        used_memory_bytes / 1073741824.0 AS mem_used_gb
    FROM nutanix_matched
    ORDER BY dc_code, cluster_name, ord, collection_time DESC
),
all_clusters AS (
    SELECT dc_code, cluster_name FROM vmware_latest
    UNION
    SELECT dc_code, cluster_name FROM nutanix_latest
),
merged AS (
    SELECT
        ac.dc_code,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_capacity, 0) ELSE COALESCE(n.cpu_cap_ghz, 0) END AS cpu_cap_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.cpu_ghz_used, 0) ELSE COALESCE(n.cpu_used_ghz, 0) END AS cpu_used_ghz,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_capacity_gb, 0) ELSE COALESCE(n.mem_cap_gb, 0) END AS mem_cap_gb,
        CASE WHEN {_VMWARE_PRIORITY}
            THEN COALESCE(v.memory_used_gb, 0) ELSE COALESCE(n.mem_used_gb, 0) END AS mem_used_gb
    FROM all_clusters ac
    LEFT JOIN vmware_latest v ON v.dc_code = ac.dc_code AND v.cluster_name = ac.cluster_name
    LEFT JOIN nutanix_latest n ON n.dc_code = ac.dc_code AND n.cluster_name = ac.cluster_name
)
SELECT
    dc_code,
    COALESCE(AVG(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_avg_pct,
    COALESCE(AVG(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_avg_pct,
    COALESCE(MAX(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_max_pct,
    COALESCE(MAX(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_max_pct,
    COALESCE(MIN(CASE WHEN cpu_cap_ghz > 0 THEN 100.0 * cpu_used_ghz / cpu_cap_ghz END), 0) AS cpu_min_pct,
    COALESCE(MIN(CASE WHEN mem_cap_gb > 0 THEN 100.0 * mem_used_gb / mem_cap_gb END), 0) AS mem_min_pct
FROM merged
GROUP BY dc_code
"""
