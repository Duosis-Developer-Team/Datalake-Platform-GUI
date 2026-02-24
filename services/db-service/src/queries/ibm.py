# IBM Power (HMC) SQL query definitions — source: ibm_server_general
# asyncpg placeholder syntax: $1  (NOT %s)

# ── Individual query ──────────────────────────────────────────────────────────

HOST_COUNT = """
SELECT COUNT(DISTINCT server_details_servername)
FROM public.ibm_server_general
WHERE server_details_servername LIKE $1
"""

# ── Batch query ───────────────────────────────────────────────────────────────
# $1 → list of wildcard patterns, e.g. ['%AZ11%', '%DC11%', ...]
# Groups by servername so caller can map back to DC codes via substring match.

BATCH_HOST_COUNT = """
SELECT
    server_details_servername,
    COUNT(DISTINCT server_details_servername) AS host_count
FROM public.ibm_server_general
WHERE server_details_servername LIKE ANY($1::text[])
GROUP BY server_details_servername
"""
