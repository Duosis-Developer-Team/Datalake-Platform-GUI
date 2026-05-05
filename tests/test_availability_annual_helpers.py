"""Unit tests for annual availability page helpers (pure functions)."""

from __future__ import annotations

from src.pages.availability_annual import (
    _bar_color_for_pct,
    _overall_availability_pct,
    _truncate_label,
)


def test_overall_availability_pct():
    assert _overall_availability_pct(None) == 0.0
    assert _overall_availability_pct({}) == 0.0
    assert _overall_availability_pct({"availability_pct": 99.5}) == 99.5
    assert _overall_availability_pct({"availability_pct": "98.25"}) == 98.25


def test_bar_color_thresholds():
    assert _bar_color_for_pct(100.0) == "#12B76A"
    assert _bar_color_for_pct(99.999) == "#12B76A"
    assert _bar_color_for_pct(99.998) == "#F79009"
    assert _bar_color_for_pct(99.9) == "#F79009"
    assert _bar_color_for_pct(50.0) == "#F04438"


def test_truncate_label():
    assert _truncate_label("", 10) == ""
    assert _truncate_label("short", 10) == "short"
    assert _truncate_label("abcdefghij", 5) == "abcd…"
