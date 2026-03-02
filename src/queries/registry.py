# Query Registry — central catalog of all available SQL queries.
# To add a new query for a future dashboard, register it here.
# The db_service uses this registry for dynamic query execution.

from src.queries import nutanix, vmware, ibm, energy, customer, intel_dc

# Schema for each entry:
#   sql           : SQL string (from the provider module)
#   source        : DB table name (informational)
#   result_type   : "value" | "row" | "rows"
#   params_style  : "wildcard"  → caller passes f"%{dc_code}%"
#                   "exact"     → caller passes dc_code as-is
#                   "array_wildcard" → caller passes list of wildcard patterns
#                   "array_exact"    → caller passes list of exact DC codes
#   provider      : "nutanix" | "vmware" | "ibm" | "energy" | "customer"
#   batch_key     : column name to map rows back to DC code (batch queries only)

QUERY_REGISTRY: dict[str, dict] = {
    # --- Nutanix (individual) ---
    "nutanix_host_count": {
        "sql": nutanix.HOST_COUNT,
        "source": "nutanix_cluster_metrics",
        "result_type": "value",
        "params_style": "wildcard",
        "provider": "nutanix",
    },
    "nutanix_memory": {
        "sql": nutanix.MEMORY,
        "source": "nutanix_cluster_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "nutanix",
    },
    "nutanix_storage": {
        "sql": nutanix.STORAGE,
        "source": "nutanix_cluster_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "nutanix",
    },
    "nutanix_cpu": {
        "sql": nutanix.CPU,
        "source": "nutanix_cluster_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "nutanix",
    },
    # --- Nutanix (batch) ---
    "nutanix_batch_host_count": {
        "sql": nutanix.BATCH_HOST_COUNT,
        "source": "nutanix_cluster_metrics",
        "result_type": "rows",
        "params_style": "array_exact",
        "provider": "nutanix",
        "batch_key": "cluster_name",
    },
    "nutanix_batch_memory": {
        "sql": nutanix.BATCH_MEMORY,
        "source": "nutanix_cluster_metrics",
        "result_type": "rows",
        "params_style": "array_exact",
        "provider": "nutanix",
        "batch_key": "cluster_name",
    },
    "nutanix_batch_storage": {
        "sql": nutanix.BATCH_STORAGE,
        "source": "nutanix_cluster_metrics",
        "result_type": "rows",
        "params_style": "array_exact",
        "provider": "nutanix",
        "batch_key": "cluster_name",
    },
    "nutanix_batch_cpu": {
        "sql": nutanix.BATCH_CPU,
        "source": "nutanix_cluster_metrics",
        "result_type": "rows",
        "params_style": "array_exact",
        "provider": "nutanix",
        "batch_key": "cluster_name",
    },
    # --- VMware (individual) ---
    "vmware_counts": {
        "sql": vmware.COUNTS,
        "source": "datacenter_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "vmware",
    },
    "vmware_memory": {
        "sql": vmware.MEMORY,
        "source": "datacenter_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "vmware",
    },
    "vmware_storage": {
        "sql": vmware.STORAGE,
        "source": "datacenter_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "vmware",
    },
    "vmware_cpu": {
        "sql": vmware.CPU,
        "source": "datacenter_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "vmware",
    },
    # --- VMware (batch) ---
    "vmware_batch_counts": {
        "sql": vmware.BATCH_COUNTS,
        "source": "datacenter_metrics",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "vmware",
        "batch_key": "datacenter",
    },
    "vmware_batch_memory": {
        "sql": vmware.BATCH_MEMORY,
        "source": "datacenter_metrics",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "vmware",
        "batch_key": "datacenter",
    },
    "vmware_batch_storage": {
        "sql": vmware.BATCH_STORAGE,
        "source": "datacenter_metrics",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "vmware",
        "batch_key": "datacenter",
    },
    "vmware_batch_cpu": {
        "sql": vmware.BATCH_CPU,
        "source": "datacenter_metrics",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "vmware",
        "batch_key": "datacenter",
    },
    # --- IBM Power (individual) ---
    "ibm_host_count": {
        "sql": ibm.HOST_COUNT,
        "source": "ibm_server_general",
        "result_type": "value",
        "params_style": "wildcard",
        "provider": "ibm",
    },
    "ibm_vios_count": {
        "sql": ibm.VIOS_COUNT,
        "source": "ibm_vios_general",
        "result_type": "value",
        "params_style": "wildcard",
        "provider": "ibm",
    },
    "ibm_lpar_count": {
        "sql": ibm.LPAR_COUNT,
        "source": "ibm_lpar_general",
        "result_type": "value",
        "params_style": "wildcard",
        "provider": "ibm",
    },
    "ibm_memory": {
        "sql": ibm.MEMORY,
        "source": "ibm_server_general",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "ibm",
    },
    "ibm_cpu": {
        "sql": ibm.CPU,
        "source": "ibm_server_general",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "ibm",
    },
    # --- IBM Power (batch) ---
    "ibm_batch_host_count": {
        "sql": ibm.BATCH_HOST_COUNT,
        "source": "ibm_server_general",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "ibm",
        "batch_key": "server_details_servername",
    },
    "ibm_batch_vios_count": {
        "sql": ibm.BATCH_VIOS_COUNT,
        "source": "ibm_vios_general",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "ibm",
        "batch_key": "vios_details_servername",
    },
    "ibm_batch_lpar_count": {
        "sql": ibm.BATCH_LPAR_COUNT,
        "source": "ibm_lpar_general",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "ibm",
        "batch_key": "lpar_details_servername",
    },
    "ibm_batch_memory": {
        "sql": ibm.BATCH_MEMORY,
        "source": "ibm_server_general",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "ibm",
        "batch_key": "server_details_servername",
    },
    "ibm_batch_cpu": {
        "sql": ibm.BATCH_CPU,
        "source": "ibm_server_general",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "ibm",
        "batch_key": "server_details_servername",
    },
    # --- Energy (individual) ---
    "energy_ibm": {
        "sql": energy.IBM,
        "source": "ibm_server_power",
        "result_type": "value",
        "params_style": "wildcard",
        "provider": "energy",
    },
    "energy_vcenter": {
        "sql": energy.VCENTER,
        "source": "vmhost_metrics",
        "result_type": "value",
        "params_style": "exact",
        "provider": "energy",
    },
    # Legacy key kept for backward compatibility with existing overrides/tests.
    # Uses same SQL/metadata as energy_vcenter.
    "energy_racks": {
        "sql": energy.VCENTER,
        "source": "vmhost_metrics",
        "result_type": "value",
        "params_style": "exact",
        "provider": "energy",
    },
    # --- Energy (batch) ---
    "energy_batch_ibm": {
        "sql": energy.BATCH_IBM,
        "source": "ibm_server_power",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "energy",
        "batch_key": "server_name",
    },
    "energy_batch_vcenter": {
        "sql": energy.BATCH_VCENTER,
        "source": "vmhost_metrics",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "energy",
        "batch_key": "vmhost",
    },
    # --- Customer (pattern = ILIKE %%value%%) ---
    "customer_nutanix_totals": {
        "sql": customer.NUTANIX_TOTALS,
        "source": "nutanix_cluster_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "customer",
    },
    "customer_nutanix_by_dc": {
        "sql": customer.NUTANIX_BY_DC,
        "source": "nutanix_cluster_metrics",
        "result_type": "rows",
        "params_style": "wildcard",
        "provider": "customer",
        "batch_key": "datacenter_name",
    },
    "customer_vmware_totals": {
        "sql": customer.VMWARE_TOTALS,
        "source": "datacenter_metrics",
        "result_type": "row",
        "params_style": "wildcard",
        "provider": "customer",
    },
    "customer_vmware_by_dc": {
        "sql": customer.VMWARE_BY_DC,
        "source": "datacenter_metrics",
        "result_type": "rows",
        "params_style": "wildcard",
        "provider": "customer",
        "batch_key": "datacenter",
    },
    "customer_ibm_lpar_totals": {
        "sql": customer.IBM_LPAR_TOTALS,
        "source": "ibm_lpar_general",
        "result_type": "value",
        "params_style": "wildcard",
        "provider": "customer",
    },
    "customer_ibm_vios_totals": {
        "sql": customer.IBM_VIOS_TOTALS,
        "source": "ibm_vios_general",
        "result_type": "value",
        "params_style": "wildcard_pair",
        "provider": "customer",
    },
    "customer_ibm_host_totals": {
        "sql": customer.IBM_HOST_TOTALS,
        "source": "ibm_server_general",
        "result_type": "value",
        "params_style": "wildcard",
        "provider": "customer",
    },
    "customer_vcenter_host_totals": {
        "sql": customer.VCENTER_HOST_TOTALS,
        "source": "vmhost_metrics",
        "result_type": "value",
        "params_style": "wildcard",
        "provider": "customer",
    },
    # --- Intel DC-level raw VM fetch (dedup done in Python) ---
    "intel_dc_vmware_vms": {
        "sql": intel_dc.VMWARE_VMS_FOR_DC,
        "source": "vm_metrics",
        "result_type": "rows",
        "params_style": "wildcard",
        "provider": "intel",
    },
    "intel_dc_nutanix_vms": {
        "sql": intel_dc.NUTANIX_VMS_FOR_DC,
        "source": "nutanix_vm_metrics, nutanix_cluster_metrics",
        "result_type": "rows",
        "params_style": "wildcard",
        "provider": "intel",
    },
}
