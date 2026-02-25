# IBM Power (HMC) SQL query definitions
# Sources: ibm_server_general, ibm_vios_general, ibm_lpar_general

# --- Individual queries ---

HOST_COUNT = """
SELECT COUNT(DISTINCT server_details_servername)
FROM public.ibm_server_general
WHERE server_details_servername LIKE %s
"""

VIOS_COUNT = """
SELECT COUNT(DISTINCT viosname) AS vios_count
FROM public.ibm_vios_general
WHERE vios_details_servername LIKE %s
"""

LPAR_COUNT = """
SELECT COUNT(DISTINCT lparname) AS lpar_count
FROM public.ibm_lpar_general
WHERE lpar_details_servername LIKE %s
"""

MEMORY = """
WITH latest AS (
    SELECT DISTINCT ON (server_details_servername)
        server_details_servername,
        server_memory_configurablemem,
        server_memory_assignedmemtolpars
    FROM public.ibm_server_general
    WHERE server_details_servername LIKE %s
    ORDER BY server_details_servername, time DESC
)
SELECT
    COALESCE(SUM(server_memory_configurablemem), 0) AS total_memory,
    COALESCE(SUM(server_memory_assignedmemtolpars), 0) AS assigned_memory
FROM latest
"""

CPU = """
WITH latest AS (
    SELECT DISTINCT ON (server_details_servername)
        server_details_servername,
        server_processor_utilizedprocunits,
        server_processor_utilizedprocunitsdeductidle,
        server_physicalprocessorpool_assignedprocunits
    FROM public.ibm_server_general
    WHERE server_details_servername LIKE %s
    ORDER BY server_details_servername, time DESC
)
SELECT
    COALESCE(SUM(server_processor_utilizedprocunits), 0) AS used_proc,
    COALESCE(SUM(server_processor_utilizedprocunitsdeductidle), 0) AS deducted_proc,
    COALESCE(SUM(server_physicalprocessorpool_assignedprocunits), 0) AS assigned_proc
FROM latest
"""

# --- Batch queries ---
# Groups by server name; caller maps back to DC via pattern match.

BATCH_HOST_COUNT = """
SELECT
    server_details_servername,
    COUNT(DISTINCT server_details_servername) AS host_count
FROM public.ibm_server_general
WHERE server_details_servername LIKE ANY(%s)
GROUP BY server_details_servername
"""

BATCH_VIOS_COUNT = """
SELECT
    vios_details_servername,
    COUNT(DISTINCT viosname) AS vios_count
FROM public.ibm_vios_general
WHERE vios_details_servername LIKE ANY(%s)
GROUP BY vios_details_servername
"""

BATCH_LPAR_COUNT = """
SELECT
    lpar_details_servername,
    COUNT(DISTINCT lparname) AS lpar_count
FROM public.ibm_lpar_general
WHERE lpar_details_servername LIKE ANY(%s)
GROUP BY lpar_details_servername
"""

BATCH_MEMORY = """
WITH latest AS (
    SELECT DISTINCT ON (server_details_servername)
        server_details_servername,
        server_memory_configurablemem,
        server_memory_assignedmemtolpars
    FROM public.ibm_server_general
    WHERE server_details_servername LIKE ANY(%s)
    ORDER BY server_details_servername, time DESC
)
SELECT
    server_details_servername,
    server_memory_configurablemem AS total_memory,
    server_memory_assignedmemtolpars AS assigned_memory
FROM latest
"""

BATCH_CPU = """
WITH latest AS (
    SELECT DISTINCT ON (server_details_servername)
        server_details_servername,
        server_processor_utilizedprocunits,
        server_processor_utilizedprocunitsdeductidle,
        server_physicalprocessorpool_assignedprocunits
    FROM public.ibm_server_general
    WHERE server_details_servername LIKE ANY(%s)
    ORDER BY server_details_servername, time DESC
)
SELECT
    server_details_servername,
    server_processor_utilizedprocunits AS used_proc,
    server_processor_utilizedprocunitsdeductidle AS deducted_proc,
    server_physicalprocessorpool_assignedprocunits AS assigned_proc
FROM latest
"""
