# SQL queries for CRM sales data endpoints.
# All queries join via discovery_crm_customer_alias to resolve canonical_customer_key → CRM accountid.
# Scope: realized sales orders only (statecode 3 Fulfilled, 4 Invoiced) — see ADR-0010.

CUSTOMER_ALIAS_SUBQUERY = """
    SELECT a.crm_accountid
    FROM   discovery_crm_customer_alias a
    WHERE  a.canonical_customer_key = %s
       OR  a.crm_account_name ILIKE %s
"""

# ---------------------------------------------------------------------------
# /customers/{name}/sales/summary
# ---------------------------------------------------------------------------

SALES_SUMMARY = """
WITH customer_ids AS (
    SELECT crm_accountid FROM discovery_crm_customer_alias
    WHERE canonical_customer_key = %s OR crm_account_name ILIKE %s
),
ytd_realized AS (
    SELECT COALESCE(SUM(so.totalamount), 0) AS ytd_revenue_total,
           COALESCE(COUNT(DISTINCT so.salesorderid), 0) AS ytd_order_count,
           MIN(so.transactioncurrency_text) AS currency
    FROM   discovery_crm_salesorders so
    WHERE  so.customerid IN (SELECT crm_accountid FROM customer_ids)
      AND  so.statecode IN (3, 4)
      AND  EXTRACT(YEAR FROM COALESCE(so.fulfilldate, so.submitdate, so.modifiedon::date))
           = EXTRACT(YEAR FROM CURRENT_DATE)
),
in_progress_orders AS (
    SELECT COALESCE(COUNT(*), 0) AS active_order_count,
           COALESCE(SUM(so.totalamount), 0) AS active_order_value
    FROM   discovery_crm_salesorders so
    WHERE  so.customerid IN (SELECT crm_accountid FROM customer_ids)
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
    so.transactioncurrency_text        AS currency
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
WHERE  so.customerid IN (
           SELECT crm_accountid FROM discovery_crm_customer_alias
           WHERE canonical_customer_key = %s OR crm_account_name ILIKE %s
       )
  AND  so.statecode IN (3, 4)
ORDER BY so.modifiedon DESC NULLS LAST, d.extendedamount DESC NULLS LAST;
"""

# ---------------------------------------------------------------------------
# /customers/{name}/sales/efficiency
# ---------------------------------------------------------------------------

SALES_EFFICIENCY = """
WITH customer_ids AS (
    SELECT crm_accountid FROM discovery_crm_customer_alias
    WHERE canonical_customer_key = %s OR crm_account_name ILIKE %s
),
billed_by_product AS (
    SELECT
        d.product_name,
        d.uomid_name                         AS unit,
        SUM(d.quantity)                      AS total_billed_qty,
        SUM(d.extendedamount)                AS total_billed_amount,
        so.transactioncurrency_text          AS currency
    FROM   discovery_crm_salesorderdetails d
    JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
    WHERE  so.customerid IN (SELECT crm_accountid FROM customer_ids)
      AND  so.statecode IN (3, 4)
    GROUP BY d.product_name, d.uomid_name, so.transactioncurrency_text
),
catalog_prices AS (
    SELECT
        p.name                               AS product_name,
        ppl.uomid_name                       AS unit,
        ppl.amount                           AS catalog_unit_price,
        pl.name                              AS price_list
    FROM   discovery_crm_productpricelevels ppl
    JOIN   discovery_crm_products p         ON p.productid = ppl.productid
    JOIN   discovery_crm_pricelevels pl     ON pl.pricelevelid = ppl.pricelevelid
    WHERE  pl.statecode = 0
)
SELECT
    b.product_name,
    b.unit,
    b.total_billed_qty,
    b.total_billed_amount,
    b.currency,
    cp.catalog_unit_price,
    cp.price_list,
    CASE
        WHEN cp.catalog_unit_price > 0 AND b.total_billed_qty > 0
        THEN ROUND((b.total_billed_amount / (b.total_billed_qty * cp.catalog_unit_price) * 100)::numeric, 2)
        ELSE NULL
    END                                      AS catalog_coverage_pct
FROM billed_by_product b
LEFT JOIN catalog_prices cp
    ON  lower(trim(cp.product_name)) = lower(trim(b.product_name))
    AND lower(trim(coalesce(cp.unit, ''))) = lower(trim(coalesce(b.unit, '')))
ORDER BY b.total_billed_amount DESC NULLS LAST;
"""

# ---------------------------------------------------------------------------
# /customers/{name}/sales/efficiency-by-category (sold side; usage merged in Python)
# ---------------------------------------------------------------------------

SALES_SOLD_BY_CATEGORY = """
WITH customer_ids AS (
    SELECT crm_accountid FROM discovery_crm_customer_alias
    WHERE canonical_customer_key = %s OR crm_account_name ILIKE %s
)
SELECT
    COALESCE(pca.category_code, 'other')     AS category_code,
    COALESCE(pca.category_label, 'Other')    AS category_label,
    COALESCE(pca.gui_tab_binding, 'other')   AS gui_tab_binding,
    COALESCE(NULLIF(TRIM(pca.resource_unit), ''), NULLIF(TRIM(d.uomid_name), ''), 'Adet') AS resource_unit,
    SUM(d.quantity)::double precision        AS sold_qty,
    SUM(d.extendedamount)::double precision    AS sold_amount_tl
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
JOIN   customer_ids c ON so.customerid = c.crm_accountid
LEFT JOIN discovery_crm_product_category_alias pca ON pca.productid = d.productid
WHERE  so.statecode IN (3, 4)
GROUP BY COALESCE(pca.category_code, 'other'),
         COALESCE(pca.category_label, 'Other'),
         COALESCE(pca.gui_tab_binding, 'other'),
         COALESCE(NULLIF(TRIM(pca.resource_unit), ''), NULLIF(TRIM(d.uomid_name), ''), 'Adet')
ORDER BY sold_amount_tl DESC NULLS LAST;
"""

# ---------------------------------------------------------------------------
# /customers/{name}/sales/catalog-valuation
# ---------------------------------------------------------------------------

CATALOG_VALUATION = """
WITH customer_alias AS (
    SELECT netbox_musteri_value, canonical_customer_key
    FROM   discovery_crm_customer_alias
    WHERE  canonical_customer_key = %s OR crm_account_name ILIKE %s
    LIMIT  1
),
tl_catalog AS (
    SELECT
        p.name         AS product_name,
        ppl.uomid_name AS unit,
        ppl.amount     AS unit_price_tl
    FROM   discovery_crm_productpricelevels ppl
    JOIN   discovery_crm_products p   ON p.productid = ppl.productid
    JOIN   discovery_crm_pricelevels pl ON pl.pricelevelid = ppl.pricelevelid
    WHERE  pl.name ILIKE '%%TL%%'
      AND  pl.statecode = 0
)
SELECT
    tc.product_name,
    tc.unit,
    tc.unit_price_tl,
    'catalog'          AS valuation_type
FROM tl_catalog tc
ORDER BY tc.product_name;
"""

# ---------------------------------------------------------------------------
# Customer alias management
# ---------------------------------------------------------------------------

GET_ALL_ALIASES = """
SELECT
    crm_accountid,
    crm_account_name,
    canonical_customer_key,
    netbox_musteri_value,
    notes,
    source,
    created_at,
    updated_at
FROM discovery_crm_customer_alias
ORDER BY crm_account_name;
"""

UPSERT_ALIAS = """
INSERT INTO discovery_crm_customer_alias
    (crm_accountid, crm_account_name, canonical_customer_key, netbox_musteri_value, notes, source, created_at, updated_at)
VALUES (%s, %s, %s, %s, %s, 'manual', now(), now())
ON CONFLICT (crm_accountid) DO UPDATE
    SET canonical_customer_key = EXCLUDED.canonical_customer_key,
        netbox_musteri_value   = EXCLUDED.netbox_musteri_value,
        notes                  = EXCLUDED.notes,
        source                 = 'manual',
        updated_at             = now();
"""

# ---------------------------------------------------------------------------
# Product category alias (GUI)
# ---------------------------------------------------------------------------

LIST_PRODUCT_CATEGORY_ALIASES = """
SELECT
    productid,
    product_name,
    category_code,
    category_label,
    gui_tab_binding,
    resource_unit,
    source,
    last_seeded_at,
    last_modified_at,
    notes
FROM discovery_crm_product_category_alias
ORDER BY product_name NULLS LAST, productid;
"""

UPDATE_PRODUCT_CATEGORY_ALIAS = """
UPDATE discovery_crm_product_category_alias
SET category_code = %s,
    category_label = %s,
    gui_tab_binding = %s,
    resource_unit = %s,
    notes = COALESCE(%s, notes),
    source = 'manual',
    last_modified_at = now()
WHERE productid = %s;
"""
