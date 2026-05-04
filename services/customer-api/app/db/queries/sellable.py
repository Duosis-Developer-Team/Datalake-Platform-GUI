"""SQL queries for the Sellable Potential dashboard.

Queries split between two databases (joined in the application layer per
ADR-0013):

  webui-db: panel registry, infra source bindings, ratios, unit conversions,
            thresholds, panel<->page links, price overrides, snapshots.

  datalake: per-panel total/allocated lookups (built dynamically from the
            infra-source descriptor), CRM YTD realized sales totals.
"""

# ---------------------------------------------------------------------------
# Panel registry CRUD (webui-db)
# ---------------------------------------------------------------------------

LIST_PANEL_DEFS = """
SELECT panel_key, label, family, resource_kind, display_unit, sort_order,
       enabled, notes, updated_by, updated_at
FROM   gui_panel_definition
ORDER BY sort_order, panel_key;
"""

GET_PANEL_DEF = """
SELECT panel_key, label, family, resource_kind, display_unit, sort_order,
       enabled, notes, updated_by, updated_at
FROM   gui_panel_definition
WHERE  panel_key = %s;
"""

UPSERT_PANEL_DEF = """
INSERT INTO gui_panel_definition
    (panel_key, label, family, resource_kind, display_unit, sort_order,
     enabled, notes, updated_by, updated_at)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
ON CONFLICT (panel_key) DO UPDATE SET
    label         = EXCLUDED.label,
    family        = EXCLUDED.family,
    resource_kind = EXCLUDED.resource_kind,
    display_unit  = EXCLUDED.display_unit,
    sort_order    = EXCLUDED.sort_order,
    enabled       = EXCLUDED.enabled,
    notes         = COALESCE(EXCLUDED.notes, gui_panel_definition.notes),
    updated_by    = EXCLUDED.updated_by,
    updated_at    = NOW();
"""

# ---------------------------------------------------------------------------
# Panel infra source CRUD (webui-db)
# ---------------------------------------------------------------------------

LIST_INFRA_SOURCES = """
SELECT panel_key, dc_code, source_table, total_column, total_unit,
       allocated_table, allocated_column, allocated_unit,
       filter_clause, notes, updated_by, updated_at
FROM   gui_panel_infra_source
ORDER BY panel_key, dc_code;
"""

GET_INFRA_SOURCE = """
SELECT panel_key, dc_code, source_table, total_column, total_unit,
       allocated_table, allocated_column, allocated_unit,
       filter_clause, notes, updated_by, updated_at
FROM   gui_panel_infra_source
WHERE  panel_key = %s
  AND  (dc_code = %s OR dc_code = '*')
ORDER BY (dc_code = '*') ASC
LIMIT 1;
"""

UPSERT_INFRA_SOURCE = """
INSERT INTO gui_panel_infra_source
    (panel_key, dc_code, source_table, total_column, total_unit,
     allocated_table, allocated_column, allocated_unit,
     filter_clause, notes, updated_by, updated_at)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
ON CONFLICT (panel_key, dc_code) DO UPDATE SET
    source_table     = EXCLUDED.source_table,
    total_column     = EXCLUDED.total_column,
    total_unit       = EXCLUDED.total_unit,
    allocated_table  = EXCLUDED.allocated_table,
    allocated_column = EXCLUDED.allocated_column,
    allocated_unit   = EXCLUDED.allocated_unit,
    filter_clause    = EXCLUDED.filter_clause,
    notes            = COALESCE(EXCLUDED.notes, gui_panel_infra_source.notes),
    updated_by       = EXCLUDED.updated_by,
    updated_at       = NOW();
"""

# ---------------------------------------------------------------------------
# Resource ratio CRUD
# ---------------------------------------------------------------------------

LIST_RATIOS = """
SELECT family, dc_code, cpu_per_unit, ram_gb_per_unit, storage_gb_per_unit,
       notes, updated_by, updated_at
FROM   gui_panel_resource_ratio
ORDER BY family, dc_code;
"""

GET_RATIO_FOR = """
SELECT family, dc_code, cpu_per_unit, ram_gb_per_unit, storage_gb_per_unit,
       notes, updated_by, updated_at
FROM   gui_panel_resource_ratio
WHERE  family = %s
  AND  (dc_code = %s OR dc_code = '*')
ORDER BY (dc_code = '*') ASC
LIMIT 1;
"""

UPSERT_RATIO = """
INSERT INTO gui_panel_resource_ratio
    (family, dc_code, cpu_per_unit, ram_gb_per_unit, storage_gb_per_unit,
     notes, updated_by, updated_at)
VALUES (%s,%s,%s,%s,%s,%s,%s, NOW())
ON CONFLICT (family, dc_code) DO UPDATE SET
    cpu_per_unit        = EXCLUDED.cpu_per_unit,
    ram_gb_per_unit     = EXCLUDED.ram_gb_per_unit,
    storage_gb_per_unit = EXCLUDED.storage_gb_per_unit,
    notes               = COALESCE(EXCLUDED.notes, gui_panel_resource_ratio.notes),
    updated_by          = EXCLUDED.updated_by,
    updated_at          = NOW();
"""

# ---------------------------------------------------------------------------
# Unit conversion CRUD
# ---------------------------------------------------------------------------

LIST_UNIT_CONVERSIONS = """
SELECT from_unit, to_unit, factor, operation, ceil_result,
       notes, updated_by, updated_at
FROM   gui_unit_conversion
ORDER BY from_unit, to_unit;
"""

GET_UNIT_CONVERSION = """
SELECT from_unit, to_unit, factor, operation, ceil_result,
       notes, updated_by, updated_at
FROM   gui_unit_conversion
WHERE  from_unit = %s AND to_unit = %s;
"""

UPSERT_UNIT_CONVERSION = """
INSERT INTO gui_unit_conversion
    (from_unit, to_unit, factor, operation, ceil_result,
     notes, updated_by, updated_at)
VALUES (%s,%s,%s,%s,%s,%s,%s, NOW())
ON CONFLICT (from_unit, to_unit) DO UPDATE SET
    factor      = EXCLUDED.factor,
    operation   = EXCLUDED.operation,
    ceil_result = EXCLUDED.ceil_result,
    notes       = COALESCE(EXCLUDED.notes, gui_unit_conversion.notes),
    updated_by  = EXCLUDED.updated_by,
    updated_at  = NOW();
"""

DELETE_UNIT_CONVERSION = """
DELETE FROM gui_unit_conversion WHERE from_unit = %s AND to_unit = %s;
"""

# ---------------------------------------------------------------------------
# Threshold lookup with panel_key precedence
# ---------------------------------------------------------------------------

GET_THRESHOLD_FOR_PANEL = """
SELECT sellable_limit_pct
FROM   gui_crm_threshold_config
WHERE  (panel_key = %s OR resource_type = %s)
  AND  (dc_code   = %s OR dc_code = '*')
ORDER BY (panel_key = %s) DESC,
         (dc_code = '*') ASC
LIMIT 1;
"""

# ---------------------------------------------------------------------------
# Price lookup: price-override first, then catalog TL price
# ---------------------------------------------------------------------------

GET_PRICE_OVERRIDE_FOR_PANEL = """
SELECT po.unit_price_tl, po.currency, po.productid
FROM   gui_crm_price_override   po
JOIN   gui_crm_service_pages    sp  ON sp.panel_key = %s
JOIN   gui_crm_service_mapping_seed     sm  ON sm.page_key = sp.page_key
LEFT  JOIN gui_crm_service_mapping_override ov ON ov.productid = sm.productid
WHERE  po.productid = COALESCE(ov.productid, sm.productid)
ORDER BY (po.unit_price_tl IS NOT NULL) DESC, po.updated_at DESC
LIMIT 1;
"""

# ---------------------------------------------------------------------------
# Catalog TL price (datalake DB) — fallback when no operator override exists.
# ---------------------------------------------------------------------------

CATALOG_TL_PRICE_FOR_PRODUCT = """
SELECT ppl.amount, pl.transactioncurrency_text
FROM   discovery_crm_productpricelevels ppl
JOIN   discovery_crm_pricelevels        pl  ON pl.pricelevelid = ppl.pricelevelid
WHERE  ppl.productid = %s
ORDER BY (pl.transactioncurrency_text = 'TL') DESC,
         ppl.amount DESC
LIMIT 1;
"""

# ---------------------------------------------------------------------------
# Currency exchange rates from CRM price levels (TL is the base / target).
# ---------------------------------------------------------------------------

LIST_EXCHANGE_RATES = """
SELECT transactioncurrency_text AS currency,
       MAX(exchangerate) FILTER (WHERE exchangerate IS NOT NULL AND exchangerate > 0) AS rate
FROM   discovery_crm_pricelevels
GROUP  BY transactioncurrency_text;
"""

# ---------------------------------------------------------------------------
# YTD realized sales total in TL (multi-currency aware on the caller side).
# ---------------------------------------------------------------------------

YTD_REALIZED_SALES = """
SELECT COALESCE(so.transactioncurrency_text, 'TL') AS currency,
       COALESCE(SUM(so.totalamount), 0)::double precision AS amount
FROM   discovery_crm_salesorders so
WHERE  so.statecode IN (3, 4)
  AND  EXTRACT(YEAR FROM COALESCE(so.fulfilldate, so.submitdate, so.modifiedon::date))
       = EXTRACT(YEAR FROM CURRENT_DATE)
GROUP  BY so.transactioncurrency_text;
"""

# ---------------------------------------------------------------------------
# Unmapped products counter (productids without a seed or override row).
# ---------------------------------------------------------------------------

UNMAPPED_PRODUCT_COUNT = """
SELECT COUNT(*)::bigint
FROM   discovery_crm_products pr
LEFT JOIN gui_crm_service_mapping_seed     s ON s.productid = pr.productid
LEFT JOIN gui_crm_service_mapping_override o ON o.productid = pr.productid
WHERE  s.productid IS NULL AND o.productid IS NULL;
"""

# ---------------------------------------------------------------------------
# Snapshot writer
# ---------------------------------------------------------------------------

INSERT_METRIC_SNAPSHOT = """
INSERT INTO gui_metric_snapshot (metric_key, scope_type, scope_id, value, unit, captured_at)
VALUES (%s, %s, %s, %s, %s, NOW())
ON CONFLICT (metric_key, scope_type, scope_id, captured_at) DO NOTHING;
"""

LIST_METRIC_SNAPSHOTS = """
SELECT metric_key, scope_type, scope_id, value, unit, captured_at
FROM   gui_metric_snapshot
WHERE  metric_key = %s
  AND  scope_id   = %s
  AND  captured_at >= NOW() - (%s || ' hours')::interval
ORDER BY captured_at;
"""

# ---------------------------------------------------------------------------
# Bulk-load queries — replace N per-panel round-trips with 3 single queries.
# Used by compute_all_panels to pre-fetch all metadata before the panel loop.
# ---------------------------------------------------------------------------

# Best-matching infra source per panel_key for a given dc_code.
# dc_code-specific rows win over wildcard ('*') rows (ORDER BY ... (dc_code='*') ASC → False < True).
BULK_INFRA_SOURCES_FOR_DC = """
SELECT DISTINCT ON (panel_key)
    panel_key, dc_code, source_table, total_column, total_unit,
    allocated_table, allocated_column, allocated_unit,
    filter_clause, notes
FROM   gui_panel_infra_source
WHERE  dc_code = %s OR dc_code = '*'
ORDER  BY panel_key, (dc_code = '*') ASC;
"""

# All threshold rows for a dc_code (Python replicates panel_key > resource_type precedence).
BULK_THRESHOLDS_FOR_DC = """
SELECT panel_key, resource_type, dc_code, sellable_limit_pct
FROM   gui_crm_threshold_config
WHERE  dc_code = %s OR dc_code = '*'
ORDER  BY (dc_code = '*') ASC;
"""

# Best price override per panel_key (catalog fallback is handled per-panel only when missing).
BULK_PRICE_OVERRIDES = """
SELECT DISTINCT ON (sp.panel_key)
    sp.panel_key,
    po.unit_price_tl
FROM   gui_crm_service_pages       sp
JOIN   gui_crm_service_mapping_seed sm  ON sm.page_key  = sp.page_key
LEFT   JOIN gui_crm_service_mapping_override ov
                                        ON ov.productid = sm.productid
JOIN   gui_crm_price_override       po
       ON po.productid = COALESCE(ov.productid, sm.productid)
WHERE  po.unit_price_tl IS NOT NULL
ORDER  BY sp.panel_key, po.updated_at DESC;
"""
