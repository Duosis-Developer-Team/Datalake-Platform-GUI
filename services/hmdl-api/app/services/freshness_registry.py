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

# Tables that at least one service actually queries. Freshness monitoring is
# opt-in by usage: a table nobody reads is not a platform health signal, it is
# the freshness of data the platform abandoned. Auto-discovery monitored all 159
# tables carrying a timestamp column, of which 96 feed no query — that is where
# 33 of the page's 40 alerts came from.
#
# Curated, not computed. hmdl-api cannot see the other services' source at
# runtime, and grepping for table names has two failure modes this set was built
# to avoid: `zabbix_network_interface_metrics` matches inside
# `raw_zabbix_network_interface_metrics_v`, and `raw_vmware_vm_config` matches a
# comment in licensed_os.py that records the table is dead.
#
# Only BASE TABLEs belong here — discover_specs filters on table_type, so a view
# in this set could never be discovered and would sit in data_missing forever
# reporting a curation defect that isn't one. That excludes the live network
# source raw_zabbix_network_interface_metrics_v, which is a view; its freshness
# is out of this framework's reach.
#
# MAINTENANCE: a new query against a new table adds that table here in the same
# commit. A table missing from this set never alerts.
# Seeded 2026-07-27 from a word-boundary sweep of services/, src/, shared/.
MONITORED = frozenset({
    "cluster_metrics", "datacenter_metrics", "discovery_crm_accounts",
    "discovery_crm_pricelevels", "discovery_crm_productpricelevels",
    "discovery_crm_products", "discovery_crm_salesorderdetails",
    "discovery_crm_salesorders", "discovery_loki_location", "discovery_loki_rack",
    "discovery_netbox_inventory_device", "discovery_netbox_virtualization_vm",
    "discovery_nutanix_inventory_cluster", "discovery_nutanix_inventory_vm",
    "discovery_servicecore_incidents", "discovery_servicecore_servicerequests",
    "discovery_servicecore_users", "discovery_vmware_inventory_datastore",
    "ibm_lpar_general", "ibm_lpar_performance_metrics", "ibm_server_general",
    "ibm_server_power", "ibm_vios_general", "nutanix_cluster_metrics",
    "nutanix_host_performance_metrics", "nutanix_snapshot_schedule_metrics",
    "nutanix_vm_metrics", "nutanix_vm_performance_metrics",
    "raw_brocade_port_statistics", "raw_brocade_port_status",
    "raw_brocade_san_fcport_1", "raw_ibm_storage_system",
    "raw_ibm_storage_system_stats", "raw_ibm_storage_vdisk",
    "raw_netbackup_disk_pools_metrics", "raw_netbackup_jobs_metrics",
    "raw_s3icos_pool_metrics", "raw_s3icos_vault_inventory",
    "raw_s3icos_vault_metrics", "raw_veeam_jobs_states",
    "raw_veeam_repositories_states", "raw_veeam_sessions",
    "raw_vmware_datastore_host_mount", "raw_vmware_datastore_metrics_agg",
    "raw_zabbix_hana_linux_host_metrics",
    "raw_zabbix_network_backbone_interface_metrics",
    "raw_zabbix_network_device_health_metrics",
    "raw_zabbix_network_firewall_metrics",
    "raw_zabbix_network_leaf_interface_metrics",
    "raw_zabbix_network_management_interface_metrics",
    "raw_zabbix_network_router_uplink_metrics",
    "raw_zabbix_network_spine_interface_metrics",
    "raw_zabbix_network_switch_shared_interface_metrics",
    "raw_zerto_license_metrics", "raw_zerto_site_metrics", "raw_zerto_vm_metrics",
    "raw_zerto_vpg_metrics", "vm_metrics", "vmhost_metrics",
    "vmware_host_performance_metrics", "vmware_vm_performance_metrics",
    "zabbix_storage_device_metrics", "zabbix_storage_disk_metrics",
})

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


def is_monitored(table: str) -> bool:
    """True when at least one service queries this table (see MONITORED)."""
    return table in MONITORED


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
        "monitored": is_monitored(table),
        "warn_hours": float(ov.get("warn_hours", default_warn)),
        "dead_hours": float(ov.get("dead_hours", default_dead)),
    }
