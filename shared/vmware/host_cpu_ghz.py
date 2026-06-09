"""Parse host base CPU GHz from NetBox inventory and aggregate VM CPU allocation."""
from __future__ import annotations

import re
import time
from typing import Any, Mapping, Sequence

DEFAULT_HOST_CPU_GHZ = 2.0
_GHZ_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*GHz", re.IGNORECASE)

# Simple process-local cache: (map, monotonic_expiry)
_host_map_cache: tuple[dict[str, float], float] | None = None
_HOST_MAP_TTL_SEC = 1200.0

NETBOX_HOST_CPU_STRINGS = """
SELECT DISTINCT ON (name)
    name,
    custom_fields->'CPU'->>0 AS cpu_cf,
    cpu AS cpu_col
FROM public.discovery_netbox_inventory_device
WHERE status_value = 'active'
ORDER BY name, collection_time DESC NULLS LAST
"""


def parse_cpu_ghz_from_text(text: str | None) -> float | None:
    """Extract base GHz from strings like 'Intel(R) Xeon(R) Gold 6248 CPU @ 2.50GHz'."""
    if not text:
        return None
    match = _GHZ_RE.search(str(text).strip())
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return value if value > 0 else None


def build_host_ghz_map(
    rows: Sequence[tuple[Any, ...]],
    *,
    default_ghz: float = DEFAULT_HOST_CPU_GHZ,
) -> dict[str, float]:
    """Build vmhost name -> GHz map from NetBox query rows (name, cpu_cf, cpu_col)."""
    mapping: dict[str, float] = {}
    for row in rows or ():
        if not row or not row[0]:
            continue
        name = str(row[0]).strip()
        if not name:
            continue
        ghz = parse_cpu_ghz_from_text(row[1] if len(row) > 1 else None)
        if ghz is None:
            ghz = parse_cpu_ghz_from_text(row[2] if len(row) > 2 else None)
        if ghz is not None:
            mapping[name] = ghz
    return mapping


def resolve_host_ghz(
    vmhost: str | None,
    host_map: Mapping[str, float],
    *,
    default_ghz: float = DEFAULT_HOST_CPU_GHZ,
) -> tuple[float, str]:
    """Return (ghz_per_core, source) where source is netbox|default."""
    host = (vmhost or "").strip()
    if host and host in host_map:
        return float(host_map[host]), "netbox"
    return float(default_ghz), "default"


def aggregate_vm_allocation(
    vm_rows: Sequence[tuple[Any, ...]],
    host_map: Mapping[str, float],
    *,
    default_ghz: float = DEFAULT_HOST_CPU_GHZ,
) -> dict[str, Any]:
    """
    Sum VM-level allocation from rows:
      (vmhost, number_of_cpus, total_memory_capacity_gb, provisioned_space_gb, used_space_gb)
    """
    cpu_alloc_ghz = 0.0
    cpu_alloc_ghz_sales = 0.0
    mem_alloc_gb = 0.0
    stor_provisioned_gb = 0.0
    stor_actual_used_gb = 0.0
    hosts_resolved = 0
    hosts_fallback_default = 0
    seen_hosts: set[str] = set()

    for row in vm_rows or ():
        if not row:
            continue
        vmhost = str(row[0] or "").strip()
        vcpus = int(row[1] or 0)
        mem_gb = float(row[2] or 0)
        prov_gb = float(row[3] or 0)
        used_gb = float(row[4] or 0)

        ghz, source = resolve_host_ghz(vmhost, host_map, default_ghz=default_ghz)
        cpu_alloc_ghz += vcpus * ghz
        cpu_alloc_ghz_sales += vcpus
        mem_alloc_gb += mem_gb
        stor_provisioned_gb += prov_gb
        stor_actual_used_gb += used_gb

        if vmhost and vmhost not in seen_hosts:
            seen_hosts.add(vmhost)
            if source == "netbox":
                hosts_resolved += 1
            else:
                hosts_fallback_default += 1

    return {
        "stor_provisioned_gb": round(stor_provisioned_gb, 2),
        "stor_actual_used_gb": round(stor_actual_used_gb, 2),
        "cpu_alloc_ghz_vm": round(cpu_alloc_ghz, 2),
        "cpu_alloc_ghz_sales": round(cpu_alloc_ghz_sales, 2),
        "mem_alloc_gb_vm": round(mem_alloc_gb, 2),
        "cpu_alloc_hosts_resolved": hosts_resolved,
        "cpu_alloc_hosts_fallback_default": hosts_fallback_default,
        "cpu_alloc_hosts_unmatched": hosts_fallback_default,
    }


def enrich_vm_cpu_sales_fields(
    vmhost: str | None,
    vcpus: float,
    host_map: Mapping[str, float],
    *,
    default_ghz: float = DEFAULT_HOST_CPU_GHZ,
    is_nutanix: bool = False,
) -> dict[str, Any]:
    """Per-VM sales (1 vCPU = 1 GHz) vs real (vCPU × host GHz) for customer views."""
    sales = float(vcpus or 0)
    if is_nutanix:
        host_ghz = 1.0
        real = sales
    else:
        host_ghz, _ = resolve_host_ghz(vmhost, host_map, default_ghz=default_ghz)
        real = sales * host_ghz
    return {
        "cpu_ghz_sales": round(sales, 2),
        "cpu_ghz_real": round(real, 2),
        "host_ghz_per_core": round(host_ghz, 2),
        "cpu_exceeds_sales_limit": real > sales + 1e-9,
    }


def enrich_customer_vm_cpu_list(
    vm_rows: list[dict],
    host_map: Mapping[str, float],
    *,
    default_ghz: float = DEFAULT_HOST_CPU_GHZ,
) -> list[dict]:
    """Attach sales/real CPU fields to customer VM dict rows."""
    enriched: list[dict] = []
    for vm in vm_rows or []:
        source = str(vm.get("source") or "")
        is_nutanix_only = source.strip().lower() == "nutanix"
        extras = enrich_vm_cpu_sales_fields(
            vm.get("vmhost"),
            float(vm.get("cpu") or 0),
            host_map,
            default_ghz=default_ghz,
            is_nutanix=is_nutanix_only,
        )
        enriched.append({**vm, **extras})
    return enriched


def sum_cpu_real_total(vm_rows: list[dict]) -> float:
    return round(sum(float(vm.get("cpu_ghz_real") or 0) for vm in (vm_rows or [])), 2)


def compute_cpu_overalloc_flags(
    cpu_cap: float,
    cpu_alloc_ghz_sales: float,
    cpu_alloc_ghz_vm: float,
) -> dict[str, bool]:
    """Derive DC-level overallocation flags for UI badges/alerts."""
    cap = float(cpu_cap or 0)
    if cap <= 0:
        return {"cpu_overallocated_sales": False, "cpu_overallocated_real": False}
    return {
        "cpu_overallocated_sales": float(cpu_alloc_ghz_sales or 0) > cap,
        "cpu_overallocated_real": float(cpu_alloc_ghz_vm or 0) > cap,
    }


def cached_host_map(
    loader,
    *,
    default_ghz: float = DEFAULT_HOST_CPU_GHZ,
    ttl_sec: float = _HOST_MAP_TTL_SEC,
) -> dict[str, float]:
    """Return cached host GHz map; loader is a zero-arg callable returning NetBox rows."""
    global _host_map_cache
    now = time.monotonic()
    if _host_map_cache is not None:
        cached_map, expiry = _host_map_cache
        if now < expiry:
            return cached_map
    rows = loader()
    mapping = build_host_ghz_map(rows, default_ghz=default_ghz)
    _host_map_cache = (mapping, now + ttl_sec)
    return mapping


def clear_host_map_cache() -> None:
    """Clear process-local NetBox host GHz cache (for tests)."""
    global _host_map_cache
    _host_map_cache = None
