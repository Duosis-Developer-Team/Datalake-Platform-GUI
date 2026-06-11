"""SQL + assembly for the datalake coverage report (cluster / IBM host present-absent).

Reads three read-only tables in the `hmdl` schema:
  hmdl_datalake_coverage_cluster   — VMware + Nutanix cluster coverage
  hmdl_datalake_coverage_ibm_host  — IBM Power host coverage
  hmdl_datalake_coverage_target    — NiFi collector connectivity (for "why missing")

Mirrors the query style of `collectors.py`: `_SCHEMA` f-string interpolation,
`pool.fetch_all`, `%s` positional params. Per-row status/reason derivation lives in
`app.services.coverage`.
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.db import pool
from app.services import coverage as cov

_SCHEMA = settings.hmdl_schema


def _fetch_clusters() -> list[dict[str, Any]]:
    return pool.fetch_all(
        f"""
        SELECT source, cluster_name, collected, expected, is_live,
               last_collected, checked_at
        FROM {_SCHEMA}.hmdl_datalake_coverage_cluster
        ORDER BY source, cluster_name
        """
    )


def _fetch_ibm_hosts() -> list[dict[str, Any]]:
    return pool.fetch_all(
        f"""
        SELECT servername, collected, expected, is_live,
               last_collected, checked_at
        FROM {_SCHEMA}.hmdl_datalake_coverage_ibm_host
        ORDER BY servername
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


def _build_cluster_row(r: dict, issues: dict) -> dict[str, Any]:
    source = r.get("source") or ""
    collected = bool(r.get("collected"))
    expected = bool(r.get("expected"))
    is_live = bool(r.get("is_live"))
    dc = cov.derive_dc(r.get("cluster_name"))
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
    dc = cov.derive_dc(r.get("servername"))
    status = cov.row_status(collected, expected, is_live)
    ti: list[dict] = []
    if status == "missing":
        ti = issues.get((dc, cov.IBM_PLATFORM), [])
    return {
        "servername": r.get("servername"),
        "dc": dc,
        "collected": collected,
        "expected": expected,
        "is_live": is_live,
        "last_collected": r.get("last_collected"),
        "status": status,
        "reason": cov.reason_text(status, r.get("last_collected"), ti),
        "target_issues": ti,
    }


def build_coverage(*, dc: str | None = None, source: str | None = None) -> dict[str, Any]:
    """Assemble the coverage report, optionally filtered by Location (dc) and source."""
    issues = _issues_by_key(_fetch_target_issues())

    clusters = [_build_cluster_row(r, issues) for r in _fetch_clusters()]
    hosts = [_build_host_row(r, issues) for r in _fetch_ibm_hosts()]

    # distinct Locations across both data sets (for the UI dropdown) — before filtering.
    locations = sorted({row["dc"] for row in clusters} | {row["dc"] for row in hosts})

    dc_norm = (dc or "").strip().upper() or None
    src_norm = (source or "").strip().lower() or None
    if dc_norm:
        clusters = [c for c in clusters if c["dc"] == dc_norm]
        hosts = [h for h in hosts if h["dc"] == dc_norm]
    # `source` doubles as a data-type selector: ibm → hosts only; vmware/nutanix →
    # clusters of that source only (hosts hidden); empty → both.
    if src_norm == "ibm":
        clusters = []
    elif src_norm in ("vmware", "nutanix"):
        clusters = [c for c in clusters if c["source"].lower() == src_norm]
        hosts = []

    # X/Y summary over the (filtered) set.
    cluster_buckets: dict[str, dict[str, int]] = {"all": cov.empty_bucket()}
    for c in clusters:
        s = c["source"].lower() or "other"
        cluster_buckets.setdefault(s, cov.empty_bucket())
        cov.tally(cluster_buckets["all"], c["collected"], c["expected"], c["is_live"])
        cov.tally(cluster_buckets[s], c["collected"], c["expected"], c["is_live"])

    host_bucket = cov.empty_bucket()
    for h in hosts:
        cov.tally(host_bucket, h["collected"], h["expected"], h["is_live"])

    return {
        "summary": {"cluster": cluster_buckets, "ibm_host": host_bucket},
        "clusters": clusters,
        "ibm_hosts": hosts,
        "locations": locations,
        "dc_filter": dc_norm,
        "source_filter": src_norm,
    }
