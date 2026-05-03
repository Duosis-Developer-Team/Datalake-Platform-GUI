# SQL queries for CRM service mapping (operator config in webui-db).
#
# Pages registry, seed (YAML-derived) and override tables live in webui-db.
# The list-mappings endpoint returns rows enriched in Python with product
# metadata (name, number) coming from datalake DB so we can stay free of
# cross-DB joins.

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

# Webui-side: full mapping rows keyed by productid. Product display names come
# from the datalake side (ALL_PRODUCTS in crm_sales.py) and are merged in Python.
#
# A LEFT JOIN onto gui_crm_service_pages preserves rows whose effective page_key
# becomes NULL (when neither seed nor override exists). Those rows are surfaced
# by the API as source='unmatched' so operators can decide whether to map or
# leave them pending.
LIST_SERVICE_MAPPINGS_WEBUI = """
SELECT
    COALESCE(o.productid, s.productid)                     AS productid,
    COALESCE(o.page_key, s.page_key)                       AS category_code,
    pg.category_label,
    pg.gui_tab_binding,
    NULLIF(TRIM(pg.resource_unit), '')                     AS resource_unit,
    CASE
        WHEN o.productid IS NOT NULL THEN 'override'
        WHEN s.productid IS NOT NULL THEN 'yaml'
        ELSE 'unmatched'
    END                                                     AS source
FROM       gui_crm_service_mapping_seed s
FULL JOIN  gui_crm_service_mapping_override o ON o.productid = s.productid
LEFT JOIN  gui_crm_service_pages pg
       ON  pg.page_key = COALESCE(o.page_key, s.page_key);
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

# ---------------------------------------------------------------------------
# Customer alias (gui_crm_customer_alias in webui-db; replaces the empty
# discovery_crm_customer_alias table in datalake DB).
# ---------------------------------------------------------------------------

GET_ALL_ALIASES = """
SELECT crm_accountid,
       crm_account_name,
       canonical_customer_key,
       netbox_musteri_value,
       notes,
       source,
       created_at,
       updated_at
FROM   gui_crm_customer_alias
ORDER BY crm_account_name;
"""

RESOLVE_ALIAS_BY_NAME = """
SELECT crm_accountid
FROM   gui_crm_customer_alias
WHERE  canonical_customer_key = %s
   OR  crm_account_name ILIKE %s;
"""

UPSERT_ALIAS = """
INSERT INTO gui_crm_customer_alias
    (crm_accountid, crm_account_name, canonical_customer_key, netbox_musteri_value, notes, source, created_at, updated_at)
VALUES (%s, %s, %s, %s, %s, 'manual', now(), now())
ON CONFLICT (crm_accountid) DO UPDATE
    SET crm_account_name       = COALESCE(EXCLUDED.crm_account_name, gui_crm_customer_alias.crm_account_name),
        canonical_customer_key = EXCLUDED.canonical_customer_key,
        netbox_musteri_value   = EXCLUDED.netbox_musteri_value,
        notes                  = EXCLUDED.notes,
        source                 = 'manual',
        updated_at             = now();
"""

DELETE_ALIAS = """
DELETE FROM gui_crm_customer_alias WHERE crm_accountid = %s;
"""
