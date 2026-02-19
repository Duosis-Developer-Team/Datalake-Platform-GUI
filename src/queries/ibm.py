# IBM Power (HMC) SQL query definitions — source: ibm_server_general

# --- Individual queries ---

HOST_COUNT = """
SELECT COUNT(DISTINCT server_details_servername)
FROM public.ibm_server_general
WHERE server_details_servername LIKE %s
"""

# --- Batch queries ---
# Groups by DC code prefix so the caller can map results back to DC codes.
# Pattern list passed as ARRAY via psycopg2 for LIKE ANY(...)

BATCH_HOST_COUNT = """
SELECT
    server_details_servername,
    COUNT(DISTINCT server_details_servername) AS host_count
FROM public.ibm_server_general
WHERE server_details_servername LIKE ANY(%s)
GROUP BY server_details_servername
"""
