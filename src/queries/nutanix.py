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
# Returns one row per DC code. Caller maps rows by dc_code.
# Parameter: list of DC codes passed as PostgreSQL array via psycopg2 (ANY(%s))

BATCH_HOST_COUNT = """
SELECT DISTINCT ON (cluster_name)
    cluster_name,
    num_nodes
FROM public.nutanix_cluster_metrics
WHERE cluster_name = ANY(%s)
ORDER BY cluster_name, collection_time DESC
"""

BATCH_MEMORY = """
SELECT DISTINCT ON (cluster_name)
    cluster_name,
    total_memory_capacity,
    ((memory_usage_avg / 1000) * total_memory_capacity) / 1000 AS used_memory
FROM public.nutanix_cluster_metrics
WHERE cluster_name = ANY(%s)
ORDER BY cluster_name, collection_time DESC
"""

BATCH_STORAGE = """
SELECT DISTINCT ON (cluster_name)
    cluster_name,
    storage_capacity / 2 AS storage_cap,
    storage_usage / 2    AS storage_used
FROM public.nutanix_cluster_metrics
WHERE cluster_name = ANY(%s)
ORDER BY cluster_name, collection_time DESC
"""

BATCH_CPU = """
SELECT DISTINCT ON (cluster_name)
    cluster_name,
    total_cpu_capacity,
    (cpu_usage_avg * total_cpu_capacity) / 1000000 AS cpu_used
FROM public.nutanix_cluster_metrics
WHERE cluster_name = ANY(%s)
ORDER BY cluster_name, collection_time DESC
"""
