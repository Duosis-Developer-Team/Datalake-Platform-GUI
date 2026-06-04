"""IBM Power sellable KPI constraint hints for the DC view."""

from __future__ import annotations

_POWER_FAMILIES = frozenset({"virt_power", "virt_power_hana"})


def power_sellable_constraint_hints(
    families: list[str] | str,
    *,
    cpu_raw: float,
    cpu_constrained: float,
    ram_raw: float,
    ram_total: float,
    ram_allocated: float,
    ram_threshold_pct: float = 80.0,
) -> list[str]:
    """Return short English messages explaining why Power sellable values are zero.

    Does not replace ratio-bound badges; those are computed separately from raw vs
    constrained deltas per resource kind.
    """
    if isinstance(families, str):
        families = [families]
    if not _POWER_FAMILIES.intersection(families):
        return []

    hints: list[str] = []
    operational_free = max(ram_total - ram_allocated, 0.0)

    if ram_raw < 1e-6 and ram_total > 1e-6:
        if operational_free > 1e-6:
            hints.append(
                f"RAM threshold-bound: {operational_free:,.0f} GB free operationally, "
                f"0 GB sellable at {ram_threshold_pct:.0f}% ceiling"
            )
        else:
            hints.append(
                f"RAM threshold-bound: no headroom under {ram_threshold_pct:.0f}% sellable ceiling"
            )

    ram_gb_per_core = 32.0 if "virt_power_hana" in families else 16.0
    if cpu_raw > 1e-6 and cpu_constrained < 1e-6 and ram_raw < 1e-6:
        hints.append(f"CPU blocked by RAM ratio (1 Core : {ram_gb_per_core:.0f} GB)")

    return hints
