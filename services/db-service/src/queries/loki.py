# Loki (NetBox) SQL query definitions — source: loki_locations
# Used to dynamically resolve the list of active datacenters.
# No parameters — no placeholder changes needed.

# Returns distinct datacenter names using the parent/child hierarchy:
#   parent_id IS NULL  → the row itself IS a datacenter
#   parent_id NOT NULL → the row is a sub-location; parent_name is the DC name

DC_LIST = """
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
    AND status_value = 'active'
ORDER BY 1
"""

# Fallback: same query without status filter (used when status_value is unpopulated)
DC_LIST_NO_STATUS = """
SELECT DISTINCT
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END AS dc_name
FROM public.loki_locations
WHERE
    CASE WHEN parent_id IS NULL THEN name ELSE parent_name END IS NOT NULL
ORDER BY 1
"""
