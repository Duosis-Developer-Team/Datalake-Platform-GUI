# VMware Datastore SQL query definitions (Klasik mimari "storage eşleştirmesi").
#
# Three source tables, joined on datastore_moid:
#   raw_vmware_datastore_metrics_agg      — per-datastore capacity/usage snapshot
#   raw_vmware_datastore_host_mount       — datastore ↔ host mount mapping (eşleştirme)
#   discovery_vmware_inventory_datastore  — static datastore detail (VMFS / NAS)
#
# DC scoping: the metrics table carries `datacenter_name` (vSphere Datacenter name),
# matched with the same convention as the other VMware queries:
#   datacenter_name ILIKE '%<DC_CODE>%'
# Classic-only (Klasik Mimari): we want classic VMware datastores, excluding
# hyperconverged Nutanix storage (sourced from Nutanix directly and shown elsewhere).
# Originally this was a whitelist on the DC13 naming convention
# (`datacenter_name ILIKE '%KM%'`), but after the datastore collection was rolled out
# to all DCs (except DC17) into this single table via the DC13 main NiFi flow, the
# other DCs name their classic vDCs differently — e.g. DC14-Intel-vDC, DC16-Mixed-vDC,
# LONDON-ICT21, UZ11-DC — none of which contain "KM". So the whitelist hid their
# classic datastores entirely. We now use a BLACKLIST instead, excluding Nutanix two
# ways so it also handles "Mixed" vDCs where classic and Nutanix datastores share one
# datacenter_name (e.g. DC16-Mixed-vDC):
#   - datacenter_name NOT ILIKE '%Nutanix%'  → drops dedicated *-Nutanix-vDC datacenters
#   - datastore_name  NOT ILIKE '%NTNX%'      → drops NTNX-* datastores (local-ds, SVM)
#       inside Mixed vDCs. This subsumes the old NTNX-SVM exclusion.
# Verified DC13/AZ11/DC18 are unchanged (90/7/22), while DC14/DC16/ICT21/UZ11 newly
# surface their classic datastores; DC11/DC12/DC15 stay empty because they are fully
# hyperconverged (only Nutanix datastores exist).
# Backup-only datastores (name containing NBU or Veeam) are excluded from
# visualization and sellable computations.
# Backing classification (service layer): datastore_name containing 'IBM' =
# IBM-backed storage (capacity shared with the Power architecture), else Intel.
# The mount/inventory tables have no datacenter column, so they are scoped via the
# set of datastore_moid values that belong to the DC in the metrics table.
#
# "Latest snapshot" pattern: DISTINCT ON (...) ... ORDER BY ... collection_timestamp DESC
# (inventory is upsert-based, so its latest row is by last_observed).
#
# NOTE: in the raw datastore tables `collection_timestamp` is stored as TEXT
# (ISO-8601), so it is cast to timestamptz for range/ordering comparisons.

# --- Per-datastore latest metrics (capacity / usage / host & vm counts) ---
DATASTORE_METRICS = """
SELECT DISTINCT ON (datastore_moid)
    datastore_moid,
    datastore_name,
    datacenter_name,
    type,
    capacity_bytes,
    free_bytes,
    used_bytes,
    uncommitted_bytes,
    used_percent,
    accessible,
    maintenance_mode,
    multiple_host_access,
    host_count,
    vm_count
FROM public.raw_vmware_datastore_metrics_agg
WHERE datacenter_name ILIKE ('%%' || %s || '%%')
  AND datacenter_name NOT ILIKE '%%Nutanix%%'
  AND datastore_name NOT ILIKE '%%NTNX%%'
  AND datastore_name NOT ILIKE '%%NBU%%'
  AND datastore_name NOT ILIKE '%%veeam%%'
  AND collection_timestamp::timestamptz BETWEEN %s AND %s
ORDER BY datastore_moid, collection_timestamp::timestamptz DESC
"""

# --- Datastore ↔ host mount mapping (latest per datastore+host) ---
# Scoped to the datastores present in this DC's metrics snapshot.
DATASTORE_HOST_MOUNTS = """
SELECT DISTINCT ON (hm.datastore_moid, hm.host_moid)
    hm.datastore_moid,
    hm.host_moid,
    hm.host_name,
    hm.mount_path,
    hm.access_mode,
    hm.mounted,
    hm.accessible,
    hm.inaccessible_reason
FROM public.raw_vmware_datastore_host_mount hm
WHERE hm.collection_timestamp::timestamptz BETWEEN %s AND %s
  AND hm.datastore_moid IN (
      SELECT datastore_moid
      FROM public.raw_vmware_datastore_metrics_agg
      WHERE datacenter_name ILIKE ('%%' || %s || '%%')
        AND datacenter_name NOT ILIKE '%%Nutanix%%'
        AND datastore_name NOT ILIKE '%%NTNX%%'
        AND datastore_name NOT ILIKE '%%NBU%%'
        AND datastore_name NOT ILIKE '%%veeam%%'
        AND collection_timestamp::timestamptz BETWEEN %s AND %s
  )
ORDER BY hm.datastore_moid, hm.host_moid, hm.collection_timestamp::timestamptz DESC
"""

# --- Static datastore inventory detail (latest per datastore via last_observed) ---
# component_moid == datastore_moid. VMFS-specific (vmfs_*) and NAS-specific (nas_*)
# columns are populated only for the matching datastore type, NULL otherwise.
DATASTORE_INVENTORY = """
SELECT DISTINCT ON (component_moid)
    component_moid,
    type,
    capacity_gb,
    status,
    status_description,
    vmfs_uuid,
    vmfs_version,
    vmfs_block_size_mb,
    nas_remote_host,
    nas_remote_path,
    nas_type
FROM public.discovery_vmware_inventory_datastore
ORDER BY component_moid, last_observed DESC
"""
