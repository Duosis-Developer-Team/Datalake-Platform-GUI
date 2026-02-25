# Customer (tenant) SQL query definitions
# Filter by VM/Host naming pattern (e.g. ILIKE '%boyner%')
# Sources: nutanix_cluster_metrics, datacenter_metrics, ibm_lpar_general, ibm_vios_general, ibm_server_general, vmhost_metrics

# --- Nutanix: cluster_name ILIKE pattern ---

# Global totals (one row: total_hosts, total_vms) for clusters matching pattern
NUTANIX_TOTALS = """
WITH latest AS (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        datacenter_name,
        num_nodes,
        total_vms
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name ILIKE %s
    ORDER BY cluster_name, collection_time DESC
)
SELECT COALESCE(SUM(num_nodes), 0) AS total_hosts, COALESCE(SUM(total_vms), 0) AS total_vms
FROM latest
"""

# Per-DC breakdown (datacenter_name, host_count, vm_count)
NUTANIX_BY_DC = """
WITH latest AS (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        datacenter_name,
        num_nodes,
        total_vms
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name ILIKE %s
    ORDER BY cluster_name, collection_time DESC
)
SELECT datacenter_name, SUM(num_nodes) AS host_count, SUM(total_vms) AS vm_count
FROM latest
GROUP BY datacenter_name
"""

# --- VMware: datacenter ILIKE pattern ---

# Global totals (one row: total_clusters, total_hosts, total_vms)
VMWARE_TOTALS = """
WITH latest AS (
    SELECT DISTINCT ON (datacenter)
        datacenter,
        total_cluster_count,
        total_host_count,
        total_vm_count
    FROM public.datacenter_metrics
    WHERE datacenter ILIKE %s
    ORDER BY datacenter, timestamp DESC
)
SELECT
    COALESCE(SUM(total_cluster_count), 0) AS total_clusters,
    COALESCE(SUM(total_host_count), 0) AS total_hosts,
    COALESCE(SUM(total_vm_count), 0) AS total_vms
FROM latest
"""

# Per-DC breakdown (datacenter, cluster_count, host_count, vm_count)
VMWARE_BY_DC = """
SELECT DISTINCT ON (datacenter)
    datacenter,
    total_cluster_count AS cluster_count,
    total_host_count AS host_count,
    total_vm_count AS vm_count
FROM public.datacenter_metrics
WHERE datacenter ILIKE %s
ORDER BY datacenter, timestamp DESC
"""

# --- IBM: LPAR name (VM), VIOS name, server name ILIKE pattern ---

# Total distinct LPARs (VMs) matching pattern
IBM_LPAR_TOTALS = """
SELECT COUNT(DISTINCT lparname) AS lpar_count
FROM public.ibm_lpar_general
WHERE lparname ILIKE %s
"""

# Total distinct VIOS matching pattern (by VIOS name or server name)
IBM_VIOS_TOTALS = """
SELECT COUNT(DISTINCT viosname) AS vios_count
FROM public.ibm_vios_general
WHERE viosname ILIKE %s OR vios_details_servername ILIKE %s
"""

# Total distinct IBM servers (hosts) matching pattern
IBM_HOST_TOTALS = """
SELECT COUNT(DISTINCT server_details_servername) AS host_count
FROM public.ibm_server_general
WHERE server_details_servername ILIKE %s
"""

# Per-server breakdown - caller maps server_name to DC
IBM_HOST_BY_SERVER = """
SELECT server_details_servername AS server_name, COUNT(*) AS host_count
FROM public.ibm_server_general
WHERE server_details_servername ILIKE %s
GROUP BY server_details_servername
"""
IBM_VIOS_BY_SERVER = """
SELECT vios_details_servername AS server_name, COUNT(DISTINCT viosname) AS vios_count
FROM public.ibm_vios_general
WHERE viosname ILIKE %s OR vios_details_servername ILIKE %s
GROUP BY vios_details_servername
"""
IBM_LPAR_BY_SERVER = """
SELECT lpar_details_servername AS server_name, COUNT(DISTINCT lparname) AS lpar_count
FROM public.ibm_lpar_general
WHERE lparname ILIKE %s
GROUP BY lpar_details_servername
"""

# --- vCenter: vmhost ILIKE pattern ---

# Total distinct hosts matching pattern
VCENTER_HOST_TOTALS = """
SELECT COUNT(DISTINCT vmhost) AS host_count
FROM public.vmhost_metrics
WHERE vmhost ILIKE %s
"""

# Per-host (vmhost) - caller maps hostname to DC
VCENTER_BY_HOST = """
SELECT DISTINCT ON (vmhost) vmhost, power_usage
FROM public.vmhost_metrics
WHERE vmhost ILIKE %s
ORDER BY vmhost, "timestamp" DESC
"""
