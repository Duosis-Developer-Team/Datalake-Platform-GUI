# SQL queries for datacenter sales-potential endpoint.
# Computes idle/unallocated capacity per DC and multiplies by standard catalog unit prices.

DC_SALES_POTENTIAL = """
WITH
-- 1. Catalog standard unit prices (TL price list as reference)
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
-- 2. Per-DC compute capacity (from NetBox device inventory)
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
-- 3. Rack capacity per DC (from rack inventory)
dc_rack_capacity AS (
    SELECT
        r.site_name                        AS dc_name,
        SUM(r.u_height)                    AS total_rack_u,
        COUNT(DISTINCT r.id)               AS rack_count
    FROM   discovery_loki_racks r
    WHERE  r.site_name ILIKE %s
    GROUP BY r.site_name
),
-- 4. Allocated vCPU/RAM from VMware (customers using this DC)
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
-- 5. Allocated from Nutanix
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

# Simpler aggregated summary for the DC potential page hero stats
DC_POTENTIAL_SUMMARY = """
WITH customer_invoiced_by_dc AS (
    -- Customers with VMs in this DC (via NetBox site → customer alias)
    SELECT DISTINCT
        a.canonical_customer_key,
        a.crm_accountid
    FROM   discovery_netbox_virtualization_vm vm
    JOIN   discovery_crm_customer_alias a
           ON lower(trim(a.netbox_musteri_value)) = lower(trim(vm.custom_fields_musteri))
    WHERE  vm.site_name ILIKE %s
),
ytd_billed AS (
    SELECT
        COALESCE(SUM(i.totalamount), 0) AS total_billed_ytd,
        COUNT(DISTINCT i.invoiceid)     AS invoice_count
    FROM   discovery_crm_invoices i
    WHERE  i.customerid IN (SELECT crm_accountid FROM customer_invoiced_by_dc)
      AND  i.statecode IN (0, 3)
      AND  EXTRACT(YEAR FROM i.invoicedate) = EXTRACT(YEAR FROM CURRENT_DATE)
),
pipeline_by_dc AS (
    SELECT
        COALESCE(SUM(o.estimatedvalue), 0) AS total_pipeline_value,
        COUNT(*)                           AS open_opportunity_count
    FROM   discovery_crm_opportunities o
    WHERE  o.customerid IN (SELECT crm_accountid FROM customer_invoiced_by_dc)
      AND  o.statecode = 0
)
SELECT
    %s::TEXT                               AS dc_code,
    yb.total_billed_ytd,
    yb.invoice_count,
    pb.total_pipeline_value,
    pb.open_opportunity_count,
    (SELECT COUNT(DISTINCT crm_accountid) FROM customer_invoiced_by_dc) AS customer_count
FROM ytd_billed yb, pipeline_by_dc pb;
"""
