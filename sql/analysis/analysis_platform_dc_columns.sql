-- Analysis: Platform count and DC identifier consistency
-- Run these to verify Nutanix datacenter_name and VMware dc match your DC list (e.g. AZ11 vs Azerbaycan).
-- If Nutanix uses location name (e.g. Azerbaycan) and loki uses DC code (AZ11), the app maps via DC_LOCATIONS.

-- 1) Nutanix: distinct datacenter_name values (compare with loki DC list and DC_LOCATIONS)
SELECT DISTINCT datacenter_name
FROM public.nutanix_cluster_metrics
ORDER BY 1;

-- 2) VMware: distinct dc values (should match loki DC codes)
SELECT DISTINCT dc
FROM public.datacenter_metrics
ORDER BY 1;

-- 3) Per-DC platform-style counts for Nutanix (clusters per datacenter_name) — last 7 days
WITH latest AS (
    SELECT DISTINCT ON (cluster_name) datacenter_name, cluster_name
    FROM public.nutanix_cluster_metrics
    WHERE collection_time >= NOW() - INTERVAL '7 days'
    ORDER BY cluster_name, collection_time DESC
)
SELECT datacenter_name, COUNT(*) AS nutanix_platform_count
FROM latest
GROUP BY datacenter_name
ORDER BY 1;

-- 4) Per-DC platform-style counts for VMware (hypervisors per dc) — last 7 days
WITH latest_per_hypervisor AS (
    SELECT DISTINCT ON (dc, datacenter) dc, datacenter
    FROM public.datacenter_metrics
    WHERE timestamp >= NOW() - INTERVAL '7 days'
    ORDER BY dc, datacenter, timestamp DESC
)
SELECT dc, COUNT(*) AS vmware_platform_count
FROM latest_per_hypervisor
GROUP BY dc
ORDER BY 1;

-- 5) IBM: distinct DC codes extracted from server name (regex) — last 7 days
SELECT (regexp_matches(UPPER(server_details_servername), 'DC[0-9]+|AZ[0-9]+|ICT[0-9]+'))[1] AS dc_code,
       COUNT(DISTINCT server_details_servername) AS host_count
FROM public.ibm_server_general
WHERE time >= NOW() - INTERVAL '7 days'
GROUP BY 1
ORDER BY 1;
