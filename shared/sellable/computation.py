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
