"""Datacenters list: Potential Sales (Virtualization) ribbon helper."""
from __future__ import annotations

from src.pages.datacenters import _dc_sellable_ribbon, _potential_sales_display
from src.utils.format_units import fmt_tl_range


def _collect_text_nodes(node) -> list[str]:
    out: list[str] = []
    if node is None:
        return out
    if isinstance(node, str):
        out.append(node)
        return out
    ch = getattr(node, "children", None)
    if ch is None:
        return out
    if isinstance(ch, (list, tuple)):
        for c in ch:
            out.extend(_collect_text_nodes(c))
    else:
        out.extend(_collect_text_nodes(ch))
    return out


def test_sellable_ribbon_renders_zero_without_error():
    el = _dc_sellable_ribbon(0.0, total_portfolio_tl=0.0)
    assert el is not None


def test_sellable_ribbon_renders_virt_tl_and_label():
    el = _dc_sellable_ribbon(12000.0, total_portfolio_tl=24000.0)
    assert el is not None
    texts = _collect_text_nodes(el)
    assert "Potential Sales (Virtualization)" in texts
    assert "12.0 Bin TL" in texts


def test_sellable_ribbon_renders_range_when_min_max_differ():
    el = _dc_sellable_ribbon(
        1_500_000.0,
        virt_tl_min=1_300_000.0,
        virt_tl_max=1_700_000.0,
        total_portfolio_tl=3_000_000.0,
    )
    texts = _collect_text_nodes(el)
    expected = fmt_tl_range(1_300_000.0, 1_700_000.0)
    assert expected in texts
    assert "–" in expected


def test_potential_sales_display_single_value():
    short, full = _potential_sales_display(175_300.0, 175_300.0)
    assert "175.3 Bin TL" in short
    assert full == "175,300 TL"


def test_potential_sales_display_range():
    short, full = _potential_sales_display(1_500_000.0, 2_100_000.0)
    assert short == fmt_tl_range(1_500_000.0, 2_100_000.0)
    assert full == "1,500,000 – 2,100,000 TL"


def test_potential_sales_display_loading():
    short, full = _potential_sales_display(0.0, 0.0, loading=True)
    assert short == "Hesaplanıyor…"
    assert full == "—"
