# SQL queries for datacenter sales-potential endpoints.
#
# After the WebUI App DB split:
#   - Customer alias resolution and product->category mapping live in webui-db.
#   - Sales-potential computations join those mappings in the application layer.
#   - These queries return raw datalake-side rows keyed by productid / accountid.
#
# v1: catalog × coarse capacity rows (legacy, kept for backwards compatibility).
# v2: realized CRM sales + sellable ceilings from gui_crm_threshold_config (ADR-0010).

# ---------------------------------------------------------------------------
# Distinct NetBox tenant values for VMs in a DC (input for alias resolution).
# ---------------------------------------------------------------------------

DC_TENANT_VALUES = """
SELECT DISTINCT lower(trim(coalesce(vm.custom_fields_musteri, ''))) AS tenant_value
FROM   discovery_netbox_virtualization_vm vm
WHERE  vm.site_name ILIKE %s
  AND  vm.custom_fields_musteri IS NOT NULL
  AND  trim(vm.custom_fields_musteri) <> '';
"""

# ---------------------------------------------------------------------------
# Per-DC YTD billing summary (alias resolution done in Python).
# Pass an array of CRM accountids that map to this DC's tenants.
# ---------------------------------------------------------------------------

DC_POTENTIAL_SUMMARY = """
WITH ytd_realized AS (
    SELECT COALESCE(SUM(so.totalamount), 0) AS total_billed_ytd,
           COUNT(DISTINCT so.salesorderid)  AS invoice_count
    FROM   discovery_crm_salesorders so
    WHERE  so.customerid = ANY(%s)
      AND  so.statecode IN (3, 4)
      AND  EXTRACT(YEAR FROM COALESCE(so.fulfilldate, so.submitdate, so.modifiedon::date))
           = EXTRACT(YEAR FROM CURRENT_DATE)
)
SELECT
    %s::TEXT                            AS dc_code,
    ytd.total_billed_ytd,
    ytd.invoice_count,
    0.0::double precision               AS total_pipeline_value,
    0::bigint                           AS open_opportunity_count,
    cardinality(%s::text[])             AS customer_count
FROM ytd_realized ytd;
"""

# ---------------------------------------------------------------------------
# Sold totals by raw productid for a DC's resolved customers.
# Mapping productid -> category is applied in Python from webui-db.
# ---------------------------------------------------------------------------

DC_SOLD_RAW_BY_PRODUCT_FOR_DC = """
SELECT
    d.productid,
    d.product_name,
    COALESCE(NULLIF(TRIM(d.uomid_name), ''), 'Adet') AS resource_unit,
    SUM(d.quantity)::double precision      AS sold_qty,
    SUM(d.extendedamount)::double precision AS sold_amount_tl
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
WHERE  so.customerid = ANY(%s)
  AND  so.statecode IN (3, 4)
  AND  COALESCE(so.fulfilldate::date, so.submitdate::date, so.modifiedon::date)
       >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY d.productid, d.product_name, COALESCE(NULLIF(TRIM(d.uomid_name), ''), 'Adet')
ORDER BY sold_amount_tl DESC NULLS LAST;
"""

# Licensed-OS attribution needs the quantity kept per CRM account (so it can be
# split across the DCs that account occupies), and uses the entitlement baseline
# statecode 0,1,3,4 — every order in production currently sits at 0, so the
# 12-month realized filter above would return nothing. Matches the baseline
# customer-api /sales/resource-compliance uses (ADR-0016).
# Params: (accountids[],)
SOLD_QTY_BY_ACCOUNT_AND_PRODUCT = """
SELECT so.customerid,
       d.productid,
       SUM(d.quantity)::double precision AS sold_qty
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
WHERE  so.customerid = ANY(%s)
  AND  so.statecode IN (0, 1, 3, 4)
  AND  so.ordernumber LIKE 'PRJ-%%'
GROUP BY so.customerid, d.productid;
"""

# ---------------------------------------------------------------------------
# Nutanix capacity proxy per DC name (unchanged).
# ---------------------------------------------------------------------------

DC_NUTANIX_CLUSTER_CAPACITY = """
WITH latest AS (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        datacenter_name,
        total_cpu_capacity,
        total_memory_capacity
    FROM   nutanix_cluster_metrics
    WHERE  datacenter_name ILIKE %s
      AND  collection_time >= NOW() - INTERVAL '7 days'
    ORDER BY cluster_name, collection_time DESC
)
SELECT
    COALESCE(SUM(total_cpu_capacity), 0)::double precision   AS total_cpu_capacity,
    COALESCE(SUM(total_memory_capacity), 0)::double precision / 1073741824.0 AS total_memory_gb
FROM latest;
"""

# ---------------------------------------------------------------------------
# Catalog price fallback (kept; production may stay empty).
# Average price for unit pattern; gui_crm_price_override is the primary source.
# ---------------------------------------------------------------------------

DC_CATALOG_AVG_UNIT_PRICE = """
SELECT COALESCE(AVG(ppl.amount), 0)::double precision
FROM   discovery_crm_productpricelevels ppl
JOIN   discovery_crm_pricelevels pl ON pl.pricelevelid = ppl.pricelevelid
WHERE  pl.name ILIKE '%%TL%%'
  AND  pl.statecode = 0
  AND  lower(coalesce(ppl.uomid_name, '')) LIKE %s;
"""

# ---------------------------------------------------------------------------
# Legacy v1 catalog × capacity (kept for /sales-potential v1 endpoint).
#
# NOTE: the rack-capacity CTEs (dc_capacity / dc_rack_capacity) were removed —
# they referenced discovery_loki_racks (plural) and
# discovery_netbox_inventory_device_type, neither of which exist in the
# database, so total_rack_u/used_rack_u/free_rack_u were always broken.
# Plan A supersedes rack capacity/used math with shared/colocation/occupancy.py
# + DatabaseService.get_colocation_aggregate(); this v1 endpoint has no
# remaining callers (see task/architecture-audit-2026-05-12/gaps_and_actions.md
# M-01) so the columns are dropped rather than repointed.
# ---------------------------------------------------------------------------

DC_SALES_POTENTIAL = """
WITH
tl_catalog AS (
    SELECT
        p.name           AS product_name,
        ppl.uomid_name   AS unit,
        ppl.amount       AS unit_price_tl,
        pl.name          AS price_list
    FROM   discovery_crm_productpricelevels ppl
    JOIN   discovery_crm_products p   ON p.productid  = ppl.productid
    JOIN   discovery_crm_pricelevels pl ON pl.pricelevelid = ppl.pricelevelid
    WHERE  pl.name ILIKE '%%TL%%'
      AND  pl.statecode = 0
      AND  p.statecode  = 0
),
dc_allocated_vmware AS (
    SELECT
        vm.datacenter_name                 AS dc_name,
        COALESCE(SUM(vm.number_of_cpus), 0)       AS allocated_vcpu,
        COALESCE(SUM(vm.memory_mb / 1024.0), 0)   AS allocated_ram_gb
    FROM   vm_metrics vm
    WHERE  vm.datacenter_name ILIKE %s
      AND  vm.timestamp >= NOW() - INTERVAL '2 hours'
    GROUP BY vm.datacenter_name
),
dc_allocated_nutanix AS (
    SELECT
        n.cluster_name                         AS dc_name,
        COALESCE(SUM(n.cpu_count), 0)          AS allocated_vcpu,
        COALESCE(SUM(n.memory_size_bytes / 1073741824.0), 0) AS allocated_ram_gb
    FROM   nutanix_vm_metrics n
    WHERE  n.cluster_name ILIKE %s
      AND  n.collection_time >= NOW() - INTERVAL '2 hours'
    GROUP BY n.cluster_name
)
SELECT
    %s::TEXT                                   AS dc_code,
    COALESCE(va.allocated_vcpu, 0) + COALESCE(na.allocated_vcpu, 0)    AS total_allocated_vcpu,
    COALESCE(va.allocated_ram_gb, 0) + COALESCE(na.allocated_ram_gb, 0) AS total_allocated_ram_gb,
    tc.product_name,
    tc.unit,
    tc.unit_price_tl,
    tc.price_list
FROM tl_catalog tc
LEFT JOIN dc_allocated_vmware va ON va.dc_name ILIKE %s
LEFT JOIN dc_allocated_nutanix na ON na.dc_name ILIKE %s
ORDER BY tc.product_name NULLS LAST;
"""

# ---------------------------------------------------------------------------
# Webui-side: alias rows that map to a tenant value list (executed against webui-db).
# ---------------------------------------------------------------------------

WEBUI_ALIAS_ACCOUNTIDS_FOR_TENANTS = """
SELECT crm_accountid
FROM   gui_crm_customer_alias
WHERE  lower(trim(coalesce(netbox_musteri_value, ''))) = ANY(%s);
"""

# Same lookup, but keeps the tenant value so the caller can map a CRM account back
# to the NetBox tenant it came from. Needed when quantities have to be attributed
# per tenant (licensed-OS DC allocation), not just summed across a DC.
WEBUI_ALIAS_ACCOUNTS_WITH_TENANT = """
SELECT crm_accountid,
       lower(trim(coalesce(netbox_musteri_value, ''))) AS tenant_value
FROM   gui_crm_customer_alias
WHERE  lower(trim(coalesce(netbox_musteri_value, ''))) = ANY(%s);
"""

# productid -> page_key, operator override winning over the generated seed.
WEBUI_PRODUCT_PAGE_KEYS = """
SELECT COALESCE(o.productid, s.productid)          AS productid,
       COALESCE(o.page_key, s.page_key, 'other')   AS page_key
FROM       gui_crm_service_mapping_seed s
FULL JOIN  gui_crm_service_mapping_override o ON o.productid = s.productid;
"""

WEBUI_RESOLVE_ACCOUNTID_BY_DISPLAY_NAME = """
SELECT crm_accountid,
       crm_account_name
FROM   gui_crm_customer_alias
WHERE  crm_account_name ILIKE %s
   OR  canonical_customer_key = %s
ORDER BY CASE WHEN crm_account_name ILIKE %s THEN 0 ELSE 1 END
LIMIT 1;
"""

WEBUI_PHYSICAL_MAPPINGS_FOR_ACCOUNT = """
SELECT match_method,
       match_value,
       enabled,
       priority
FROM   gui_crm_customer_source_mapping
WHERE  crm_accountid = %s
  AND data_source = 'physical_device'
  AND enabled = TRUE
ORDER BY priority, id;
"""

# CRM accounts that have at least one project order — the candidate set for
# tenant name matching when no manual alias exists.
CRM_PROJECT_ACCOUNTS = """
SELECT DISTINCT a.accountid, a.name
FROM   discovery_crm_accounts a
JOIN   discovery_crm_salesorders so ON so.customerid = a.accountid
WHERE  so.ordernumber LIKE 'PRJ-%%'
  AND  TRIM(COALESCE(a.name, '')) <> '';
"""

# Weighted unit price per product across every customer, from real orders.
# discovery_crm_productpricelevels (the catalog) is empty in production, so what
# people actually paid is the only price source. Live 2026-07-27:
# MS Windows Lisans 446.63 TL/VM, SUSE Lisans Bedeli 5,238.76 TL.
# Amounts are converted to TL first. `extendedamount` is stored in the ORDER's
# currency, and the same product is sold in more than one: MS Windows Lisans has
# 287 TL lines, 7 USD and 2 EUR (2026-07-27). Summing them raw produced 446.63
# "TL"; converting via the Dynamics rate (TL = amount / exchangerate) gives the
# real 471.41 TL. The inner join drops lines whose currency has no active rate —
# a line we cannot convert must not be averaged in as if it were TL.
PLATFORM_UNIT_PRICE_BY_PRODUCT = """
WITH fx AS (
    SELECT DISTINCT ON (transactioncurrency_text)
           transactioncurrency_text AS ccy,
           NULLIF(exchangerate, 0)  AS rate
    FROM   discovery_crm_pricelevels
    WHERE  statecode = 0
    ORDER BY transactioncurrency_text, modifiedon DESC
)
SELECT d.productid,
       (SUM(d.extendedamount / fx.rate) / NULLIF(SUM(d.quantity), 0))::double precision AS unit_price_tl
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
JOIN   fx ON fx.ccy = d.transactioncurrency_text
WHERE  so.statecode IN (0, 1, 3, 4)
  AND  so.ordernumber LIKE 'PRJ-%%'
  AND  d.quantity > 0
GROUP BY d.productid
HAVING SUM(d.quantity) > 0;
"""
