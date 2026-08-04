"""SQL for colocation sellable rack-role rules (webui-db)."""

LIST_ROLE_RULES = """
SELECT role_id,
       sellable,
       notes,
       updated_by,
       updated_at
FROM   gui_colocation_role_rule
ORDER BY role_id;
"""

UPSERT_ROLE_RULE = """
INSERT INTO gui_colocation_role_rule
    (role_id, sellable, notes, updated_by, updated_at)
VALUES (%s, %s, %s, %s, NOW())
ON CONFLICT (role_id) DO UPDATE SET
    sellable   = EXCLUDED.sellable,
    notes      = COALESCE(EXCLUDED.notes, gui_colocation_role_rule.notes),
    updated_by = EXCLUDED.updated_by,
    updated_at = NOW();
"""
