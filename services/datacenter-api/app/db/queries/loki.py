DC_LIST_WITH_SITE = """
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name,
    site_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
    AND status_value = 'active'
ORDER BY 1
"""

DC_LIST_WITH_SITE_NO_STATUS = """
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name,
    site_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
ORDER BY 1
"""

DC_LIST = """
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
    AND status_value = 'active'
ORDER BY 1
"""

DC_LIST_NO_STATUS = """
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
ORDER BY 1
"""

LOCATION_DC_MAP = """
SELECT
    name AS location_name,
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name
FROM public.loki_locations
WHERE CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
"""
