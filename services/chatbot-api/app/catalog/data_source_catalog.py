"""Data source catalog — maps business concepts to existing service/tool surfaces.

Compact: the exact endpoints live in tool_registry / api_clients; this is for
planning and explanation only. Reconciled against the repo (repo = source of
truth): every tool here exists in tool_registry, every table exists in the DB.
"""

from __future__ import annotations

API_TOOL_TO_ENDPOINT = {
    "get_dashboard_overview": "datacenter-api:/api/v1/dashboard/overview",
    "get_datacenters_summary": "datacenter-api:/api/v1/datacenters/summary",
    "get_datacenter_detail": "datacenter-api:/api/v1/datacenters/{dc_code}",
    "get_sla": "datacenter-api:/api/v1/sla",
    "get_dc_classic_clusters": "datacenter-api:/api/v1/datacenters/{dc_code}/clusters/classic",
    "get_dc_hyperconverged_clusters": "datacenter-api:/api/v1/datacenters/{dc_code}/clusters/hyperconverged",
    "get_dc_compute_classic": "datacenter-api:/api/v1/datacenters/{dc_code}/compute/classic",
    "get_dc_compute_hyperconverged": "datacenter-api:/api/v1/datacenters/{dc_code}/compute/hyperconverged",
    "get_dc_storage_capacity": "datacenter-api:/api/v1/datacenters/{dc_code}/storage/capacity",
    "get_dc_storage_performance": "datacenter-api:/api/v1/datacenters/{dc_code}/storage/performance",
    "get_dc_zabbix_storage_trend": "datacenter-api:/api/v1/datacenters/{dc_code}/zabbix-storage/trend",
    "get_dc_network_summary": "datacenter-api:/api/v1/datacenters/{dc_code}/network/port-summary",
    "get_dc_backup_summary": "datacenter-api:/api/v1/datacenters/{dc_code}/backup/{vendor}",
    "get_dc_backup_jobs": "datacenter-api:/api/v1/datacenters/{dc_code}/backup/{vendor}/jobs",
    "get_dc_s3_pools": "datacenter-api:/api/v1/datacenters/{dc_code}/s3/pools",
    "get_customer_resources": "customer-api:/api/v1/customers/{customer_name}/resources",
    "get_customer_s3_vaults": "customer-api:/api/v1/customers/{customer_name}/s3/vaults",
    "get_sellable_summary": "crm-engine:/api/v1/crm/sellable-potential/summary",
}

DB_TOOL_TO_QUERY_KEY = {
    "get_dc_host_cpu_latest": "db_get_dc_host_cpu_latest",
    "get_dc_host_cpu_top": "db_get_dc_host_cpu_top",
    "get_dc_host_cpu_summary": "db_get_dc_host_cpu_summary",
    "get_dc_vm_cpu_top": "db_get_dc_vm_cpu_top",
    "get_dc_vm_cpu_latest": "db_get_dc_vm_cpu_latest",
    "get_dc_vm_cpu_summary": "db_get_dc_vm_cpu_summary",
    "get_dc_classic_host_cpu_allocation_variability": "db_get_dc_classic_host_cpu_allocation_variability",
}

# Tables verified to exist in the DB. (vmware_cluster_metrics does NOT exist —
# use cluster_metrics / vmware_host_metrics instead.)
PROVIDER_TABLES = {
    "classic": ["datacenter_metrics", "cluster_metrics", "vmware_host_metrics",
                "vmhost_metrics", "vmware_host_performance_metrics", "vmware_vm_performance_metrics"],
    "hyperconverged": ["nutanix_cluster_metrics", "nutanix_host_performance_metrics",
                       "nutanix_vm_performance_metrics", "nutanix_vm_metrics"],
    "power": ["ibm_server_general", "ibm_lpar_general", "ibm_lpar_performance_metrics", "ibm_vios_general"],
    "s3": ["S3 pool/vault tables via API"],
    "backup": ["NetBackup/Zerto/Veeam job and repo tables via API"],
    "crm": ["gui_*", "discovery_crm_*", "crm mapping/config tables"],
}


def db_tool_keys() -> set[str]:
    return set(DB_TOOL_TO_QUERY_KEY)


def api_tool_keys() -> set[str]:
    return set(API_TOOL_TO_ENDPOINT)
