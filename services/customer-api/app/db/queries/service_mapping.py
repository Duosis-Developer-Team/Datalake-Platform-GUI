# SQL for CRM service mapping (YAML seed in DB + operator overrides).

LIST_SERVICE_PAGES = """
SELECT page_key,
       category_label,
       gui_tab_binding,
       resource_unit,
       icon,
       route_hint,
       tab_hint,
       sub_tab_hint
FROM   gui_crm_service_pages
ORDER BY page_key;
"""

LIST_SERVICE_MAPPINGS = """
SELECT productid,
       product_name,
       product_number,
       category_code,
       category_label,
       gui_tab_binding,
       resource_unit,
       mapping_source AS source
FROM   v_gui_crm_product_mapping
ORDER BY product_name NULLS LAST, productid;
"""

UPSERT_SERVICE_MAPPING_OVERRIDE = """
INSERT INTO gui_crm_service_mapping_override (productid, page_key, notes, updated_by, updated_at)
VALUES (%s, %s, %s, %s, now())
ON CONFLICT (productid) DO UPDATE SET
    page_key   = EXCLUDED.page_key,
    notes      = COALESCE(EXCLUDED.notes, gui_crm_service_mapping_override.notes),
    updated_by = EXCLUDED.updated_by,
    updated_at = now();
"""

DELETE_SERVICE_MAPPING_OVERRIDE = """
DELETE FROM gui_crm_service_mapping_override WHERE productid = %s;
"""

VALIDATE_PAGE_KEY = """
SELECT 1 FROM gui_crm_service_pages WHERE page_key = %s LIMIT 1;
"""
