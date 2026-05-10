"""Tests for virt sellable panel normalization and aggregation helpers."""
from __future__ import annotations

from src.utils.virt_sellable_aggregate import (
    aggregate_virt_sellable_panels,
    normalize_clusters_if_full_universe,
    total_potential_tl,
)


def test_normalize_full_universe_returns_none():
    opts = [{"label": "A", "value": "A"}, {"label": "B", "value": "B"}]
    assert normalize_clusters_if_full_universe(["B", "A"], opts) is None


def test_normalize_partial_keeps_list():
    opts = [{"label": "A", "value": "A"}, {"label": "B", "value": "B"}]
    assert normalize_clusters_if_full_universe(["A"], opts) == ["A"]


def test_normalize_no_option_data_passes_through():
    assert normalize_clusters_if_full_universe(["x"], None) == ["x"]
    assert normalize_clusters_if_full_universe(None, None) is None


def test_total_potential_tl_sums():
    panels = [
        {"potential_tl": 1.5},
        {"potential_tl": 2.0},
        {"foo": 1},
    ]
    assert total_potential_tl(panels) == 3.5


def test_aggregate_virt_sellable_panels_totals():
    panels = [
        {"resource_kind": "cpu", "potential_tl": 10.0, "sellable_constrained": 5.0, "display_unit": "Core"},
        {"resource_kind": "ram", "potential_tl": 3.0, "sellable_constrained": 100.0},
        {"resource_kind": "other", "potential_tl": 7.0},
    ]
    total_tl, by_kind, has_known = aggregate_virt_sellable_panels(panels)
    assert total_tl == 20.0
    assert has_known is True
    assert float(by_kind["cpu"]["tl"]) == 10.0
    assert float(by_kind["ram"]["tl"]) == 3.0
