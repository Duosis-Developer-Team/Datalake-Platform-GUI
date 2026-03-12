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
SELECT
    COALESCE(AVG(server_memory_configurablemem), 0) AS total_memory,
    COALESCE(AVG(server_memory_assignedmemtolpars), 0) AS assigned_memory
FROM public.ibm_server_general
WHERE server_details_servername LIKE %s AND time BETWEEN %s AND %s
"""

CPU = """
SELECT
    COALESCE(AVG(server_processor_utilizedprocunits), 0) AS used_proc,
    COALESCE(AVG(server_processor_utilizedprocunitsdeductidle), 0) AS deducted_proc,
    COALESCE(AVG(server_physicalprocessorpool_assignedprocunits), 0) AS assigned_proc
FROM public.ibm_server_general
WHERE server_details_servername LIKE %s AND time BETWEEN %s AND %s
"""

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
SELECT server_details_servername, server_memory_configurablemem, server_memory_assignedmemtolpars
FROM public.ibm_server_general
WHERE time BETWEEN %s AND %s
"""

BATCH_RAW_CPU = """
SELECT server_details_servername,
       server_processor_utilizedprocunits,
       server_processor_utilizedprocunitsdeductidle,
       server_physicalprocessorpool_assignedprocunits
FROM public.ibm_server_general
WHERE time BETWEEN %s AND %s
"""

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
        server_memory_configurablemem,
        server_memory_assignedmemtolpars
    FROM public.ibm_server_general
    WHERE time BETWEEN %s AND %s
)
SELECT
    dc_code,
    AVG(server_memory_configurablemem) AS total_memory,
    AVG(server_memory_assignedmemtolpars) AS assigned_memory
FROM extracted
WHERE dc_code = ANY(%s)
GROUP BY dc_code
"""

BATCH_CPU = """
WITH extracted AS (
    SELECT
        (regexp_matches(UPPER(server_details_servername), 'DC[0-9]+|AZ[0-9]+|ICT[0-9]+'))[1] AS dc_code,
        server_processor_utilizedprocunits,
        server_processor_utilizedprocunitsdeductidle,
        server_physicalprocessorpool_assignedprocunits
    FROM public.ibm_server_general
    WHERE time BETWEEN %s AND %s
)
SELECT
    dc_code,
    AVG(server_processor_utilizedprocunits) AS used_proc,
    AVG(server_processor_utilizedprocunitsdeductidle) AS deducted_proc,
    AVG(server_physicalprocessorpool_assignedprocunits) AS assigned_proc
FROM extracted
WHERE dc_code = ANY(%s)
GROUP BY dc_code
"""
