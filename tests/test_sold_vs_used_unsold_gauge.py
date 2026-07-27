"""A "used / sold" ratio has no value when nothing was sold.

The card divides used by sold. For a row flagged UNSOLD USAGE the denominator is
zero, so efficiency_pct comes back None and the gauge rendered a literal 0% —
next to an OVER-UTILIZED badge and a 74-unit overage. "0%" reads as "barely
used"; the truth is the opposite, and the ratio is undefined rather than low.
"""
from __future__ import annotations

from src.components.sold_vs_used_panel import _one_row_card

_UNSOLD = {
    "category_label": "RHEL Lisans",
    "category_code": "license_redhat",
    "resource_unit": "Adet",
    "entitled_qty": 0,
    "used_qty": 74,
    "detected": 74,
    "overage_qty": 74,
    "efficiency_pct": None,
    "status": "unsold_usage",
}

_NORMAL = {
    "category_label": "Windows Lisans",
    "resource_unit": "per VM",
    "entitled_qty": 10,
    "used_qty": 15,
    "overage_qty": 5,
    "efficiency_pct": 150.0,
    "status": "over",
}


def _text(c) -> str:
    return str(c)


def test_unsold_row_does_not_render_the_ratio_gauge_at_all():
    """Asserted on the gauge's own title rather than the string "0%", which also
    occurs in CSS widths."""
    assert "Used / sold" not in _text(_one_row_card(_UNSOLD))


def test_unsold_row_says_plainly_that_nothing_was_sold():
    rendered = _text(_one_row_card(_UNSOLD)).lower()
    assert "satılmamış" in rendered or "hiç satılmamış" in rendered


def test_unsold_row_still_shows_the_quantity_at_stake():
    assert "74" in _text(_one_row_card(_UNSOLD))


def test_a_row_with_a_real_ratio_keeps_its_gauge():
    rendered = _text(_one_row_card(_NORMAL))
    assert "Used / sold" in rendered
    assert "150" in rendered
