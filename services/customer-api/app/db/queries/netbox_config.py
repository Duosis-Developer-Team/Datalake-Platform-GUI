"""SQL for NetBox/Loki visualization exclusion config (webui-db)."""

LIST_VIZ_EXCLUSIONS = """
SELECT id,
       view_scope,
       dimension,
       dimension_value,
       notes,
       updated_by,
       updated_at
FROM   gui_netbox_viz_exclusion
ORDER BY view_scope, dimension, dimension_value;
"""

UPSERT_VIZ_EXCLUSION = """
INSERT INTO gui_netbox_viz_exclusion
    (view_scope, dimension, dimension_value, notes, updated_by, updated_at)
VALUES (%s, %s, %s, %s, %s, NOW())
ON CONFLICT (view_scope, dimension, dimension_value) DO UPDATE SET
    notes      = COALESCE(EXCLUDED.notes, gui_netbox_viz_exclusion.notes),
    updated_by = EXCLUDED.updated_by,
    updated_at = NOW();
"""

DELETE_VIZ_EXCLUSION_BY_ID = """
DELETE FROM gui_netbox_viz_exclusion WHERE id = %s;
"""
