"""NetBox/Loki configuration queries (datalake + webui)."""

DISTINCT_DEVICE_ROLES = """
SELECT DISTINCT device_role_name
FROM public.discovery_netbox_inventory_device
WHERE status_value = 'active'
  AND device_role_name IS NOT NULL
  AND TRIM(device_role_name) <> ''
ORDER BY device_role_name;
"""

LIST_EXCLUDED_DEVICE_ROLES = """
SELECT dimension_value
FROM gui_netbox_viz_exclusion
WHERE view_scope = %s
  AND dimension = 'device_role'
ORDER BY dimension_value;
"""
