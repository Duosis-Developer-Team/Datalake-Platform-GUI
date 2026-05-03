"""dc_sales_potential_v2 — sellable ceiling resource blocks.

Ceiling now comes from gui_crm_threshold_config (webui-db) instead of a
hard-coded constant. The pure helper `_resource_view` accepts the ceiling.
"""
from __future__ import annotations

from app.services.dc_sales_potential_v2 import (
    DEFAULT_SELLABLE_LIMIT_PCT,
    _resource_view,
)


def test_resource_view_remaining_hits_zero_when_sold_exceeds_ceiling():
    total = 100.0
    sold = 90.0
    b = _resource_view(total, sold, unit_price=10.0, ceiling_pct=80.0)
    assert b["remaining_sellable_pct"] == 0.0
    assert b["sold_pct_of_ceiling"] == 90.0
    assert b["ceiling_pct"] == 80.0


def test_resource_view_default_ceiling_value():
    assert DEFAULT_SELLABLE_LIMIT_PCT == 80.0


def test_resource_view_no_capacity_but_sold():
    b = _resource_view(0.0, 5.0, unit_price=1.0, ceiling_pct=80.0)
    assert b["remaining_sellable_pct"] == 0.0
    assert b["sold_pct_of_ceiling"] == 100.0


def test_resource_view_uses_provided_ceiling():
    b = _resource_view(100.0, 50.0, unit_price=2.0, ceiling_pct=70.0)
    # 70 - 50 = 20% remaining
    assert b["remaining_sellable_pct"] == 20.0
    assert b["remaining_sellable_qty"] == 20.0
    assert b["potential_revenue_tl"] == 40.0
