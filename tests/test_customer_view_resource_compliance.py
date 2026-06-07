"""Customer View resource compliance UI helpers."""
from __future__ import annotations

from src.components.resource_compliance_panel import (
    build_resource_compliance_table,
    filter_compliance_rows,
)
from src.components.sold_vs_used_panel import build_compliance_stack


def _payload() -> dict:
    return {
        "scope": "virtualization",
        "rows": [
            {
                "category_code": "virt_classic_cpu",
                "category_label": "Klasik Mimari (KM) — CPU",
                "gui_tab_binding": "virtualization.classic",
                "resource_unit": "vCPU",
                "entitled_qty": 0,
                "used_qty": 42,
                "overage_qty": 42,
                "overage_loss_tl": 2100.0,
                "status": "unsold_usage",
            },
            {
                "category_code": "virt_hyperconverged_cpu",
                "category_label": "Hyperconverged Mimari — CPU",
                "gui_tab_binding": "virtualization.hyperconverged",
                "resource_unit": "vCPU",
                "entitled_qty": 18,
                "used_qty": 550,
                "overage_qty": 532,
                "overage_loss_tl": 56163.24,
                "status": "over",
            },
        ],
        "summary": {
            "total_overage_loss_tl": 58263.24,
            "has_overuse": True,
            "overuse_status": "overuse",
        },
    }


def test_filter_compliance_rows_by_tab():
    classic = filter_compliance_rows(_payload(), "virtualization.classic")
    assert len(classic) == 1
    assert classic[0]["category_code"] == "virt_classic_cpu"


def test_build_resource_compliance_table_renders():
    panel = build_resource_compliance_table(_payload(), currency="TL")
    assert panel is not None
    children = getattr(panel, "children", None) or []
    assert len(children) >= 2


def test_build_compliance_stack_for_classic_tab():
    stack = build_compliance_stack(_payload(), "virtualization.classic")
    assert stack is not None
