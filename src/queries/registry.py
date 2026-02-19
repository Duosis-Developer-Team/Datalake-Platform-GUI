# Query Registry — central catalog of all available SQL queries.
# To add a new query for a future dashboard, register it here.
# The db_service uses this registry for dynamic query execution.

from src.queries import nutanix, vmware, ibm, energy

# Schema for each entry:
#   sql           : SQL string (from the provider module)
#   source        : DB table name (informational)
#   result_type   : "value" | "row" | "rows"
#   params_style  : "wildcard"  → caller passes f"%{dc_code}%"
#                   "exact"     → caller passes dc_code as-is
#                   "array_wildcard" → caller passes list of wildcard patterns
#                   "array_exact"    → caller passes list of exact DC codes
#   provider      : "nutanix" | "vmware" | "ibm" | "energy"
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
    # --- IBM Power (batch) ---
    "ibm_batch_host_count": {
        "sql": ibm.BATCH_HOST_COUNT,
        "source": "ibm_server_general",
        "result_type": "rows",
        "params_style": "array_wildcard",
        "provider": "ibm",
        "batch_key": "server_details_servername",
    },
    # --- Energy (individual) ---
    "energy_racks": {
        "sql": energy.RACKS,
        "source": "loki_racks",
        "result_type": "value",
        "params_style": "exact",
        "provider": "energy",
    },
    "energy_ibm": {
        "sql": energy.IBM,
        "source": "ibm_server_power_sum",
        "result_type": "value",
        "params_style": "wildcard",
        "provider": "energy",
    },
    "energy_vcenter": {
        "sql": energy.VCENTER,
        "source": "vmhost_metrics",
        "result_type": "value",
        "params_style": "wildcard",
        "provider": "energy",
    },
    # --- Energy (batch) ---
    "energy_batch_racks": {
        "sql": energy.BATCH_RACKS,
        "source": "loki_racks",
        "result_type": "rows",
        "params_style": "array_exact",
        "provider": "energy",
        "batch_key": "location_name",
    },
    "energy_batch_ibm": {
        "sql": energy.BATCH_IBM,
        "source": "ibm_server_power_sum",
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
}
