"""Unit tests for annual availability page helpers (pure functions)."""

from __future__ import annotations

from src.pages.availability_annual import (
    _bar_color_for_pct,
    _overall_availability_pct,
    _resolve_panel_state,
    _truncate_label,
)


def test_resolve_panel_state():
    assert _resolve_panel_state("error", None, 0) == "fetch_failed"
    assert _resolve_panel_state("ok", {"availability_pct": 99.0}, 1) == "ok"
    assert _resolve_panel_state("ok", None, 2) == "no_match"


def test_overall_availability_pct():
    assert _overall_availability_pct(None) is None
    assert _overall_availability_pct({}) is None
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
