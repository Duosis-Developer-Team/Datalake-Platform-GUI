"""dc_sales_potential_v2 — sellable ceiling resource blocks.

Ceiling now comes from gui_crm_threshold_config (webui-db) instead of a
hard-coded constant. The pure helper `_resource_view` accepts the ceiling.

Cross-check: customer-api ``SellableService`` uses the same raw headroom
formula ``apply_threshold`` from ``shared/sellable/computation.py`` for
``sellable_raw`` before ratio-constraining — keep the two pipelines aligned.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_GUI_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _GUI_ROOT not in sys.path:
    sys.path.append(_GUI_ROOT)

from app.services.dc_sales_potential_v2 import (
    DEFAULT_SELLABLE_LIMIT_PCT,
    _implied_price_from_sales,
    _resource_view,
)
from shared.sellable.computation import apply_threshold


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


def test_resource_view_remaining_qty_matches_apply_threshold():
    """Parity guard between legacy v2 math and SellableService raw headroom."""
    for total, sold, ceiling in (
        (100.0, 50.0, 80.0),
        (0.0, 5.0, 80.0),
        (256.0, 200.0, 75.0),
    ):
        view = _resource_view(total, sold, unit_price=1.0, ceiling_pct=ceiling)
        want = apply_threshold(total, sold, ceiling)
        assert abs(view["remaining_sellable_qty"] - want) < 1e-3


def test_implied_price_from_sales_virt_cpu_and_ram():
    by_cat = {
        ("virt_classic", "vCPU"): {
            "category_code": "virt_classic",
            "sold_qty": 10.0,
            "sold_amount_tl": 5000.0,
        },
        ("virt_classic", "GB"): {
            "category_code": "virt_classic",
            "sold_qty": 100.0,
            "sold_amount_tl": 2000.0,
        },
    }
    assert _implied_price_from_sales(by_cat, "cpu") == 500.0
    assert _implied_price_from_sales(by_cat, "ram") == 20.0


def test_implied_price_from_sales_ignores_non_virt():
    by_cat = {
        ("other_cat", "vCPU"): {
            "category_code": "other_cat",
            "sold_qty": 100.0,
            "sold_amount_tl": 99999.0,
        },
    }
    assert _implied_price_from_sales(by_cat, "cpu") == 0.0


def test_implied_price_from_sales_empty():
    assert _implied_price_from_sales({}, "cpu") == 0.0
