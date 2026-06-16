"""Host-level sellable unit computation (triple min CPU/RAM/Storage + shared pool dedupe)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .computation import apply_utilization_gate
from .models import ResourceRatio


@dataclass
class HostSellableResult:
    """Per-host sellable units and ratio-bound waste."""

    n_units_min: float = 0.0
    n_units_max: float = 0.0
    cpu_constrained: float = 0.0
    ram_constrained: float = 0.0
    stor_constrained_min: float = 0.0
    stor_constrained_max: float = 0.0
    waste_cpu: float = 0.0
    waste_ram: float = 0.0
    waste_stor_min: float = 0.0
    waste_stor_max: float = 0.0
    constraint_tags: list[str] = field(default_factory=list)
    sellable_tl_min: float = 0.0
    sellable_tl_max: float = 0.0


def _unit_limits(
    raw_cpu: float,
    raw_ram: float,
    raw_stor: float,
    ratio: ResourceRatio,
    *,
    cpu_cap: float = 0.0,
    mem_cap: float = 0.0,
    stor_cap: float = 0.0,
) -> float:
    """Triple-min unit count; gated resources (raw=0) must pull the minimum to zero."""
    limits: list[float] = []
    if cpu_cap > 0 and ratio.cpu_per_unit > 0:
        limits.append(raw_cpu / ratio.cpu_per_unit)
    if mem_cap > 0 and ratio.ram_gb_per_unit > 0:
        limits.append(raw_ram / ratio.ram_gb_per_unit)
    if stor_cap > 0 and ratio.storage_gb_per_unit > 0:
        limits.append(raw_stor / ratio.storage_gb_per_unit)
    return min(limits) if limits else 0.0


def _format_waste_tag(kind: str, amount: float, unit: str) -> str | None:
    if amount <= 1e-6:
        return None
    if unit.upper() == "GHZ":
        return f"{amount:,.0f} GHz CPU ratio-bound"
    if unit.upper() == "GB":
        return f"{amount:,.0f} GB {kind} ratio-bound"
    return f"{amount:,.0f} {unit} {kind} ratio-bound"


def host_storage_free_gb(host: dict, *, include_shared: bool) -> float:
    """Return storage free GB for a host (exclusive or exclusive+shared mounts)."""
    exclusive = float(host.get("stor_exclusive_free_gb") or 0.0)
    if not include_shared:
        return max(exclusive, 0.0)
    shared = 0.0
    for mount in host.get("datastore_mounts") or []:
        if mount.get("shared"):
            shared += float(mount.get("free_gb") or 0.0)
    if not host.get("datastore_mounts") and float(host.get("stor_cap_gb") or 0) > 0:
        cap = float(host.get("stor_cap_gb") or 0.0)
        used = float(host.get("stor_used_host_gb") or host.get("stor_used_gb") or 0.0)
        return max(cap - used, 0.0)
    return max(exclusive + shared, 0.0)


def host_raw_headroom(
    host: dict,
    *,
    resource: str,
    threshold_pct: float,
    cpu_track: str = "effective",
    ram_track: str = "physical",
    effective_ghz_per_unit: float = 1.0,
) -> float:
    """Gated raw sellable headroom for one resource on one host."""
    _ = effective_ghz_per_unit
    if resource == "cpu":
        cap = float(host.get("cpu_cap_ghz") or host.get("cpu_total") or 0.0)
        if cpu_track == "physical":
            alloc = float(host.get("cpu_alloc_ghz_physical") or host.get("cpu_alloc_phys") or 0.0)
        elif cpu_track == "peak":
            alloc = float(host.get("cpu_used_ghz") or 0.0)
        else:
            alloc = float(host.get("cpu_alloc_ghz") or host.get("cpu_alloc") or 0.0)
        util = float(host.get("cpu_used_pct") or host.get("cpu_util_pct") or 0.0)
        return apply_utilization_gate(cap, alloc, util, threshold_pct)

    if resource == "ram":
        if ram_track == "peak":
            cap = float(
                host.get("mem_cap_gb_at_peak")
                or host.get("mem_peak_total")
                or host.get("mem_cap_gb")
                or host.get("ram_total")
                or 0.0
            )
            used = float(host.get("mem_used_gb_peak") or host.get("mem_peak_used") or 0.0)
            util = float(host.get("mem_peak_util_pct") or host.get("mem_used_pct") or 0.0)
            return apply_utilization_gate(cap, used, util, threshold_pct)
        cap = float(host.get("mem_cap_gb") or host.get("ram_total") or 0.0)
        alloc = float(host.get("mem_alloc_gb") or host.get("ram_alloc") or 0.0)
        util = float(host.get("mem_used_pct") or host.get("ram_util_pct") or 0.0)
        return apply_utilization_gate(cap, alloc, util, threshold_pct)

    if resource == "storage":
        cap = float(host.get("stor_cap_gb") or 0.0)
        prov = float(host.get("stor_provisioned_gb") or 0.0)
        if cap > 0 and prov > cap:
            prov = cap
        util = float(host.get("stor_used_pct") or 0.0)
        if cap <= 0:
            return 0.0
        if util <= 0 and prov > 0:
            util = 100.0 * prov / cap
        return apply_utilization_gate(cap, prov, util, threshold_pct)

    return 0.0


def compute_host_sellable_units(
    host: dict,
    ratio: ResourceRatio,
    *,
    cpu_threshold_pct: float,
    ram_threshold_pct: float,
    storage_threshold_pct: float,
    cpu_track: str = "effective",
    ram_track: str = "physical",
    effective_ghz_per_unit: float = 1.0,
    storage_include_shared: bool = False,
    storage_in_triple: bool = True,
    unit_price_tl: float = 0.0,
) -> HostSellableResult:
    """Compute min/max sellable units for one host with triple ratio coupling."""
    _ = effective_ghz_per_unit
    cpu_cap = float(host.get("cpu_cap_ghz") or host.get("cpu_total") or 0.0)
    mem_cap = float(host.get("mem_cap_gb") or host.get("ram_total") or 0.0)
    raw_cpu = host_raw_headroom(
        host,
        resource="cpu",
        threshold_pct=cpu_threshold_pct,
        cpu_track=cpu_track,
    )
    raw_ram = host_raw_headroom(
        host,
        resource="ram",
        threshold_pct=ram_threshold_pct,
        ram_track=ram_track,
    )
    stor_free_min = host_storage_free_gb(host, include_shared=False)
    stor_free_max = host_storage_free_gb(host, include_shared=True)
    cap = float(host.get("stor_cap_gb") or 0.0)
    prov = float(host.get("stor_provisioned_gb") or 0.0)
    if cap > 0 and prov > cap:
        prov = cap
    util = float(host.get("stor_used_pct") or 0.0)
    if cap > 0:
        raw_stor_gate = apply_utilization_gate(cap, prov, util, storage_threshold_pct)
        raw_stor = min(raw_stor_gate, stor_free_min) if stor_free_min > 0 else raw_stor_gate
        raw_stor_max = min(raw_stor_gate, stor_free_max) if stor_free_max > 0 else raw_stor_gate
    else:
        raw_stor = stor_free_min
        raw_stor_max = stor_free_max

    stor_cap_for_triple = cap if storage_in_triple else 0.0
    if cap > 0 and raw_stor <= 0 and stor_free_min <= 0 and storage_in_triple:
        n_min = 0.0
    else:
        n_min = _unit_limits(
            raw_cpu,
            raw_ram,
            raw_stor,
            ratio,
            cpu_cap=cpu_cap,
            mem_cap=mem_cap,
            stor_cap=stor_cap_for_triple,
        )
    n_max = _unit_limits(
        raw_cpu,
        raw_ram,
        raw_stor_max,
        ratio,
        cpu_cap=cpu_cap,
        mem_cap=mem_cap,
        stor_cap=stor_cap_for_triple,
    )
    if storage_include_shared:
        n_min = n_max

    cpu_c = n_min * ratio.cpu_per_unit
    ram_c = n_min * ratio.ram_gb_per_unit
    stor_c_min = n_min * ratio.storage_gb_per_unit
    stor_c_max = n_max * ratio.storage_gb_per_unit

    waste_cpu = max(raw_cpu - cpu_c, 0.0)
    waste_ram = max(raw_ram - ram_c, 0.0)
    waste_stor_min = max(raw_stor - stor_c_min, 0.0)
    waste_stor_max = max(raw_stor_max - stor_c_max, 0.0)

    tags: list[str] = []
    for tag in (
        _format_waste_tag("CPU", waste_cpu, "GHz"),
        _format_waste_tag("RAM", waste_ram, "GB"),
        _format_waste_tag("Storage", waste_stor_min, "GB"),
    ):
        if tag:
            tags.append(tag)

    tl_min = n_min * unit_price_tl if unit_price_tl > 0 else 0.0
    tl_max = n_max * unit_price_tl if unit_price_tl > 0 else 0.0

    return HostSellableResult(
        n_units_min=n_min,
        n_units_max=n_max,
        cpu_constrained=cpu_c,
        ram_constrained=ram_c,
        stor_constrained_min=stor_c_min,
        stor_constrained_max=stor_c_max,
        waste_cpu=waste_cpu,
        waste_ram=waste_ram,
        waste_stor_min=waste_stor_min,
        waste_stor_max=waste_stor_max,
        constraint_tags=tags,
        sellable_tl_min=tl_min,
        sellable_tl_max=tl_max,
    )


def aggregate_family_storage_range(
    host_results: list[HostSellableResult],
    shared_pools: list[dict],
    ratio: ResourceRatio,
) -> tuple[float, float]:
    """Family-level storage sellable range with shared pool dedupe."""
    if not host_results:
        return 0.0, 0.0
    lo = sum(r.stor_constrained_min for r in host_results)
    hi_candidates = [r.stor_constrained_max for r in host_results]
    shared_free = sum(float(p.get("free_gb") or 0.0) for p in shared_pools if p.get("shared"))
    exclusive_free = sum(
        float(p.get("free_gb") or 0.0) for p in shared_pools if not p.get("shared")
    )
    hi_from_hosts = max(hi_candidates) if hi_candidates else 0.0
    pool_cap = exclusive_free + shared_free
    if ratio.storage_gb_per_unit > 0 and pool_cap > 0:
        pool_units = pool_cap / ratio.storage_gb_per_unit
        hi = min(hi_from_hosts, pool_units * ratio.storage_gb_per_unit)
    else:
        hi = hi_from_hosts
    return max(lo, 0.0), max(hi, lo)


def enrich_host_display_fields(host: dict, sellable: HostSellableResult) -> dict:
    """Attach sellable display fields to a host dict."""
    out = dict(host)
    out["sellable_n_min"] = round(sellable.n_units_min, 2)
    out["sellable_n_max"] = round(sellable.n_units_max, 2)
    out["sellable_tl_min"] = round(sellable.sellable_tl_min, 2)
    out["sellable_tl_max"] = round(sellable.sellable_tl_max, 2)
    out["constraint_tags"] = list(sellable.constraint_tags)
    return out
