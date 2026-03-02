"""Datacenter-scoped Intel virtualization queries (VMware + Nutanix).

These queries fetch **raw VM-level data** per DC. All deduplication,
counting, and aggregation is done in Python (DatabaseService) to keep
the DB load minimal and improve fetch speed.

VMware side : filter vm_metrics.datacenter by DC code pattern.
Nutanix side: join nutanix_vm_metrics → nutanix_cluster_metrics via
              cluster_uuid and filter by cluster_name DC pattern.
"""

# ---------------------------------------------------------------------------
# VMware: latest snapshot per VM in a given DC
# Returns: (vmname, number_of_cpus, total_memory_capacity_gb, provisioned_space_gb)
# Params : (dc_code, start_ts, end_ts)
# ---------------------------------------------------------------------------
VMWARE_VMS_FOR_DC = """
SELECT DISTINCT ON (vmname)
    vmname,
    number_of_cpus,
    total_memory_capacity_gb,
    provisioned_space_gb
FROM public.vm_metrics
WHERE datacenter ILIKE ('%%' || %s || '%%')
  AND "timestamp" BETWEEN %s AND %s
ORDER BY vmname, "timestamp" DESC
"""

# ---------------------------------------------------------------------------
# Nutanix: latest snapshot per VM in a given DC
# Returns: (vm_name, cpu_count, memory_capacity_bytes, disk_capacity_bytes)
# Params : (dc_code, start_ts, end_ts)
# ---------------------------------------------------------------------------
NUTANIX_VMS_FOR_DC = """
SELECT DISTINCT ON (n.vm_name)
    n.vm_name,
    n.cpu_count,
    n.memory_capacity,
    n.disk_capacity
FROM public.nutanix_vm_metrics n
JOIN public.nutanix_cluster_metrics c
  ON c.cluster_uuid::uuid = n.cluster_uuid
WHERE c.cluster_name LIKE ('%%' || %s || '%%')
  AND n.collection_time BETWEEN %s AND %s
ORDER BY n.vm_name, n.collection_time DESC
"""
