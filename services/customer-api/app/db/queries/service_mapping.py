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

UPSERT_ALIAS_AUTO = """
INSERT INTO gui_crm_customer_alias
    (crm_accountid, crm_account_name, canonical_customer_key, netbox_musteri_value, notes, source, created_at, updated_at)
VALUES (%s, %s, %s, NULL, NULL, 'auto', now(), now())
ON CONFLICT (crm_accountid) DO UPDATE
    SET crm_account_name = CASE
            WHEN gui_crm_customer_alias.source = 'manual' THEN gui_crm_customer_alias.crm_account_name
            ELSE EXCLUDED.crm_account_name
        END,
        canonical_customer_key = CASE
            WHEN gui_crm_customer_alias.source = 'manual' THEN gui_crm_customer_alias.canonical_customer_key
            ELSE COALESCE(gui_crm_customer_alias.canonical_customer_key, EXCLUDED.canonical_customer_key)
        END,
        updated_at = CASE
            WHEN gui_crm_customer_alias.source = 'manual' THEN gui_crm_customer_alias.updated_at
            ELSE now()
        END;
"""

LIST_ORPHAN_SOURCE_MAPPINGS = """
SELECT m.id,
       m.crm_accountid,
       m.crm_account_name,
       m.data_source,
       m.match_method,
       m.match_value
FROM   gui_crm_customer_source_mapping m
LEFT JOIN gui_crm_customer_alias a ON a.crm_accountid = m.crm_accountid
WHERE  a.crm_accountid IS NULL
ORDER BY m.crm_account_name, m.id;
"""

UPDATE_SOURCE_MAPPING_ACCOUNT = """
UPDATE gui_crm_customer_source_mapping
SET crm_accountid = %s,
    crm_account_name = %s,
    updated_at = now()
WHERE id = %s;
"""

# ---------------------------------------------------------------------------
# Customer source mappings (gui_crm_customer_source_mapping)
# ---------------------------------------------------------------------------

LIST_SOURCE_MAPPINGS = """
SELECT id,
       crm_accountid,
       crm_account_name,
       data_source,
       match_method,
       match_value,
       display_label,
       priority,
       enabled,
       notes,
       source,
       created_at,
       updated_at
FROM   gui_crm_customer_source_mapping
ORDER BY crm_account_name, data_source, priority, id;
"""

LIST_SOURCE_MAPPINGS_FOR_ACCOUNT = """
SELECT id,
       crm_accountid,
       crm_account_name,
       data_source,
       match_method,
       match_value,
       display_label,
       priority,
       enabled,
       notes,
       source,
       created_at,
       updated_at
FROM   gui_crm_customer_source_mapping
WHERE  crm_accountid = %s
ORDER BY data_source, priority, id;
"""

LIST_SOURCE_MAPPINGS_BY_ACCOUNT_IDS = """
SELECT id,
       crm_accountid,
       crm_account_name,
       data_source,
       match_method,
       match_value,
       display_label,
       priority,
       enabled,
       notes,
       source,
       created_at,
       updated_at
FROM   gui_crm_customer_source_mapping
WHERE  crm_accountid = ANY(%s)
ORDER BY crm_accountid, data_source, priority, id;
"""

DELETE_SOURCE_MAPPINGS_FOR_ACCOUNT = """
DELETE FROM gui_crm_customer_source_mapping WHERE crm_accountid = %s;
"""

UPSERT_SOURCE_MAPPING = """
INSERT INTO gui_crm_customer_source_mapping (
    crm_accountid,
    crm_account_name,
    data_source,
    match_method,
    match_value,
    display_label,
    priority,
    enabled,
    notes,
    source,
    created_at,
    updated_at
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
ON CONFLICT (crm_accountid, data_source, match_method, match_value) DO UPDATE
    SET crm_account_name = EXCLUDED.crm_account_name,
        display_label    = COALESCE(EXCLUDED.display_label, gui_crm_customer_source_mapping.display_label),
        priority         = EXCLUDED.priority,
        enabled          = EXCLUDED.enabled,
        notes            = COALESCE(EXCLUDED.notes, gui_crm_customer_source_mapping.notes),
        source           = EXCLUDED.source,
        updated_at       = now();
"""

RESOLVE_ACCOUNTID_BY_DISPLAY_NAME = """
SELECT crm_accountid,
       crm_account_name,
       canonical_customer_key,
       netbox_musteri_value
FROM   gui_crm_customer_alias
WHERE  crm_account_name ILIKE %s
   OR  canonical_customer_key = %s
ORDER BY CASE WHEN crm_account_name ILIKE %s THEN 0 ELSE 1 END
LIMIT 1;
"""

# ---------------------------------------------------------------------------
# Customer profile flags (VIP / cache-pinned) — migration 018
# ---------------------------------------------------------------------------

LIST_PROFILE_FLAGS = """
SELECT crm_accountid,
       is_vip,
       cache_pinned,
       updated_by,
       created_at,
       updated_at
FROM   gui_crm_customer_profile_flags;
"""

GET_PROFILE_FLAG = """
SELECT crm_accountid,
       is_vip,
       cache_pinned,
       updated_by,
       created_at,
       updated_at
FROM   gui_crm_customer_profile_flags
WHERE  crm_accountid = %s;
"""

UPSERT_PROFILE_VIP = """
INSERT INTO gui_crm_customer_profile_flags
    (crm_accountid, is_vip, cache_pinned, updated_by, created_at, updated_at)
VALUES (%s, %s, %s, %s, now(), now())
ON CONFLICT (crm_accountid) DO UPDATE SET
    is_vip       = EXCLUDED.is_vip,
    cache_pinned = EXCLUDED.cache_pinned,
    updated_by   = EXCLUDED.updated_by,
    updated_at   = now();
"""

LIST_PINNED_DISPLAY_NAMES = """
SELECT DISTINCT TRIM(m.crm_account_name) AS crm_account_name
FROM   gui_crm_customer_profile_flags f
JOIN   gui_crm_customer_source_mapping m ON m.crm_accountid = f.crm_accountid
WHERE  (f.cache_pinned = TRUE OR f.is_vip = TRUE)
  AND  TRIM(COALESCE(m.crm_account_name, '')) <> ''
UNION
SELECT TRIM(a.crm_account_name) AS crm_account_name
FROM   gui_crm_customer_profile_flags f
JOIN   (
    SELECT DISTINCT crm_accountid, crm_account_name
    FROM gui_crm_customer_source_mapping
) a ON a.crm_accountid = f.crm_accountid
WHERE  (f.cache_pinned = TRUE OR f.is_vip = TRUE)
  AND  TRIM(COALESCE(a.crm_account_name, '')) <> '';
"""

MAPPING_COUNTS_BY_ACCOUNT = """
SELECT crm_accountid,
       COUNT(*) FILTER (
           WHERE enabled = TRUE
             AND TRIM(COALESCE(match_value, '')) <> ''
       )::int AS enabled_mapping_count
FROM   gui_crm_customer_source_mapping
GROUP BY crm_accountid;
"""
