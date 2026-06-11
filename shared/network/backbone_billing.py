"""Backbone billing helpers aligned with interface_calculation.py reference."""

from __future__ import annotations

BPS_PER_MBIT = 1_000_000


def p95_bps_to_mbit(p95_total_bps: float) -> float:
    """Convert P95 total bps to Mbit/s (Mbps) — same as reference script / 1_000_000."""
    return float(p95_total_bps or 0) / BPS_PER_MBIT


def estimate_backbone_cost_tl(p95_total_bps: float, unit_price_tl_per_mbit: float) -> float:
    """estimated_cost_tl = (p95_total_bps / 1_000_000) * unit_price_tl_per_mbit."""
    return round(p95_bps_to_mbit(p95_total_bps) * float(unit_price_tl_per_mbit or 0), 2)
