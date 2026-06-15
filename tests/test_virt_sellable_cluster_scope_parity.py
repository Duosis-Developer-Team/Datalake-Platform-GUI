"""Summary vs Virtualization sellable parity — cluster scope and aggregation."""
from __future__ import annotations

from unittest.mock import patch

from src.pages.dc_summary_sellable import _resolve_virt_panels
from src.utils.virt_sellable_aggregate import (
    collect_virt_sellable_panels,
    merge_power_panels_for_summary,
    virt_tab_cluster_scope,
    virt_total_potential_range,
)


def test_virt_tab_cluster_scope_passes_explicit_lists():
    classic, hyperconv = virt_tab_cluster_scope(["A", "B"], ["HC-1"])
    assert classic == ["A", "B"]
    assert hyperconv == ["HC-1"]


def test_virt_tab_cluster_scope_empty_becomes_none():
    classic, hyperconv = virt_tab_cluster_scope([], [])
    assert classic is None
    assert hyperconv is None


def test_resolve_virt_panels_uses_virt_tab_cluster_scope():
    with patch(
        "src.pages.dc_summary_sellable.collect_virt_sellable_panels",
        return_value=[{"potential_tl": 100.0}],
    ) as mock_collect:
        panels = _resolve_virt_panels(
            "DC11",
            None,
            classic_clusters=["KM-1"],
            hyperconv_clusters=["HC-1"],
        )
    assert panels
    mock_collect.assert_called_once_with("DC11", ["KM-1"], ["HC-1"])


def test_none_vs_explicit_cluster_scope_normalized_for_full_inventory():
    """Full DC inventory lists normalize to None for cache key parity."""
    from src.components.virt_cluster_filter import normalize_virt_cluster_scope

    all_c = ["KM-1", "KM-2"]
    assert normalize_virt_cluster_scope(None, all_c) is None
    assert normalize_virt_cluster_scope(all_c, all_c) is None
    assert normalize_virt_cluster_scope(["KM-1"], all_c) == ["KM-1"]


def test_summary_and_virt_total_use_same_range_helper():
    panels = [
        {
            "family": "virt_classic",
            "resource_kind": "storage",
            "potential_tl": 500000.0,
            "potential_tl_min": 400000.0,
            "potential_tl_max": 600000.0,
        },
        {
            "family": "virt_power",
            "resource_kind": "cpu",
            "potential_tl": 100000.0,
        },
    ]
    merged = merge_power_panels_for_summary(panels)
    total, lo, hi = virt_total_potential_range(merged)
    assert total == 600000.0
    assert lo == 500000.0
    assert hi == 700000.0


def test_app_virt_total_card_uses_range_helper():
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[1].joinpath("app.py").read_text(
            encoding="utf-8"
        )
    )
    assert "_build_virt_total_sellable_children" in source


def test_summary_virt_parity_same_cluster_lists_same_args():
    """Summary _resolve_virt_panels passes the same cluster lists as the Virt tab."""
    classic = ["CL-A"]
    hyperconv = ["HC-A"]
    with patch(
        "src.pages.dc_summary_sellable.collect_virt_sellable_panels",
        return_value=[{"potential_tl": 42.0}],
    ) as summary_collect:
        panels = _resolve_virt_panels(
            "DC13", None, classic_clusters=classic, hyperconv_clusters=hyperconv
        )
    summary_collect.assert_called_once_with("DC13", classic, hyperconv)
    assert panels
