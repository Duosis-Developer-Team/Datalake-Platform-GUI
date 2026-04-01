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

IBM_LPAR_TOTALS = """
SELECT COUNT(DISTINCT lparname) AS lpar_count
FROM public.ibm_lpar_general
WHERE lparname ILIKE %s
  AND LEFT(lparname, 1) <> '_'
  AND time BETWEEN %s AND %s
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

CUSTOMER_POWER_CPU_TOTAL = """
WITH latest_lpar_stats AS (
    SELECT DISTINCT ON (lparname)
        lpar_processor_currentvirtualprocessors
    FROM public.ibm_lpar_general
    WHERE lparname ILIKE %s
      AND LEFT(lparname, 1) <> '_'
      AND time BETWEEN %s AND %s
    ORDER BY lparname, time DESC
)
SELECT
    COALESCE(SUM(lpar_processor_currentvirtualprocessors), 0) AS "Total CPU (Power HMC)"
FROM latest_lpar_stats
"""

CUSTOMER_POWER_MEMORY_TOTAL = """
WITH latest_lpar_stats AS (
    SELECT DISTINCT ON (lparname)
        lpar_memory_logicalmem / 1.048576 AS lpar_memory_logicalmem
    FROM public.ibm_lpar_general
    WHERE lparname ILIKE %s
      AND LEFT(lparname, 1) <> '_'
      AND time BETWEEN %s AND %s
    ORDER BY lparname, time DESC
)
SELECT
    COALESCE(SUM(lpar_memory_logicalmem), 0) AS "Total Memory (Power HMC)"
FROM latest_lpar_stats
"""

CUSTOMER_POWER_VM_LIST = """
SELECT DISTINCT
    lparname AS "VM Name",
    'Power HMC' AS "Source"
FROM public.ibm_lpar_general
WHERE lparname ILIKE %s AND time BETWEEN %s AND %s
ORDER BY "VM Name"
"""

CUSTOMER_POWER_DELETED_LPAR_NAMES = """
SELECT DISTINCT lparname
FROM public.ibm_lpar_general
WHERE lparname ILIKE %s
  AND LEFT(lparname, 1) = '_'
  AND time BETWEEN %s AND %s
ORDER BY lparname
"""

CUSTOMER_POWER_LPAR_DETAIL_LIST = """
WITH agg AS (
    SELECT lparname,
        MIN(lpar_processor_utilizedprocunits
            / NULLIF(lpar_processor_currentvirtualprocessors, 0) * 100.0) AS cpu_pct_min,
        AVG(lpar_processor_utilizedprocunits
            / NULLIF(lpar_processor_currentvirtualprocessors, 0) * 100.0) AS cpu_pct_avg,
        MAX(lpar_processor_utilizedprocunits
            / NULLIF(lpar_processor_currentvirtualprocessors, 0) * 100.0) AS cpu_pct_max,
        MIN(lpar_memory_backedphysicalmem
            / NULLIF(lpar_memory_logicalmem, 0) * 100.0) AS mem_pct_min,
        AVG(lpar_memory_backedphysicalmem
            / NULLIF(lpar_memory_logicalmem, 0) * 100.0) AS mem_pct_avg,
        MAX(lpar_memory_backedphysicalmem
            / NULLIF(lpar_memory_logicalmem, 0) * 100.0) AS mem_pct_max
    FROM public.ibm_lpar_general
    WHERE lparname ILIKE %s
      AND LEFT(lparname, 1) <> '_'
      AND time BETWEEN %s AND %s
    GROUP BY lparname
),
latest_lpar AS (
    SELECT DISTINCT ON (lparname)
        lparname,
        lpar_processor_currentvirtualprocessors,
        lpar_memory_logicalmem / 1.048576 AS memory_gb,
        lpar_details_state
    FROM public.ibm_lpar_general
    WHERE lparname ILIKE %s
      AND LEFT(lparname, 1) <> '_'
      AND time BETWEEN %s AND %s
    ORDER BY lparname, time DESC
)
SELECT
    l.lparname AS "VM Name",
    'Power HMC' AS "Source",
    COALESCE(l.lpar_processor_currentvirtualprocessors, 0) AS "CPU",
    ROUND(COALESCE(a.cpu_pct_min, 0)::numeric, 2) AS "CPU min pct",
    ROUND(COALESCE(a.cpu_pct_avg, 0)::numeric, 2) AS "CPU avg pct",
    ROUND(COALESCE(a.cpu_pct_max, 0)::numeric, 2) AS "CPU max pct",
    COALESCE(l.memory_gb, 0) AS "Memory (GB)",
    ROUND(COALESCE(a.mem_pct_min, 0)::numeric, 2) AS "Mem min pct",
    ROUND(COALESCE(a.mem_pct_avg, 0)::numeric, 2) AS "Mem avg pct",
    ROUND(COALESCE(a.mem_pct_max, 0)::numeric, 2) AS "Mem max pct",
    COALESCE(l.lpar_details_state, '') AS "State"
FROM latest_lpar l
JOIN agg a ON a.lparname = l.lparname
ORDER BY "VM Name"
"""

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

CUSTOMER_VEEAM_DEFINED_SESSIONS = """
SELECT
    COUNT(DISTINCT name) AS "Defined Sessions"
FROM public.raw_veeam_sessions
WHERE name ILIKE %s
"""

CUSTOMER_VEEAM_SESSION_TYPES = """
SELECT
    session_type AS "Session Type",
    COUNT(DISTINCT name) AS "Defined Session Count"
FROM public.raw_veeam_sessions
WHERE name ILIKE %s
GROUP BY session_type
ORDER BY "Defined Session Count" DESC
"""

CUSTOMER_VEEAM_SESSION_PLATFORMS = """
SELECT
    platform_name AS "Platform",
    COUNT(DISTINCT name) AS "Defined Session Count"
FROM public.raw_veeam_sessions
WHERE name ILIKE %s
GROUP BY platform_name
ORDER BY "Defined Session Count" DESC
"""

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
# Cluster discovery — Pure vs VMware-managed Nutanix (normalize in Python)
# Params: (start_ts, end_ts)
ALL_VMWARE_CLUSTER_NAMES = """
SELECT DISTINCT ON (cluster)
    cluster,
    CASE WHEN cluster ILIKE '%%KM%%' THEN 'classic' ELSE 'hyperconv' END AS arch_type
FROM public.cluster_metrics
WHERE timestamp BETWEEN %s AND %s
ORDER BY cluster, timestamp DESC
"""

# Params: (start_ts, end_ts)
ALL_NUTANIX_CLUSTER_NAMES = """
SELECT DISTINCT ON (cluster_name)
    cluster_name,
    cluster_uuid
FROM public.nutanix_cluster_metrics
WHERE collection_time BETWEEN %s AND %s
ORDER BY cluster_name, collection_time DESC
"""

# Fallback params: ()
ALL_NUTANIX_CLUSTER_NAMES_LATEST = """
SELECT DISTINCT ON (cluster_name)
    cluster_name,
    cluster_uuid
FROM public.nutanix_cluster_metrics
ORDER BY cluster_name, collection_time DESC
"""

# =============================================================================
# Classic Compute — VMs on KM clusters (vm_metrics.cluster ILIKE '%KM%')
# =============================================================================

CUSTOMER_CLASSIC_VM_COUNT = """
SELECT COUNT(DISTINCT vmname) AS vm_count
FROM public.vm_metrics
WHERE vmname ILIKE %s
  AND cluster ILIKE '%%KM%%'
  AND LEFT(vmname, 1) <> '_'
  AND timestamp BETWEEN %s AND %s
"""

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
      AND LEFT(vmname, 1) <> '_'
      AND timestamp BETWEEN %s AND %s
    ORDER BY vmname, timestamp DESC
)
SELECT
    COALESCE(SUM(number_of_cpus), 0)          AS cpu_total,
    COALESCE(SUM(total_memory_capacity_gb), 0) AS memory_gb,
    COALESCE(SUM(provisioned_space_gb), 0)     AS disk_gb
FROM latest
"""

CUSTOMER_CLASSIC_DELETED_VM_NAMES = """
SELECT DISTINCT vmname
FROM public.vm_metrics
WHERE vmname ILIKE %s
  AND cluster ILIKE '%%KM%%'
  AND LEFT(vmname, 1) = '_'
  AND timestamp BETWEEN %s AND %s
ORDER BY vmname
"""

CUSTOMER_CLASSIC_VM_LIST = """
WITH agg AS (
    SELECT vmname,
        MIN(CASE WHEN COALESCE(total_cpu_capacity_mhz, 0) > 0
            THEN cpu_usage_min_mhz / total_cpu_capacity_mhz * 100.0 END) AS cpu_pct_min,
        AVG(CASE WHEN COALESCE(total_cpu_capacity_mhz, 0) > 0
            THEN cpu_usage_avg_mhz / total_cpu_capacity_mhz * 100.0 END) AS cpu_pct_avg,
        MAX(CASE WHEN COALESCE(total_cpu_capacity_mhz, 0) > 0
            THEN cpu_usage_max_mhz / total_cpu_capacity_mhz * 100.0 END) AS cpu_pct_max,
        MIN(memory_usage_min_perc) AS mem_pct_min,
        AVG(memory_usage_avg_perc) AS mem_pct_avg,
        MAX(memory_usage_max_perc) AS mem_pct_max,
        MIN(used_space_gb) AS disk_used_min_gb,
        MAX(used_space_gb) AS disk_used_max_gb
    FROM public.vm_metrics
    WHERE vmname ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND LEFT(vmname, 1) <> '_'
      AND timestamp BETWEEN %s AND %s
    GROUP BY vmname
),
latest AS (
    SELECT DISTINCT ON (vmname)
        vmname,
        cluster,
        number_of_cpus,
        total_memory_capacity_gb,
        provisioned_space_gb
    FROM public.vm_metrics
    WHERE vmname ILIKE %s
      AND cluster ILIKE '%%KM%%'
      AND LEFT(vmname, 1) <> '_'
      AND timestamp BETWEEN %s AND %s
    ORDER BY vmname, timestamp DESC
)
SELECT
    l.vmname AS "VM Name",
    'Classic' AS "Source",
    l.cluster AS "Cluster",
    COALESCE(l.number_of_cpus, 0) AS "CPU",
    ROUND(COALESCE(a.cpu_pct_min, 0)::numeric, 2) AS "CPU min pct",
    ROUND(COALESCE(a.cpu_pct_avg, 0)::numeric, 2) AS "CPU avg pct",
    ROUND(COALESCE(a.cpu_pct_max, 0)::numeric, 2) AS "CPU max pct",
    COALESCE(l.total_memory_capacity_gb, 0) AS "Memory (GB)",
    ROUND(COALESCE(a.mem_pct_min, 0)::numeric, 2) AS "Mem min pct",
    ROUND(COALESCE(a.mem_pct_avg, 0)::numeric, 2) AS "Mem avg pct",
    ROUND(COALESCE(a.mem_pct_max, 0)::numeric, 2) AS "Mem max pct",
    COALESCE(l.provisioned_space_gb, 0) AS "Disk (GB)",
    ROUND(COALESCE(a.disk_used_min_gb, 0)::numeric, 2) AS "Disk used min (GB)",
    ROUND(COALESCE(a.disk_used_max_gb, 0)::numeric, 2) AS "Disk used max (GB)"
FROM latest l
JOIN agg a ON a.vmname = l.vmname
ORDER BY l.vmname
"""

# =============================================================================
# Hyperconverged — VMware non-KM + Nutanix only on VMware-managed clusters
# Params: (vm_pattern, start_ts, end_ts, vm_pattern, start_ts, end_ts,
#          managed_cluster_names[], start_ts, end_ts)
# =============================================================================

CUSTOMER_HYPERCONV_VM_COUNT = """
WITH vmware_vms AS (
    SELECT DISTINCT vmname
    FROM public.vm_metrics
    WHERE vmname ILIKE %s
      AND cluster NOT ILIKE '%%KM%%'
      AND LEFT(vmname, 1) <> '_'
      AND timestamp BETWEEN %s AND %s
),
nutanix_vms AS (
    SELECT DISTINCT nvm.vm_name
    FROM public.nutanix_vm_metrics nvm
    WHERE nvm.vm_name ILIKE %s
      AND LEFT(nvm.vm_name, 1) <> '_'
      AND nvm.collection_time BETWEEN %s AND %s
      AND nvm.cluster_uuid::text IN (
        SELECT DISTINCT ON (cluster_name) cluster_uuid
        FROM public.nutanix_cluster_metrics
        WHERE cluster_name = ANY(%s::text[])
          AND collection_time BETWEEN %s AND %s
        ORDER BY cluster_name, collection_time DESC
      )
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
      AND LEFT(vmname, 1) <> '_'
      AND timestamp BETWEEN %s AND %s
    ORDER BY vmname, timestamp DESC
),
nutanix_latest AS (
    SELECT DISTINCT ON (nvm.vm_name)
        nvm.vm_name,
        nvm.cpu_count,
        (nvm.memory_capacity / 1024.0 / 1024.0 / 1024.0) AS memory_gb,
        (nvm.disk_capacity  / 1024.0 / 1024.0 / 1024.0) AS disk_gb
    FROM public.nutanix_vm_metrics nvm
    WHERE nvm.vm_name ILIKE %s
      AND LEFT(nvm.vm_name, 1) <> '_'
      AND nvm.collection_time BETWEEN %s AND %s
      AND nvm.cluster_uuid::text IN (
        SELECT DISTINCT ON (cluster_name) cluster_uuid
        FROM public.nutanix_cluster_metrics
        WHERE cluster_name = ANY(%s::text[])
          AND collection_time BETWEEN %s AND %s
        ORDER BY cluster_name, collection_time DESC
      )
    ORDER BY nvm.vm_name, nvm.collection_time DESC
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

CUSTOMER_HYPERCONV_DELETED_VM_NAMES = """
SELECT DISTINCT vm_name FROM (
    SELECT vmname AS vm_name
    FROM public.vm_metrics
    WHERE vmname ILIKE %s
      AND cluster NOT ILIKE '%%KM%%'
      AND LEFT(vmname, 1) = '_'
      AND timestamp BETWEEN %s AND %s
    UNION
    SELECT nvm.vm_name
    FROM public.nutanix_vm_metrics nvm
    WHERE nvm.vm_name ILIKE %s
      AND LEFT(nvm.vm_name, 1) = '_'
      AND nvm.collection_time BETWEEN %s AND %s
      AND nvm.cluster_uuid::text IN (
        SELECT DISTINCT ON (cluster_name) cluster_uuid
        FROM public.nutanix_cluster_metrics
        WHERE cluster_name = ANY(%s::text[])
          AND collection_time BETWEEN %s AND %s
        ORDER BY cluster_name, collection_time DESC
      )
) d
ORDER BY vm_name
"""

CUSTOMER_HYPERCONV_VM_LIST = """
WITH vmware_agg AS (
    SELECT vmname,
        MIN(CASE WHEN COALESCE(total_cpu_capacity_mhz, 0) > 0
            THEN cpu_usage_min_mhz / total_cpu_capacity_mhz * 100.0 END) AS cpu_pct_min,
        AVG(CASE WHEN COALESCE(total_cpu_capacity_mhz, 0) > 0
            THEN cpu_usage_avg_mhz / total_cpu_capacity_mhz * 100.0 END) AS cpu_pct_avg,
        MAX(CASE WHEN COALESCE(total_cpu_capacity_mhz, 0) > 0
            THEN cpu_usage_max_mhz / total_cpu_capacity_mhz * 100.0 END) AS cpu_pct_max,
        MIN(memory_usage_min_perc) AS mem_pct_min,
        AVG(memory_usage_avg_perc) AS mem_pct_avg,
        MAX(memory_usage_max_perc) AS mem_pct_max,
        MIN(used_space_gb) AS disk_used_min_gb,
        MAX(used_space_gb) AS disk_used_max_gb
    FROM public.vm_metrics
    WHERE vmname ILIKE %s
      AND cluster NOT ILIKE '%%KM%%'
      AND LEFT(vmname, 1) <> '_'
      AND timestamp BETWEEN %s AND %s
    GROUP BY vmname
),
vmware_latest AS (
    SELECT DISTINCT ON (vmname)
        vmname,
        cluster,
        number_of_cpus,
        total_memory_capacity_gb,
        provisioned_space_gb
    FROM public.vm_metrics
    WHERE vmname ILIKE %s
      AND cluster NOT ILIKE '%%KM%%'
      AND LEFT(vmname, 1) <> '_'
      AND timestamp BETWEEN %s AND %s
    ORDER BY vmname, timestamp DESC
),
nutanix_agg AS (
    SELECT nvm.vm_name,
        MIN(nvm.cpu_usage_min / 10000.0) AS cpu_pct_min,
        AVG(nvm.cpu_usage_avg / 10000.0) AS cpu_pct_avg,
        MAX(nvm.cpu_usage_max / 10000.0) AS cpu_pct_max,
        MIN(nvm.memory_usage_min / 10000.0) AS mem_pct_min,
        AVG(nvm.memory_usage_avg / 10000.0) AS mem_pct_avg,
        MAX(nvm.memory_usage_max / 10000.0) AS mem_pct_max,
        MIN(nvm.used_storage / 1073741824.0) AS disk_used_min_gb,
        MAX(nvm.used_storage / 1073741824.0) AS disk_used_max_gb
    FROM public.nutanix_vm_metrics nvm
    WHERE nvm.vm_name ILIKE %s
      AND LEFT(nvm.vm_name, 1) <> '_'
      AND nvm.collection_time BETWEEN %s AND %s
      AND nvm.cluster_uuid::text IN (
        SELECT DISTINCT ON (cluster_name) cluster_uuid
        FROM public.nutanix_cluster_metrics
        WHERE cluster_name = ANY(%s::text[])
          AND collection_time BETWEEN %s AND %s
        ORDER BY cluster_name, collection_time DESC
      )
    GROUP BY nvm.vm_name
),
nutanix_latest AS (
    SELECT DISTINCT ON (nvm.vm_name)
        nvm.vm_name,
        nvm.cpu_count,
        (nvm.memory_capacity / 1024.0 / 1024.0 / 1024.0) AS memory_gb,
        (nvm.disk_capacity  / 1024.0 / 1024.0 / 1024.0) AS disk_gb
    FROM public.nutanix_vm_metrics nvm
    WHERE nvm.vm_name ILIKE %s
      AND LEFT(nvm.vm_name, 1) <> '_'
      AND nvm.collection_time BETWEEN %s AND %s
      AND nvm.cluster_uuid::text IN (
        SELECT DISTINCT ON (cluster_name) cluster_uuid
        FROM public.nutanix_cluster_metrics
        WHERE cluster_name = ANY(%s::text[])
          AND collection_time BETWEEN %s AND %s
        ORDER BY cluster_name, collection_time DESC
      )
    ORDER BY nvm.vm_name, nvm.collection_time DESC
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
    COALESCE(v.number_of_cpus, n.cpu_count, 0) AS "CPU",
    ROUND(
        (CASE WHEN v.vmname IS NOT NULL THEN va.cpu_pct_min ELSE na.cpu_pct_min END)::numeric,
        2
    ) AS "CPU min pct",
    ROUND(
        (CASE WHEN v.vmname IS NOT NULL THEN va.cpu_pct_avg ELSE na.cpu_pct_avg END)::numeric,
        2
    ) AS "CPU avg pct",
    ROUND(
        (CASE WHEN v.vmname IS NOT NULL THEN va.cpu_pct_max ELSE na.cpu_pct_max END)::numeric,
        2
    ) AS "CPU max pct",
    COALESCE(v.total_memory_capacity_gb, n.memory_gb, 0) AS "Memory (GB)",
    ROUND(
        (CASE WHEN v.vmname IS NOT NULL THEN va.mem_pct_min ELSE na.mem_pct_min END)::numeric,
        2
    ) AS "Mem min pct",
    ROUND(
        (CASE WHEN v.vmname IS NOT NULL THEN va.mem_pct_avg ELSE na.mem_pct_avg END)::numeric,
        2
    ) AS "Mem avg pct",
    ROUND(
        (CASE WHEN v.vmname IS NOT NULL THEN va.mem_pct_max ELSE na.mem_pct_max END)::numeric,
        2
    ) AS "Mem max pct",
    COALESCE(v.provisioned_space_gb, n.disk_gb, 0) AS "Disk (GB)",
    ROUND(
        (CASE WHEN v.vmname IS NOT NULL THEN va.disk_used_min_gb ELSE na.disk_used_min_gb END)::numeric,
        2
    ) AS "Disk used min (GB)",
    ROUND(
        (CASE WHEN v.vmname IS NOT NULL THEN va.disk_used_max_gb ELSE na.disk_used_max_gb END)::numeric,
        2
    ) AS "Disk used max (GB)"
FROM all_unique u
LEFT JOIN vmware_latest v ON v.vmname = u.vm_name
LEFT JOIN nutanix_latest n ON n.vm_name = u.vm_name
LEFT JOIN vmware_agg va ON va.vmname = u.vm_name
LEFT JOIN nutanix_agg na ON na.vm_name = u.vm_name
ORDER BY "Source", "VM Name"
"""

# =============================================================================
# Pure Nutanix (AHV) — clusters with no VMware non-KM match after normalization
# Params: (managed_cluster_names[], start_ts, end_ts, vm_pattern, start_ts, end_ts)
# =============================================================================

CUSTOMER_PURE_NUTANIX_VM_COUNT = """
WITH cluster_uuids AS (
    SELECT DISTINCT ON (cluster_name) cluster_uuid
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name = ANY(%s::text[])
      AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
),
latest AS (
    SELECT DISTINCT ON (nvm.vm_name)
        nvm.vm_name
    FROM public.nutanix_vm_metrics nvm
    WHERE nvm.vm_name ILIKE %s
      AND LEFT(nvm.vm_name, 1) <> '_'
      AND nvm.collection_time BETWEEN %s AND %s
      AND nvm.cluster_uuid::text IN (SELECT cluster_uuid FROM cluster_uuids)
    ORDER BY nvm.vm_name, nvm.collection_time DESC
)
SELECT COUNT(*)::int FROM latest
"""

CUSTOMER_PURE_NUTANIX_RESOURCE_TOTALS = """
WITH cluster_uuids AS (
    SELECT DISTINCT ON (cluster_name) cluster_uuid
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name = ANY(%s::text[])
      AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
),
latest AS (
    SELECT DISTINCT ON (nvm.vm_name)
        nvm.cpu_count,
        (nvm.memory_capacity / 1024.0 / 1024.0 / 1024.0) AS memory_gb,
        (nvm.disk_capacity  / 1024.0 / 1024.0 / 1024.0) AS disk_gb
    FROM public.nutanix_vm_metrics nvm
    WHERE nvm.vm_name ILIKE %s
      AND LEFT(nvm.vm_name, 1) <> '_'
      AND nvm.collection_time BETWEEN %s AND %s
      AND nvm.cluster_uuid::text IN (SELECT cluster_uuid FROM cluster_uuids)
    ORDER BY nvm.vm_name, nvm.collection_time DESC
)
SELECT
    COALESCE(SUM(cpu_count), 0) AS cpu_total,
    COALESCE(SUM(memory_gb), 0) AS memory_gb,
    COALESCE(SUM(disk_gb), 0) AS disk_gb
FROM latest
"""

CUSTOMER_PURE_NUTANIX_DELETED_VM_NAMES = """
WITH cluster_uuids AS (
    SELECT DISTINCT ON (cluster_name) cluster_uuid
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name = ANY(%s::text[])
      AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
)
SELECT DISTINCT nvm.vm_name
FROM public.nutanix_vm_metrics nvm
WHERE nvm.vm_name ILIKE %s
  AND LEFT(nvm.vm_name, 1) = '_'
  AND nvm.collection_time BETWEEN %s AND %s
  AND nvm.cluster_uuid::text IN (SELECT cluster_uuid FROM cluster_uuids)
ORDER BY nvm.vm_name
"""

CUSTOMER_PURE_NUTANIX_VM_LIST = """
WITH cluster_uuids AS (
    SELECT DISTINCT ON (cluster_name) cluster_uuid, cluster_name
    FROM public.nutanix_cluster_metrics
    WHERE cluster_name = ANY(%s::text[])
      AND collection_time BETWEEN %s AND %s
    ORDER BY cluster_name, collection_time DESC
),
agg AS (
    SELECT nvm.vm_name,
        MIN(nvm.cpu_usage_min / 10000.0) AS cpu_pct_min,
        AVG(nvm.cpu_usage_avg / 10000.0) AS cpu_pct_avg,
        MAX(nvm.cpu_usage_max / 10000.0) AS cpu_pct_max,
        MIN(nvm.memory_usage_min / 10000.0) AS mem_pct_min,
        AVG(nvm.memory_usage_avg / 10000.0) AS mem_pct_avg,
        MAX(nvm.memory_usage_max / 10000.0) AS mem_pct_max,
        MIN(nvm.used_storage / 1073741824.0) AS disk_used_min_gb,
        MAX(nvm.used_storage / 1073741824.0) AS disk_used_max_gb
    FROM public.nutanix_vm_metrics nvm
    WHERE nvm.vm_name ILIKE %s
      AND LEFT(nvm.vm_name, 1) <> '_'
      AND nvm.collection_time BETWEEN %s AND %s
      AND nvm.cluster_uuid::text IN (SELECT cluster_uuid FROM cluster_uuids)
    GROUP BY nvm.vm_name
),
latest AS (
    SELECT DISTINCT ON (nvm.vm_name)
        nvm.vm_name,
        nvm.cluster_uuid,
        nvm.cpu_count,
        (nvm.memory_capacity / 1024.0 / 1024.0 / 1024.0) AS memory_gb,
        (nvm.disk_capacity  / 1024.0 / 1024.0 / 1024.0) AS disk_gb
    FROM public.nutanix_vm_metrics nvm
    WHERE nvm.vm_name ILIKE %s
      AND LEFT(nvm.vm_name, 1) <> '_'
      AND nvm.collection_time BETWEEN %s AND %s
      AND nvm.cluster_uuid::text IN (SELECT cluster_uuid FROM cluster_uuids)
    ORDER BY nvm.vm_name, nvm.collection_time DESC
)
SELECT
    l.vm_name AS "VM Name",
    'Pure Nutanix (AHV)' AS "Source",
    cu.cluster_name AS "Cluster",
    COALESCE(l.cpu_count, 0) AS "CPU",
    ROUND(COALESCE(a.cpu_pct_min, 0)::numeric, 2) AS "CPU min pct",
    ROUND(COALESCE(a.cpu_pct_avg, 0)::numeric, 2) AS "CPU avg pct",
    ROUND(COALESCE(a.cpu_pct_max, 0)::numeric, 2) AS "CPU max pct",
    COALESCE(l.memory_gb, 0) AS "Memory (GB)",
    ROUND(COALESCE(a.mem_pct_min, 0)::numeric, 2) AS "Mem min pct",
    ROUND(COALESCE(a.mem_pct_avg, 0)::numeric, 2) AS "Mem avg pct",
    ROUND(COALESCE(a.mem_pct_max, 0)::numeric, 2) AS "Mem max pct",
    COALESCE(l.disk_gb, 0) AS "Disk (GB)",
    ROUND(COALESCE(a.disk_used_min_gb, 0)::numeric, 2) AS "Disk used min (GB)",
    ROUND(COALESCE(a.disk_used_max_gb, 0)::numeric, 2) AS "Disk used max (GB)"
FROM latest l
JOIN agg a ON a.vm_name = l.vm_name
JOIN cluster_uuids cu ON l.cluster_uuid::text = cu.cluster_uuid
ORDER BY "VM Name"
"""
