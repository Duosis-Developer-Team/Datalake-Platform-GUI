"""Hybrid freshness registry: auto-discovery rules + curated overrides.

Pure (no DB). Discovery finds public tables with a freshness column; this module
decides which to monitor (EXCLUDE deprecated/legacy), what family + label they
belong to, and their thresholds. Curation is seeded from what we know and is
meant to be refined by the team over time.
"""
from __future__ import annotations

# Preference order for a table's freshness timestamp column.
FRESHNESS_COLUMNS = [
    "collection_time", "collection_timestamp", "checked_at", "processed_at",
    "finished_at", "check_time", "last_seen_at", "last_observed", "timestamp",
    "time", "last_updated",
]

# Deprecated / superseded / non-monitored tables (seed — team refines).
# The legacy loki_* timeseries are replaced by discovery_* (live snapshot).
_EXCLUDE_EXACT = {
    "loki_platforms", "loki_device_types", "loki_devices", "loki_locations",
    "loki_racks", "nutanix_snapshot_schedule",
    "raw_ibm_storage_ports", "raw_ibm_storage_vdisk_dumps",
}

# name-prefix -> friendly family (first match wins; order matters)
_FAMILY_PREFIXES = [
    ("discovery_netbox", "NetBox"),
    ("discovery_loki", "Loki"),
    ("discovery_ibm", "IBM"),
    ("discovery_vmware", "VMware"),
    ("discovery", "NetBox"),
    ("raw_vmware", "VMware"),
    ("raw_ibm", "IBM"),
    ("raw_panduit", "Panduit"),
    ("raw_veeam", "Backup"),
    ("vmware", "VMware"),
    ("nutanix", "Nutanix"),
    ("ibm", "IBM"),
    ("zabbix", "Zabbix"),
    ("loki", "Loki"),
    ("cluster_metrics", "VMware"),
    ("datacenter_metrics", "VMware"),
    ("vmhost", "VMware"),
    ("vm_", "VMware"),
]

# per-table overrides: label / family / warn_hours / dead_hours
OVERRIDES: dict[str, dict] = {
    "raw_vmware_datastore_metrics_agg": {"label": "VMware Datastore Metrics"},
    "raw_vmware_datastore_host_mount": {"label": "VMware Datastore Mounts"},
    "cluster_metrics": {"label": "VMware Clusters"},
    "nutanix_cluster_metrics": {"label": "Nutanix Clusters"},
    "datacenter_metrics": {"label": "VMware Datacenter"},
    "ibm_lpar_general": {"label": "IBM LPARs"},
}

# HMDL automation log tables (hmdl schema). warn/dead reference config settings.
AUTOMATION_SPECS = [
    {"key": "zabbix_sync", "label": "NetBox → Zabbix Sync", "cadence": "~8 saatte bir",
     "schema": "hmdl", "table": "zabbix_sync_log", "column": "processed_at",
     "warn": "ah_zabbix_warn_hours", "dead": "ah_zabbix_dead_hours", "where": "dry_run = FALSE"},
    {"key": "collector_sync", "label": "Datalake Collector Sync", "cadence": "günlük 02:00",
     "schema": "hmdl", "table": "collector_sync_log", "column": "finished_at",
     "warn": "ah_collector_warn_hours", "dead": "ah_collector_dead_hours",
     "where": "dry_run = FALSE", "extra": "collector"},
    {"key": "reachability_checks", "label": "Collector Reachability Checks",
     "cadence": "collector sync ile", "schema": "hmdl", "table": "collector_check_log",
     "column": "checked_at", "warn": "ah_checks_warn_hours", "dead": "ah_checks_dead_hours",
     "where": None},
    {"key": "vm_reconciliation", "label": "VM Envanter Reconciliation", "cadence": "günlük",
     "schema": "hmdl", "table": "hmdl_datalake_monitoring_clusters", "column": "check_time",
     "warn": "ah_recon_warn_hours", "dead": "ah_recon_dead_hours", "where": None},
]


def is_excluded(table: str) -> bool:
    return table in _EXCLUDE_EXACT


def family_of(table: str) -> str:
    t = table.lower()
    for prefix, fam in _FAMILY_PREFIXES:
        if t.startswith(prefix):
            return fam
    return "Other"


def _label_for(table: str) -> str:
    ov = OVERRIDES.get(table, {})
    if ov.get("label"):
        return ov["label"]
    return table.replace("_", " ").title()


def resolve(table: str, columns: list[str], *, default_warn: float, default_dead: float) -> dict | None:
    if is_excluded(table):
        return None
    col = next((c for c in FRESHNESS_COLUMNS if c in columns), None)
    if not col:
        return None
    ov = OVERRIDES.get(table, {})
    return {
        "table": table,
        "column": col,
        "label": _label_for(table),
        "family": ov.get("family") or family_of(table),
        "warn_hours": float(ov.get("warn_hours", default_warn)),
        "dead_hours": float(ov.get("dead_hours", default_dead)),
    }
