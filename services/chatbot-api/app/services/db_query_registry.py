"""Allowlisted read-only DB query templates (CTO pack 05).

These are the ONLY SQL statements the chatbot may ever run against the DB, and
only when ``CHATBOT_DB_ENABLED=true``. The LLM never writes SQL; the orchestrator
picks a query_key and the chatbot binds validated parameters.

The host-CPU templates below were verified against the live bulutlake schema.
They expose per-HOST CPU (which the existing APIs only surface as cluster
aggregates), merging three sources into one normalized shape:

    source | host_name | cluster | cpu_pct | cpu_used | cpu_total | unit | collection_time

* VMware  -> vmware_host_performance_metrics       (cpu_usage_avg_perc, GHz)
* Nutanix -> nutanix_host_performance_metrics       (cpu_usage_avg/total_cpu_capacity, GHz)
           joined to nutanix_cluster_metrics for the cluster_uuid -> DC mapping
* IBM     -> ibm_server_general                     (utilized/total proc units, cores)

DC filtering is by ILIKE pattern (e.g. '%DC13%') against the cluster / server name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.services.db_readonly import ReadOnlyViolation, assert_read_only, get_db


@dataclass
class DBQuery:
    key: str
    description: str
    sql: str
    params: tuple[str, ...] = ()
    enabled: bool = False  # opt-in per template after schema verification


# --------------------------------------------------------------------------- #
# Host-level CPU — three sources unioned into one normalized result set.
# Each member is parenthesized so its own ORDER BY drives DISTINCT ON (latest
# row per host). Numeric casts wrap the *whole* arithmetic expression so integer
# division never silently yields 0.
# --------------------------------------------------------------------------- #

_HOST_CPU_UNION = """
    (SELECT DISTINCT ON (vmhost)
        'vmware' AS source, vmhost AS host_name, cluster AS cluster,
        round(cpu_usage_avg_perc::numeric, 1) AS cpu_pct,
        round(cpu_ghz_used::numeric, 1) AS cpu_used,
        round(cpu_ghz_capacity::numeric, 1) AS cpu_total,
        'GHz' AS unit,
        to_char(timestamp::timestamptz, 'YYYY-MM-DD HH24:MI') AS collection_time
     FROM vmware_host_performance_metrics
     WHERE cluster ILIKE %(dc)s
     ORDER BY vmhost, timestamp DESC)
    UNION ALL
    (SELECT DISTINCT ON (h.host_name)
        'nutanix' AS source, h.host_name AS host_name, NULL::text AS cluster,
        round((h.cpu_usage_avg::numeric / NULLIF(h.total_cpu_capacity, 0) * 100), 1) AS cpu_pct,
        round((h.cpu_usage_avg / 1e9)::numeric, 1) AS cpu_used,
        round((h.total_cpu_capacity / 1e9)::numeric, 1) AS cpu_total,
        'GHz' AS unit,
        to_char(h.collection_time::timestamptz, 'YYYY-MM-DD HH24:MI') AS collection_time
     FROM nutanix_host_performance_metrics h
     WHERE h.cluster_uuid IN (
        SELECT DISTINCT cluster_uuid FROM nutanix_cluster_metrics WHERE cluster_name ILIKE %(dc)s
     )
     ORDER BY h.host_name, h.collection_time DESC)
    UNION ALL
    (SELECT DISTINCT ON (server_details_servername)
        'ibm' AS source, server_details_servername AS host_name, NULL::text AS cluster,
        round((server_processor_utilizedprocunits / NULLIF(server_processor_totalprocunits, 0) * 100)::numeric, 1) AS cpu_pct,
        round(server_processor_utilizedprocunits::numeric, 2) AS cpu_used,
        round(server_processor_totalprocunits::numeric, 2) AS cpu_total,
        'cores' AS unit,
        to_char("time"::timestamptz, 'YYYY-MM-DD HH24:MI') AS collection_time
     FROM ibm_server_general
     WHERE server_details_servername ILIKE %(dc)s
       -- ibm_server_general is ~20M rows, so bound to the recent (indexed) window
       -- to keep DISTINCT ON fast. Returns currently-reporting IBM Power servers.
       AND "time" >= now() - interval '3 days'
     ORDER BY server_details_servername, "time" DESC)
"""

_HOST_CPU_COLS = "source, host_name, cluster, cpu_pct, cpu_used, cpu_total, unit, collection_time"


# --------------------------------------------------------------------------- #
# VM-level CPU — Nutanix + IBM LPAR. Data is ~days old, so the recency window is
# anchored to each source's own max timestamp (NOT now()) via %(days)s.
#   * Nutanix (nutanix_vm_performance_metrics): cpu_usage_avg is ppm (1e6=100%) -> /10000 = %.
#   * IBM LPAR (ibm_lpar_performance_metrics): utilized/entitled proc units * 100
#     (uncapped LPARs can exceed 100%).
# VMware VM is intentionally excluded: vmware_vm_performance_metrics has no usable
# CPU capacity (total_cpu_capacity_mhz = 0) so a % can't be computed without
# fabricating, and its 6.5M-row scan blew the statement timeout. The evaluator
# surfaces this gap to the model.
# --------------------------------------------------------------------------- #

_VM_CPU_UNION = """
    (SELECT 'nutanix' AS source, h.vm_name AS vm_name, h.host_name AS host_name, NULL::text AS cluster,
        round(avg(h.cpu_usage_avg / 10000.0)::numeric, 1) AS cpu_pct_avg,
        round(max(h.cpu_usage_max / 10000.0)::numeric, 1) AS cpu_pct_max,
        round(avg(h.cpu_usage_avg / 10000.0)::numeric, 1) AS cpu_used_avg, NULL::numeric AS cpu_total,
        'percent' AS unit, count(*) AS sample_count,
        to_char(min(h.collection_time::timestamptz), 'YYYY-MM-DD HH24:MI') AS first_collection_time,
        to_char(max(h.collection_time::timestamptz), 'YYYY-MM-DD HH24:MI') AS last_collection_time
     FROM nutanix_vm_performance_metrics h
     WHERE h.cluster_uuid::text IN (
        SELECT DISTINCT cluster_uuid FROM nutanix_cluster_metrics WHERE cluster_name ILIKE %(dc)s
     )
       AND h.collection_time >= (SELECT max(collection_time) FROM nutanix_vm_performance_metrics) - (%(days)s * interval '1 day')
     GROUP BY h.vm_name, h.host_name)
    UNION ALL
    (SELECT 'ibm' AS source, lpar_name AS vm_name, server_name AS host_name, NULL::text AS cluster,
        round(avg(utilized_proc_units / NULLIF(entitled_proc_units, 0) * 100)::numeric, 1) AS cpu_pct_avg,
        round(max(utilized_proc_units / NULLIF(entitled_proc_units, 0) * 100)::numeric, 1) AS cpu_pct_max,
        round(avg(utilized_proc_units)::numeric, 2) AS cpu_used_avg,
        round(max(entitled_proc_units)::numeric, 2) AS cpu_total,
        'cores' AS unit, count(*) AS sample_count,
        to_char(min(timestamp), 'YYYY-MM-DD HH24:MI') AS first_collection_time,
        to_char(max(timestamp), 'YYYY-MM-DD HH24:MI') AS last_collection_time
     FROM ibm_lpar_performance_metrics
     WHERE server_name ILIKE %(dc)s
       AND timestamp >= (SELECT max(timestamp) FROM ibm_lpar_performance_metrics) - (%(days)s * interval '1 day')
     GROUP BY lpar_name, server_name)
"""

_VM_CPU_COLS = (
    "source, vm_name, host_name, cluster, cpu_pct_avg, cpu_pct_max, cpu_used_avg, "
    "cpu_total, unit, sample_count, first_collection_time, last_collection_time"
)


DB_QUERIES: dict[str, DBQuery] = {
    # ----- Host-level CPU (verified against live schema) ------------------ #
    "db_get_dc_host_cpu_latest": DBQuery(
        key="db_get_dc_host_cpu_latest",
        description="Per-host latest CPU usage in a datacenter (VMware/Nutanix/IBM).",
        sql=(
            f"SELECT {_HOST_CPU_COLS} FROM ({_HOST_CPU_UNION}) c "
            "ORDER BY source, host_name LIMIT %(limit)s"
        ),
        params=("dc", "limit"),
        enabled=True,
    ),
    "db_get_dc_host_cpu_top": DBQuery(
        key="db_get_dc_host_cpu_top",
        description="Highest-CPU hosts in a datacenter (VMware/Nutanix/IBM).",
        sql=(
            f"SELECT {_HOST_CPU_COLS} FROM ({_HOST_CPU_UNION}) c "
            "ORDER BY cpu_pct DESC NULLS LAST LIMIT %(limit)s"
        ),
        params=("dc", "limit"),
        enabled=True,
    ),
    "db_get_dc_host_cpu_summary": DBQuery(
        key="db_get_dc_host_cpu_summary",
        description="Per-source host CPU summary (count, avg/max/min, latest collection).",
        sql=(
            f"WITH hosts AS ({_HOST_CPU_UNION}) "
            "SELECT source, count(*) AS host_count, "
            "round(avg(cpu_pct), 1) AS cpu_avg_pct, "
            "round(max(cpu_pct), 1) AS cpu_max_pct, "
            "round(min(cpu_pct), 1) AS cpu_min_pct, "
            "max(collection_time) AS latest_collection "
            "FROM hosts GROUP BY source ORDER BY source"
        ),
        params=("dc",),
        enabled=True,
    ),
    # ----- VM-level CPU (verified against live schema) -------------------- #
    "db_get_dc_vm_cpu_top": DBQuery(
        key="db_get_dc_vm_cpu_top",
        description="Top VMs by CPU over the last N days in a datacenter (VMware/Nutanix/IBM).",
        sql=(
            f"SELECT {_VM_CPU_COLS} FROM ({_VM_CPU_UNION}) c "
            "ORDER BY cpu_pct_avg DESC NULLS LAST, cpu_used_avg DESC NULLS LAST LIMIT %(limit)s"
        ),
        params=("dc", "days", "limit"),
        enabled=True,
    ),
    "db_get_dc_vm_cpu_latest": DBQuery(
        key="db_get_dc_vm_cpu_latest",
        description="Most recent per-VM CPU snapshot in a datacenter.",
        sql=(
            f"SELECT {_VM_CPU_COLS} FROM ({_VM_CPU_UNION}) c "
            "ORDER BY last_collection_time DESC, cpu_pct_avg DESC NULLS LAST LIMIT %(limit)s"
        ),
        params=("dc", "days", "limit"),
        enabled=True,
    ),
    "db_get_dc_vm_cpu_summary": DBQuery(
        key="db_get_dc_vm_cpu_summary",
        description="Per-source VM CPU summary (count, avg/max, latest collection).",
        sql=(
            f"WITH v AS ({_VM_CPU_UNION}) "
            "SELECT source, count(*) AS vm_count, round(avg(cpu_pct_avg), 1) AS avg_cpu_pct, "
            "round(max(cpu_pct_max), 1) AS max_cpu_pct, max(last_collection_time) AS latest_collection "
            "FROM v GROUP BY source ORDER BY source"
        ),
        params=("dc", "days"),
        enabled=True,
    ),
    # ----- Classic-architecture host CPU allocation variability ----------- #
    # "Classic" (Klasik Mimari) = cluster name contains 'KM'. Allocated CPU per
    # host = sum of VMs' vCPU on that host (number_of_cpus; the GHz capacity
    # column is empty in this dataset, so we report vCPU count, not GHz — no
    # fabrication). Per host: variability (stddev / min-max range) of allocated
    # vCPU over the recent N-day window, plus direction (first vs last sample).
    "db_get_dc_classic_host_cpu_allocation_variability": DBQuery(
        key="db_get_dc_classic_host_cpu_allocation_variability",
        description="Top classic (KM) hosts by allocated-vCPU variability over N days.",
        sql=(
            "WITH host_ts AS ("
            "  SELECT vmhost, cluster, timestamp::timestamptz AS ts, sum(number_of_cpus) AS alloc_vcpu"
            "  FROM vmware_vm_performance_metrics"
            "  WHERE cluster ILIKE %(dc)s AND cluster ILIKE '%%KM%%'"
            "    AND inserted_at >= (SELECT max(inserted_at) FROM vmware_vm_performance_metrics) - (%(days)s * interval '1 day')"
            "  GROUP BY vmhost, cluster, timestamp), "
            "agg AS ("
            "  SELECT vmhost AS host_name, max(cluster) AS cluster,"
            "    round(avg(alloc_vcpu)::numeric, 1) AS alloc_vcpu_avg,"
            "    min(alloc_vcpu) AS alloc_vcpu_min, max(alloc_vcpu) AS alloc_vcpu_max,"
            "    round(stddev(alloc_vcpu)::numeric, 2) AS alloc_vcpu_stddev,"
            "    (max(alloc_vcpu) - min(alloc_vcpu)) AS alloc_vcpu_range, count(*) AS sample_count,"
            "    (array_agg(alloc_vcpu ORDER BY ts DESC))[1] AS last_v,"
            "    (array_agg(alloc_vcpu ORDER BY ts ASC))[1] AS first_v,"
            "    to_char(min(ts), 'YYYY-MM-DD HH24:MI') AS first_collection_time,"
            "    to_char(max(ts), 'YYYY-MM-DD HH24:MI') AS last_collection_time"
            "  FROM host_ts GROUP BY vmhost) "
            "SELECT host_name, cluster, 'vCPU' AS unit, alloc_vcpu_avg, alloc_vcpu_min, alloc_vcpu_max,"
            " alloc_vcpu_stddev, alloc_vcpu_range, (last_v - first_v) AS alloc_vcpu_change,"
            " CASE WHEN last_v > first_v THEN 'artis' WHEN last_v < first_v THEN 'azalis' ELSE 'sabit' END AS direction,"
            " sample_count, first_collection_time, last_collection_time"
            " FROM agg ORDER BY alloc_vcpu_stddev DESC NULLS LAST LIMIT %(limit)s"
        ),
        params=("dc", "days", "limit"),
        enabled=True,
    ),
    # ----- VMware cluster inventory (for API-vs-DB comparison) ------------- #
    # cluster_metrics holds the per-cluster VMware inventory. 'KM' in the name =
    # classic, otherwise hyperconverged-named. Returns the latest snapshot per
    # cluster across ALL time (the API endpoint is time-filtered, so the DB set
    # is broader — the difference is exactly what the user asks for).
    "db_get_dc_vmware_clusters": DBQuery(
        key="db_get_dc_vmware_clusters",
        description="VMware cluster inventory (name, type, host/vm count, latest collection) for a DC.",
        sql=(
            "SELECT 'cluster_metrics' AS source, cluster_name, cluster_type, host_count, vm_count, "
            "latest_collection_time FROM ("
            "  SELECT DISTINCT ON (cluster) cluster AS cluster_name,"
            "    CASE WHEN cluster ILIKE '%%KM%%' THEN 'classic' ELSE 'hyperconverged' END AS cluster_type,"
            "    vhost_count AS host_count, vm_count,"
            "    to_char(timestamp::timestamptz, 'YYYY-MM-DD HH24:MI') AS latest_collection_time"
            "  FROM cluster_metrics WHERE datacenter ILIKE %(dc)s"
            "  ORDER BY cluster, timestamp DESC) c "
            "ORDER BY cluster_name LIMIT %(limit)s"
        ),
        params=("dc", "limit"),
        enabled=True,
    ),
    # ----- Global KM cluster memory ranking (per-cluster, all DCs) -------- #
    "db_get_global_km_cluster_memory_top": DBQuery(
        key="db_get_global_km_cluster_memory_top",
        description="Top classic (KM) clusters by memory_used_gb across all datacenters (optional DC filter).",
        sql=(
            "WITH latest AS ("
            "  SELECT DISTINCT ON (cluster)"
            "    datacenter,"
            "    cluster AS cluster_name,"
            "    round(memory_used_gb::numeric, 1) AS memory_used_gb,"
            "    round(memory_capacity_gb::numeric, 1) AS memory_capacity_gb,"
            "    CASE WHEN memory_capacity_gb > 0"
            "      THEN round(100.0 * memory_used_gb / memory_capacity_gb, 1)"
            "      ELSE NULL END AS memory_pct,"
            "    to_char(timestamp::timestamptz, 'YYYY-MM-DD HH24:MI') AS collection_time"
            "  FROM cluster_metrics"
            "  WHERE cluster ILIKE '%%KM%%'"
            "    AND (%(dc)s IS NULL OR datacenter ILIKE %(dc)s)"
            "  ORDER BY cluster, timestamp DESC"
            ") "
            "SELECT datacenter, cluster_name, memory_used_gb, memory_capacity_gb, memory_pct, collection_time"
            " FROM latest"
            " ORDER BY memory_used_gb DESC NULLS LAST, memory_pct DESC NULLS LAST"
            " LIMIT %(limit)s"
        ),
        params=("dc", "limit"),
        enabled=True,
    ),
    # ----- Generic examples (disabled by default) ------------------------- #
    "db_list_recent_collection_times": DBQuery(
        key="db_list_recent_collection_times",
        description="Latest collection time per source table.",
        sql=(
            "SELECT source_name, max(collectiontime) AS latest_collectiontime "
            "FROM data_collection_health GROUP BY source_name "
            "ORDER BY latest_collectiontime DESC LIMIT %(limit)s"
        ),
        params=("limit",),
        enabled=False,
    ),
}

# Validate every template at import time so a malformed/forbidden template fails
# fast in CI rather than at request time.
for _q in DB_QUERIES.values():
    assert_read_only(_q.sql)


def list_enabled_keys() -> list[str]:
    return [k for k, q in DB_QUERIES.items() if q.enabled]


def run_query(key: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Run an allowlisted, enabled template. Raises ``ReadOnlyViolation`` otherwise."""
    q = DB_QUERIES.get(key)
    if q is None:
        raise ReadOnlyViolation(f"unknown query key: {key}")
    if not q.enabled:
        raise ReadOnlyViolation(f"query '{key}' is not enabled")
    bound = {p: (params or {}).get(p) for p in q.params}
    return get_db().run_template(q.sql, bound)
