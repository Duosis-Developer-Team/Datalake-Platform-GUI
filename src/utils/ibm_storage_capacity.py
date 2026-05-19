"""IBM Storage physical vs efficient capacity calculations for DC view."""

from __future__ import annotations

from typing import Callable


def topology_divisor(topology: str | None) -> float:
    """Return 2 for hyperswap topology, otherwise 1."""
    return 2.0 if (topology or "").strip().lower() == "hyperswap" else 1.0


def compute_system_capacities_gb(
    system: dict,
    parse_gb: Callable[[str | None], float],
) -> dict[str, float]:
    """
    Per-system capacities in GB.

    Physical values are divided by topology divisor (hyperswap / 2).
    Efficient values are derived from mdisk totals minus physical (no divisor).
    """
    div = topology_divisor(system.get("topology"))

    phys_total = parse_gb(system.get("physical_capacity")) / div
    phys_free = parse_gb(system.get("physical_free_capacity")) / div
    phys_used = max(0.0, phys_total - phys_free)

    phys_cap_raw = parse_gb(system.get("physical_capacity"))
    phys_free_raw = parse_gb(system.get("physical_free_capacity"))
    mdisk_total = parse_gb(system.get("total_mdisk_capacity"))
    mdisk_free = parse_gb(system.get("total_free_space"))

    eff_total = max(0.0, mdisk_total - phys_cap_raw)
    eff_free = max(0.0, mdisk_free - phys_free_raw)
    eff_used = max(0.0, eff_total - eff_free)

    return {
        "phys_total_gb": phys_total,
        "phys_free_gb": phys_free,
        "phys_used_gb": phys_used,
        "eff_total_gb": eff_total,
        "eff_free_gb": eff_free,
        "eff_used_gb": eff_used,
    }


def aggregate_ibm_storage_capacities(
    systems: list[dict],
    parse_gb: Callable[[str | None], float],
) -> dict[str, float]:
    """Aggregate physical and efficient capacities across all systems."""
    phys_total_gb = 0.0
    phys_free_gb = 0.0
    eff_total_gb = 0.0
    eff_free_gb = 0.0

    for system in systems:
        caps = compute_system_capacities_gb(system, parse_gb)
        phys_total_gb += caps["phys_total_gb"]
        phys_free_gb += caps["phys_free_gb"]
        eff_total_gb += caps["eff_total_gb"]
        eff_free_gb += caps["eff_free_gb"]

    phys_used_gb = max(0.0, phys_total_gb - phys_free_gb)
    eff_used_gb = max(0.0, eff_total_gb - eff_free_gb)

    utilization_pct = (phys_used_gb / phys_total_gb * 100.0) if phys_total_gb > 0 else 0.0

    return {
        "phys_total_gb": phys_total_gb,
        "phys_used_gb": phys_used_gb,
        "phys_free_gb": phys_free_gb,
        "eff_total_gb": eff_total_gb,
        "eff_used_gb": eff_used_gb,
        "eff_free_gb": eff_free_gb,
        "utilization_pct": utilization_pct,
    }
