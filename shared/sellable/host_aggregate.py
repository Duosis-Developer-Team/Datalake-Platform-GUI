"""Host-level compute aggregation for Capacity Planning and sellable pipelines."""
from __future__ import annotations

from typing import Any


def _sum_field(hosts: list[dict], key: str, default: float = 0.0) -> float:
    return sum(float(h.get(key) or default) for h in hosts)


def _sum_storage_dedupe_by_cluster(hosts: list[dict]) -> tuple[float, float, float, float]:
    """Sum storage metrics once per cluster (Nutanix cluster pool, not per-node sum)."""
    seen: set[str] = set()
    cap = prov = used = free = 0.0
    for h in hosts:
        cluster = str(h.get("cluster") or "")
        if cluster in seen:
            continue
        seen.add(cluster)
        cap += float(h.get("stor_cap_gb") or 0.0)
        prov += float(h.get("stor_provisioned_gb") or 0.0)
        used += float(h.get("stor_used_host_gb") or h.get("stor_used_gb") or 0.0)
        free += float(h.get("stor_free_gb") or 0.0)
    return cap, prov, used, free


def aggregate_hosts_compute(hosts: list[dict], *, dedupe_cluster_storage: bool = False) -> dict[str, Any]:
    """Sum per-host capacity/allocation fields into a compute summary dict.

    Used by datacenter-api /hosts responses and DC view Capacity Planning when
    cluster-level aggregates are replaced by filtered host sums.
    """
    if not hosts:
        return {
            "hosts": 0,
            "vms": 0,
            "cpu_cap": 0.0,
            "cpu_used": 0.0,
            "cpu_alloc_ghz_vm": 0.0,
            "cpu_alloc_ghz_physical": 0.0,
            "cpu_util_pct_max": 0.0,
            "mem_cap": 0.0,
            "mem_used": 0.0,
            "mem_alloc_gb_vm": 0.0,
            "mem_used_gb_peak": 0.0,
            "mem_util_pct_max": 0.0,
            "stor_cap_gb": 0.0,
            "stor_provisioned_gb": 0.0,
            "stor_used_gb": 0.0,
            "stor_free_gb": 0.0,
        }

    cpu_cap = _sum_field(hosts, "cpu_cap_ghz")
    cpu_used = _sum_field(hosts, "cpu_used_ghz")
    mem_cap = _sum_field(hosts, "mem_cap_gb")
    mem_used = _sum_field(hosts, "mem_used_gb")
    mem_peak_used = _sum_field(hosts, "mem_used_gb_peak") or mem_used
    cpu_util_max = max((float(h.get("cpu_used_pct") or 0.0) for h in hosts), default=0.0)
    mem_util_max = max(
        (float(h.get("mem_peak_util_pct") or h.get("mem_used_pct") or 0.0) for h in hosts),
        default=0.0,
    )
    stor_cap = _sum_field(hosts, "stor_cap_gb")
    stor_prov = _sum_field(hosts, "stor_provisioned_gb")
    stor_used = _sum_field(hosts, "stor_used_gb") or _sum_field(hosts, "stor_used_host_gb")
    stor_free = _sum_field(hosts, "stor_free_gb")
    if dedupe_cluster_storage:
        stor_cap, stor_prov, stor_used, stor_free = _sum_storage_dedupe_by_cluster(hosts)

    cpu_alloc = _sum_field(hosts, "cpu_alloc_ghz")
    cpu_alloc_phys = _sum_field(hosts, "cpu_alloc_ghz_physical")
    mem_alloc = _sum_field(hosts, "mem_alloc_gb")

    return {
        "hosts": len(hosts),
        "vms": int(_sum_field(hosts, "vm_count")),
        "cpu_cap": round(cpu_cap, 2),
        "cpu_used": round(cpu_used, 2),
        "cpu_alloc_ghz_vm": round(cpu_alloc, 2),
        "cpu_alloc_ghz_physical": round(cpu_alloc_phys, 2),
        "cpu_util_pct_max": round(cpu_util_max, 1),
        "cpu_pct_max": round(cpu_util_max, 1),
        "mem_cap": round(mem_cap, 2),
        "mem_used": round(mem_used, 2),
        "mem_alloc_gb_vm": round(mem_alloc, 2),
        "mem_used_gb_peak": round(mem_peak_used, 2),
        "mem_cap_gb_at_peak": round(mem_cap, 2),
        "mem_util_pct_max": round(mem_util_max, 1),
        "mem_pct_max": round(mem_util_max, 1),
        "stor_cap_gb": round(stor_cap, 2),
        "stor_provisioned_gb": round(stor_prov, 2),
        "stor_used_gb": round(stor_used, 2),
        "stor_free_gb": round(stor_free, 2),
        "stor_cap": round(stor_cap / 1024.0, 2) if stor_cap else 0.0,
        "stor_used": round(stor_used / 1024.0, 2) if stor_used else 0.0,
    }


def build_deduped_storage_pools(hosts: list[dict]) -> list[dict[str, Any]]:
    """Collect unique datastore pools referenced by host mount lists."""
    seen: dict[str, dict] = {}
    for h in hosts:
        for mount in h.get("datastore_mounts") or []:
            moid = str(mount.get("datastore_moid") or mount.get("moid") or "")
            if not moid or moid in seen:
                continue
            seen[moid] = {
                "datastore_moid": moid,
                "name": mount.get("name") or mount.get("datastore_name") or moid,
                "backing": mount.get("backing") or "intel",
                "cap_gb": float(mount.get("cap_gb") or 0.0),
                "free_gb": float(mount.get("free_gb") or 0.0),
                "used_gb": float(mount.get("used_gb") or 0.0),
                "used_pct": float(mount.get("used_pct") or 0.0),
                "shared": bool(mount.get("shared")),
            }
    return sorted(seen.values(), key=lambda p: p.get("free_gb", 0.0), reverse=True)


def finalize_host_payload(
    payload: dict[str, Any],
    *,
    dedupe_cluster_storage: bool = False,
) -> dict[str, Any]:
    """Attach summary and deduped storage_pools to a hosts API payload."""
    hosts = list(payload.get("hosts") or [])
    out = dict(payload)
    out["summary"] = aggregate_hosts_compute(hosts, dedupe_cluster_storage=dedupe_cluster_storage)
    out["storage_pools"] = build_deduped_storage_pools(hosts)
    return out
