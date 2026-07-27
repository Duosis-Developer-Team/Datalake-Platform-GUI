"""Colocation potential renders as its own line, never folded into the
virtualization min-max range."""
from unittest.mock import patch

from src.pages.datacenters import (
    _colocation_potential,
    _colocation_sales_line,
    _dc_sellable_ribbon,
)


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


def test_colocation_potential_fans_out_per_dc_calls_via_parallel_execute():
    """Per-DC get_colocation calls must be routed through parallel_execute —
    the codebase's existing N-DC fan-out helper (used at dc_view.py's
    batch1/batch2 and datacenters_virt_sellable.py's warm pool) — rather than
    a bare serial loop, so a cold/expired cache doesn't block render for one
    HTTP round trip per DC in sequence."""
    calls: list[list[str]] = []

    def fake_parallel_execute(tasks):
        calls.append(sorted(tasks.keys()))
        return {key: fn() for key, fn in tasks.items()}

    responses = {
        "*": {"aggregate": {"unit_price_tl": 1000.0, "free_u_potential_tl": 5_000_000.0}},
        "DC11": {"aggregate": {"free_u_potential_tl": 2_000_000.0}},
        "DC13": {"aggregate": {"free_u_potential_tl": 3_000_000.0}},
    }

    with patch(
        "src.pages.datacenters.parallel_execute", side_effect=fake_parallel_execute
    ) as mock_parallel_execute, patch(
        "src.pages.datacenters.api.get_colocation", side_effect=lambda code: responses[code]
    ):
        total, by_dc = _colocation_potential(["DC11", "DC13"])

    # Exactly one fan-out call carrying both DC codes — not one call per DC,
    # which would just relabel the same serial loop the fix was meant to end.
    assert mock_parallel_execute.call_count == 1
    assert calls == [["DC11", "DC13"]]
    assert total == 5_000_000.0
    assert by_dc == {"DC11": 2_000_000.0, "DC13": 3_000_000.0}
