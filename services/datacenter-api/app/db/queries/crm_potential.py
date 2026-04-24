# SQL queries for datacenter sales-potential endpoints.
# v1: catalog × coarse capacity rows (legacy).
# v2: realized CRM sales + 80%% sellable ceiling (ADR-0010).

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

DC_POTENTIAL_SUMMARY = """
WITH customer_in_dc AS (
    SELECT DISTINCT
        a.canonical_customer_key,
        a.crm_accountid
    FROM   discovery_netbox_virtualization_vm vm
    JOIN   discovery_crm_customer_alias a
           ON lower(trim(coalesce(a.netbox_musteri_value, ''))) = lower(trim(coalesce(vm.custom_fields_musteri, '')))
    WHERE  vm.site_name ILIKE %s
),
ytd_realized AS (
    SELECT
        COALESCE(SUM(so.totalamount), 0) AS total_billed_ytd,
        COUNT(DISTINCT so.salesorderid)  AS invoice_count
    FROM   discovery_crm_salesorders so
    WHERE  so.customerid IN (SELECT crm_accountid FROM customer_in_dc)
      AND  so.statecode IN (3, 4)
      AND  EXTRACT(YEAR FROM COALESCE(so.fulfilldate, so.submitdate, so.modifiedon::date))
           = EXTRACT(YEAR FROM CURRENT_DATE)
)
SELECT
    %s::TEXT                               AS dc_code,
    ytd.total_billed_ytd,
    ytd.invoice_count,
    0.0::double precision                  AS total_pipeline_value,
    0::bigint                              AS open_opportunity_count,
    (SELECT COUNT(DISTINCT crm_accountid) FROM customer_in_dc) AS customer_count
FROM ytd_realized ytd;
"""

# --- v2: physical-ish totals from latest Nutanix cluster metrics (per DC name) ---

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

DC_SOLD_VIRTUALIZATION_FOR_DC = """
WITH cust AS (
    SELECT DISTINCT a.crm_accountid
    FROM   discovery_netbox_virtualization_vm vm
    JOIN   discovery_crm_customer_alias a
           ON lower(trim(coalesce(a.netbox_musteri_value, ''))) = lower(trim(coalesce(vm.custom_fields_musteri, '')))
    WHERE  vm.site_name ILIKE %s
)
SELECT
    COALESCE(SUM(CASE WHEN lower(coalesce(m.resource_unit, d.uomid_name, '')) LIKE '%%vcpu%%'
                      OR lower(coalesce(m.resource_unit, d.uomid_name, '')) = 'vcpu'
                 THEN d.quantity ELSE 0 END), 0)::double precision AS sold_vcpu,
    COALESCE(SUM(CASE WHEN lower(coalesce(m.resource_unit, d.uomid_name, '')) LIKE '%%gb%%'
                      AND COALESCE(m.category_code, '') LIKE 'virt%%'
                 THEN d.quantity ELSE 0 END), 0)::double precision AS sold_ram_gb
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
JOIN   cust c ON so.customerid = c.crm_accountid
LEFT JOIN v_gui_crm_product_mapping m ON m.productid = d.productid
WHERE  so.statecode IN (3, 4)
  AND COALESCE(so.fulfilldate::date, so.submitdate::date, so.modifiedon::date)
      >= CURRENT_DATE - INTERVAL '12 months';
"""

DC_SOLD_BY_CATEGORY_FOR_DC = """
WITH cust AS (
    SELECT DISTINCT a.crm_accountid
    FROM   discovery_netbox_virtualization_vm vm
    JOIN   discovery_crm_customer_alias a
           ON lower(trim(coalesce(a.netbox_musteri_value, ''))) = lower(trim(coalesce(vm.custom_fields_musteri, '')))
    WHERE  vm.site_name ILIKE %s
)
SELECT
    COALESCE(m.category_code, 'other')     AS category_code,
    COALESCE(m.category_label, 'Other')   AS category_label,
    COALESCE(m.gui_tab_binding, 'other')   AS gui_tab_binding,
    COALESCE(NULLIF(TRIM(m.resource_unit), ''), NULLIF(TRIM(d.uomid_name), ''), 'Adet') AS resource_unit,
    SUM(d.quantity)::double precision        AS sold_qty,
    SUM(d.extendedamount)::double precision  AS sold_amount_tl
FROM   discovery_crm_salesorderdetails d
JOIN   discovery_crm_salesorders so ON so.salesorderid = d.salesorderid
JOIN   cust c ON so.customerid = c.crm_accountid
LEFT JOIN v_gui_crm_product_mapping m ON m.productid = d.productid
WHERE  so.statecode IN (3, 4)
  AND COALESCE(so.fulfilldate::date, so.submitdate::date, so.modifiedon::date)
      >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY COALESCE(m.category_code, 'other'),
         COALESCE(m.category_label, 'Other'),
         COALESCE(m.gui_tab_binding, 'other'),
         COALESCE(NULLIF(TRIM(m.resource_unit), ''), NULLIF(TRIM(d.uomid_name), ''), 'Adet')
ORDER BY sold_amount_tl DESC NULLS LAST;
"""

DC_CATALOG_AVG_UNIT_PRICE = """
SELECT COALESCE(AVG(ppl.amount), 0)::double precision
FROM   discovery_crm_productpricelevels ppl
JOIN   discovery_crm_pricelevels pl ON pl.pricelevelid = ppl.pricelevelid
WHERE  pl.name ILIKE '%%TL%%'
  AND  pl.statecode = 0
  AND  lower(coalesce(ppl.uomid_name, '')) LIKE %s;
"""
