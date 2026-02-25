# Nutanix SQL query definitions — source: nutanix_cluster_metrics
# Individual queries (single DC) and batch queries (all DCs at once)

# --- Individual queries (parameterized with LIKE %s wildcard) ---

HOST_COUNT = """
SELECT num_nodes
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE %s
ORDER BY collection_time DESC
LIMIT 1
"""

VM_COUNT = """
SELECT total_vms
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE %s
ORDER BY collection_time DESC
LIMIT 1
"""

MEMORY = """
SELECT
    total_memory_capacity,
    ((memory_usage_avg / 1000) * total_memory_capacity) / 1000
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE %s
ORDER BY collection_time DESC
LIMIT 1
"""

STORAGE = """
SELECT
    storage_capacity / 2,
    storage_usage / 2
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE %s
ORDER BY collection_time DESC
LIMIT 1
"""

CPU = """
SELECT
    total_cpu_capacity,
    (cpu_usage_avg * total_cpu_capacity) / 1000000
FROM public.nutanix_cluster_metrics
WHERE cluster_name LIKE %s
ORDER BY collection_time DESC
LIMIT 1
"""

# --- Batch queries (all DCs in a single roundtrip) ---
# Uses `datacenter_name` column (exact DC code) instead of cluster_name LIKE wildcard.
# `datacenter_name` is a direct column in nutanix_cluster_metrics → exact match is safe and fast.
# When multiple clusters exist per DC, we SUM metrics across all clusters per DC.

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
    WHERE datacenter_name = ANY(%s)
    ORDER BY cluster_name, collection_time DESC
) latest
GROUP BY datacenter_name
"""

BATCH_MEMORY = """
SELECT
    datacenter_name,
    SUM(total_memory_capacity) AS total_memory_capacity,
    SUM(((memory_usage_avg / 1000) * total_memory_capacity) / 1000) AS used_memory
FROM (
    SELECT DISTINCT ON (cluster_name)
        datacenter_name,
        cluster_name,
        total_memory_capacity,
        memory_usage_avg
    FROM public.nutanix_cluster_metrics
    WHERE datacenter_name = ANY(%s)
    ORDER BY cluster_name, collection_time DESC
) latest
GROUP BY datacenter_name
"""

BATCH_STORAGE = """
SELECT
    datacenter_name,
    SUM(storage_capacity / 2) AS storage_cap,
    SUM(storage_usage / 2)    AS storage_used
FROM (
    SELECT DISTINCT ON (cluster_name)
        datacenter_name,
        cluster_name,
        storage_capacity,
        storage_usage
    FROM public.nutanix_cluster_metrics
    WHERE datacenter_name = ANY(%s)
    ORDER BY cluster_name, collection_time DESC
) latest
GROUP BY datacenter_name
"""

BATCH_CPU = """
SELECT
    datacenter_name,
    SUM(total_cpu_capacity) AS total_cpu_capacity,
    SUM((cpu_usage_avg * total_cpu_capacity) / 1000000) AS cpu_used
FROM (
    SELECT DISTINCT ON (cluster_name)
        datacenter_name,
        cluster_name,
        total_cpu_capacity,
        cpu_usage_avg
    FROM public.nutanix_cluster_metrics
    WHERE datacenter_name = ANY(%s)
    ORDER BY cluster_name, collection_time DESC
) latest
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
    WHERE datacenter_name = ANY(%s)
    ORDER BY cluster_name, collection_time DESC
) latest
GROUP BY datacenter_name
"""
