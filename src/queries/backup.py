"""
SQL queries for backup-related metrics at the datacenter level.

These are intentionally generic (no direct DC filter). DC attribution is
handled in the application layer based on name patterns and IP/address
grouping so that multiple DC detection strategies can be applied.
"""

# NetBackup -------------------------------------------------------------------

# Latest disk pool metrics per pool ID within a given time range.
# Params: (start_ts, end_ts)
NETBACKUP_DISK_POOLS_LATEST = """
SELECT DISTINCT ON (id)
    collection_timestamp,
    netbackup_host,
    name,
    stype,
    storagecategory,
    diskvolumes_name,
    diskvolumes_state,
    usablesizebytes,
    availablespacebytes,
    usedcapacitybytes
FROM public.raw_netbackup_disk_pools_metrics
WHERE collection_timestamp BETWEEN %s AND %s
ORDER BY id, collection_timestamp DESC
"""


# Zerto -----------------------------------------------------------------------

# Latest Zerto site metrics per site ID within a given time range.
# Params: (start_ts, end_ts)
ZERTO_SITES_LATEST = """
SELECT DISTINCT ON (id)
    collection_timestamp,
    zerto_host,
    name,
    site_type,
    is_connected,
    incoming_throughput_mb,
    outgoing_bandwidth_mb,
    provisioned_storage_mb,
    used_storage_mb
FROM public.raw_zerto_site_metrics
WHERE collection_timestamp BETWEEN %s AND %s
ORDER BY id, collection_timestamp DESC
"""


# Veeam -----------------------------------------------------------------------

# Latest Veeam repository state per repository ID within a given time range.
# Params: (start_ts, end_ts)
VEEAM_REPOSITORIES_LATEST = """
SELECT DISTINCT ON (id)
    collection_time,
    id,
    name,
    host_name,
    type,
    capacity_gb,
    free_gb,
    used_space_gb,
    is_online
FROM public.raw_veeam_repositories_states
WHERE collection_time BETWEEN %s AND %s
ORDER BY id, collection_time DESC
"""

