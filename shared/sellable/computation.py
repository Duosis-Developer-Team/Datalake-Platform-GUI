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
    alloc_pct = 100.0 * max(allocated, 0.0) / total
    util_pct = max(utilization_pct or 0.0, 0.0)
    effective_pct = max(alloc_pct, util_pct)
    if effective_pct > threshold_pct + 1e-9:
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


# ---------------------------------------------------------------------------
# Host-based computation (ADR: host-based CRM calculation)
#
# A VM is provisioned on a single host, so sellable capacity must respect
# per-host fragmentation: a DC with 10 hosts each having 1 free unit cannot
# host a 10-unit VM. Each host is evaluated on its own (CPU + RAM coupled by
# the family ratio); the family unit count is the SUM of per-host unit counts.
# Storage is intentionally excluded from the per-host min() — it is computed
# separately per architecture (KM datastores vs HCI/Power own storage).
# ---------------------------------------------------------------------------


def host_effective_units(
    hosts: "Iterable[dict]",
    ratio: ResourceRatio,
    *,
    cpu_threshold_pct: float = 100.0,
    ram_threshold_pct: float = 100.0,
    cpu_track: str = "effective",
    effective_ghz_per_unit: float = 1.0,
) -> float:
    """Sum of per-host effective unit counts.

    Each host dict must carry CPU/RAM total/alloc fields in display units.
    ``cpu_track`` selects which CPU allocation basis to use:
      - ``effective`` — ``cpu_total`` / ``cpu_alloc`` (sales GHz rule)
      - ``physical``  — ``cpu_total_phys`` / ``cpu_alloc_phys`` (vCPU × host GHz)
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
        raw_ram = apply_utilization_gate(
            float(h.get("ram_total") or 0.0),
            float(h.get("ram_alloc") or 0.0),
            float(h.get("ram_util_pct") or 0.0),
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
) -> list[PanelResult]:
    """Host-based ratio constraint with physical and effective CPU tracks."""
    panel_list = list(panels)
    n_phys = host_effective_units(
        hosts,
        ratio,
        cpu_threshold_pct=cpu_threshold_pct,
        ram_threshold_pct=ram_threshold_pct,
        cpu_track="physical",
    )
    n_eff = host_effective_units(
        hosts,
        ratio,
        cpu_threshold_pct=cpu_threshold_pct,
        ram_threshold_pct=ram_threshold_pct,
        cpu_track="effective",
        effective_ghz_per_unit=effective_ghz_per_unit,
    )

    out: list[PanelResult] = []
    for p in panel_list:
        if p.resource_kind == "cpu":
            constrained_phys = n_phys * ratio.cpu_per_unit
            constrained_eff = n_eff * ratio.cpu_per_unit
            ratio_bound = (
                constrained_eff + 1e-6 < p.sellable_raw
                or constrained_phys + 1e-6 < (p.sellable_physical or p.sellable_raw or 0.0)
            )
            out.append(
                replace(
                    p,
                    sellable_physical=constrained_phys,
                    sellable_effective=constrained_eff,
                    sellable_constrained=constrained_eff,
                    ratio_bound=ratio_bound,
                    computation_mode="host_based",
                )
            )
        elif p.resource_kind == "ram":
            constrained = n_eff * ratio.ram_gb_per_unit
            ratio_bound = constrained + 1e-6 < p.sellable_raw
            out.append(replace(p, sellable_constrained=constrained, ratio_bound=ratio_bound))
        else:
            out.append(replace(p, sellable_constrained=p.sellable_raw, ratio_bound=False))
    return out


def constrain_by_ratio_dual_cpu_cluster(
    panels: Iterable[PanelResult],
    ratio: ResourceRatio,
    *,
    cpu_raw_physical: float,
    cpu_raw_effective: float,
    decouple_resource_kinds: frozenset[str] | None = None,
) -> list[PanelResult]:
    """Cluster fallback dual CPU constraint using separate raw sellable values."""
    decouple = frozenset() if decouple_resource_kinds is None else decouple_resource_kinds
    panel_list = list(panels)
    by_kind = _split_by_kind(panel_list)

    cpu_p = by_kind.get("cpu")
    ram_p = by_kind.get("ram")
    sto_p = by_kind.get("storage")

    def _n_for_cpu(raw_cpu: float) -> float:
        effective_units: list[float] = []
        if raw_cpu > 0 and ratio.cpu_per_unit > 0:
            effective_units.append(raw_cpu / ratio.cpu_per_unit)
        if ram_p is not None and ratio.ram_gb_per_unit > 0:
            effective_units.append(ram_p.sellable_raw / ratio.ram_gb_per_unit)
        if (
            sto_p is not None
            and ratio.storage_gb_per_unit > 0
            and "storage" not in decouple
        ):
            effective_units.append(sto_p.sellable_raw / ratio.storage_gb_per_unit)
        return min(effective_units) if effective_units else 0.0

    n_phys = _n_for_cpu(cpu_raw_physical)
    n_eff = _n_for_cpu(cpu_raw_effective)

    out: list[PanelResult] = []
    for p in panel_list:
        if p.resource_kind == "cpu" and cpu_p is not None:
            constrained_phys = n_phys * ratio.cpu_per_unit
            constrained_eff = n_eff * ratio.cpu_per_unit
            ratio_bound = constrained_eff + 1e-6 < cpu_p.sellable_raw
            out.append(
                replace(
                    p,
                    sellable_physical=constrained_phys,
                    sellable_effective=constrained_eff,
                    sellable_constrained=constrained_eff,
                    ratio_bound=ratio_bound,
                    computation_mode="cluster_fallback",
                )
            )
        elif p.resource_kind == "ram" and ram_p is not None:
            constrained = n_eff * ratio.ram_gb_per_unit
            ratio_bound = constrained + 1e-6 < p.sellable_raw
            out.append(replace(p, sellable_constrained=constrained, ratio_bound=ratio_bound))
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
                constrained = n_eff * ratio.storage_gb_per_unit
                ratio_bound = constrained + 1e-6 < p.sellable_raw
                out.append(replace(p, sellable_constrained=constrained, ratio_bound=ratio_bound))
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
