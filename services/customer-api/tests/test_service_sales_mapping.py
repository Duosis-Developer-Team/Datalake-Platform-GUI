"""Tests for service sales line aggregation."""
from __future__ import annotations

from app.utils.service_sales_mapping import map_service_sales_lines


def test_map_service_sales_lines_aggregates_by_category():
    lines = [
        {"productid": "p1", "amount_tl": 100.0},
        {"productid": "p2", "amount_tl": 50.0},
    ]
    product_mapping = {
        "p1": {"category_code": "virt", "category_label": "Virtualization"},
        "p2": {"category_code": "virt", "category_label": "Virtualization"},
    }
    out = map_service_sales_lines(lines, product_mapping)
    assert len(out) == 1
    assert out[0]["service_code"] == "virt"
    assert out[0]["amount_tl"] == 150.0
