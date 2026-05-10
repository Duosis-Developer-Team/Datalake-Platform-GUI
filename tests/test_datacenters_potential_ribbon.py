"""Datacenters list: Potential Sales (Virtualization) ribbon helper."""
from __future__ import annotations

from src.pages.datacenters import _dc_sellable_ribbon, _fmt_tl_short


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
    short, _full = _fmt_tl_short(12000.0)
    texts = _collect_text_nodes(el)
    assert short in texts, f"expected formatted TL headline {short!r} in ribbon texts {texts}"
    assert "Potential Sales (Virtualization)" in texts
