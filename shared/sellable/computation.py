"""Pure computation helpers for the Sellable Potential pipeline.

Functions here are intentionally framework- and DB-agnostic so they can be
covered by fast unit tests without any infra dependency. The algorithm is:

  1. ``convert_unit``   — apply a UnitConversion to a raw datalake number.
  2. ``apply_threshold`` — sellable_raw = max(total*pct/100 - allocated, 0).
  3. ``constrain_by_ratio`` — given a family's CPU/RAM/Storage triplet of
     sellable_raw values + a ResourceRatio, compute how many CPU units the
     scarce resource permits, then back-derive the constrained sellable for
     each panel (CPU stays at the chosen number, RAM = N*ram_gb_per_unit,
     Storage = N*storage_gb_per_unit).
  4. ``compute_potential_tl`` — sellable_constrained * unit_price_tl.

All numbers are expressed in the panel's display_unit BEFORE these helpers
are called (the caller runs convert_unit first).
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Iterable

from .models import PanelResult, ResourceRatio, UnitConversion


def convert_unit(value: float | int | None, conv: UnitConversion | None) -> float:
    """Apply ``conv`` to ``value``. Missing values are treated as 0; missing
    conversions act as identity. ``ceil_result`` rounds up after the operation.
    """
    if value is None:
        return 0.0
    v = float(value)
    if conv is None:
        return v
    if conv.factor == 0:
        return 0.0
    if conv.operation == "multiply":
        v = v * conv.factor
    else:
        v = v / conv.factor
    if conv.ceil_result:
        v = float(math.ceil(v))
    return v


def apply_threshold(total: float, allocated: float, pct: float) -> float:
    """Compute sellable_raw = max(total * pct/100 - allocated, 0)."""
    if total <= 0:
        return 0.0
    capped = total * (max(pct, 0.0) / 100.0)
    return max(capped - max(allocated, 0.0), 0.0)


def utilization_gate_blocked(
    total: float,
    allocated: float,
    utilization_pct: float | None,
    threshold_pct: float,
) -> bool:
    """Return True when max(allocation%, utilization%) exceeds the threshold."""
    if total <= 0:
        return False
    alloc_pct = 100.0 * max(allocated, 0.0) / total
    util_pct = max(utilization_pct or 0.0, 0.0)
    return max(alloc_pct, util_pct) > threshold_pct + 1e-9


def apply_utilization_gate(
    total: float,
    allocated: float,
    utilization_pct: float | None,
    threshold_pct: float,
) -> float:
    """Apply CRM threshold with allocation and peak-utilization gates.

    When ``max(allocation%, utilization%)`` exceeds ``threshold_pct``, sellable
    headroom is zero. Otherwise falls back to :func:`apply_threshold`.
    """
    if total <= 0:
        return 0.0
    if utilization_gate_blocked(total, allocated, utilization_pct, threshold_pct):
        return 0.0
    return apply_threshold(total, allocated, threshold_pct)


def _split_by_kind(panels: Iterable[PanelResult]) -> dict[str, PanelResult]:
    """Index panels by resource_kind (cpu/ram/storage). Last one wins; we
    expect a single panel per kind per family."""
    out: dict[str, PanelResult] = {}
    for p in panels:
        out[p.resource_kind] = p
    return out


def constrain_by_ratio(
    panels: Iterable[PanelResult],
    ratio: ResourceRatio,
    *,
    decouple_resource_kinds: frozenset[str] | None = None,
) -> list[PanelResult]:
    """Apply the family's CPU:RAM:Storage ratio across same-family panels.

    Returns a NEW list of PanelResult instances with ``sellable_constrained``
    and ``ratio_bound`` populated. Panels whose resource_kind is not part of
    the cpu/ram/storage triplet are returned with ``sellable_constrained ==
    sellable_raw`` and ``ratio_bound = False``.

    When ``decouple_resource_kinds`` contains e.g. ``\"storage\"``, that kind is
    omitted from the ``min()`` over effective units; storage panels are emitted
    with ``sellable_raw`` and ``sellable_constrained`` set to 0 (no disk
    sellable until infra is bound).

    Algorithm:
      effective_cpu     = sellable_raw_cpu / ratio.cpu_per_unit
      effective_ram     = sellable_raw_ram / ratio.ram_gb_per_unit
      effective_storage = sellable_raw_storage / ratio.storage_gb_per_unit
      n = min(present effective values)            # 0 if any is 0
      sellable_constrained_cpu     = n * ratio.cpu_per_unit
      sellable_constrained_ram     = n * ratio.ram_gb_per_unit
      sellable_constrained_storage = n * ratio.storage_gb_per_unit
      ratio_bound = constrained < raw - 1e-6
    """
    decouple = frozenset() if decouple_resource_kinds is None else decouple_resource_kinds

    panel_list = list(panels)
    by_kind = _split_by_kind(panel_list)

    cpu_p = by_kind.get("cpu")
    ram_p = by_kind.get("ram")
    sto_p = by_kind.get("storage")

    effective_units: list[float] = []
    if cpu_p is not None and ratio.cpu_per_unit > 0:
        effective_units.append(cpu_p.sellable_raw / ratio.cpu_per_unit)
    if ram_p is not None and ratio.ram_gb_per_unit > 0:
        effective_units.append(ram_p.sellable_raw / ratio.ram_gb_per_unit)
    if sto_p is not None and ratio.storage_gb_per_unit > 0 and "storage" not in decouple:
        effective_units.append(sto_p.sellable_raw / ratio.storage_gb_per_unit)

    n = min(effective_units) if effective_units else 0.0

    out: list[PanelResult] = []
    for p in panel_list:
        if p.resource_kind == "cpu" and cpu_p is not None:
            constrained = n * ratio.cpu_per_unit
        elif p.resource_kind == "ram" and ram_p is not None:
            constrained = n * ratio.ram_gb_per_unit
        elif p.resource_kind == "storage" and sto_p is not None:
            if "storage" in decouple:
                out.append(
                    replace(
                        p,
                        sellable_raw=0.0,
                        sellable_constrained=0.0,
                        ratio_bound=False,
                    )
                )
                continue
            constrained = n * ratio.storage_gb_per_unit
        else:
            # 'other' resource_kind (firewall, license, ...) is not bound
            # by the CPU:RAM:Storage ratio. Keep raw.
            new = replace(p, sellable_constrained=p.sellable_raw, ratio_bound=False)
            out.append(new)
            continue
        ratio_bound = constrained + 1e-6 < p.sellable_raw
        out.append(replace(p, sellable_constrained=constrained, ratio_bound=ratio_bound))
    return out


def compute_potential_tl(sellable_constrained: float, unit_price_tl: float) -> float:
    """Final monetary projection. Negative inputs collapse to 0."""
    return max(sellable_constrained, 0.0) * max(unit_price_tl, 0.0)


def compute_effective_bottleneck_units(
    panels: Iterable[PanelResult],
    ratio: ResourceRatio,
) -> tuple[float, str | None]:
    """Effective ratio units from constrained CPU/RAM (sales/effective track)."""
    by_kind = _split_by_kind(panels)
    cpu_p = by_kind.get("cpu")
    ram_p = by_kind.get("ram")
    candidates: list[tuple[float, str]] = []
    if cpu_p is not None and ratio.cpu_per_unit > 0:
        cpu_constrained = max(float(cpu_p.sellable_constrained or 0.0), 0.0)
        candidates.append((cpu_constrained / ratio.cpu_per_unit, "cpu"))
    if ram_p is not None and ratio.ram_gb_per_unit > 0:
        ram_constrained = max(float(ram_p.sellable_constrained or 0.0), 0.0)
        candidates.append((ram_constrained / ratio.ram_gb_per_unit, "ram"))
    if not candidates:
        return 0.0, None
    n_eff = min(c[0] for c in candidates)
    bottleneck = min(candidates, key=lambda c: (c[0], 0 if c[1] == "cpu" else 1))[1]
    return max(n_eff, 0.0), bottleneck


def apply_storage_ratio_cap(
    panels: Iterable[PanelResult],
    ratio: ResourceRatio,
) -> list[PanelResult]:
    """Cap storage sellable by compute effective bottleneck (never increases values)."""
    panel_list = list(panels)
    by_kind = _split_by_kind(panel_list)
    sto_p = by_kind.get("storage")
    if sto_p is None or ratio.storage_gb_per_unit <= 0:
        return panel_list

    n_eff, bottleneck_kind = compute_effective_bottleneck_units(panel_list, ratio)
    storage_cap = max(n_eff * ratio.storage_gb_per_unit, 0.0)

    out: list[PanelResult] = []
    for p in panel_list:
        if p.resource_kind != "storage":
            out.append(p)
            continue

        raw_max = float(p.sellable_max if p.sellable_max is not None else p.sellable_raw)
        raw_min = float(p.sellable_min if p.sellable_min is not None else p.sellable_constrained)
        prev_constrained = float(p.sellable_constrained)

        new_min = min(raw_min, storage_cap)
        new_max = min(raw_max, storage_cap)
        if p.sellable_max is not None:
            new_constrained = new_min
        else:
            new_constrained = min(prev_constrained, storage_cap)

        capped = (
            new_constrained + 1e-6 < prev_constrained
            or new_max + 1e-6 < raw_max
            or new_min + 1e-6 < raw_min
        )
        constraint_reason = p.constraint_reason if p.constraint_reason != "none" else "none"
        if p.gate_blocked:
            constraint_reason = "gate_blocked"
        elif n_eff <= 1e-9 and raw_max > 1e-6:
            constraint_reason = "compute_bottleneck"
        elif capped:
            constraint_reason = "ratio_bound" if constraint_reason == "none" else constraint_reason

        out.append(
            replace(
                p,
                sellable_constrained=new_constrained,
                sellable_min=new_min if p.sellable_min is not None else None,
                sellable_max=new_max if p.sellable_max is not None else None,
                ratio_bound=p.ratio_bound or capped,
                constraint_reason=constraint_reason,
                bottleneck_kind=bottleneck_kind if capped else p.bottleneck_kind,
                bottleneck_units=n_eff if capped else p.bottleneck_units,
            )
        )
    return out


def annotate_panel_constraint_metadata(panels: Iterable[PanelResult]) -> list[PanelResult]:
    """Populate constraint_reason on CPU/RAM panels for UI badges."""
    out: list[PanelResult] = []
    for p in panels:
        if p.resource_kind == "storage" and p.constraint_reason not in ("none", ""):
            out.append(p)
            continue
        reason = "none"
        if p.gate_blocked:
            reason = "gate_blocked"
        elif p.ratio_bound:
            reason = "ratio_bound"
        if reason == p.constraint_reason:
            out.append(p)
        else:
            out.append(replace(p, constraint_reason=reason))
    return out


# ---------------------------------------------------------------------------
# Host-based computation (ADR: host-based CRM calculation)
#
# A VM is provisioned on a single host, so sellable capacity must respect
# per-host fragmentation: a DC with 10 hosts each having 1 free unit cannot
# host a 10-unit VM. Each host is evaluated on its own (CPU + RAM coupled by
# the family ratio); the family unit count is the SUM of per-host unit counts.
# Storage participates in per-host triple min when using
# :func:`constrain_by_ratio_per_host_triple_dual`.
# ---------------------------------------------------------------------------


def host_effective_units(
    hosts: "Iterable[dict]",
    ratio: ResourceRatio,
    *,
    cpu_threshold_pct: float = 100.0,
    ram_threshold_pct: float = 100.0,
    cpu_track: str = "effective",
    ram_track: str = "physical",
    effective_ghz_per_unit: float = 1.0,
) -> float:
    """Sum of per-host effective unit counts.

    Each host dict must carry CPU/RAM total/alloc fields in display units.
    ``cpu_track`` selects which CPU allocation basis to use:
      - ``effective`` — ``cpu_total`` / ``cpu_alloc`` (sales GHz rule)
      - ``physical``  — ``cpu_total_phys`` / ``cpu_alloc_phys`` (vCPU × host GHz)
    ``ram_track`` selects RAM basis:
      - ``physical`` — per-host VM-configured RAM allocation
      - ``max``      — per-host max RAM (``mem_cap_gb_at_peak`` / ``mem_used_gb_peak``)
    """
    if ratio.cpu_per_unit <= 0 or ratio.ram_gb_per_unit <= 0:
        return 0.0
    n_total = 0.0
    for h in hosts:
        if cpu_track == "physical":
            cpu_total = float(h.get("cpu_total_phys") or h.get("cpu_total") or 0.0)
            cpu_alloc = float(h.get("cpu_alloc_phys") or 0.0)
            ghz = float(h.get("ghz_per_core") or 1.0)
            cpu_den = ratio.cpu_per_unit * ghz if ghz > 0 else ratio.cpu_per_unit
        else:
            cpu_total = float(h.get("cpu_total") or 0.0)
            cpu_alloc = float(h.get("cpu_alloc") or 0.0)
            cpu_den = ratio.cpu_per_unit * max(effective_ghz_per_unit, 1e-9)
        raw_cpu = apply_utilization_gate(
            cpu_total,
            cpu_alloc,
            float(h.get("cpu_util_pct") or 0.0),
            cpu_threshold_pct,
        )
        if ram_track in ("max", "peak"):
            ram_total = float(
                h.get("mem_cap_gb_at_peak") or h.get("ram_peak_total") or 0.0
            )
            ram_alloc = float(h.get("mem_used_gb_peak") or h.get("ram_peak_used") or 0.0)
            ram_util = float(h.get("mem_peak_util_pct") or h.get("ram_peak_util_pct") or 0.0)
        else:
            ram_total = float(h.get("ram_total") or 0.0)
            ram_alloc = float(h.get("ram_alloc") or 0.0)
            ram_util = float(h.get("ram_util_pct") or 0.0)
        raw_ram = apply_utilization_gate(
            ram_total,
            ram_alloc,
            ram_util,
            ram_threshold_pct,
        )
        n_total += min(raw_cpu / cpu_den, raw_ram / ratio.ram_gb_per_unit)
    return n_total


def constrain_by_ratio_per_host_dual(
    panels: Iterable[PanelResult],
    ratio: ResourceRatio,
    hosts: "list[dict]",
    *,
    cpu_threshold_pct: float = 100.0,
    ram_threshold_pct: float = 100.0,
    effective_ghz_per_unit: float = 1.0,
    ram_raw_physical: float | None = None,
    ram_raw_peak: float | None = None,
) -> list[PanelResult]:
    """Host-based ratio constraint with allocation/max CPU and RAM tracks."""
    panel_list = list(panels)
    n_cpu_eff = host_effective_units(
        hosts,
        ratio,
        cpu_threshold_pct=cpu_threshold_pct,
        ram_threshold_pct=ram_threshold_pct,
        cpu_track="effective",
        ram_track="physical",
        effective_ghz_per_unit=effective_ghz_per_unit,
    )
    n_cpu_max = host_effective_units(
        hosts,
        ratio,
        cpu_threshold_pct=cpu_threshold_pct,
        ram_threshold_pct=ram_threshold_pct,
        cpu_track="max",
        ram_track="max",
        effective_ghz_per_unit=effective_ghz_per_unit,
    )
    n_ram_phys = host_effective_units(
        hosts,
        ratio,
        cpu_threshold_pct=cpu_threshold_pct,
        ram_threshold_pct=ram_threshold_pct,
        cpu_track="physical",
        ram_track="physical",
    )
    n_ram_max = host_effective_units(
        hosts,
        ratio,
        cpu_threshold_pct=cpu_threshold_pct,
        ram_threshold_pct=ram_threshold_pct,
        cpu_track="max",
        ram_track="max",
        effective_ghz_per_unit=effective_ghz_per_unit,
    )

    out: list[PanelResult] = []
    for p in panel_list:
        if p.resource_kind == "cpu":
            constrained_eff = n_cpu_eff * ratio.cpu_per_unit
            constrained_max = n_cpu_max * ratio.cpu_per_unit
            ratio_bound = constrained_eff + 1e-6 < p.sellable_raw
            out.append(
                replace(
                    p,
                    sellable_allocation=constrained_eff,
                    sellable_max_util=constrained_max,
                    sellable_effective=constrained_eff,
                    sellable_physical=None,
                    sellable_constrained=constrained_eff,
                    ratio_bound=ratio_bound,
                    computation_mode="host_based",
                )
            )
        elif p.resource_kind == "ram":
            constrained_phys = n_ram_phys * ratio.ram_gb_per_unit
            constrained_max = n_ram_max * ratio.ram_gb_per_unit
            raw_phys = ram_raw_physical if ram_raw_physical is not None else p.sellable_raw
            raw_max = ram_raw_peak if ram_raw_peak is not None else p.sellable_raw
            ratio_bound = (
                constrained_phys + 1e-6 < raw_phys
                or constrained_max + 1e-6 < raw_max
            )
            out.append(
                replace(
                    p,
                    sellable_physical=constrained_phys,
                    sellable_effective=constrained_max,
                    sellable_allocation=constrained_phys,
                    sellable_max_util=constrained_max,
                    sellable_constrained=constrained_phys,
                    ratio_bound=ratio_bound,
                    computation_mode="host_based",
                )
            )
        else:
            out.append(replace(p, sellable_constrained=p.sellable_raw, ratio_bound=False))
    return out


def constrain_by_ratio_per_host_triple_dual(
    panels: Iterable[PanelResult],
    ratio: ResourceRatio,
    hosts: list[dict],
    *,
    cpu_threshold_pct: float = 100.0,
    ram_threshold_pct: float = 100.0,
    storage_threshold_pct: float = 100.0,
    effective_ghz_per_unit: float = 1.0,
    ram_raw_physical: float | None = None,
    ram_raw_peak: float | None = None,
    shared_pools: list[dict] | None = None,
    unit_price_tl: float = 0.0,
    ibm_storage_range: tuple[float, float] | None = None,
    cluster_storage_raw_gb: float | None = None,
) -> list[PanelResult]:
    """Host-based triple min(CPU, RAM, Storage) with dual CPU/RAM tracks."""
    from .host_sellable import (
        HostSellableResult,
        aggregate_family_storage_range,
        compute_host_sellable_units,
    )

    panel_list = list(panels)
    if not hosts:
        return constrain_by_ratio_per_host_dual(
            panel_list,
            ratio,
            hosts,
            cpu_threshold_pct=cpu_threshold_pct,
            ram_threshold_pct=ram_threshold_pct,
            effective_ghz_per_unit=effective_ghz_per_unit,
            ram_raw_physical=ram_raw_physical,
            ram_raw_peak=ram_raw_peak,
        )

    def _accumulate(
        cpu_track: str,
        ram_track: str,
        storage_shared: bool,
    ) -> tuple[float, list[HostSellableResult]]:
        n_sum = 0.0
        results: list[HostSellableResult] = []
        for h in hosts:
            result = compute_host_sellable_units(
                h,
                ratio,
                cpu_threshold_pct=cpu_threshold_pct,
                ram_threshold_pct=ram_threshold_pct,
                storage_threshold_pct=storage_threshold_pct,
                cpu_track=cpu_track,
                ram_track=ram_track,
                effective_ghz_per_unit=effective_ghz_per_unit,
                storage_include_shared=storage_shared,
                storage_in_triple=cluster_storage_raw_gb is None and not h.get("storage_cluster_pool"),
                unit_price_tl=unit_price_tl,
            )
            n_sum += result.n_units_max if storage_shared else result.n_units_min
            results.append(result)
        return n_sum, results

    n_phys, _ = _accumulate("effective", "physical", False)
    n_cpu_alloc, _ = _accumulate("effective", "physical", False)
    n_ram_alloc, host_stor_alloc = _accumulate("effective", "physical", False)
    _, host_stor_alloc_shared = _accumulate("effective", "physical", True)

    n_cpu_max, _ = _accumulate("max", "max", False)
    n_ram_max, host_stor_max = _accumulate("max", "max", False)
    _, host_stor_max_shared = _accumulate("max", "max", True)

    stor_lo_alloc, stor_hi_alloc = aggregate_family_storage_range(
        host_stor_alloc,
        shared_pools or [],
        ratio,
    )
    stor_lo_max, stor_hi_max = aggregate_family_storage_range(
        host_stor_max,
        shared_pools or [],
        ratio,
    )
    stor_constrained_alloc = sum(r.stor_constrained_min for r in host_stor_alloc)
    stor_constrained_max = sum(r.stor_constrained_min for r in host_stor_max)

    if cluster_storage_raw_gb is not None:
        n_bn_alloc = min(n_cpu_alloc, n_ram_alloc) if n_ram_alloc > 0 else n_cpu_alloc
        n_bn_max = min(n_cpu_max, n_ram_max) if n_ram_max > 0 else n_cpu_max
        stor_cap_alloc = max(n_bn_alloc, 0.0) * ratio.storage_gb_per_unit
        stor_cap_max = max(n_bn_max, 0.0) * ratio.storage_gb_per_unit
        stor_constrained_alloc = min(max(cluster_storage_raw_gb, 0.0), stor_cap_alloc)
        stor_constrained_max = min(max(cluster_storage_raw_gb, 0.0), stor_cap_max)
        stor_lo_alloc = stor_constrained_alloc
        stor_lo_max = stor_constrained_max
        stor_hi_alloc = min(
            max(cluster_storage_raw_gb, 0.0),
            max(n_cpu_alloc, n_ram_alloc) * ratio.storage_gb_per_unit,
        )
        stor_hi_max = min(
            max(cluster_storage_raw_gb, 0.0),
            max(n_cpu_max, n_ram_max) * ratio.storage_gb_per_unit,
        )

    if ibm_storage_range is not None:
        ibm_lo, ibm_hi = ibm_storage_range
        stor_lo_alloc = max(stor_lo_alloc, ibm_lo)
        stor_lo_max = max(stor_lo_max, ibm_lo)
        if ibm_hi > 0:
            stor_hi_alloc = min(stor_hi_alloc, ibm_hi) if stor_hi_alloc > 0 else ibm_hi
            stor_hi_max = min(stor_hi_max, ibm_hi) if stor_hi_max > 0 else ibm_hi
        stor_constrained_alloc = max(stor_constrained_alloc, stor_lo_alloc)
        stor_constrained_max = max(stor_constrained_max, stor_lo_max)
        if stor_hi_alloc > 0:
            stor_constrained_alloc = min(stor_constrained_alloc, stor_hi_alloc)
        if stor_hi_max > 0:
            stor_constrained_max = min(stor_constrained_max, stor_hi_max)

    cpu_alloc_val = n_cpu_alloc * ratio.cpu_per_unit
    cpu_max_val = n_cpu_max * ratio.cpu_per_unit
    ram_alloc_val = n_ram_alloc * ratio.ram_gb_per_unit
    ram_max_val = n_ram_max * ratio.ram_gb_per_unit
    _ = n_phys, host_stor_alloc_shared, host_stor_max_shared

    out: list[PanelResult] = []
    for p in panel_list:
        if p.resource_kind == "cpu":
            ratio_bound = cpu_alloc_val + 1e-6 < p.sellable_raw
            out.append(
                replace(
                    p,
                    sellable_allocation=cpu_alloc_val,
                    sellable_max_util=cpu_max_val,
                    sellable_effective=cpu_alloc_val,
                    sellable_physical=None,
                    sellable_constrained=cpu_alloc_val,
                    ratio_bound=ratio_bound,
                    computation_mode="host_based",
                )
            )
        elif p.resource_kind == "ram":
            raw_phys = ram_raw_physical if ram_raw_physical is not None else p.sellable_raw
            raw_max = ram_raw_peak if ram_raw_peak is not None else p.sellable_raw
            ratio_bound = (
                ram_alloc_val + 1e-6 < raw_phys
                or ram_max_val + 1e-6 < raw_max
            )
            out.append(
                replace(
                    p,
                    sellable_physical=ram_alloc_val,
                    sellable_allocation=ram_alloc_val,
                    sellable_max_util=ram_max_val,
                    sellable_effective=ram_max_val,
                    sellable_constrained=ram_alloc_val,
                    ratio_bound=ratio_bound,
                    computation_mode="host_based",
                )
            )
        elif p.resource_kind == "storage":
            ratio_bound = stor_constrained_alloc + 1e-6 < p.sellable_raw
            stor_hi_out = stor_hi_max if stor_hi_max > stor_lo_alloc + 1e-6 else None
            out.append(
                replace(
                    p,
                    sellable_constrained=stor_constrained_alloc,
                    sellable_min=stor_lo_alloc,
                    sellable_max=stor_hi_out,
                    sellable_allocation=stor_constrained_alloc,
                    sellable_max_util=stor_constrained_max,
                    ratio_bound=ratio_bound,
                    computation_mode="host_based",
                    constraint_reason="ratio_bound" if ratio_bound else "none",
                )
            )
        else:
            out.append(replace(p, sellable_constrained=p.sellable_raw, ratio_bound=False))
    return out


def constrain_by_ratio_dual_cpu_cluster(
    panels: Iterable[PanelResult],
    ratio: ResourceRatio,
    *,
    cpu_raw_physical: float,
    cpu_raw_effective: float,
    cpu_raw_max: float | None = None,
    ram_raw_physical: float | None = None,
    ram_raw_peak: float | None = None,
    decouple_resource_kinds: frozenset[str] | None = None,
) -> list[PanelResult]:
    """Cluster fallback dual CPU/RAM constraint using separate raw sellable values."""
    decouple = frozenset() if decouple_resource_kinds is None else decouple_resource_kinds
    panel_list = list(panels)
    by_kind = _split_by_kind(panel_list)

    cpu_p = by_kind.get("cpu")
    ram_p = by_kind.get("ram")
    sto_p = by_kind.get("storage")

    def _n_for_cpu(raw_cpu: float, raw_ram: float | None = None) -> float:
        effective_units: list[float] = []
        if raw_cpu > 0 and ratio.cpu_per_unit > 0:
            effective_units.append(raw_cpu / ratio.cpu_per_unit)
        ram_raw = raw_ram
        if ram_raw is None and ram_p is not None:
            ram_raw = ram_p.sellable_raw
        if ram_p is not None and ratio.ram_gb_per_unit > 0 and ram_raw is not None:
            effective_units.append(ram_raw / ratio.ram_gb_per_unit)
        if (
            sto_p is not None
            and ratio.storage_gb_per_unit > 0
            and "storage" not in decouple
        ):
            effective_units.append(sto_p.sellable_raw / ratio.storage_gb_per_unit)
        return min(effective_units) if effective_units else 0.0

    ram_phys = ram_raw_physical
    ram_max = ram_raw_peak
    if ram_p is not None:
        if ram_phys is None:
            ram_phys = (
                ram_p.sellable_allocation
                if ram_p.sellable_allocation is not None
                else (
                    ram_p.sellable_physical
                    if ram_p.sellable_physical is not None
                    else ram_p.sellable_raw
                )
            )
        if ram_max is None:
            ram_max = (
                ram_p.sellable_max_util
                if ram_p.sellable_max_util is not None
                else (
                    ram_p.sellable_effective
                    if ram_p.sellable_effective is not None
                    else ram_p.sellable_raw
                )
            )

    cpu_raw_max_val = cpu_raw_max if cpu_raw_max is not None else cpu_raw_effective

    n_cpu_alloc = _n_for_cpu(cpu_raw_effective, ram_phys)
    n_cpu_max = _n_for_cpu(cpu_raw_max_val, ram_max)
    n_ram_alloc = _n_for_cpu(cpu_raw_effective, ram_phys)
    n_ram_max = _n_for_cpu(cpu_raw_max_val, ram_max)
    n_stor_alloc = n_cpu_alloc
    n_stor_max = n_cpu_max

    out: list[PanelResult] = []
    for p in panel_list:
        if p.resource_kind == "cpu" and cpu_p is not None:
            constrained_alloc = n_cpu_alloc * ratio.cpu_per_unit
            constrained_max = n_cpu_max * ratio.cpu_per_unit
            ratio_bound = constrained_alloc + 1e-6 < cpu_p.sellable_raw
            out.append(
                replace(
                    p,
                    sellable_allocation=constrained_alloc,
                    sellable_max_util=constrained_max,
                    sellable_effective=constrained_alloc,
                    sellable_physical=None,
                    sellable_constrained=constrained_alloc,
                    ratio_bound=ratio_bound,
                    computation_mode="cluster_fallback",
                )
            )
        elif p.resource_kind == "ram" and ram_p is not None:
            constrained_alloc = n_ram_alloc * ratio.ram_gb_per_unit
            constrained_max = n_ram_max * ratio.ram_gb_per_unit
            raw_phys = ram_phys if ram_phys is not None else ram_p.sellable_raw
            raw_max = ram_max if ram_max is not None else ram_p.sellable_raw
            ratio_bound = (
                constrained_alloc + 1e-6 < raw_phys
                or constrained_max + 1e-6 < raw_max
            )
            out.append(
                replace(
                    p,
                    sellable_physical=constrained_alloc,
                    sellable_allocation=constrained_alloc,
                    sellable_max_util=constrained_max,
                    sellable_effective=constrained_max,
                    sellable_constrained=constrained_alloc,
                    ratio_bound=ratio_bound,
                    computation_mode="cluster_fallback",
                )
            )
        elif p.resource_kind == "storage" and sto_p is not None:
            if "storage" in decouple:
                out.append(
                    replace(
                        p,
                        sellable_raw=0.0,
                        sellable_constrained=0.0,
                        ratio_bound=False,
                    )
                )
            else:
                constrained_alloc = n_stor_alloc * ratio.storage_gb_per_unit
                constrained_max = n_stor_max * ratio.storage_gb_per_unit
                ratio_bound = constrained_alloc + 1e-6 < p.sellable_raw
                out.append(
                    replace(
                        p,
                        sellable_constrained=constrained_alloc,
                        sellable_min=constrained_alloc,
                        sellable_max=constrained_max if constrained_max > constrained_alloc + 1e-6 else None,
                        sellable_allocation=constrained_alloc,
                        sellable_max_util=constrained_max,
                        ratio_bound=ratio_bound,
                    )
                )
        else:
            out.append(replace(p, sellable_constrained=p.sellable_raw, ratio_bound=False))
    return out


def constrain_by_ratio_per_host(
    panels: Iterable[PanelResult],
    ratio: ResourceRatio,
    hosts: "list[dict]",
    *,
    cpu_threshold_pct: float = 100.0,
    ram_threshold_pct: float = 100.0,
) -> list[PanelResult]:
    """Host-based variant of :func:`constrain_by_ratio` for CPU/RAM panels.

    ``n = host_effective_units(...)`` is computed across the host list, then
    ``sellable_constrained_cpu = n * ratio.cpu_per_unit`` and
    ``sellable_constrained_ram = n * ratio.ram_gb_per_unit``.

    Storage and 'other' panels pass through unchanged (``sellable_constrained
    == sellable_raw``, ``ratio_bound = False``) — the architecture-aware
    storage range model fills their values separately.
    """
    panel_list = list(panels)
    n = host_effective_units(
        hosts,
        ratio,
        cpu_threshold_pct=cpu_threshold_pct,
        ram_threshold_pct=ram_threshold_pct,
    )

    out: list[PanelResult] = []
    for p in panel_list:
        if p.resource_kind == "cpu":
            constrained = n * ratio.cpu_per_unit
        elif p.resource_kind == "ram":
            constrained = n * ratio.ram_gb_per_unit
        else:
            out.append(replace(p, sellable_constrained=p.sellable_raw, ratio_bound=False))
            continue
        ratio_bound = constrained + 1e-6 < p.sellable_raw
        out.append(replace(p, sellable_constrained=constrained, ratio_bound=ratio_bound))
    return out


def compute_storage_range(
    *,
    intel_free: float,
    ibm_backed_datastore_free: float,
    ibm_storage_free: float,
) -> dict[str, float]:
    """Architecture-aware sellable storage range (KM vs IBM Power).

    IBM storage free space can be sold either as KM datastores or as native
    Power storage, so both families get a [min, max] range instead of a single
    number:

      KM    min = intel_free
      KM    max = intel_free + ibm_backed_datastore_free
      Power min = max(ibm_storage_free - ibm_backed_datastore_free, 0)
      Power max = ibm_storage_free

    All inputs must be pre-thresholded free capacities in the same unit.
    """
    intel_free = max(intel_free, 0.0)
    ibm_ds_free = max(ibm_backed_datastore_free, 0.0)
    ibm_free = max(ibm_storage_free, 0.0)
    return {
        "km_min": intel_free,
        "km_max": intel_free + ibm_ds_free,
        "power_min": max(ibm_free - ibm_ds_free, 0.0),
        "power_max": ibm_free,
    }
