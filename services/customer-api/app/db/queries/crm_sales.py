# SQL queries for CRM sales data endpoints.
# All queries join via discovery_crm_customer_alias to resolve canonical_customer_key → CRM accountid.

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
ytd_revenue AS (
    SELECT COALESCE(SUM(i.totalamount), 0) AS ytd_revenue_total,
           COALESCE(COUNT(DISTINCT i.invoiceid), 0) AS invoice_count,
           MIN(i.transactioncurrency_text) AS currency
    FROM   discovery_crm_invoices i
    WHERE  i.customerid IN (SELECT crm_accountid FROM customer_ids)
      AND  i.statecode IN (0, 3)  -- Active or Paid
      AND  EXTRACT(YEAR FROM i.invoicedate) = EXTRACT(YEAR FROM CURRENT_DATE)
),
open_pipeline AS (
    SELECT COALESCE(SUM(o.estimatedvalue), 0) AS pipeline_value,
           COALESCE(COUNT(*), 0) AS opportunity_count
    FROM   discovery_crm_opportunities o
    WHERE  o.customerid IN (SELECT crm_accountid FROM customer_ids)
      AND  o.statecode = 0  -- Open
),
active_orders AS (
    SELECT COALESCE(COUNT(*), 0) AS active_order_count,
           COALESCE(SUM(so.totalamount), 0) AS active_order_value
    FROM   discovery_crm_salesorders so
    WHERE  so.customerid IN (SELECT crm_accountid FROM customer_ids)
      AND  so.statecode IN (0, 1)  -- Active, Submitted
),
active_contracts AS (
    SELECT COALESCE(COUNT(*), 0) AS active_contract_count,
           COALESCE(SUM(c.totalprice), 0) AS total_contract_value,
           COALESCE(
               SUM(CASE
                   WHEN c.billingfrequencycode = 1 THEN c.totalprice          -- Annual
                   WHEN c.billingfrequencycode = 3 THEN c.totalprice / 12.0   -- Monthly already
                   WHEN c.billingfrequencycode = 2 THEN c.totalprice / 4.0    -- Quarterly
                   ELSE 0
               END), 0
           ) AS estimated_mrr
    FROM   discovery_crm_contracts c
    WHERE  c.customerid IN (SELECT crm_accountid FROM customer_ids)
      AND  c.statecode = 0  -- Active
      AND  (c.expireson IS NULL OR c.expireson >= CURRENT_DATE)
)
SELECT
    ytd_revenue.ytd_revenue_total,
    ytd_revenue.invoice_count,
    ytd_revenue.currency,
    open_pipeline.pipeline_value,
    open_pipeline.opportunity_count,
    active_orders.active_order_count,
    active_orders.active_order_value,
    active_contracts.active_contract_count,
    active_contracts.total_contract_value,
    active_contracts.estimated_mrr
FROM ytd_revenue, open_pipeline, active_orders, active_contracts;
"""

# ---------------------------------------------------------------------------
# /customers/{name}/sales/items
# ---------------------------------------------------------------------------

SALES_ITEMS = """
SELECT
    'invoice'                          AS source_type,
    i.invoicenumber                    AS reference_number,
    i.invoicedate::TEXT                AS date,
    i.statecode_text                   AS status,
    d.product_name,
    d.productdescription,
    d.uomid_name                       AS unit,
    d.quantity,
    d.priceperunit                     AS unit_price,
    d.extendedamount                   AS line_total,
    i.transactioncurrency_text         AS currency
FROM   discovery_crm_invoicedetails d
JOIN   discovery_crm_invoices i ON i.invoiceid = d.invoiceid
WHERE  i.customerid IN (
           SELECT crm_accountid FROM discovery_crm_customer_alias
           WHERE canonical_customer_key = %s OR crm_account_name ILIKE %s
       )
  AND  i.statecode IN (0, 3)

UNION ALL

SELECT
    'salesorder'                       AS source_type,
    so.ordernumber                     AS reference_number,
    so.submitdate::TEXT                AS date,
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
  AND  so.statecode IN (0, 1, 3)  -- Active, Submitted, Fulfilled

ORDER BY date DESC NULLS LAST;
"""

# ---------------------------------------------------------------------------
# /customers/{name}/sales/efficiency
# ---------------------------------------------------------------------------
# Compares billed capacity (from invoicedetails/salesorderdetails quantity × unit)
# with actual utilization (from VM/compute tables joined via alias).

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
        i.transactioncurrency_text           AS currency
    FROM   discovery_crm_invoicedetails d
    JOIN   discovery_crm_invoices i ON i.invoiceid = d.invoiceid
    WHERE  i.customerid IN (SELECT crm_accountid FROM customer_ids)
      AND  i.statecode IN (0, 3)
    GROUP BY d.product_name, d.uomid_name, i.transactioncurrency_text
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
        WHEN cp.catalog_unit_price > 0
        THEN ROUND((b.total_billed_amount / (b.total_billed_qty * cp.catalog_unit_price) * 100)::numeric, 2)
        ELSE NULL
    END                                      AS catalog_coverage_pct
FROM billed_by_product b
LEFT JOIN catalog_prices cp
    ON  lower(trim(cp.product_name)) = lower(trim(b.product_name))
    AND lower(trim(cp.unit))         = lower(trim(b.unit))
ORDER BY b.total_billed_amount DESC NULLS LAST;
"""

# ---------------------------------------------------------------------------
# /customers/{name}/sales/catalog-valuation
# ---------------------------------------------------------------------------
# Estimates current resource value against the standard price catalog.

CATALOG_VALUATION = """
WITH customer_alias AS (
    SELECT netbox_musteri_value, canonical_customer_key
    FROM   discovery_crm_customer_alias
    WHERE  canonical_customer_key = %s OR crm_account_name ILIKE %s
    LIMIT  1
),
-- Standard TL price list as reference
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
