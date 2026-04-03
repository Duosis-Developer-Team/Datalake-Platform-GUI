# Customer (tenant) SQL query definitions.
# Filter by VM/Host naming pattern (e.g. ILIKE '%boyner%').
# Sources: vm_metrics, nutanix_vm_metrics, ibm_lpar_general, ibm_vios_general, ibm_server_general.
#
# Compute type split (vm_metrics.cluster field):
#   Classic Compute      — vm_metrics WHERE cluster ILIKE '%KM%'
#   Hyperconverged       — vm_metrics WHERE cluster NOT ILIKE '%KM%'  +  nutanix_vm_metrics (Acropolis)
#   Power/SAP Compute    — ibm_lpar_general
#
# VM counts use VM-level deduplication (vm_metrics + nutanix_vm_metrics)
# so VMs present in both platforms are counted exactly once.

# --- VM-level deduplication (correct totals: no double-count of VMs in both VMware and Nutanix) ---
# Params: (pattern, start_ts, end_ts, pattern, start_ts, end_ts)
CUSTOMER_VM_DEDUP = """
WITH all_vmware_vms AS (
    SELECT DISTINCT ON (vmname) vmname
    FROM public.vm_metrics
    WHERE vmname ILIKE %s AND timestamp BETWEEN %s AND %s
    ORDER BY vmname, timestamp DESC
),
all_nutanix_vms AS (
    SELECT DISTINCT ON (vm_name) vm_name
    FROM public.nutanix_vm_metrics
    WHERE vm_name ILIKE %s AND collection_time BETWEEN %s AND %s
    ORDER BY vm_name, collection_time DESC
)
SELECT
    (SELECT COUNT(*)::int FROM all_vmware_vms v WHERE NOT EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname)) AS vmware_only,
    (SELECT COUNT(*)::int FROM all_vmware_vms v WHERE EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname)) AS in_both,
    (SELECT COUNT(*)::int FROM all_nutanix_vms n WHERE NOT EXISTS (SELECT 1 FROM all_vmware_vms v WHERE v.vmname = n.vm_name)) AS nutanix_only
"""

# --- Intel virtualization (VMware + Nutanix) customer assets ---

# CPU totals (Total CPU panel in Grafana)
# Params: (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts)
CUSTOMER_INTEL_CPU_TOTALS = """
WITH all_vmware_vms AS (
    SELECT DISTINCT ON (vmname)
        vmname,
        number_of_cpus
    FROM public.vm_metrics
    WHERE vmname ILIKE %s AND "timestamp" BETWEEN %s AND %s
    ORDER BY vmname, "timestamp" DESC
),
all_nutanix_vms AS (
    SELECT DISTINCT ON (vm_name)
        vm_name,
        cpu_count
    FROM public.nutanix_vm_metrics
    WHERE vm_name ILIKE %s AND collection_time BETWEEN %s AND %s
    ORDER BY vm_name, collection_time DESC
)
SELECT
    (
        SELECT COALESCE(SUM(v.number_of_cpus), 0)
        FROM all_vmware_vms v
        WHERE NOT EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname)
    ) AS "Total CPU (VMware)",
    (
        (
            SELECT COALESCE(SUM(v.number_of_cpus), 0)
            FROM all_vmware_vms v
            WHERE EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname)
        )
        +
        (
            SELECT COALESCE(SUM(n.cpu_count), 0)
            FROM all_nutanix_vms n
            WHERE NOT EXISTS (SELECT 1 FROM all_vmware_vms v WHERE v.vmname = n.vm_name)
        )
    ) AS "Total CPU (Nutanix)",
    (
        (
            SELECT COALESCE(SUM(v.number_of_cpus), 0)
            FROM all_vmware_vms v
            WHERE NOT EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname)
        )
        +
        (
            (SELECT COALESCE(SUM(v.number_of_cpus), 0) FROM all_vmware_vms v WHERE EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname))
            +
            (SELECT COALESCE(SUM(n.cpu_count), 0) FROM all_nutanix_vms n WHERE NOT EXISTS (SELECT 1 FROM all_vmware_vms v WHERE v.vmname = n.vm_name))
        )
    ) AS "Total CPU"
"""

# VM counts (VM's of Customer stat panel in Grafana)
# Params: (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts)
CUSTOMER_INTEL_VM_COUNTS = """
WITH vmware_vms AS (
    SELECT DISTINCT vmname
    FROM public.vm_metrics
    WHERE vmname ILIKE %s AND "timestamp" BETWEEN %s AND %s
),
nutanix_vms AS (
    SELECT DISTINCT vm_name
    FROM public.nutanix_vm_metrics
    WHERE vm_name ILIKE %s AND collection_time BETWEEN %s AND %s
)
SELECT
    (
        SELECT COUNT(*)
        FROM vmware_vms v
        WHERE NOT EXISTS (SELECT 1 FROM nutanix_vms n WHERE n.vm_name = v.vmname)
    ) AS "VMware",
    (
        SELECT COUNT(*)
        FROM nutanix_vms
    ) AS "Nutanix",
    (
        SELECT COUNT(*) FROM (
            SELECT vmname AS vm_name FROM vmware_vms
            UNION
            SELECT vm_name FROM nutanix_vms
        ) AS all_unique_vms
    ) AS "Total"
"""

# Memory totals (Total Memory panel in Grafana)
# Params: (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts)
CUSTOMER_INTEL_MEMORY_TOTALS = """
WITH all_vmware_vms AS (
    SELECT DISTINCT ON (vmname)
        vmname,
        total_memory_capacity_gb
    FROM public.vm_metrics
    WHERE vmname ILIKE %s AND "timestamp" BETWEEN %s AND %s
    ORDER BY vmname, "timestamp" DESC
),
all_nutanix_vms AS (
    SELECT DISTINCT ON (vm_name)
        vm_name,
        (memory_capacity / 1024.0 / 1024.0 / 1024.0) AS memory_gb
    FROM public.nutanix_vm_metrics
    WHERE vm_name ILIKE %s AND collection_time BETWEEN %s AND %s
    ORDER BY vm_name, collection_time DESC
)
SELECT
    (
        SELECT COALESCE(SUM(v.total_memory_capacity_gb), 0)
        FROM all_vmware_vms v
        WHERE NOT EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname)
    ) AS "Total Memory (VMware)",
    (
        (
            SELECT COALESCE(SUM(v.total_memory_capacity_gb), 0)
            FROM all_vmware_vms v
            WHERE EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname)
        )
        +
        (
            SELECT COALESCE(SUM(n.memory_gb), 0)
            FROM all_nutanix_vms n
            WHERE NOT EXISTS (SELECT 1 FROM all_vmware_vms v WHERE v.vmname = n.vm_name)
        )
    ) AS "Total Memory (Nutanix)",
    (
        (
            SELECT COALESCE(SUM(v.total_memory_capacity_gb), 0)
            FROM all_vmware_vms v
            WHERE NOT EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname)
        )
        +
        (
            (SELECT COALESCE(SUM(v.total_memory_capacity_gb), 0) FROM all_vmware_vms v WHERE EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname))
            +
            (SELECT COALESCE(SUM(n.memory_gb), 0) FROM all_nutanix_vms n WHERE NOT EXISTS (SELECT 1 FROM all_vmware_vms v WHERE v.vmname = n.vm_name))
        )
    ) AS "Total Memory"
"""

# Disk totals (Total Disk panel in Grafana)
# Params: (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts)
CUSTOMER_INTEL_DISK_TOTALS = """
WITH all_vmware_vms AS (
    SELECT DISTINCT ON (vmname)
        vmname,
        provisioned_space_gb
    FROM public.vm_metrics
    WHERE vmname ILIKE %s AND "timestamp" BETWEEN %s AND %s
    ORDER BY vmname, "timestamp" DESC
),
all_nutanix_vms AS (
    SELECT DISTINCT ON (vm_name)
        vm_name,
        (disk_capacity / 1024.0 / 1024.0 / 1024.0) AS disk_gb
    FROM public.nutanix_vm_metrics
    WHERE vm_name ILIKE %s AND collection_time BETWEEN %s AND %s
    ORDER BY vm_name, collection_time DESC
)
SELECT
    (
        SELECT COALESCE(SUM(v.provisioned_space_gb), 0)
        FROM all_vmware_vms v
        WHERE NOT EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname)
    ) AS "Total Disk (VMware)",
    (
        SELECT COALESCE(SUM(n.disk_gb), 0)
        FROM all_nutanix_vms n
    ) AS "Total Disk (Nutanix)",
    (
        (
            SELECT COALESCE(SUM(v.provisioned_space_gb), 0)
            FROM all_vmware_vms v
            WHERE NOT EXISTS (SELECT 1 FROM all_nutanix_vms n WHERE n.vm_name = v.vmname)
        )
        +
        (
            SELECT COALESCE(SUM(n.disk_gb), 0)
            FROM all_nutanix_vms n
        )
    ) AS "Total Disk"
"""

# VM list and source (VM's of Customer table in Grafana)
# Params: (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts)
CUSTOMER_INTEL_VM_SOURCES = """
WITH all_unique_vms AS (
    SELECT vmname AS vm_name
    FROM public.vm_metrics
    WHERE vmname ILIKE %s AND "timestamp" BETWEEN %s AND %s
    UNION
    SELECT vm_name
    FROM public.nutanix_vm_metrics
    WHERE vm_name ILIKE %s AND collection_time BETWEEN %s AND %s
)
SELECT
  u.vm_name AS "VM Name",
  CASE
    WHEN EXISTS (
        SELECT 1 FROM public.vm_metrics v
        WHERE v.vmname = u.vm_name AND v."timestamp" BETWEEN %s AND %s
    )
     AND EXISTS (
        SELECT 1 FROM public.nutanix_vm_metrics n
        WHERE n.vm_name = u.vm_name AND n.collection_time BETWEEN %s AND %s
    )
    THEN 'Nutanix (Managed by VMware)'
    WHEN EXISTS (
        SELECT 1 FROM public.vm_metrics v
        WHERE v.vmname = u.vm_name AND v."timestamp" BETWEEN %s AND %s
    )
    THEN 'VMware'
    ELSE 'Nutanix'
  END AS "Source"
FROM
  all_unique_vms u
ORDER BY
  "Source", "VM Name"
"""

# Enhanced Intel VM list with resource details for billing (CPU / Memory / Disk)
# Params: (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts)
CUSTOMER_INTEL_VM_DETAIL_LIST = """
WITH vmware_latest AS (
    SELECT DISTINCT ON (vmname)
        vmname,
        number_of_cpus,
        total_memory_capacity_gb,
        provisioned_space_gb
    FROM public.vm_metrics
    WHERE vmname ILIKE %s AND "timestamp" BETWEEN %s AND %s
    ORDER BY vmname, "timestamp" DESC
),
nutanix_latest AS (
    SELECT DISTINCT ON (vm_name)
        vm_name,
        cpu_count,
        (memory_capacity / 1024.0 / 1024.0 / 1024.0) AS memory_gb,
        (disk_capacity / 1024.0 / 1024.0 / 1024.0) AS disk_gb
    FROM public.nutanix_vm_metrics
    WHERE vm_name ILIKE %s AND collection_time BETWEEN %s AND %s
    ORDER BY vm_name, collection_time DESC
),
all_unique_vms AS (
    SELECT vmname AS vm_name FROM vmware_latest
    UNION
    SELECT vm_name FROM nutanix_latest
)
SELECT
    u.vm_name AS "VM Name",
    CASE
        WHEN v.vmname IS NOT NULL AND n.vm_name IS NOT NULL
            THEN 'Nutanix (Managed by VMware)'
        WHEN v.vmname IS NOT NULL
            THEN 'VMware'
        ELSE 'Nutanix'
    END AS "Source",
    COALESCE(v.number_of_cpus, n.cpu_count, 0) AS "CPU",
    COALESCE(v.total_memory_capacity_gb, n.memory_gb, 0) AS "Memory (GB)",
    COALESCE(v.provisioned_space_gb, n.disk_gb, 0) AS "Disk (GB)"
FROM
    all_unique_vms u
    LEFT JOIN vmware_latest v ON v.vmname = u.vm_name
    LEFT JOIN nutanix_latest n ON n.vm_name = u.vm_name
ORDER BY
    "Source",
    "VM Name"
"""

# --- Nutanix: cluster_name ILIKE pattern ---

# Params: (pattern, start_ts, end_ts)
NUTANIX_TOTALS = """
WITH latest AS (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        datacenter_name,
        num_nodes,
        total_vms
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name ILIKE %s AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
)
SELECT COALESCE(SUM(num_nodes), 0) AS total_hosts, COALESCE(SUM(total_vms), 0) AS total_vms
FROM latest
"""

NUTANIX_BY_DC = """
WITH latest AS (
    SELECT DISTINCT ON (cluster_name)
        cluster_name,
        datacenter_name,
        num_nodes,
        total_vms
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name ILIKE %s AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
)
SELECT datacenter_name, SUM(num_nodes) AS host_count, SUM(total_vms) AS vm_count
FROM latest
GROUP BY datacenter_name
"""

# VMware: (pattern, start_ts, end_ts)
VMWARE_TOTALS = """
WITH latest AS (
    SELECT DISTINCT ON (datacenter)
        datacenter,
        total_cluster_count,
        total_host_count,
        total_vm_count
    FROM public.datacenter_metrics
    WHERE datacenter ILIKE %s AND timestamp BETWEEN %s AND %s
    ORDER BY datacenter, timestamp DESC
)
SELECT
    COALESCE(SUM(total_cluster_count), 0) AS total_clusters,
    COALESCE(SUM(total_host_count), 0) AS total_hosts,
    COALESCE(SUM(total_vm_count), 0) AS total_vms
FROM latest
"""

VMWARE_BY_DC = """
SELECT DISTINCT ON (datacenter)
    datacenter,
    total_cluster_count AS cluster_count,
    total_host_count AS host_count,
    total_vm_count AS vm_count
FROM public.datacenter_metrics
WHERE datacenter ILIKE %s AND timestamp BETWEEN %s AND %s
ORDER BY datacenter, timestamp DESC
"""

# IBM: (pattern, start_ts, end_ts) or (pattern, pattern, start_ts, end_ts)
IBM_LPAR_TOTALS = """
SELECT COUNT(DISTINCT lparname) AS lpar_count
FROM public.ibm_lpar_general
WHERE lparname ILIKE %s AND time BETWEEN %s AND %s
"""

IBM_VIOS_TOTALS = """
SELECT COUNT(DISTINCT viosname) AS vios_count
FROM public.ibm_vios_general
WHERE (viosname ILIKE %s OR vios_details_servername ILIKE %s) AND time BETWEEN %s AND %s
"""

IBM_HOST_TOTALS = """
SELECT COUNT(DISTINCT server_details_servername) AS host_count
FROM public.ibm_server_general
WHERE server_details_servername ILIKE %s AND time BETWEEN %s AND %s
"""

# (pattern, start_ts, end_ts) or (p, p, start_ts, end_ts)
IBM_HOST_BY_SERVER = """
SELECT server_details_servername AS server_name, COUNT(*) AS host_count
FROM public.ibm_server_general
WHERE server_details_servername ILIKE %s AND time BETWEEN %s AND %s
GROUP BY server_details_servername
"""
IBM_VIOS_BY_SERVER = """
SELECT vios_details_servername AS server_name, COUNT(DISTINCT viosname) AS vios_count
FROM public.ibm_vios_general
WHERE (viosname ILIKE %s OR vios_details_servername ILIKE %s) AND time BETWEEN %s AND %s
GROUP BY vios_details_servername
"""
IBM_LPAR_BY_SERVER = """
SELECT lpar_details_servername AS server_name, COUNT(DISTINCT lparname) AS lpar_count
FROM public.ibm_lpar_general
WHERE lparname ILIKE %s AND time BETWEEN %s AND %s
GROUP BY lpar_details_servername
"""

# Power / HANA (IBM LPAR) customer assets (HANA Virtualization section in Grafana)

# Total CPU (Power HMC) — latest per LPAR, then sum
# Params: (lpar_pattern, start_ts, end_ts)
CUSTOMER_POWER_CPU_TOTAL = """
WITH latest_lpar_stats AS (
    SELECT DISTINCT ON (lparname)
        lpar_processor_currentvirtualprocessors
    FROM public.ibm_lpar_general
    WHERE lparname ILIKE %s AND time BETWEEN %s AND %s
    ORDER BY lparname, time DESC
)
SELECT
    COALESCE(SUM(lpar_processor_currentvirtualprocessors), 0) AS "Total CPU (Power HMC)"
FROM latest_lpar_stats
"""

# Total Memory (Power HMC) — latest per LPAR, then sum (GB)
# Params: (lpar_pattern, start_ts, end_ts)
CUSTOMER_POWER_MEMORY_TOTAL = """
WITH latest_lpar_stats AS (
    SELECT DISTINCT ON (lparname)
        lpar_memory_logicalmem / 1024.0 AS lpar_memory_logicalmem
    FROM public.ibm_lpar_general
    WHERE lparname ILIKE %s AND time BETWEEN %s AND %s
    ORDER BY lparname, time DESC
)
SELECT
    COALESCE(SUM(lpar_memory_logicalmem), 0) AS "Total Memory (Power HMC)"
FROM latest_lpar_stats
"""

# LPAR VM list for customer
# Params: (lpar_pattern, start_ts, end_ts)
CUSTOMER_POWER_VM_LIST = """
SELECT DISTINCT
    lparname AS "VM Name",
    'Power HMC' AS "Source"
FROM public.ibm_lpar_general
WHERE lparname ILIKE %s AND time BETWEEN %s AND %s
ORDER BY "VM Name"
"""

# Enhanced LPAR VM list with resource details for billing (CPU / Memory / State)
# Params: (lpar_pattern, start_ts, end_ts)
CUSTOMER_POWER_LPAR_DETAIL_LIST = """
WITH latest_lpar AS (
    SELECT DISTINCT ON (lparname)
        lparname,
        lpar_processor_currentvirtualprocessors,
        lpar_memory_logicalmem / 1024.0 AS memory_gb,
        lpar_details_state
    FROM public.ibm_lpar_general
    WHERE lparname ILIKE %s AND time BETWEEN %s AND %s
    ORDER BY lparname, time DESC
)
SELECT
    lparname AS "VM Name",
    'Power HMC' AS "Source",
    COALESCE(lpar_processor_currentvirtualprocessors, 0) AS "CPU",
    COALESCE(memory_gb, 0) AS "Memory (GB)",
    COALESCE(lpar_details_state, '') AS "State"
FROM latest_lpar
ORDER BY "VM Name"
"""

# vCenter: (pattern, start_ts, end_ts)
VCENTER_HOST_TOTALS = """
SELECT COUNT(DISTINCT vmhost) AS host_count
FROM public.vmhost_metrics
WHERE vmhost ILIKE %s AND "timestamp" BETWEEN %s AND %s
"""

VCENTER_BY_HOST = """
SELECT DISTINCT ON (vmhost) vmhost, power_usage
FROM public.vmhost_metrics
WHERE vmhost ILIKE %s AND "timestamp" BETWEEN %s AND %s
ORDER BY vmhost, "timestamp" DESC
"""

# ---------------------------------------------------------------------------
# Backup and storage (Veeam, Zerto, IBM storage)
# ---------------------------------------------------------------------------

# Veeam — total defined sessions for customer
# Params: (name_pattern,)
CUSTOMER_VEEAM_DEFINED_SESSIONS = """
SELECT
    COUNT(DISTINCT name) AS "Defined Sessions"
FROM public.raw_veeam_sessions
WHERE name ILIKE %s
"""

# Veeam — session types distribution
# Params: (name_pattern,)
CUSTOMER_VEEAM_SESSION_TYPES = """
SELECT
    session_type AS "Session Type",
    COUNT(DISTINCT name) AS "Defined Session Count"
FROM public.raw_veeam_sessions
WHERE name ILIKE %s
GROUP BY session_type
ORDER BY "Defined Session Count" DESC
"""

# Veeam — platform distribution
# Params: (name_pattern,)
CUSTOMER_VEEAM_SESSION_PLATFORMS = """
SELECT
    platform_name AS "Platform",
    COUNT(DISTINCT name) AS "Defined Session Count"
FROM public.raw_veeam_sessions
WHERE name ILIKE %s
GROUP BY platform_name
ORDER BY "Defined Session Count" DESC
"""

# Zerto — protected total VMs
# Params: (start_ts, end_ts, name_like_pattern)
CUSTOMER_ZERTO_PROTECTED_VMS = """
WITH ranked_records AS (
    SELECT
        vmscount,
        ROW_NUMBER() OVER(PARTITION BY id ORDER BY collection_timestamp DESC) AS rn
    FROM public.raw_zerto_vpg_metrics
    WHERE collection_timestamp BETWEEN %s AND %s
      AND name LIKE %s
)
SELECT
    COALESCE(SUM(vmscount), 0) AS "Protected Total VMs"
FROM ranked_records
WHERE rn = 1
"""

# IBM Storage volume capacity (optional; table may not exist in all environments)
# Params: (name_like_pattern, start_ts, end_ts)
CUSTOMER_STORAGE_VOLUME_CAPACITY = """
WITH latest_vdisk_stats AS (
    SELECT DISTINCT ON (name)
        capacity::numeric AS capacity_gb
    FROM public.raw_ibm_storage_vdisk
    WHERE name ILIKE %s AND "timestamp" BETWEEN %s AND %s
    ORDER BY name, "timestamp" DESC
)
SELECT
    COALESCE(SUM(capacity_gb), 0) AS "Total Volume Capacity (GB)"
FROM latest_vdisk_stats
"""

# NetBackup — backup size and deduplication summary for billing
# Params: (workload_pattern, start_ts, end_ts)
CUSTOMER_NETBACKUP_BACKUP_SUMMARY = """
WITH filtered AS (
    SELECT
        kilobytestransferred,
        dedupratio
    FROM public.raw_netbackup_jobs_metrics
    WHERE workloaddisplayname ILIKE %s
      AND jobtype = 'BACKUP'
      AND percentcomplete = 100
      AND collection_timestamp BETWEEN %s AND %s
)
SELECT
    COALESCE(CAST(SUM(kilobytestransferred) / 1024.0 / 1024.0 / 1024.0 AS NUMERIC(20, 2)), 0) AS "Pre Dedup Size (GiB)",
    COALESCE(
        CAST(SUM(kilobytestransferred / NULLIF(dedupratio, 0)) / 1024.0 / 1024.0 / 1024.0 AS NUMERIC(20, 2)),
        0
    ) AS "Post Dedup Size (GiB)",
    COALESCE(CAST(AVG(NULLIF(dedupratio, 0)) AS NUMERIC(20, 2)), 1) || 'x' AS "Deduplication Factor"
FROM filtered
"""

# Zerto — provisioned storage per VPG for last 30 days (GiB)
# Params: (name_like_pattern)
CUSTOMER_ZERTO_PROVISIONED_STORAGE = """
WITH latest AS (
    SELECT DISTINCT ON (name)
        name,
        provisioned_storage_mb
    FROM public.raw_zerto_vpg_metrics
    WHERE name ILIKE %s
      AND collection_timestamp >= NOW() - INTERVAL '30 days'
    ORDER BY name, provisioned_storage_mb DESC
)
SELECT
    name,
    COALESCE(provisioned_storage_mb / 1024.0, 0) AS "Provisioned Storage (GiB)"
FROM latest
ORDER BY name
"""

# =============================================================================
# Classic Compute — VMs on KM clusters (vm_metrics.cluster ILIKE '%KM%')
# =============================================================================

# Classic VM count
# Params: (vm_pattern, start_ts, end_ts)
CUSTOMER_CLASSIC_VM_COUNT = """
SELECT COUNT(DISTINCT vmname) AS vm_count
FROM public.vm_metrics
WHERE vmname ILIKE %s
  AND cluster ILIKE '%%KM%%'
  AND timestamp BETWEEN %s AND %s
"""

# Classic VM resource totals (CPU cores, memory GB, disk GB)
# Params: (vm_pattern, start_ts, end_ts)
CUSTOMER_CLASSIC_RESOURCE_TOTALS = """
WITH latest AS (
    SELECT DISTINCT ON (vmname)
        vmname,
        number_of_cpus,
        total_memory_capacity_gb,
        provisioned_space_gb
    FROM public.vm_metrics
    WHERE vmname ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY vmname, timestamp DESC
)
SELECT
    COALESCE(SUM(number_of_cpus), 0)          AS cpu_total,
    COALESCE(SUM(total_memory_capacity_gb), 0) AS memory_gb,
    COALESCE(SUM(provisioned_space_gb), 0)     AS disk_gb
FROM latest
"""

# Classic VM detail list for billing
# Params: (vm_pattern, start_ts, end_ts)
CUSTOMER_CLASSIC_VM_LIST = """
WITH latest AS (
    SELECT DISTINCT ON (vmname)
        vmname,
        cluster,
        number_of_cpus,
        total_memory_capacity_gb,
        provisioned_space_gb
    FROM public.vm_metrics
    WHERE vmname ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY vmname, timestamp DESC
)
SELECT
    vmname           AS "VM Name",
    'Classic'        AS "Source",
    cluster          AS "Cluster",
    COALESCE(number_of_cpus, 0)           AS "CPU",
    COALESCE(total_memory_capacity_gb, 0) AS "Memory (GB)",
    COALESCE(provisioned_space_gb, 0)     AS "Disk (GB)"
FROM latest
ORDER BY vmname
"""

# =============================================================================
# Hyperconverged Compute — VMs on non-KM VMware clusters + Nutanix Acropolis
# =============================================================================

# Hyperconverged VM count (VMware non-KM + Nutanix, deduplicated)
# Params: (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts)
CUSTOMER_HYPERCONV_VM_COUNT = """
WITH vmware_vms AS (
    SELECT DISTINCT vmname
    FROM public.vm_metrics
    WHERE vmname ILIKE %s
      AND cluster NOT ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
),
nutanix_vms AS (
    SELECT DISTINCT vm_name
    FROM public.nutanix_vm_metrics
    WHERE vm_name ILIKE %s AND collection_time BETWEEN %s AND %s
)
SELECT
    (SELECT COUNT(*) FROM vmware_vms v
     WHERE NOT EXISTS (SELECT 1 FROM nutanix_vms n WHERE n.vm_name = v.vmname)) AS vmware_only,
    (SELECT COUNT(*) FROM nutanix_vms)                                          AS nutanix_total,
    (SELECT COUNT(*) FROM (
        SELECT vmname AS vm_name FROM vmware_vms
        UNION
        SELECT vm_name FROM nutanix_vms
    ) all_unique)                                                                AS total
"""

# Hyperconverged VM resource totals (CPU / memory / disk, deduplicated)
# Params: (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts)
CUSTOMER_HYPERCONV_RESOURCE_TOTALS = """
WITH vmware_latest AS (
    SELECT DISTINCT ON (vmname)
        vmname,
        number_of_cpus,
        total_memory_capacity_gb,
        provisioned_space_gb
    FROM public.vm_metrics
    WHERE vmname ILIKE %s
      AND cluster NOT ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY vmname, timestamp DESC
),
nutanix_latest AS (
    SELECT DISTINCT ON (vm_name)
        vm_name,
        cpu_count,
        (memory_capacity / 1024.0 / 1024.0 / 1024.0) AS memory_gb,
        (disk_capacity  / 1024.0 / 1024.0 / 1024.0) AS disk_gb
    FROM public.nutanix_vm_metrics
    WHERE vm_name ILIKE %s AND collection_time BETWEEN %s AND %s
    ORDER BY vm_name, collection_time DESC
)
SELECT
    (
        (SELECT COALESCE(SUM(v.number_of_cpus), 0) FROM vmware_latest v
         WHERE NOT EXISTS (SELECT 1 FROM nutanix_latest n WHERE n.vm_name = v.vmname))
        + (SELECT COALESCE(SUM(n.cpu_count), 0) FROM nutanix_latest n)
    ) AS cpu_total,
    (
        (SELECT COALESCE(SUM(v.total_memory_capacity_gb), 0) FROM vmware_latest v
         WHERE NOT EXISTS (SELECT 1 FROM nutanix_latest n WHERE n.vm_name = v.vmname))
        + (SELECT COALESCE(SUM(n.memory_gb), 0) FROM nutanix_latest n)
    ) AS memory_gb,
    (
        (SELECT COALESCE(SUM(v.provisioned_space_gb), 0) FROM vmware_latest v
         WHERE NOT EXISTS (SELECT 1 FROM nutanix_latest n WHERE n.vm_name = v.vmname))
        + (SELECT COALESCE(SUM(n.disk_gb), 0) FROM nutanix_latest n)
    ) AS disk_gb
"""

# Hyperconverged VM detail list for billing (VMware non-KM + Nutanix, deduplicated)
# Params: (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts)
CUSTOMER_HYPERCONV_VM_LIST = """
WITH vmware_latest AS (
    SELECT DISTINCT ON (vmname)
        vmname,
        cluster,
        number_of_cpus,
        total_memory_capacity_gb,
        provisioned_space_gb
    FROM public.vm_metrics
    WHERE vmname ILIKE %s
      AND cluster NOT ILIKE '%%KM%%'
      AND timestamp BETWEEN %s AND %s
    ORDER BY vmname, timestamp DESC
),
nutanix_latest AS (
    SELECT DISTINCT ON (vm_name)
        vm_name,
        cpu_count,
        (memory_capacity / 1024.0 / 1024.0 / 1024.0) AS memory_gb,
        (disk_capacity  / 1024.0 / 1024.0 / 1024.0) AS disk_gb
    FROM public.nutanix_vm_metrics
    WHERE vm_name ILIKE %s AND collection_time BETWEEN %s AND %s
    ORDER BY vm_name, collection_time DESC
),
all_unique AS (
    SELECT vmname AS vm_name FROM vmware_latest
    UNION
    SELECT vm_name FROM nutanix_latest
)
SELECT
    u.vm_name AS "VM Name",
    CASE
        WHEN v.vmname IS NOT NULL AND n.vm_name IS NOT NULL THEN 'Nutanix (VMware Managed)'
        WHEN v.vmname IS NOT NULL                           THEN 'VMware'
        ELSE 'Nutanix'
    END AS "Source",
    COALESCE(v.cluster, 'Nutanix') AS "Cluster",
    COALESCE(v.number_of_cpus, n.cpu_count, 0)           AS "CPU",
    COALESCE(v.total_memory_capacity_gb, n.memory_gb, 0) AS "Memory (GB)",
    COALESCE(v.provisioned_space_gb, n.disk_gb, 0)       AS "Disk (GB)"
FROM all_unique u
LEFT JOIN vmware_latest v ON v.vmname = u.vm_name
LEFT JOIN nutanix_latest n ON n.vm_name = u.vm_name
ORDER BY "Source", "VM Name"
"""

# --- Physical Inventory (discovery_netbox_inventory_device) ---
# Only active devices (same convention as loki_locations DC list: status_value = 'active').
# Further aggregation/filtering is done in Python (dc_service) after loading this snapshot.
# Location resolution uses the in-memory loki LOCATION_DC_MAP (loki.py), not a SQL JOIN.
#
# The table is append-only (one row per device per collection run); DISTINCT ON keeps only
# the most recent row per logical device key (name, site_id, location_id).

PHYSICAL_INVENTORY_ALL_DEVICES = """
SELECT DISTINCT ON (name, site_id, location_id)
    id,
    name,
    device_type_name,
    manufacturer_name,
    device_role_name,
    tenant_id,
    site_id,
    site_name,
    location_id,
    location_name
FROM public.discovery_netbox_inventory_device
WHERE status_value = 'active'
ORDER BY name, site_id, location_id, collection_time DESC NULLS LAST
"""
