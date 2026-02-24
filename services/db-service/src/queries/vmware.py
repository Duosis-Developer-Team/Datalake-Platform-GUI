# VMware SQL query definitions — source: datacenter_metrics
# asyncpg placeholder syntax: $1, $2, ...  (NOT %s)

# ── Individual queries (single DC, ILIKE wildcard) ────────────────────────────

COUNTS = """
SELECT total_cluster_count, total_host_count, total_vm_count
FROM public.datacenter_metrics
WHERE datacenter ILIKE $1
  AND timestamp >= NOW() - INTERVAL '4 hours'
ORDER BY timestamp DESC
LIMIT 1
"""

MEMORY = """
SELECT
    total_memory_capacity_gb * 1024 * 1024 * 1024,
    total_memory_used_gb     * 1024 * 1024 * 1024
FROM public.datacenter_metrics
WHERE datacenter ILIKE $1
  AND timestamp >= NOW() - INTERVAL '4 hours'
ORDER BY timestamp DESC
LIMIT 1
"""

STORAGE = """
SELECT
    total_storage_capacity_gb * (1024 * 1024),
    total_used_storage_gb     * (1024 * 1024)
FROM public.datacenter_metrics
WHERE datacenter ILIKE $1
  AND timestamp >= NOW() - INTERVAL '4 hours'
ORDER BY timestamp DESC
LIMIT 1
"""

CPU = """
SELECT
    total_cpu_ghz_capacity * 1000000000,
    total_cpu_ghz_used     * 1000000000
FROM public.datacenter_metrics
WHERE datacenter ILIKE $1
  AND timestamp >= NOW() - INTERVAL '4 hours'
ORDER BY timestamp DESC
LIMIT 1
"""

# ── Batch queries (all DCs — one roundtrip) ───────────────────────────────────
# $1 → list of wildcard patterns, e.g. ['%AZ11%', '%DC11%', ...]
# asyncpg converts Python list → PostgreSQL text[] automatically.

BATCH_COUNTS = """
SELECT DISTINCT ON (datacenter)
    datacenter,
    total_cluster_count,
    total_host_count,
    total_vm_count
FROM public.datacenter_metrics
WHERE datacenter ILIKE ANY($1::text[])
  AND timestamp >= NOW() - INTERVAL '4 hours'
ORDER BY datacenter, timestamp DESC
"""

BATCH_MEMORY = """
SELECT DISTINCT ON (datacenter)
    datacenter,
    total_memory_capacity_gb * 1024 * 1024 * 1024 AS mem_cap,
    total_memory_used_gb     * 1024 * 1024 * 1024 AS mem_used
FROM public.datacenter_metrics
WHERE datacenter ILIKE ANY($1::text[])
  AND timestamp >= NOW() - INTERVAL '4 hours'
ORDER BY datacenter, timestamp DESC
"""

BATCH_STORAGE = """
SELECT DISTINCT ON (datacenter)
    datacenter,
    total_storage_capacity_gb * (1024 * 1024) AS stor_cap,
    total_used_storage_gb     * (1024 * 1024) AS stor_used
FROM public.datacenter_metrics
WHERE datacenter ILIKE ANY($1::text[])
  AND timestamp >= NOW() - INTERVAL '4 hours'
ORDER BY datacenter, timestamp DESC
"""

BATCH_CPU = """
SELECT DISTINCT ON (datacenter)
    datacenter,
    total_cpu_ghz_capacity * 1000000000 AS cpu_cap,
    total_cpu_ghz_used     * 1000000000 AS cpu_used
FROM public.datacenter_metrics
WHERE datacenter ILIKE ANY($1::text[])
  AND timestamp >= NOW() - INTERVAL '4 hours'
ORDER BY datacenter, timestamp DESC
"""
