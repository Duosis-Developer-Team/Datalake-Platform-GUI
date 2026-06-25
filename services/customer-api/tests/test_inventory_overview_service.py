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
            "category_label": "Klasik Mimari — CPU",
            "resource_unit": "vCPU",
            "source": "yaml",
        },
        "p2": {
            "category_code": "virt_classic_cpu",
            "category_label": "Klasik Mimari — CPU",
            "resource_unit": "vCPU",
            "source": "yaml",
        },
        "u1": {"category_code": None, "source": "unmatched"},
    }
    raw = [
        {
            "productid": "p1",
            "product_name": "KM CPU SKU",
            "entitled_qty": 10,
            "entitled_amount_tl": 100,
            "resource_unit": "vCPU",
        },
        {
            "productid": "p2",
            "product_name": "KM CPU SKU 2",
            "entitled_qty": 5,
            "entitled_amount_tl": 50,
            "resource_unit": "vCPU",
        },
        {"productid": "u1", "entitled_qty": 99, "entitled_amount_tl": 999, "resource_unit": "Adet"},
    ]
    agg = aggregate_entitled_by_panel_key(raw, mapping)
    assert agg["virt_classic_cpu"]["entitled_qty"] == 15.0
    assert agg["virt_classic_cpu"]["entitled_amount_tl"] == 150.0
    assert "KM CPU SKU" in agg["virt_classic_cpu"]["product_names"]


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
        computation_mode="host_based",
    )
    defaults.update(kwargs)
    return PanelResult(**defaults)


def _webui_rows(sql: str):
    if "FROM   gui_panel_definition" in sql:
        return [
            {
                "panel_key": "virt_classic_cpu",
                "label": "Classic CPU",
                "family": "virt_classic",
                "resource_kind": "cpu",
                "display_unit": "vCPU",
            },
            {
                "panel_key": "backup_veeam",
                "label": "Veeam Backup",
                "family": "backup_veeam",
                "resource_kind": "other",
                "display_unit": "Adet",
            },
        ]
    if "gui_crm_service_mapping_seed" in sql:
        return [
            {
                "productid": "p-cpu",
                "category_code": "virt_classic_cpu",
                "category_label": "Klasik Mimari — CPU",
                "resource_unit": "vCPU",
                "source": "yaml",
            },
            {
                "productid": "p-bkp",
                "category_code": "backup_veeam",
                "category_label": "Veeam Cloud Connect Backup",
                "resource_unit": "Adet",
                "source": "yaml",
            },
        ]
    if "FROM   gui_crm_service_pages" in sql:
        return [
            {
                "page_key": "virt_classic_cpu",
                "category_label": "Klasik Mimari — CPU",
                "gui_tab_binding": "virtualization.classic",
                "resource_unit": "vCPU",
            },
            {
                "page_key": "backup_veeam",
                "category_label": "Veeam Cloud Connect Backup",
                "gui_tab_binding": "backup.veeam",
                "resource_unit": "Adet",
            },
        ]
    return []


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
            computation_mode=None,
        ),
    ]
    sellable._count_unmapped_products.return_value = 3

    sales = MagicMock()
    def _run_query(sql, params):
        if "!= ALL" in sql:
            return [{"productid": "x", "product_name": "Unknown SKU", "entitled_qty": 1, "entitled_amount_tl": 100}]
        return [
            {
                "productid": "p-cpu",
                "product_name": "KM CPU",
                "resource_unit": "vCPU",
                "entitled_qty": 30.0,
                "entitled_amount_tl": 45000.0,
            },
            {
                "productid": "p-bkp",
                "product_name": "Veeam SKU",
                "resource_unit": "Adet",
                "entitled_qty": 12.0,
                "entitled_amount_tl": 12000.0,
            },
        ]

    sales._run_query.side_effect = _run_query

    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.side_effect = lambda sql: _webui_rows(sql)

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
    panels = {p["panel_key"]: p for p in payload["panels"]}
    cpu = panels["virt_classic_cpu"]
    assert cpu["crm_sold_qty"] == 30.0
    assert cpu["used_qty"] == 40.0
    assert cpu["sellable_qty"] == 20.0
    assert cpu["free_qty"] == 60.0
    assert cpu["service_label"] == "Klasik Mimari — CPU"
    assert cpu["family_label"] == "Klasik Mimari"
    assert cpu["infra_binding"] == "bound"
    bkp = panels["backup_veeam"]
    assert bkp["status"] == "crm_only"
    assert bkp["service_label"] == "Veeam Cloud Connect Backup"
    assert bkp["infra_binding"] == "crm_only"
