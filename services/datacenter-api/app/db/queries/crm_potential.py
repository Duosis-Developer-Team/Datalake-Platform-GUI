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
dc_capacity AS (
    SELECT
        d.site_name                        AS dc_name,
        SUM(dt.u_height)                   AS total_rack_units_used,
        COUNT(DISTINCT d.id)               AS device_count
    FROM   discovery_netbox_inventory_device d
    JOIN   discovery_netbox_inventory_device_type dt
           ON dt.id = d.device_type_id
    WHERE  d.site_name ILIKE %s
    GROUP BY d.site_name
),
dc_rack_capacity AS (
    SELECT
        r.site_name                        AS dc_name,
        SUM(r.u_height)                    AS total_rack_u,
        COUNT(DISTINCT r.id)               AS rack_count
    FROM   discovery_loki_racks r
    WHERE  r.site_name ILIKE %s
    GROUP BY r.site_name
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
    COALESCE(rc.total_rack_u, 0)               AS total_rack_u,
    COALESCE(cap.total_rack_units_used, 0)     AS used_rack_u,
    GREATEST(COALESCE(rc.total_rack_u, 0) - COALESCE(cap.total_rack_units_used, 0), 0) AS free_rack_u,
    COALESCE(va.allocated_vcpu, 0) + COALESCE(na.allocated_vcpu, 0)    AS total_allocated_vcpu,
    COALESCE(va.allocated_ram_gb, 0) + COALESCE(na.allocated_ram_gb, 0) AS total_allocated_ram_gb,
    tc.product_name,
    tc.unit,
    tc.unit_price_tl,
    tc.price_list
FROM tl_catalog tc
FULL JOIN dc_rack_capacity rc  ON TRUE
FULL JOIN dc_capacity cap      ON TRUE
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
