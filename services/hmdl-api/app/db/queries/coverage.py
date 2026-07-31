"""SQL + assembly for the datalake coverage report.

Reads read-only tables in the `hmdl` schema:
  hmdl_datalake_coverage_cluster          — VMware + Nutanix cluster coverage
  hmdl_datalake_coverage_ibm_host         — IBM Power host coverage
  hmdl_datalake_coverage_vcenter          — vCenter / Prism parent rollup
  hmdl_datalake_coverage_backup_endpoint  — NetBackup / Veeam / Zerto endpoints
  hmdl_datalake_coverage_target           — NiFi collector connectivity (why missing)

Mirrors the query style of `collectors.py`: `_SCHEMA` f-string interpolation,
`pool.fetch_all`, `%s` positional params. Per-row status/reason derivation lives in
`app.services.coverage`.
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.db import pool
from app.db.queries import collectors as coll_q
from app.services import coverage as cov

_SCHEMA = settings.hmdl_schema

_BACKUP_SOURCES = frozenset({"netbackup", "veeam", "zerto"})
_VCENTER_STATUSES = frozenset({"live", "partial", "missing", "extra", "stale", "unknown"})


def _fetch_clusters() -> list[dict[str, Any]]:
    return pool.fetch_all(
        f"""
        SELECT source, cluster_name, dc_code, parent_name, expected_source,
               collected, expected, is_live, last_collected, checked_at
        FROM {_SCHEMA}.hmdl_datalake_coverage_cluster
        ORDER BY source, cluster_name
        """
    )


def _fetch_ibm_hosts() -> list[dict[str, Any]]:
    return pool.fetch_all(
        f"""
        SELECT servername, dc_code, expected_source, collected, expected, is_live,
               last_collected, checked_at
        FROM {_SCHEMA}.hmdl_datalake_coverage_ibm_host
        ORDER BY servername
        """
    )


def _fetch_vcenters() -> list[dict[str, Any]]:
    return pool.fetch_all(
        f"""
        SELECT source, parent_name, dc_code,
               expected_clusters, collected_clusters, live_clusters,
               status, checked_at
        FROM {_SCHEMA}.hmdl_datalake_coverage_vcenter
        ORDER BY source, parent_name
        """
    )


def _fetch_backup_endpoints() -> list[dict[str, Any]]:
    return pool.fetch_all(
        f"""
        SELECT source, endpoint_ip, endpoint_name, dc_code,
               collected, expected, expected_source, network_ok,
               last_collected, is_live, checked_at
        FROM {_SCHEMA}.hmdl_datalake_coverage_backup_endpoint
        ORDER BY source, dc_code, endpoint_ip
        """
    )


def _fetch_target_issues() -> list[dict[str, Any]]:
    """Unreachable / problematic collector targets, keyed later by (dc_code, platform)."""
    return pool.fetch_all(
        f"""
        SELECT dc_code, platform, dns, proxy, check_status, network_access
        FROM {_SCHEMA}.hmdl_datalake_coverage_target
        WHERE network_access IS NOT TRUE OR check_status <> 'ok'
        """
    )


def _issues_by_key(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        key = ((r.get("dc_code") or "").upper(), (r.get("platform") or ""))
        out.setdefault(key, []).append(r)
    return out


def _resolve_dc(db_dc: Any, *name_fallbacks: Any) -> str:
    raw = str(db_dc or "").strip().upper()
    if raw and raw not in ("UNKNOWN", "NONE", "NULL"):
        return raw
    for name in name_fallbacks:
        derived = cov.derive_dc(name if isinstance(name, str) else None)
        if derived != "Diğer":
            return derived
    return raw or "Diğer"


def _build_cluster_row(r: dict, issues: dict) -> dict[str, Any]:
    source = r.get("source") or ""
    collected = bool(r.get("collected"))
    expected = bool(r.get("expected"))
    is_live = bool(r.get("is_live"))
    dc = _resolve_dc(r.get("dc_code"), r.get("cluster_name"), r.get("parent_name"))
    status = cov.row_status(collected, expected, is_live)
    ti: list[dict] = []
    if status == "missing":
        platform = cov.SOURCE_PLATFORM.get(source.lower())
        if platform:
            ti = issues.get((dc, platform), [])
    return {
        "source": source,
        "cluster_name": r.get("cluster_name"),
        "dc": dc,
        "parent_name": r.get("parent_name"),
        "expected_source": r.get("expected_source"),
        "collected": collected,
        "expected": expected,
        "is_live": is_live,
        "last_collected": r.get("last_collected"),
        "status": status,
        "reason": cov.reason_text(status, r.get("last_collected"), ti),
        "target_issues": ti,
    }


def _build_host_row(r: dict, issues: dict) -> dict[str, Any]:
    collected = bool(r.get("collected"))
    expected = bool(r.get("expected"))
    is_live = bool(r.get("is_live"))
    dc = _resolve_dc(r.get("dc_code"), r.get("servername"))
    status = cov.row_status(collected, expected, is_live)
    ti: list[dict] = []
    if status == "missing":
        ti = issues.get((dc, cov.IBM_PLATFORM), [])
    return {
        "servername": r.get("servername"),
        "dc": dc,
        "expected_source": r.get("expected_source"),
        "collected": collected,
        "expected": expected,
        "is_live": is_live,
        "last_collected": r.get("last_collected"),
        "status": status,
        "reason": cov.reason_text(status, r.get("last_collected"), ti),
        "target_issues": ti,
    }


def _build_vcenter_row(r: dict) -> dict[str, Any]:
    status = str(r.get("status") or "unknown").lower()
    if status not in _VCENTER_STATUSES:
        status = "unknown"
    return {
        "source": r.get("source") or "",
        "parent_name": r.get("parent_name"),
        "dc": _resolve_dc(r.get("dc_code"), r.get("parent_name")),
        "expected_clusters": int(r.get("expected_clusters") or 0),
        "collected_clusters": int(r.get("collected_clusters") or 0),
        "live_clusters": int(r.get("live_clusters") or 0),
        "status": status,
        "checked_at": r.get("checked_at"),
    }


def _build_backup_row(r: dict) -> dict[str, Any]:
    collected = bool(r.get("collected"))
    expected = bool(r.get("expected"))
    is_live = bool(r.get("is_live"))
    status = cov.row_status(collected, expected, is_live)
    return {
        "source": (r.get("source") or "").lower(),
        "endpoint_ip": r.get("endpoint_ip"),
        "endpoint_name": r.get("endpoint_name"),
        "dc": _resolve_dc(r.get("dc_code"), r.get("endpoint_name")),
        "collected": collected,
        "expected": expected,
        "expected_source": r.get("expected_source"),
        "network_ok": r.get("network_ok") if r.get("network_ok") is None else bool(r.get("network_ok")),
        "is_live": is_live,
        "last_collected": r.get("last_collected"),
        "status": status,
        "reason": cov.reason_text(status, r.get("last_collected"), []),
        "checked_at": r.get("checked_at"),
    }


def _empty_vcenter_bucket() -> dict[str, int]:
    return {"total": 0, "live": 0, "partial": 0, "missing": 0, "stale": 0, "extra": 0}


def _tally_vcenter(bucket: dict[str, int], status: str) -> None:
    bucket["total"] += 1
    if status in bucket:
        bucket[status] += 1


def build_coverage(*, dc: str | None = None, source: str | None = None) -> dict[str, Any]:
    """Assemble the coverage report, optionally filtered by Location (dc) and source."""
    issues = _issues_by_key(_fetch_target_issues())

    clusters = [_build_cluster_row(r, issues) for r in _fetch_clusters()]
    hosts = [_build_host_row(r, issues) for r in _fetch_ibm_hosts()]
    vcenters = [_build_vcenter_row(r) for r in _fetch_vcenters()]
    backups = [_build_backup_row(r) for r in _fetch_backup_endpoints()]

    coverage_dcs = (
        {row["dc"] for row in clusters}
        | {row["dc"] for row in hosts}
        | {row["dc"] for row in vcenters}
        | {row["dc"] for row in backups}
    )
    loki_dcs = {
        str(loc.get("dc_code") or "").strip().upper()
        for loc in coll_q.list_root_locations()
        if loc.get("dc_code")
    }
    locations = sorted(loki_dcs | coverage_dcs | {"Diğer"})

    dc_norm = (dc or "").strip().upper() or None
    src_norm = (source or "").strip().lower() or None
    if dc_norm:
        clusters = [c for c in clusters if c["dc"] == dc_norm]
        hosts = [h for h in hosts if h["dc"] == dc_norm]
        vcenters = [v for v in vcenters if v["dc"] == dc_norm]
        backups = [b for b in backups if b["dc"] == dc_norm]

    # `source` doubles as a data-type selector:
    # ibm → hosts only; vmware/nutanix → clusters+vcenters of that source;
    # netbackup/veeam/zerto → backup endpoints of that source; empty → all.
    if src_norm == "ibm":
        clusters = []
        vcenters = []
        backups = []
    elif src_norm in ("vmware", "nutanix"):
        clusters = [c for c in clusters if c["source"].lower() == src_norm]
        vcenters = [v for v in vcenters if v["source"].lower() == src_norm]
        hosts = []
        backups = []
    elif src_norm in _BACKUP_SOURCES:
        clusters = []
        hosts = []
        vcenters = []
        backups = [b for b in backups if b["source"] == src_norm]

    cluster_buckets: dict[str, dict[str, int]] = {"all": cov.empty_bucket()}
    for c in clusters:
        s = c["source"].lower() or "other"
        cluster_buckets.setdefault(s, cov.empty_bucket())
        cov.tally(cluster_buckets["all"], c["collected"], c["expected"], c["is_live"])
        cov.tally(cluster_buckets[s], c["collected"], c["expected"], c["is_live"])

    host_bucket = cov.empty_bucket()
    for h in hosts:
        cov.tally(host_bucket, h["collected"], h["expected"], h["is_live"])

    vcenter_bucket = _empty_vcenter_bucket()
    for v in vcenters:
        _tally_vcenter(vcenter_bucket, v["status"])

    backup_buckets: dict[str, dict[str, int]] = {"all": cov.empty_bucket()}
    for b in backups:
        s = b["source"] or "other"
        backup_buckets.setdefault(s, cov.empty_bucket())
        cov.tally(backup_buckets["all"], b["collected"], b["expected"], b["is_live"])
        cov.tally(backup_buckets[s], b["collected"], b["expected"], b["is_live"])

    return {
        "summary": {
            "cluster": cluster_buckets,
            "ibm_host": host_bucket,
            "vcenter": vcenter_bucket,
            "backup_endpoint": backup_buckets,
        },
        "clusters": clusters,
        "ibm_hosts": hosts,
        "vcenters": vcenters,
        "backup_endpoints": backups,
        "locations": locations,
        "dc_filter": dc_norm,
        "source_filter": src_norm,
    }
