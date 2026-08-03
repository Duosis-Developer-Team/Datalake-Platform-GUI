"""HC Nutanix disk intersection for Veeam/Zerto replication storage.

Only VMs present in VMware metrics ∩ Nutanix metrics ∩ vendor protected set
contribute Nutanix disk to replication sellable (ADR-0032).
"""
from __future__ import annotations

from typing import Iterable, Mapping


def intersect_hc_nutanix_names(
    vmware_names: Iterable[str] | None,
    nutanix_names: Iterable[str] | None,
    vendor_names: Iterable[str] | None,
) -> set[str]:
    """Return names present in all three sets (case-folded exact match)."""
    vw = {str(n).strip().casefold() for n in (vmware_names or []) if str(n).strip()}
    nx = {str(n).strip().casefold() for n in (nutanix_names or []) if str(n).strip()}
    vd = {str(n).strip().casefold() for n in (vendor_names or []) if str(n).strip()}
    if not vw or not nx or not vd:
        return set()
    return vw & nx & vd


def sum_nutanix_disk_for_names(
    nutanix_rows: Iterable[Mapping] | None,
    matched_names: Iterable[str] | None,
    *,
    name_key: str = "name",
    disk_key: str = "disk_gb",
) -> dict[str, float | int]:
    """Sum Nutanix disk_gb for rows whose name is in matched_names."""
    wanted = {str(n).strip().casefold() for n in (matched_names or []) if str(n).strip()}
    total = 0.0
    count = 0
    for row in nutanix_rows or []:
        name = str(row.get(name_key) or "").strip()
        if not name or name.casefold() not in wanted:
            continue
        total += float(row.get(disk_key) or 0.0)
        count += 1
    return {"disk_gb": round(total, 3), "vm_count": count}
