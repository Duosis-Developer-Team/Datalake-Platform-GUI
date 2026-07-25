"""SQL + assembly for HMDL automation health (schedule / freshness).

Each HMDL automation writes a run-log/observability table in the `hmdl` schema; the
most recent timestamp there tells us when the automation last ran:

  datalake_collector_sync  -> collector_sync_log.finished_at (+ proxy coverage)
  db_to_zabbix_sync        -> zabbix_sync_log.processed_at
  run_basic_checks         -> collector_check_log.checked_at
  vm_reconciliation        -> hmdl_datalake_monitoring_clusters.check_time

Per-row freshness classification is pure and lives in `app.services.automation_health`.
The `now()` reference is read from the DB so ages align with the server clock.
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.db import pool
from app.services import automation_health as ah

_SCHEMA = settings.hmdl_schema


def _now():
    row = pool.fetch_one("SELECT now() AS now")
    return row["now"] if row else None


def _max_ts(sql: str) -> Any:
    row = pool.fetch_one(sql)
    if not row:
        return None
    # single-column SELECT max(...) AS ts
    return row.get("ts")


def _collector_extra() -> dict[str, Any]:
    total = pool.fetch_one(f"SELECT count(*) AS c FROM {_SCHEMA}.proxy_node")
    total_n = int(total["c"]) if total else 0
    covered = pool.fetch_one(
        f"""
        WITH last AS (
            SELECT run_id FROM {_SCHEMA}.collector_sync_log
            WHERE dry_run = FALSE
            ORDER BY finished_at DESC NULLS LAST, id DESC LIMIT 1
        )
        SELECT count(DISTINCT proxy_id) AS c
        FROM {_SCHEMA}.collector_sync_log
        WHERE dry_run = FALSE AND run_id = (SELECT run_id FROM last)
        """
    )
    covered_n = int(covered["c"]) if covered and covered["c"] is not None else 0
    return {
        "last_run_proxies": covered_n,
        "total_proxies": total_n,
        "proxy_coverage": f"{covered_n}/{total_n}",
    }


def _proxy_health(now) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows = pool.fetch_all(
        f"""
        SELECT proxy_id, dc_code, proxy_nifi_host, last_seen_at
        FROM {_SCHEMA}.proxy_node
        ORDER BY last_seen_at ASC NULLS FIRST, proxy_id
        """
    )
    warn = settings.ah_collector_warn_hours
    dead = settings.ah_collector_dead_hours
    out: list[dict[str, Any]] = []
    summary = {"total": 0, "fresh": 0, "stale": 0, "dead": 0}
    for r in rows:
        age = ah.age_in_hours(r.get("last_seen_at"), now)
        status = ah.classify(age, warn, dead)
        out.append(
            {
                "proxy_id": r["proxy_id"],
                "dc_code": r.get("dc_code"),
                "proxy_nifi_host": r.get("proxy_nifi_host"),
                "last_seen_at": r.get("last_seen_at"),
                "age_hours": age,
                "status": status,
            }
        )
        summary["total"] += 1
        if status in summary:
            summary[status] += 1
    return out, summary


def _data_gaps() -> dict[str, Any]:
    by_source_rows = pool.fetch_all(
        f"""
        SELECT source, count(*) AS c
        FROM {_SCHEMA}.hmdl_datalake_coverage_cluster
        WHERE expected AND NOT collected
        GROUP BY source
        """
    )
    by_source = {str(r["source"]): int(r["c"]) for r in by_source_rows}
    ibm = pool.fetch_one(
        f"""
        SELECT count(*) AS c FROM {_SCHEMA}.hmdl_datalake_coverage_ibm_host
        WHERE expected AND NOT collected
        """
    )
    return {
        "cluster_missing": sum(by_source.values()),
        "ibm_missing": int(ibm["c"]) if ibm else 0,
        "by_source": by_source,
    }


# Collected DATA tables the dashboards actually read (public schema). Freshness =
# age of the newest row. This is separate from the AWX job logs above: a job can
# report "fresh" while its on-proxy NiFi data flow is dead (e.g. the VMware
# datastore flow stopped 2026-07-16 → Overview storage 0%).
_DATA_SOURCES = [
    ("vmware_clusters", "VMware Clusters", "cluster_metrics", "collection_time"),
    ("nutanix_clusters", "Nutanix Clusters", "nutanix_cluster_metrics", "collection_time"),
    ("vmware_datacenter", "VMware Datacenter", "datacenter_metrics", "collection_time"),
    ("vmware_datastore_metrics", "VMware Datastore Metrics",
     "raw_vmware_datastore_metrics_agg", "collection_timestamp"),
    ("vmware_datastore_mounts", "VMware Datastore Mounts",
     "raw_vmware_datastore_host_mount", "collection_timestamp"),
    ("ibm_lpar", "IBM LPARs", "ibm_lpar_general", "time"),
]


def _data_sources() -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Freshness of each collected DATA table (age computed in SQL to stay tz-safe
    across the tables' mixed naive/aware timestamps)."""
    warn = settings.ah_data_warn_hours
    dead = settings.ah_data_dead_hours
    rows: list[dict[str, Any]] = []
    for key, label, table, col in _DATA_SOURCES:
        r = pool.fetch_one(
            f"SELECT max({col}) AS ts, "
            f"EXTRACT(EPOCH FROM (now() - max({col})))/3600.0 AS age_hours "
            f"FROM public.{table}"
        )
        ts = r.get("ts") if r else None
        age = float(r["age_hours"]) if (r and r.get("age_hours") is not None) else None
        # Naive timestamps (some tables store local time) can read slightly ahead
        # of now() → a small negative age. That still means "just collected", so
        # clamp to 0 for a clean display; staleness is always positive.
        if age is not None and age < 0:
            age = 0.0
        rows.append(ah.build_data_source_row(
            key=key, label=label, table=table,
            last_data_at=ts, age_hours=age,
            warn_hours=warn, dead_hours=dead,
        ))
    counts = ah.overall_status_counts([r["status"] for r in rows])
    return rows, counts


def build_automation_health() -> dict[str, Any]:
    now = _now()

    collector_last = _max_ts(
        f"SELECT max(finished_at) AS ts FROM {_SCHEMA}.collector_sync_log WHERE dry_run = FALSE"
    )
    zabbix_last = _max_ts(
        f"SELECT max(processed_at) AS ts FROM {_SCHEMA}.zabbix_sync_log WHERE dry_run = FALSE"
    )
    checks_last = _max_ts(f"SELECT max(checked_at) AS ts FROM {_SCHEMA}.collector_check_log")
    recon_last = _max_ts(
        f"SELECT max(check_time) AS ts FROM {_SCHEMA}.hmdl_datalake_monitoring_clusters"
    )

    automations = [
        ah.build_automation_row(
            key="zabbix_sync",
            label="NetBox → Zabbix Sync",
            cadence="~8 saatte bir",
            last_run_at=zabbix_last,
            now=now,
            warn_hours=settings.ah_zabbix_warn_hours,
            dead_hours=settings.ah_zabbix_dead_hours,
        ),
        ah.build_automation_row(
            key="collector_sync",
            label="Datalake Collector Sync",
            cadence="günlük 02:00",
            last_run_at=collector_last,
            now=now,
            warn_hours=settings.ah_collector_warn_hours,
            dead_hours=settings.ah_collector_dead_hours,
            extra=_collector_extra(),
        ),
        ah.build_automation_row(
            key="reachability_checks",
            label="Collector Reachability Checks",
            cadence="collector sync ile",
            last_run_at=checks_last,
            now=now,
            warn_hours=settings.ah_checks_warn_hours,
            dead_hours=settings.ah_checks_dead_hours,
        ),
        ah.build_automation_row(
            key="vm_reconciliation",
            label="VM Envanter Reconciliation",
            cadence="günlük",
            last_run_at=recon_last,
            now=now,
            warn_hours=settings.ah_recon_warn_hours,
            dead_hours=settings.ah_recon_dead_hours,
        ),
    ]

    counts = ah.overall_status_counts([a["status"] for a in automations])
    proxies, proxy_summary = _proxy_health(now)
    data_sources, data_counts = _data_sources()

    return {
        "generated_at": now,
        "automations": automations,
        "counts": counts,
        "proxies": proxies,
        "proxy_summary": proxy_summary,
        "data_gaps": _data_gaps(),
        "data_sources": data_sources,
        "data_counts": data_counts,
    }
