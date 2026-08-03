"""VM Role annotation + billable virt exclusion for replication VMs."""
from __future__ import annotations

from typing import Any, Iterable, Mapping, MutableMapping

from shared.backup.replica_classifier import classify_vm_name, is_replica_like


ROLE_LABELS = {
    "billable": "Billable",
    "veeam_dr": "Veeam DR",
    "altra_replica": "Altra replica",
    "zerto": "Zerto",
    "veeam_backup": "Veeam Backup",
    "custom": "Custom replica",
    "silinecek": "Pending delete",
}

ROLE_COLORS = {
    "billable": "teal",
    "veeam_dr": "indigo",
    "altra_replica": "cyan",
    "zerto": "violet",
    "veeam_backup": "blue",
    "custom": "grape",
    "silinecek": "gray",
}


def resolve_vm_role(
    name: str | None,
    *,
    zerto_names: Iterable[str] | None = None,
    veeam_backup_names: Iterable[str] | None = None,
    patterns: dict[str, Any] | None = None,
) -> str:
    """Return role key for a VM (badge + exclusion).

    Precedence: silinecek → zerto matrix → name-bucket replica → veeam backup tag → billable.
    Veeam Backup-only stays billable for virt sold unless also DR/Zerto.
    """
    bucket = classify_vm_name(name if name is None else str(name), patterns=patterns)
    if bucket == "silinecek":
        return "silinecek"
    key = str(name or "").strip().casefold()
    zerto = {str(n).strip().casefold() for n in (zerto_names or []) if str(n).strip()}
    if key and key in zerto:
        return "zerto"
    if is_replica_like(bucket):
        return bucket
    bak = {str(n).strip().casefold() for n in (veeam_backup_names or []) if str(n).strip()}
    if key and key in bak:
        return "veeam_backup"
    return "billable"


def annotate_vm_roles(
    vm_rows: Iterable[MutableMapping[str, Any]] | None,
    *,
    zerto_names: Iterable[str] | None = None,
    veeam_backup_names: Iterable[str] | None = None,
    patterns: dict[str, Any] | None = None,
    name_key: str = "name",
) -> list[dict[str, Any]]:
    """Add ``role`` / ``role_label`` / ``role_color`` / ``virt_billable`` to each row."""
    out: list[dict[str, Any]] = []
    for row in vm_rows or []:
        item = dict(row)
        role = resolve_vm_role(
            item.get(name_key),
            zerto_names=zerto_names,
            veeam_backup_names=veeam_backup_names,
            patterns=patterns,
        )
        item["role"] = role
        item["role_label"] = ROLE_LABELS.get(role, role)
        item["role_color"] = ROLE_COLORS.get(role, "gray")
        # Backup-tagged VMs remain virt-billable; DR/Zerto/custom replicas do not.
        item["virt_billable"] = role in ("billable", "veeam_backup", "silinecek")
        out.append(item)
    return out


def exclude_non_billable_virt(
    vm_rows: Iterable[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Drop replication VMs from virt sold aggregation (keep billable + backup-only)."""
    result: list[dict[str, Any]] = []
    for row in vm_rows or []:
        if row.get("virt_billable") is False:
            continue
        if "virt_billable" not in row:
            role = str(row.get("role") or "")
            if role and role not in ("billable", "veeam_backup", "silinecek", ""):
                continue
            if not role:
                bucket = classify_vm_name(str(row.get("name") or ""))
                if is_replica_like(bucket):
                    continue
        result.append(dict(row))
    return result


def sum_billable_virt_resources(
    vm_rows: Iterable[Mapping[str, Any]] | None,
) -> dict[str, float | int]:
    """Sum cpu / memory_gb / disk_gb for virt-billable VMs only."""
    billable = exclude_non_billable_virt(vm_rows)
    return {
        "vm_count": len(billable),
        "cpu": round(sum(float(r.get("cpu") or 0.0) for r in billable), 3),
        "memory_gb": round(sum(float(r.get("memory_gb") or 0.0) for r in billable), 3),
        "disk_gb": round(sum(float(r.get("disk_gb") or 0.0) for r in billable), 3),
    }
