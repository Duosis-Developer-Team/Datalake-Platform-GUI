"""Temporary static aggregate energy display overrides for the WebUI."""

from __future__ import annotations

STATIC_TOTAL_ENERGY_KW: float = 780.0


def resolve_static_total_energy_kw(env_value: str | float | int | None) -> float | None:
    """Return target kW when override is enabled; None when disabled (0/empty)."""
    if env_value is None:
        return STATIC_TOTAL_ENERGY_KW
    try:
        value = float(env_value)
    except (TypeError, ValueError):
        return STATIC_TOTAL_ENERGY_KW
    if value <= 0:
        return None
    return value


def scale_energy_breakdown(
    ibm_kw: float,
    vcenter_kw: float,
    target_total_kw: float,
) -> tuple[float, float]:
    """Scale IBM/vCenter breakdown to target total while preserving ratio."""
    live_total = float(ibm_kw or 0) + float(vcenter_kw or 0)
    if live_total <= 0:
        half = round(target_total_kw / 2.0, 2)
        return half, round(target_total_kw - half, 2)
    ratio = target_total_kw / live_total
    scaled_ibm = round(float(ibm_kw or 0) * ratio, 2)
    scaled_vcenter = round(float(vcenter_kw or 0) * ratio, 2)
    # Fix rounding drift so components sum exactly to target.
    drift = round(target_total_kw - (scaled_ibm + scaled_vcenter), 2)
    if drift:
        scaled_vcenter = round(scaled_vcenter + drift, 2)
    return scaled_ibm, scaled_vcenter


def apply_static_aggregate_energy(
    overview: dict,
    energy_breakdown: dict,
    *,
    target_kw: float | None,
) -> None:
    """Override aggregate total kW and scale breakdown in place; per-DC stats untouched."""
    if target_kw is None:
        return
    overview["total_energy_kw"] = round(float(target_kw), 2)
    ibm_kw, vcenter_kw = scale_energy_breakdown(
        float(energy_breakdown.get("ibm_kw", 0) or 0),
        float(energy_breakdown.get("vcenter_kw", 0) or 0),
        float(target_kw),
    )
    energy_breakdown["ibm_kw"] = ibm_kw
    energy_breakdown["vcenter_kw"] = vcenter_kw
