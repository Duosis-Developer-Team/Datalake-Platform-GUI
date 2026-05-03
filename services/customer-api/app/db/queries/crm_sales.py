# SQL queries for CRM sales endpoints — datalake DB only (raw discovery_crm_*).
# Customer alias resolution and product->category mapping live in webui-db and are
# resolved in the service layer; queries here accept already-resolved CRM
# accountid lists (parameterised as text[]).
# Scope: realized sales orders only (statecode 3 Fulfilled, 4 Invoiced) — see ADR-0010.

# ---------------------------------------------------------------------------
# /customers/{name}/sales/summary
# ---------------------------------------------------------------------------

SALES_SUMMARY = """
WITH ytd_realized AS (
    SELECT COALESCE(SUM(so.totalamount), 0) AS ytd_revenue_total,
           COALESCE(COUNT(DISTINCT so.salesorderid), 0) AS ytd_order_count,
           MIN(so.transactioncurrency_text) AS currency
    FROM   discovery_crm_salesorders so
    WHERE  so.customerid = ANY(%s)
      AND  so.statecode IN (3, 4)
      AND  EXTRACT(YEAR FROM COALESCE(so.fulfilldate, so.submitdate, so.modifiedon::date))
           = EXTRACT(YEAR FROM CURRENT_DATE)
),
in_progress_orders AS (
    SELECT COALESCE(COUNT(*), 0) AS active_order_count,
           COALESCE(SUM(so.totalamount), 0) AS active_order_value
    FROM   discovery_crm_salesorders so
    WHERE  so.customerid = ANY(%s)
      AND  so.statecode IN (0, 1)
)
SELECT
    ytd_realized.ytd_revenue_total,
    ytd_realized.ytd_order_count,
    ytd_realized.currency,
    0.0::double precision AS pipeline_value,
    0::bigint AS opportunity_count,
    in_progress_orders.active_order_count,
    in_progress_orders.active_order_value,
    0::bigint AS active_contract_count,
    0.0::double precision AS total_contract_value,
    0.0::double precision AS estimated_mrr
FROM ytd_realized, in_progress_orders;
"""

# ---------------------------------------------------------------------------
# /customers/{name}/sales/items
# ---------------------------------------------------------------------------

SALES_ITEMS = """
SELECT
    'salesorder'                       AS source_type,
    so.ordernumber                     AS reference_number,
    COALESCE(so.fulfilldate::text, so.submitdate::text, so.modifiedon::text) AS date,
    so.statecode_text                  AS status,
    d.product_name,
    d.productdescription,
    d.uomid_name                       AS unit,
    d.quantity,
    d.priceperunit                     AS unit_price,
    d.extendedamount                   AS line_total,
    so.transactioncurrency_text        AS currency,
    d.productid                        AS productid
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
WHERE  so.customerid = ANY(%s)
  AND  so.statecode IN (3, 4)
ORDER BY so.modifiedon DESC NULLS LAST, d.extendedamount DESC NULLS LAST;
"""

# ---------------------------------------------------------------------------
# /customers/{name}/sales/efficiency — billed quantities by product, no catalog join
# (catalog price comes from gui_crm_price_override + discovery_crm_productpricelevels
#  resolved in the service layer; productpricelevels is currently empty in production).
# ---------------------------------------------------------------------------

SALES_EFFICIENCY_BILLED = """
SELECT
    d.productid,
    d.product_name,
    d.uomid_name                         AS unit,
    SUM(d.quantity)                      AS total_billed_qty,
    SUM(d.extendedamount)                AS total_billed_amount,
    MIN(so.transactioncurrency_text)     AS currency
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
WHERE  so.customerid = ANY(%s)
  AND  so.statecode IN (3, 4)
GROUP BY d.productid, d.product_name, d.uomid_name
ORDER BY total_billed_amount DESC NULLS LAST;
"""

# Optional fallback: catalog rows if the price-level table is populated. Service layer
# uses gui_crm_price_override first; this query is the secondary source for completeness.
SALES_CATALOG_PRICES = """
SELECT
    p.productid,
    p.name                 AS product_name,
    ppl.uomid_name         AS unit,
    ppl.amount             AS catalog_unit_price,
    pl.name                AS price_list
FROM   discovery_crm_productpricelevels ppl
JOIN   discovery_crm_products p     ON p.productid = ppl.productid
JOIN   discovery_crm_pricelevels pl ON pl.pricelevelid = ppl.pricelevelid
WHERE  pl.statecode = 0;
"""

# ---------------------------------------------------------------------------
# /customers/{name}/sales/efficiency-by-category (sold side, raw by productid)
# Mapping productid -> category lives in webui-db and is applied in Python.
# ---------------------------------------------------------------------------

SALES_SOLD_RAW_BY_PRODUCT = """
SELECT
    d.productid,
    d.product_name,
    COALESCE(NULLIF(TRIM(d.uomid_name), ''), 'Adet') AS resource_unit,
    SUM(d.quantity)::double precision     AS sold_qty,
    SUM(d.extendedamount)::double precision AS sold_amount_tl
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
WHERE  so.customerid = ANY(%s)
  AND  so.statecode IN (3, 4)
GROUP BY d.productid, d.product_name, COALESCE(NULLIF(TRIM(d.uomid_name), ''), 'Adet')
ORDER BY sold_amount_tl DESC NULLS LAST;
"""

# ---------------------------------------------------------------------------
# Full CRM product list (for service mapping page and price override dropdowns).
# ---------------------------------------------------------------------------

ALL_PRODUCTS = """
SELECT
    productid,
    name                AS product_name,
    productnumber       AS product_number,
    defaultuomid_name   AS default_unit
FROM   discovery_crm_products
ORDER BY name NULLS LAST, productid;
"""

# ---------------------------------------------------------------------------
# Discovery counts for the CRM Overview page (raw datalake tables).
# ---------------------------------------------------------------------------

DISCOVERY_TABLE_COUNTS = """
SELECT 'discovery_crm_accounts' AS table_name,
       (SELECT COUNT(*) FROM discovery_crm_accounts) AS row_count,
       (SELECT MAX(collection_time) FROM discovery_crm_accounts) AS last_collected
UNION ALL
SELECT 'discovery_crm_products',
       (SELECT COUNT(*) FROM discovery_crm_products),
       (SELECT MAX(collection_time) FROM discovery_crm_products)
UNION ALL
SELECT 'discovery_crm_pricelevels',
       (SELECT COUNT(*) FROM discovery_crm_pricelevels),
       (SELECT MAX(collection_time) FROM discovery_crm_pricelevels)
UNION ALL
SELECT 'discovery_crm_productpricelevels',
       (SELECT COUNT(*) FROM discovery_crm_productpricelevels),
       (SELECT MAX(collection_time) FROM discovery_crm_productpricelevels)
UNION ALL
SELECT 'discovery_crm_salesorders',
       (SELECT COUNT(*) FROM discovery_crm_salesorders),
       (SELECT MAX(collection_time) FROM discovery_crm_salesorders)
UNION ALL
SELECT 'discovery_crm_salesorderdetails',
       (SELECT COUNT(*) FROM discovery_crm_salesorderdetails),
       (SELECT MAX(collection_time) FROM discovery_crm_salesorderdetails);
"""
