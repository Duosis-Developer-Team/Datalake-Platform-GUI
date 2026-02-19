# Loki (NetBox) SQL query definitions — source: loki_locations
# Used to dynamically resolve the list of active data centers.

# Returns distinct datacenter names using the parent/child hierarchy:
#   - If parent_id IS NULL  → the row itself IS a datacenter (name = dc_name)
#   - If parent_id IS NOT NULL → the row is a sub-location; parent_name = dc_name
DC_LIST = """
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
    AND status_value = 'active'
ORDER BY 1
"""

# Same query without status filter (fallback if status_value is not populated)
DC_LIST_NO_STATUS = """
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
ORDER BY 1
"""
