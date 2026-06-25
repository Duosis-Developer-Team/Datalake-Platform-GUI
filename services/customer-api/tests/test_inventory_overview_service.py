"""Unit tests for InventoryOverviewService."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.inventory_overview_service import InventoryOverviewService
from app.utils.usage_comparison import (
    aggregate_entitled_by_panel_key,
    normalize_entitled_qty,
    panel_inventory_status,
)
from shared.sellable.models import PanelResult


def test_normalize_entitled_qty_tb_to_gb():
    assert normalize_entitled_qty(2.0, "TB", "GB") == 2048.0


def test_aggregate_entitled_by_panel_key_maps_products():
    mapping = {
        "p1": {
            "category_code": "virt_classic_cpu",
            "category_label": "Classic CPU",
            "resource_unit": "vCPU",
            "source": "yaml",
        },
        "p2": {
            "category_code": "virt_classic_cpu",
            "category_label": "Classic CPU",
            "resource_unit": "vCPU",
            "source": "yaml",
        },
        "u1": {"category_code": None, "source": "unmatched"},
    }
    raw = [
        {"productid": "p1", "entitled_qty": 10, "entitled_amount_tl": 100, "resource_unit": "vCPU"},
        {"productid": "p2", "entitled_qty": 5, "entitled_amount_tl": 50, "resource_unit": "vCPU"},
        {"productid": "u1", "entitled_qty": 99, "entitled_amount_tl": 999, "resource_unit": "Adet"},
    ]
    agg = aggregate_entitled_by_panel_key(raw, mapping)
    assert agg["virt_classic_cpu"]["entitled_qty"] == 15.0
    assert agg["virt_classic_cpu"]["entitled_amount_tl"] == 150.0
    assert "u1" not in str(agg)


def test_panel_inventory_status_cases():
    assert panel_inventory_status(crm_sold_qty=0, used_qty=5, has_infra_source=True) == "unsold_usage"
    assert panel_inventory_status(crm_sold_qty=10, used_qty=0, has_infra_source=False) == "crm_only"
    assert panel_inventory_status(crm_sold_qty=10, used_qty=15, has_infra_source=True) == "over"


def _panel(**kwargs) -> PanelResult:
    defaults = dict(
        panel_key="virt_classic_cpu",
        label="Classic CPU",
        family="virt_classic",
        resource_kind="cpu",
        display_unit="vCPU",
        total=100.0,
        allocated=40.0,
        sellable_constrained=20.0,
        potential_tl=30000.0,
        has_infra_source=True,
        has_price=True,
    )
    defaults.update(kwargs)
    return PanelResult(**defaults)


@pytest.fixture
def inventory_svc():
    sellable = MagicMock()
    sellable.is_available = True
    sellable.compute_all_panels.return_value = [
        _panel(),
        _panel(
            panel_key="backup_veeam",
            label="Veeam Backup",
            family="backup_veeam",
            resource_kind="other",
            display_unit="Adet",
            total=0,
            allocated=0,
            sellable_constrained=0,
            potential_tl=0,
            has_infra_source=False,
            has_price=True,
        ),
    ]
    sellable._count_unmapped_products.return_value = 3

    sales = MagicMock()
    sales._run_query.side_effect = lambda sql, params: (
        [
            {
                "productid": "p-cpu",
                "product_name": "Classic CPU",
                "resource_unit": "vCPU",
                "entitled_qty": 30.0,
                "entitled_amount_tl": 45000.0,
            },
            {
                "productid": "p-bkp",
                "product_name": "Veeam",
                "resource_unit": "Adet",
                "entitled_qty": 12.0,
                "entitled_amount_tl": 12000.0,
            },
        ]
        if "GLOBAL" in sql or "statecode IN (0, 1, 3, 4)" in sql and "customerid" not in sql
        else [{"productid": "x", "product_name": "Unknown SKU", "entitled_qty": 1, "entitled_amount_tl": 100}]
    )

    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.return_value = [
        {
            "productid": "p-cpu",
            "category_code": "virt_classic_cpu",
            "category_label": "Classic CPU",
            "resource_unit": "vCPU",
            "source": "yaml",
        },
        {
            "productid": "p-bkp",
            "category_code": "backup_veeam",
            "category_label": "Veeam Backup",
            "resource_unit": "Adet",
            "source": "yaml",
        },
    ]

    config = MagicMock()
    config.get_calc_dict.return_value = {
        "efficiency.under_pct": 80.0,
        "efficiency.over_pct": 110.0,
    }

    return InventoryOverviewService(
        sellable=sellable,
        sales=sales,
        webui=webui,
        config=config,
        crm_redis=None,
    )


def test_compute_inventory_overview_merges_panels(inventory_svc):
    payload = inventory_svc.compute_inventory_overview("*")
    assert payload["summary"]["infra_panel_count"] == 1
    assert payload["summary"]["crm_only_count"] == 1
    assert payload["summary"]["unmapped_product_count"] == 3
    panels = {p["panel_key"]: p for p in payload["panels"]}
    assert panels["virt_classic_cpu"]["crm_sold_qty"] == 30.0
    assert panels["virt_classic_cpu"]["used_qty"] == 40.0
    assert panels["virt_classic_cpu"]["sellable_qty"] == 20.0
    assert panels["backup_veeam"]["status"] == "crm_only"
    assert panels["backup_veeam"]["total"] is None
