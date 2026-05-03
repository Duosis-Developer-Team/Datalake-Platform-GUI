"""Dash layout smoke tests for ``crm_sellable_potential``."""
from __future__ import annotations

from unittest.mock import patch

from dash import html

from src.pages import crm_sellable_potential


def _fake_summary() -> dict:
    return {
        "dc_code": "*",
        "total_potential_tl": 5580.0,
        "constrained_loss_tl": 1900.0,
        "ytd_sales_tl": 250000.0,
        "unmapped_product_count": 2,
        "families": [
            {
                "family": "virt_hyperconverged",
                "label": "Hyperconverged",
                "dc_code": "*",
                "total_potential_tl": 5580.0,
                "constrained_loss_tl": 1900.0,
                "panels": [
                    {
                        "panel_key": "virt_hyperconverged_cpu",
                        "label": "HC CPU",
                        "family": "virt_hyperconverged",
                        "resource_kind": "cpu",
                        "display_unit": "vCPU",
                        "total": 10.0,
                        "allocated": 4.0,
                        "sellable_raw": 4.0,
                        "sellable_constrained": 3.0,
                        "unit_price_tl": 1500.0,
                        "potential_tl": 4500.0,
                        "ratio_bound": True,
                    },
                    {
                        "panel_key": "virt_hyperconverged_ram",
                        "label": "HC RAM",
                        "family": "virt_hyperconverged",
                        "resource_kind": "ram",
                        "display_unit": "GB",
                        "total": 80.0,
                        "allocated": 40.0,
                        "sellable_raw": 24.0,
                        "sellable_constrained": 24.0,
                        "unit_price_tl": 20.0,
                        "potential_tl": 480.0,
                        "ratio_bound": False,
                    },
                ],
            }
        ],
    }


def test_build_layout_returns_div_with_stores():
    with patch.object(crm_sellable_potential.api, "get_sellable_summary", return_value=_fake_summary()):
        layout = crm_sellable_potential.build_layout()
    assert isinstance(layout, html.Div)
    ids = [c.id for c in layout.children if hasattr(c, "id") and c.id]
    assert "sellable-store-summary" in ids
    assert "sellable-store-panels" in ids


def test_refresh_callback_sorts_panels_by_potential_tl():
    summary = _fake_summary()
    with patch.object(crm_sellable_potential.api, "get_sellable_summary", return_value=summary):
        out_summary, out_panels = crm_sellable_potential._refresh_data("*")
    assert out_summary == summary
    assert out_panels[0]["panel_key"] == "virt_hyperconverged_cpu"


def test_trend_callback_empty_metric_key():
    fig = crm_sellable_potential._trend(None)
    assert fig.layout.annotations[0].text == "Bir metric_key seç"


def test_trend_callback_with_snapshots():
    pts = [
        {"captured_at": "2026-05-01T00:00:00+00:00", "value": 10.0, "unit": "TL"},
        {"captured_at": "2026-05-02T00:00:00+00:00", "value": 12.0, "unit": "TL"},
    ]
    with patch.object(crm_sellable_potential.api, "get_metric_snapshots", return_value=pts):
        fig = crm_sellable_potential._trend("crm.sellable_potential.total_tl")
    assert len(fig.data) == 1
    assert fig.data[0].y == (10.0, 12.0)
