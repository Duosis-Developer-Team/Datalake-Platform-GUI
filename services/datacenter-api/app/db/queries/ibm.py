# IBM Power (HMC) SQL query definitions
# Sources: ibm_server_general (time), ibm_vios_general, ibm_lpar_general
# Individual: (wildcard, start_ts, end_ts). Batch: (dc_list, start_ts, end_ts) with regex DC extraction.
# Counts use COUNT(DISTINCT ...). MEMORY/CPU use DISTINCT ON (server) for latest
# row in the report window, then SUM or AVG as noted per query.

# --- Individual queries ---

HOST_COUNT = """
SELECT COUNT(DISTINCT server_details_servername)
FROM public.ibm_server_general
WHERE server_details_servername LIKE %s AND time BETWEEN %s AND %s
"""

VIOS_COUNT = """
SELECT COUNT(DISTINCT viosname) AS vios_count
FROM public.ibm_vios_general
WHERE vios_details_servername LIKE %s AND time BETWEEN %s AND %s
"""

LPAR_COUNT = """
SELECT COUNT(DISTINCT lparname) AS lpar_count
FROM public.ibm_lpar_general
WHERE lpar_details_servername LIKE %s AND time BETWEEN %s AND %s
"""

MEMORY = """
WITH latest_per_server AS (
    SELECT DISTINCT ON (server_details_servername)
        server_details_servername,
        server_memory_totalmem,
        server_memory_availablemem,
        server_memory_assignedmemtolpars
    FROM public.ibm_server_general
    WHERE server_details_servername LIKE %s AND time BETWEEN %s AND %s
    ORDER BY server_details_servername, time DESC
)
SELECT
    COALESCE(SUM(server_memory_totalmem), 0) AS total_memory,
    COALESCE(SUM(server_memory_availablemem), 0) AS available_memory,
    COALESCE(SUM(server_memory_assignedmemtolpars), 0) AS assigned_memory
FROM latest_per_server
"""

CPU = """
WITH latest_per_server AS (
    SELECT DISTINCT ON (server_details_servername)
        server_details_servername,
        server_processor_totalprocunits,
        server_processor_availableprocunits,
        server_processor_utilizedprocunits,
        server_physicalprocessorpool_assignedprocunits
    FROM public.ibm_server_general
    WHERE server_details_servername LIKE %s AND time BETWEEN %s AND %s
    ORDER BY server_details_servername, time DESC
)
SELECT
    COALESCE(SUM(server_processor_totalprocunits), 0) AS total_proc,
    COALESCE(SUM(server_processor_availableprocunits), 0) AS available_proc,
    COALESCE(AVG(server_processor_utilizedprocunits), 0) AS used_proc,
    COALESCE(AVG(server_physicalprocessorpool_assignedprocunits), 0) AS assigned_proc
FROM latest_per_server
"""

# --- Batch queries (lightweight — no regex) ---
# These fetch raw rows; DC code extraction is done in Python to minimise
# database CPU load and allow the queries to leverage simple time-range
# indexes instead of computing regexp_matches on every row.
#
# Params: (start_ts, end_ts)

BATCH_RAW_HOST = """
SELECT server_details_servername
FROM public.ibm_server_general
WHERE time BETWEEN %s AND %s
"""

BATCH_RAW_VIOS = """
SELECT vios_details_servername, viosname
FROM public.ibm_vios_general
WHERE time BETWEEN %s AND %s
"""

BATCH_RAW_LPAR = """
SELECT lpar_details_servername, lparname
FROM public.ibm_lpar_general
WHERE time BETWEEN %s AND %s
"""

BATCH_RAW_MEMORY = """
SELECT server_details_servername,
       server_memory_totalmem,
       server_memory_availablemem,
       server_memory_assignedmemtolpars,
       time
FROM public.ibm_server_general
WHERE time BETWEEN %s AND %s
"""

BATCH_RAW_CPU = """
SELECT server_details_servername,
       server_processor_totalprocunits,
       server_processor_availableprocunits,
       server_processor_utilizedprocunits,
       server_physicalprocessorpool_assignedprocunits,
       time
FROM public.ibm_server_general
WHERE time BETWEEN %s AND %s
"""

# Legacy batch queries kept for registry/explorer use but no longer called
# by _fetch_all_batch (which now uses the raw+Python approach above).

BATCH_HOST_COUNT = """
WITH extracted AS (
    SELECT
        (regexp_matches(UPPER(server_details_servername), 'DC[0-9]+|AZ[0-9]+|ICT[0-9]+'))[1] AS dc_code,
        server_details_servername
    FROM public.ibm_server_general
    WHERE time BETWEEN %s AND %s
)
SELECT dc_code, COUNT(DISTINCT server_details_servername) AS host_count
FROM extracted
WHERE dc_code = ANY(%s)
GROUP BY dc_code
"""

BATCH_VIOS_COUNT = """
WITH extracted AS (
    SELECT
        (regexp_matches(UPPER(vios_details_servername), 'DC[0-9]+|AZ[0-9]+|ICT[0-9]+'))[1] AS dc_code,
        vios_details_servername,
        viosname
    FROM public.ibm_vios_general
    WHERE time BETWEEN %s AND %s
)
SELECT dc_code, COUNT(DISTINCT viosname) AS vios_count
FROM extracted
WHERE dc_code = ANY(%s)
GROUP BY dc_code
"""

BATCH_LPAR_COUNT = """
WITH extracted AS (
    SELECT
        (regexp_matches(UPPER(lpar_details_servername), 'DC[0-9]+|AZ[0-9]+|ICT[0-9]+'))[1] AS dc_code,
        lpar_details_servername,
        lparname
    FROM public.ibm_lpar_general
    WHERE time BETWEEN %s AND %s
)
SELECT dc_code, COUNT(DISTINCT lparname) AS lpar_count
FROM extracted
WHERE dc_code = ANY(%s)
GROUP BY dc_code
"""

BATCH_MEMORY = """
WITH extracted AS (
    SELECT
        (regexp_matches(UPPER(server_details_servername), 'DC[0-9]+|AZ[0-9]+|ICT[0-9]+'))[1] AS dc_code,
        server_details_servername,
        server_memory_totalmem,
        server_memory_availablemem,
        server_memory_assignedmemtolpars,
        time
    FROM public.ibm_server_general
    WHERE time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (dc_code, server_details_servername)
        dc_code,
        server_memory_totalmem,
        server_memory_availablemem,
        server_memory_assignedmemtolpars
    FROM extracted
    ORDER BY dc_code, server_details_servername, time DESC
)
SELECT
    dc_code,
    COALESCE(SUM(server_memory_totalmem), 0) AS total_memory,
    COALESCE(SUM(server_memory_availablemem), 0) AS available_memory,
    COALESCE(SUM(server_memory_assignedmemtolpars), 0) AS assigned_memory
FROM latest
WHERE dc_code = ANY(%s)
GROUP BY dc_code
"""

BATCH_CPU = """
WITH extracted AS (
    SELECT
        (regexp_matches(UPPER(server_details_servername), 'DC[0-9]+|AZ[0-9]+|ICT[0-9]+'))[1] AS dc_code,
        server_details_servername,
        server_processor_totalprocunits,
        server_processor_availableprocunits,
        server_processor_utilizedprocunits,
        server_physicalprocessorpool_assignedprocunits,
        time
    FROM public.ibm_server_general
    WHERE time BETWEEN %s AND %s
),
latest AS (
    SELECT DISTINCT ON (dc_code, server_details_servername)
        dc_code,
        server_processor_totalprocunits,
        server_processor_availableprocunits,
        server_processor_utilizedprocunits,
        server_physicalprocessorpool_assignedprocunits
    FROM extracted
    ORDER BY dc_code, server_details_servername, time DESC
)
SELECT
    dc_code,
    COALESCE(SUM(server_processor_totalprocunits), 0) AS total_proc,
    COALESCE(SUM(server_processor_availableprocunits), 0) AS available_proc,
    COALESCE(AVG(server_processor_utilizedprocunits), 0) AS used_proc,
    COALESCE(AVG(server_physicalprocessorpool_assignedprocunits), 0) AS assigned_proc
FROM latest
WHERE dc_code = ANY(%s)
GROUP BY dc_code
"""
