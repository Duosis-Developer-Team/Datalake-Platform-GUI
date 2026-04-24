"""dc_sales_potential_v2 — 80%% sellable resource blocks."""
from __future__ import annotations

from app.services.dc_sales_potential_v2 import SELLABLE_LIMIT_PCT, _resource_view


def test_resource_view_remaining_hits_zero_when_sold_exceeds_eighty_pct():
    total = 100.0
    sold = 90.0
    b = _resource_view(total, sold, unit_price=10.0)
    assert b["remaining_sellable_pct"] == max(0.0, SELLABLE_LIMIT_PCT - 90.0)
    assert b["sold_pct_of_ceiling"] == 90.0


def test_resource_view_no_capacity_but_sold():
    b = _resource_view(0.0, 5.0, unit_price=1.0)
    assert b["remaining_sellable_pct"] == 0.0
    assert b["sold_pct_of_ceiling"] == 100.0
