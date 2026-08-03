"""Pure replica resource aggregation for future CRM inventory.

Filters VM rows through ``replica_classifier.classify_vm_name``, then sums
CPU / RAM / disk grouped by architecture (classic vs hyperconverged) and
cluster name. No database access.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from shared.backup.replica_classifier import classify_vm_name, is_replica_like


def _architecture_bucket(row: Mapping[str, Any]) -> str:
    """Return ``classic`` or ``hyperconverged`` for a VM row."""
    arch = str(row.get("architecture") or row.get("arch") or "").strip().lower()
    if arch in ("hyperconverged", "hyperconv", "hc", "nutanix"):
        return "hyperconverged"
    if arch in ("classic", "km", "vmware"):
        return "classic"
    source = str(row.get("source") or "").strip().lower()
    if "nutanix" in source:
        return "hyperconverged"
    cluster = str(row.get("cluster") or "").strip().upper()
    if cluster and "KM" not in cluster:
        # Non-KM clusters default to HC when architecture unset (ADR-0024).
        return "hyperconverged"
    return "classic"


def _empty_cluster_totals() -> dict[str, float | int]:
    return {
        "cpu": 0.0,
        "memory_gb": 0.0,
        "disk_gb": 0.0,
        "vm_count": 0,
    }


def _add_row(bucket: dict[str, dict], cluster: str, row: Mapping[str, Any]) -> None:
    entry = bucket.setdefault(cluster, _empty_cluster_totals())
    entry["cpu"] = float(entry["cpu"]) + float(row.get("cpu") or 0.0)
    entry["memory_gb"] = float(entry["memory_gb"]) + float(row.get("memory_gb") or 0.0)
    entry["disk_gb"] = float(entry["disk_gb"]) + float(row.get("disk_gb") or 0.0)
    entry["vm_count"] = int(entry["vm_count"]) + 1


def _sum_bucket(by_cluster: dict[str, dict]) -> dict[str, float | int]:
    totals = _empty_cluster_totals()
    for entry in by_cluster.values():
        totals["cpu"] = float(totals["cpu"]) + float(entry.get("cpu") or 0.0)
        totals["memory_gb"] = float(totals["memory_gb"]) + float(entry.get("memory_gb") or 0.0)
        totals["disk_gb"] = float(totals["disk_gb"]) + float(entry.get("disk_gb") or 0.0)
        totals["vm_count"] = int(totals["vm_count"]) + int(entry.get("vm_count") or 0)
    return totals


def sum_replica_resources(
    vm_rows: Iterable[Mapping[str, Any]] | None,
    patterns: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Sum resources for name-based replica VMs, grouped classic/hc × cluster.

    Each row should include at least ``name``. Optional keys: ``cluster``,
    ``cpu``, ``memory_gb``, ``disk_gb``, ``architecture`` / ``arch`` / ``source``.

    Returns classic/hc totals plus per-bucket counts (veeam_dr / altra / custom).
    """
    classic: dict[str, dict] = {}
    hyperconv: dict[str, dict] = {}
    replica_count = 0
    by_name_bucket: dict[str, int] = {
        "veeam_dr": 0,
        "altra_replica": 0,
        "custom": 0,
    }

    for row in vm_rows or []:
        name = row.get("name")
        bucket = classify_vm_name(name if name is None else str(name), patterns=patterns)
        if not is_replica_like(bucket):
            continue
        replica_count += 1
        by_name_bucket[bucket] = int(by_name_bucket.get(bucket, 0)) + 1
        cluster = str(row.get("cluster") or "").strip() or "(unknown)"
        if _architecture_bucket(row) == "hyperconverged":
            _add_row(hyperconv, cluster, row)
        else:
            _add_row(classic, cluster, row)

    classic_totals = _sum_bucket(classic)
    hc_totals = _sum_bucket(hyperconv)
    grand = _empty_cluster_totals()
    for key in ("cpu", "memory_gb", "disk_gb"):
        grand[key] = float(classic_totals[key]) + float(hc_totals[key])
    grand["vm_count"] = int(classic_totals["vm_count"]) + int(hc_totals["vm_count"])

    return {
        "classic": {"by_cluster": classic, "totals": classic_totals},
        "hyperconverged": {"by_cluster": hyperconv, "totals": hc_totals},
        "totals": grand,
        "replica_vm_count": replica_count,
        "by_name_bucket": by_name_bucket,
    }
