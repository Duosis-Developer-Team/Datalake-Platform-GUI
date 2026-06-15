"""Tests for Virt sellable TL range formatting (Summary parity)."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from src.utils.format_units import fmt_tl, fmt_tl_range
from src.utils.virt_sellable_aggregate import virt_total_potential_range


def test_fmt_tl_range_million_format():
    text = fmt_tl_range(1_500_000.0, 2_100_000.0)
    assert "Milyon TL" in text
    assert "–" in text


def test_fmt_tl_single_point_when_equal():
    assert fmt_tl_range(1_000_000.0, 1_000_000.0) == fmt_tl(1_000_000.0)


def test_virt_total_potential_range_ibm_storage_band():
    panels = [
        {
            "potential_tl": 500_000.0,
            "potential_tl_min": 400_000.0,
            "potential_tl_max": 600_000.0,
        },
        {"potential_tl": 1_000_000.0},
    ]
    total, lo, hi = virt_total_potential_range(panels)
    assert total == pytest.approx(1_500_000.0)
    assert lo == pytest.approx(1_400_000.0)
    assert hi == pytest.approx(1_600_000.0)
    headline = fmt_tl_range(lo, hi)
    assert "Milyon TL" in headline


@pytest.fixture
def dc_view_module():
    """Import dc_view with pandas stubbed (CI/dev env may lack pandas)."""
    if "pandas" not in sys.modules:
        sys.modules["pandas"] = types.ModuleType("pandas")
        sys.modules["pandas"].DataFrame = MagicMock()
    import importlib
    import src.pages.dc_view as dc_view
    return importlib.reload(dc_view)


@patch("src.pages.dc_view.api.get_sellable_by_panel")
def test_inline_kpi_total_potential_shows_range(mock_fetch, dc_view_module):
    mock_fetch.return_value = [
        {
            "resource_kind": "storage",
            "sellable_constrained": 100.0,
            "sellable_raw": 100.0,
            "potential_tl": 500_000.0,
            "potential_tl_min": 400_000.0,
            "potential_tl_max": 600_000.0,
            "sellable_min": 50.0,
            "sellable_max": 150.0,
            "total": 1000.0,
            "allocated": 500.0,
            "display_unit": "GB",
        },
        {
            "resource_kind": "cpu",
            "sellable_constrained": 10.0,
            "potential_tl": 1_000_000.0,
            "display_unit": "vCPU",
        },
    ]
    card = dc_view_module._build_sellable_inline_kpi("DC13", "virt_classic", "Test", color="blue")
    assert card is not None
    rendered = str(card)
    assert "Milyon TL" in rendered
    assert "–" in rendered


@patch("src.pages.dc_view.api.get_virt_sellable_panels")
def test_virt_total_card_uses_fmt_tl_range(mock_fetch, dc_view_module):
    mock_fetch.return_value = [
        {
            "resource_kind": "cpu",
            "sellable_constrained": 1.0,
            "potential_tl": 500_000.0,
            "display_unit": "vCPU",
        },
        {
            "resource_kind": "storage",
            "sellable_constrained": 1.0,
            "potential_tl": 1_000_000.0,
            "potential_tl_min": 800_000.0,
            "potential_tl_max": 1_200_000.0,
            "sellable_min": 1.0,
            "sellable_max": 2.0,
            "display_unit": "GB",
        },
    ]
    children = dc_view_module._build_virt_total_sellable_children("DC13", ["KM1"], ["HC1"])
    text = str(children)
    assert "Milyon TL" in text
    assert "Total Potential" in text
