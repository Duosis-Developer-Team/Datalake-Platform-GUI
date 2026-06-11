"""Summary tab layout — Combined Infrastructure first, no legacy CRM accordion."""
from __future__ import annotations

from unittest.mock import patch

from src.pages.dc_view import _build_summary_tab


def _sample_dc_data():
    return {
        "meta": {"name": "DC13", "location": "Istanbul"},
        "classic": {"hosts": 10, "cpu_cap": 100, "mem_cap": 500, "stor_cap": 50},
        "hyperconv": {"hosts": 2, "cpu_cap": 20, "mem_cap": 100},
        "power": {"hosts": 1, "lpar_count": 5},
        "intel": {"vms": 100},
        "energy": {},
    }


def _sample_sellable():
    return {
        "total_potential_tl_min": 1_000_000,
        "total_potential_tl_max": 2_000_000,
        "constrained_loss_tl": 100_000,
        "mapped_panel_count": 4,
        "unmapped_product_count": 0,
        "computation_modes": {"virt_classic": "host_based"},
        "families": [],
    }


@patch("src.pages.dc_summary_sellable.collect_virt_sellable_panels", return_value=[])
def test_summary_tab_order_combined_infrastructure_first(_mock_panels):
    tab = _build_summary_tab(_sample_dc_data(), {"preset": "7d"}, dc_id="DC13", sellable_summary=_sample_sellable())
    stack = tab
    children = stack.children
    first_card = children[0]
    assert "Combined Infrastructure" in str(first_card)


@patch("src.pages.dc_summary_sellable.collect_virt_sellable_panels", return_value=[])
def test_summary_tab_excludes_legacy_sections(_mock_panels):
    tab = _build_summary_tab(_sample_dc_data(), {"preset": "7d"}, dc_id="DC13", sellable_summary=_sample_sellable())
    rendered = str(tab)
    assert "Infrastructure Capacity" not in rendered
    assert "Diğer CRM Kategorileri" not in rendered
    assert "Capacity Detail" not in rendered
    assert "Resource Utilization" not in rendered


def test_summary_includes_sellable_executive():
    with patch("src.pages.dc_summary_sellable.collect_virt_sellable_panels", return_value=[]):
        tab = _build_summary_tab(
            _sample_dc_data(), {"preset": "7d"}, dc_id="DC13", sellable_summary=_sample_sellable()
        )
    assert "Sellable Executive Summary" in str(tab)
    assert "Sanallaştırma — Compute" in str(tab) or "Sanallaştırma compute sellable" in str(tab)
