"""SQL for per-rack load: NetBox rack membership joined to host metrics by name.

The rack list is supplied by the caller (from the same canonical per-DC rack query
the floor map and occupancy endpoint use) rather than re-derived here. A second,
independently-written DC-scoping rule is how two screens end up disagreeing about
one datacenter -- see ADR-0028 section 6.

None of the metric SELECTs below wrap their numeric columns in COALESCE(col, 0).
A NULL reading means "this counter did not report" (e.g. a collector outage), and
must reach app.services.rack_load's aggregation layer as None so it renders as
"Not monitored" -- never as an arithmetic 0, which reads as "idle" (or, on IBM's
available-memory column, would compute used = total - 0 = total: a false 100%
painting a healthy rack red). Task 1 fixed this exact bug in the aggregation
helpers; the raw SQL here must not reintroduce it one layer down by coalescing
away the NULL before aggregation ever sees it.
"""
from __future__ import annotations

# Params: (rack_names: list[str],)
DEVICES_BY_RACK_NAMES = """
SELECT DISTINCT ON (d.rack_name, lower(d.name))
    d.rack_name,
    d.name
FROM public.discovery_netbox_inventory_device d
WHERE d.rack_name = ANY(%s::text[])
  AND d.status_value = 'active'
  AND d.name IS NOT NULL
ORDER BY d.rack_name, lower(d.name), d.collection_time DESC NULLS LAST
"""

# Params: (start_ts, end_ts)
VMWARE_HOST_LATEST = """
SELECT DISTINCT ON (vmhost)
    vmhost,
    cpu_ghz_used,
    cpu_ghz_capacity,
    memory_used_gb,
    memory_capacity_gb
FROM public.vmhost_metrics
WHERE "timestamp" BETWEEN %s AND %s
ORDER BY vmhost, "timestamp" DESC
"""

# Params: (start_ts, end_ts)
NUTANIX_HOST_LATEST = """
SELECT DISTINCT ON (h.host_name)
    h.host_name,
    h.cpu_usage_avg,
    h.total_cpu_capacity,
    h.memory_usage_avg,
    h.total_memory_capacity
FROM public.nutanix_host_metrics h
WHERE h.collectiontime BETWEEN %s AND %s
ORDER BY h.host_name, h.collectiontime DESC
"""

# Params: (start_ts, end_ts)
# IBM reports AVAILABLE memory; the "used" side is derived in Python.
# NOTE: ibm_server_general's time column is named `time`, not `timestamp` --
# every other query against this table in app/db/queries/ibm.py and
# customer.py, plus sql/analysis/analysis_platform_dc_columns.sql, filters on
# `time`. Using "timestamp" here would raise UndefinedColumn at execution
# time; _run_rows swallows that and returns [], which would silently make
# every IBM-hosted rack read as "Not monitored" forever.
IBM_SERVER_LATEST = """
SELECT DISTINCT ON (server_details_servername)
    server_details_servername,
    server_processor_utilizedprocunits,
    server_processor_totalprocunits,
    server_memory_totalmem,
    server_memory_availablemem
FROM public.ibm_server_general
WHERE time BETWEEN %s AND %s
ORDER BY server_details_servername, time DESC
"""
