"""Tests for sellable constraint visualization helpers."""
from __future__ import annotations

from src.components.sellable_constraint_viz import (
    constraint_breakdown_text,
    count_constraint_breakdown,
    fmt_tl_for_card,
)


def test_fmt_tl_for_card_hides_when_constrained_zero():
    short, full = fmt_tl_for_card(211_200.0, constrained=0.0)
    assert short == "—"
    assert "sıfır" in full.lower() or "TL" in full


def test_fmt_tl_for_card_shows_when_constrained_positive():
    short, _ = fmt_tl_for_card(28_300.0, constrained=124.0)
    assert short != "—"
    assert "TL" in short


def test_constraint_breakdown_counts():
    panels = [
        {"constraint_reason": "compute_bottleneck", "resource_kind": "storage"},
        {"constraint_reason": "ratio_bound", "resource_kind": "ram"},
        {"gate_blocked": True, "constraint_reason": "gate_blocked", "resource_kind": "cpu"},
    ]
    counts = count_constraint_breakdown(panels)
    assert counts["compute_bottleneck"] == 1
    assert counts["ratio_bound"] == 1
    assert counts["gate_blocked"] == 1
    text = constraint_breakdown_text(panels)
    assert text is not None
    assert "compute darboğazı" in text
