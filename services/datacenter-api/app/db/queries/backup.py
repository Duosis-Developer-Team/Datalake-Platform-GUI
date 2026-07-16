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


# =============================================================================
# Job statistics — bar chart aggregations (Phase 1)
# =============================================================================
#
# SQL pre-aggregates by (date_trunc(granularity, ts), source_ip, status, type)
# so the result set is small (~10 IPs × N periods × 5 statuses × 5 types).
# DC filtering is applied in the application layer via per-vendor IP→DC maps
# (the IP map is built from auxiliary metrics tables that contain DC-bearing
# host/location names; jobs/sessions tables only have IPs).
#
# Granularity is bound to one of {'day','week','month'} at the service layer
# before being passed to date_trunc; the SQL uses %s so the value is properly
# escaped by psycopg2.

# Veeam sessions: per-run rows ('Success'|'Failed'|'Warning'|None result).
# Params: (granularity, start_ts, end_ts)
VEEAM_SESSION_JOB_STATS = """
SELECT
    date_trunc(%s, creation_time) AS period,
    source_ip,
    COALESCE(NULLIF(result_result, ''), 'None') AS result,
    COALESCE(NULLIF(session_type, ''), 'Unknown') AS session_type,
    COUNT(*) AS cnt
FROM public.raw_veeam_sessions
WHERE creation_time BETWEEN %s AND %s
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4
"""

# Veeam IP → DC seed: pull (source_ip, host_name) pairs whose host_name
# encodes the DC (e.g. 'Dc13-VeemConsule.blt.vc').
# Params: (start_ts, end_ts)
VEEAM_IP_TO_DC_SEED = """
SELECT DISTINCT source_ip, host_name
FROM public.raw_veeam_repositories_states
WHERE collection_time BETWEEN %s AND %s
  AND host_name IS NOT NULL
"""


# Zerto VPG snapshots: status is integer enum (1=MeetingSLA, others=problematic).
# We group by source_site directly — it already carries DC-bearing labels
# (e.g. 'DC14-Site02-V10', 'TurksatDC_ZVM').
# Params: (granularity, start_ts, end_ts)
ZERTO_VPG_JOB_STATS = """
SELECT
    date_trunc(%s, collection_timestamp) AS period,
    source_site,
    status,
    COUNT(*) AS cnt
FROM public.raw_zerto_vpg_metrics
WHERE collection_timestamp BETWEEN %s AND %s
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
"""


# NetBackup jobs: status is integer (0=success, 1=warning, else=failed exit code).
# Group by destinationmediaservername (e.g. 'nbmediadc14.blt.vc') — already
# carries DC code, so we can map to DC directly without a separate seed query.
# Params: (granularity, start_ts, end_ts)
NETBACKUP_JOB_STATS = """
SELECT
    date_trunc(%s, starttime) AS period,
    destinationmediaservername AS dc_label,
    status,
    COALESCE(NULLIF(jobtype, ''), 'Unknown') AS jobtype,
    COALESCE(NULLIF(policytype, ''), 'Unknown') AS policytype,
    COUNT(*) AS cnt
FROM public.raw_netbackup_jobs_metrics
WHERE starttime BETWEEN %s AND %s
  AND destinationmediaservername IS NOT NULL
GROUP BY 1, 2, 3, 4, 5
ORDER BY 1, 2, 3, 4, 5
"""


# Zerto license — latest row per zerto_host (global snapshot; DC attribution
# is applied in the service layer via sites_usage JSON SiteName fields).
# Params: none (DISTINCT ON latest overall; hosts collect continuously).
ZERTO_LICENSE_LATEST = """
SELECT DISTINCT ON (zerto_host)
    collection_timestamp,
    zerto_host,
    id,
    name,
    expirationdate,
    license_key,
    license_type,
    is_valid,
    max_vms,
    total_vms_count,
    sites_usage,
    days_until_expiry
FROM public.raw_zerto_license_metrics
ORDER BY zerto_host, collection_timestamp DESC
"""

# Optional time-bounded variant (warm/cache windows).
# Params: (start_ts, end_ts)
ZERTO_LICENSE_LATEST_IN_RANGE = """
SELECT DISTINCT ON (zerto_host)
    collection_timestamp,
    zerto_host,
    id,
    name,
    expirationdate,
    license_key,
    license_type,
    is_valid,
    max_vms,
    total_vms_count,
    sites_usage,
    days_until_expiry
FROM public.raw_zerto_license_metrics
WHERE collection_timestamp BETWEEN %s AND %s
ORDER BY zerto_host, collection_timestamp DESC
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

# =============================================================================
# Unique-job inventory — latest state per unique job/VPG identity.
#
# Unlike the *_JOB_STATS queries above (which pre-aggregate for bar charts),
# these return one row per distinct job/VPG so the application layer can
# build a searchable/filterable "unique jobs" table (status, type, category,
# policy_type breakdowns via shared.backup.unique_jobs). Column set verified
# against services/datacenter-api/tests/backup_jobs_schema.md (live schema
# inspection) — no adjustments were needed vs. the initial draft.
# =============================================================================

# Veeam unique jobs (latest per job id).
# Params: (start_ts, end_ts)
VEEAM_UNIQUE_JOBS_LATEST = """
SELECT DISTINCT ON (id)
    collection_time,
    id,
    name,
    type,
    status,
    last_result,
    last_run,
    objects_count,
    session_id,
    workload,
    source_ip
FROM public.raw_veeam_jobs_states
WHERE collection_time BETWEEN %s AND %s
ORDER BY id, collection_time DESC
"""

# Zerto unique VPGs (latest per VPG id).
# Params: (start_ts, end_ts)
ZERTO_UNIQUE_VPGS_LATEST = """
SELECT DISTINCT ON (id)
    collection_timestamp,
    id,
    name,
    status,
    vmscount,
    source_site,
    target_site,
    provisioned_storage_mb,
    used_storage_mb,
    zerto_host
FROM public.raw_zerto_vpg_metrics
WHERE collection_timestamp BETWEEN %s AND %s
ORDER BY id, collection_timestamp DESC
"""

# NetBackup unique jobs (latest per policy + workload; BACKUP jobs only).
# Params: (start_ts, end_ts)
NETBACKUP_UNIQUE_JOBS_LATEST = """
SELECT DISTINCT ON (policyname, COALESCE(workloaddisplayname, ''))
    starttime,
    endtime,
    jobid,
    policyname,
    policytype,
    jobtype,
    status,
    workloaddisplayname,
    clientname,
    destinationmediaservername,
    kilobytestransferred,
    dedupratio,
    percentcomplete
FROM public.raw_netbackup_jobs_metrics
WHERE starttime BETWEEN %s AND %s
  AND UPPER(COALESCE(jobtype, '')) = 'BACKUP'
ORDER BY policyname, COALESCE(workloaddisplayname, ''), starttime DESC
"""

