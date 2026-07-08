"""SQL for Nutanix snapshot metrics (Backup & Replication → Nutanix tab).

DC attribution is DB-native: snapshot.nutanix_ip -> discovery inventory cluster
(nutanix_uuid = 'nutanix-' || ip) -> cluster name carrying the DC code. Every
snapshot read is collection_time-bounded and scoped to a DC's IP set (or a
customer prefix); the base table is huge and a full scan times out.

usec epoch columns are converted to timestamps here (to_timestamp) for
tz-consistency with the Grafana dashboards.
"""

# Resolve a DC's Nutanix IPs + their cluster name (for the table "Cluster"
# column). Uses the discovery inventory (point-in-time; small).
# Param: (dc_code,)
DC_NUTANIX_IPS = """
SELECT DISTINCT
    replace(nutanix_uuid, 'nutanix-', '') AS nutanix_ip,
    name AS cluster_name
FROM public.discovery_nutanix_inventory_cluster
WHERE name LIKE ('%%' || %s || '%%')
  AND nutanix_uuid LIKE 'nutanix-%%'
"""

# Shared SELECT list + de-dup for the two scoped variants below. The column
# order MUST match shared.nutanix.snapshot_helpers.enrich_snapshot_rows.
_SNAPSHOT_SELECT = """
SELECT DISTINCT ON (snapshot_id)
    nutanix_ip,
    protection_domain_name,
    state,
    vm_names,
    missing_entities_entity_name,
    missing_entities_entity_type,
    schedule_type,
    schedule_local_max_snapshots,
    size_in_bytes,
    to_timestamp(schedule_start_times_in_usecs / 1000000.0) AS start_time,
    to_timestamp(snapshot_create_time_usecs / 1000000.0)    AS create_time,
    to_timestamp(snapshot_expiry_time_usecs / 1000000.0)    AS expiry_time,
    snapshot_id
FROM public.nutanix_snapshot_schedule_metrics
"""

# Latest row per physical snapshot within the window, scoped to the DC's IPs.
# Params: (ip_list, start_ts, end_ts)
SNAPSHOTS_BY_IPS_LATEST = _SNAPSHOT_SELECT + """
WHERE nutanix_ip = ANY(%s)
  AND collection_time BETWEEN %s AND %s
ORDER BY snapshot_id, collection_time DESC
"""

# Latest row per physical snapshot within the window, scoped to a customer by
# name prefix on either the protection domain or the VM list.
# Params: (like, like, start_ts, end_ts) where like = 'Customer-%'
SNAPSHOTS_BY_CUSTOMER_LATEST = _SNAPSHOT_SELECT + """
WHERE (protection_domain_name LIKE %s OR vm_names LIKE %s)
  AND collection_time BETWEEN %s AND %s
ORDER BY snapshot_id, collection_time DESC
"""
