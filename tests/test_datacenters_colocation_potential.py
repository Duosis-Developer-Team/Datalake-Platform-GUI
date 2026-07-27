"""Colocation potential renders as its own line, never folded into the
virtualization min-max range."""
from src.pages.datacenters import _colocation_sales_line, _dc_sellable_ribbon


def _texts(component):
    out = []
    stack = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            out.append(node)
            continue
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
        label = getattr(node, "label", None)
        if isinstance(label, str):
            out.append(label)
    return out


def test_colocation_line_renders_single_value_not_a_range():
    texts = _texts(_colocation_sales_line(16_167_802.0))

    assert "Potential Sales (Colocation)" in texts
    assert "16.17 Milyon TL" in texts
    assert not any("–" in t and "Milyon" in t for t in texts)


def test_colocation_line_absent_when_no_value():
    assert _colocation_sales_line(None) is None
    assert _colocation_sales_line(0.0) is None


def test_colocation_line_shows_loading_state():
    texts = _texts(_colocation_sales_line(None, loading=True))

    assert "Potential Sales (Colocation)" in texts
    assert "…" in texts


def test_virtualization_ribbon_label_unchanged():
    texts = _texts(_dc_sellable_ribbon(
        1_000_000.0, virt_tl_min=574_800.0, virt_tl_max=1_910_000.0,
        total_portfolio_tl=10_000_000.0,
    ))

    assert "Potential Sales (Virtualization)" in texts
    assert "Potential Sales (Colocation)" not in texts
