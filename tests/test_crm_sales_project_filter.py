#!/usr/bin/env python3
"""Tests for project (PRJ-*) scoping of Customer View CRM sales data."""
from __future__ import annotations

from src.utils.crm_sales_project_filter import (
    ALL_PROJECTS,
    filter_by_project,
    project_select_options,
    recompute_summary_for_project,
)

_ACTIVE_ORDERS = [
    {"reference_number": "PRJ-01-A", "order_total": 100.0},
    {"reference_number": "PRJ-02-B", "order_total": 250.0},
]
_ACTIVE_ITEMS = [
    {"reference_number": "PRJ-01-A", "line_total": 60.0},
    {"reference_number": "PRJ-01-A", "line_total": 40.0},
    {"reference_number": "PRJ-02-B", "line_total": 250.0},
]
_REALIZED = [
    {"reference_number": "PRJ-01-A", "line_total": 500.0, "date": "2026-03-01 00:00:00+00"},
    {"reference_number": "PRJ-01-A", "line_total": 300.0, "date": "2025-11-01 00:00:00+00"},
    {"reference_number": "PRJ-02-B", "line_total": 900.0, "date": "2026-01-05 00:00:00+00"},
]


def test_options_are_sorted_with_all_first():
    opts = project_select_options(_ACTIVE_ORDERS, _ACTIVE_ITEMS, _REALIZED)
    assert opts[0] == {"label": "All projects", "value": ALL_PROJECTS}
    assert [o["value"] for o in opts[1:]] == ["PRJ-01-A", "PRJ-02-B"]


def test_options_dedupe_and_ignore_blanks():
    opts = project_select_options([{"reference_number": ""}, {"reference_number": "PRJ-01-A"}], None)
    assert [o["value"] for o in opts] == [ALL_PROJECTS, "PRJ-01-A"]


def test_filter_all_returns_everything():
    assert filter_by_project(_REALIZED, ALL_PROJECTS) == _REALIZED
    assert filter_by_project(_REALIZED, None) == _REALIZED
    assert filter_by_project(_REALIZED, "") == _REALIZED


def test_filter_specific_project():
    got = filter_by_project(_REALIZED, "PRJ-01-A")
    assert len(got) == 2
    assert {r["line_total"] for r in got} == {500.0, 300.0}


def test_recompute_all_returns_base_unchanged():
    base = {"ytd_revenue_total": 123.0, "currency": "TL"}
    out = recompute_summary_for_project(
        base, active_orders=_ACTIVE_ORDERS, sales_items=_REALIZED,
        project=ALL_PROJECTS, current_year=2026,
    )
    assert out == base


def test_recompute_scopes_to_single_project():
    base = {"currency": "TL", "ytd_revenue_total": 9999, "active_order_value": 9999}
    out = recompute_summary_for_project(
        base, active_orders=_ACTIVE_ORDERS, sales_items=_REALIZED,
        project="PRJ-01-A", current_year=2026,
    )
    assert out["lifetime_revenue_total"] == 800.0   # 500 + 300
    assert out["ytd_revenue_total"] == 500.0        # only the 2026 row
    assert out["lifetime_order_count"] == 1
    assert out["invoice_count"] == 1                # 1 project fulfilled in 2026
    assert out["active_order_count"] == 1
    assert out["active_order_value"] == 100.0
    assert out["currency"] == "TL"                  # base fields preserved


def test_recompute_project_with_no_ytd_realized():
    base = {"currency": "TL"}
    # PRJ-02-B realized only in 2026 (900) -> ytd 900; but test a year with none
    out = recompute_summary_for_project(
        base, active_orders=_ACTIVE_ORDERS, sales_items=_REALIZED,
        project="PRJ-02-B", current_year=2027,
    )
    assert out["ytd_revenue_total"] == 0.0
    assert out["invoice_count"] == 0
    assert out["lifetime_revenue_total"] == 900.0
    assert out["active_order_value"] == 250.0
