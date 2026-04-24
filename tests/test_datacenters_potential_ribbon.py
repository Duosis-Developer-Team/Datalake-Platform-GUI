"""Datacenters list: sellable ribbon helper."""
from __future__ import annotations

from src.pages.datacenters import _dc_sellable_ribbon


def test_sellable_ribbon_empty_without_payload():
    el = _dc_sellable_ribbon(None)
    assert el is not None


def test_sellable_ribbon_renders_with_v2():
    el = _dc_sellable_ribbon(
        {
            "general_remaining_pct": 42.5,
            "potential_revenue_tl": 12000.0,
            "per_resource": {
                "cpu": {"remaining_sellable_pct": 50.0},
                "ram": {"remaining_sellable_pct": 42.5},
            },
        }
    )
    # Mantine Tooltip wraps content; smoke: component tree exists
    assert el is not None
