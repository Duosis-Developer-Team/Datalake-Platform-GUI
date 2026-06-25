"""Dash layout smoke tests for ``crm_inventory_overview``."""
from __future__ import annotations

from unittest.mock import patch

from dash import html

from src.pages import crm_inventory_overview


def _fake_payload() -> dict:
    return {
        "dc_code": "*",
        "summary": {
            "infra_panel_count": 2,
            "panel_count": 3,
            "crm_only_count": 1,
            "crm_entitled_tl": 18000.0,
            "unmapped_product_count": 2,
            "unmapped_entitled_count": 1,
            "overage_panel_count": 1,
            "unsold_usage_count": 0,
            "total_potential_tl": 4980.0,
            "note": "Capacity units are heterogeneous across panels.",
        },
        "families": [
            {
                "family": "virt_hyperconverged",
                "label": "Hyperconverged",
                "panels": [
                    {
                        "panel_key": "virt_hyperconverged_cpu",
                        "label": "HC CPU",
                        "family": "virt_hyperconverged",
                        "resource_kind": "cpu",
                        "display_unit": "vCPU",
                        "total": 10.0,
                        "crm_sold_qty": 8.0,
                        "used_qty": 6.0,
                        "sellable_qty": 3.0,
                        "potential_tl": 4500.0,
                        "has_infra_source": True,
                        "status": "ok",
                    }
                ],
            }
        ],
        "panels": [
            {
                "panel_key": "virt_hyperconverged_cpu",
                "label": "HC CPU",
                "family": "virt_hyperconverged",
                "resource_kind": "cpu",
                "display_unit": "vCPU",
                "total": 10.0,
                "crm_sold_qty": 8.0,
                "used_qty": 6.0,
                "sellable_qty": 3.0,
                "potential_tl": 4500.0,
                "has_infra_source": True,
                "status": "ok",
                "delta_used_vs_crm": -2.0,
            },
            {
                "panel_key": "backup_veeam",
                "label": "Veeam Backup",
                "family": "backup_veeam",
                "resource_kind": "other",
                "display_unit": "Adet",
                "total": None,
                "crm_sold_qty": 25.0,
                "crm_sold_tl": 5000.0,
                "used_qty": None,
                "sellable_qty": None,
                "potential_tl": 0.0,
                "has_infra_source": False,
                "status": "crm_only",
            },
        ],
        "crm_only_panels": [
            {
                "panel_key": "backup_veeam",
                "label": "Veeam Backup",
                "crm_sold_qty": 25.0,
                "crm_sold_tl": 5000.0,
                "display_unit": "Adet",
                "status": "crm_only",
            }
        ],
        "unmapped_products": [
            {"productid": "x", "product_name": "Legacy SKU", "entitled_qty": 3.0}
        ],
    }


def test_build_layout_returns_div_with_store():
    with patch.object(crm_inventory_overview.api, "get_crm_inventory_overview", return_value=_fake_payload()):
        layout = crm_inventory_overview.build_layout()
    assert isinstance(layout, html.Div)
    store = next(c for c in layout.children if getattr(c, "id", None) == "crm-inventory-store")
    assert store.data["summary"]["panel_count"] == 3


def test_build_layout_shell_has_loading_root():
    shell = crm_inventory_overview.build_layout_shell()
    assert isinstance(shell, html.Div)
    ids = [c.id for c in shell.children if hasattr(c, "id") and c.id]
    assert "crm-inventory-visible-sections" in ids
