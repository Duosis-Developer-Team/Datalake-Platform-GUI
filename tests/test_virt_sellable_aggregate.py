"""Tests for virt sellable panel aggregation helpers."""
from __future__ import annotations

from src.utils.virt_sellable_aggregate import (
    aggregate_virt_sellable_panels,
    merge_power_panels_for_summary,
    prepare_virt_sellable_panels,
    total_potential_tl,
    virt_total_potential_range,
)


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


def test_prepare_virt_sellable_panels_merges_power():
    raw = [
        {"family": "virt_power", "resource_kind": "cpu", "potential_tl": 1.0},
        {"family": "virt_power_hana", "resource_kind": "cpu", "potential_tl": 2.0},
    ]
    out = prepare_virt_sellable_panels(raw)
    assert len(out) == 1
    assert out[0]["family"] == "virt_power"
    assert out[0]["potential_tl"] == 3.0
    assert out[0]["sellable_max_util"] is None


def test_virt_total_potential_range_ibm_storage_dedup():
    panels = [
        {"family": "virt_classic", "resource_kind": "storage", "potential_tl": 10.0,
         "potential_tl_min": 10.0, "potential_tl_max": 100.0},
        {"family": "virt_power", "resource_kind": "storage", "potential_tl": 20.0,
         "potential_tl_min": 5.0, "potential_tl_max": 80.0},
        {"family": "virt_hyperconverged", "resource_kind": "cpu", "potential_tl": 50.0,
         "potential_tl_min": 40.0, "potential_tl_max": 60.0},
    ]
    _, lo, hi = virt_total_potential_range(panels)
    assert lo == 10.0 + 5.0 + 40.0
    assert hi == max(100.0, 80.0) + 60.0


def test_merge_power_clears_max_util():
    merged = merge_power_panels_for_summary([
        {"family": "virt_power", "resource_kind": "cpu", "sellable_max_util": 99.0},
        {"family": "virt_power_hana", "resource_kind": "cpu", "sellable_max_util": 1.0},
    ])
    assert len(merged) == 1
    assert merged[0]["sellable_max_util"] is None
