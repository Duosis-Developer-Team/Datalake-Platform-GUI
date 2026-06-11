"""Tests for virt TL rollup from sellable summary."""

from src.utils.virt_sellable_aggregate import virt_tl_from_sellable_summary


def test_virt_tl_from_sellable_summary_sums_virt_families():
    summary = {
        "families": [
            {"family": "virt_classic", "total_potential_tl": 100.0},
            {"family": "virt_hyperconverged", "total_potential_tl": 50.0},
            {"family": "virt_power", "total_potential_tl": 30.0},
            {"family": "backup", "total_potential_tl": 999.0},
        ],
    }
    assert virt_tl_from_sellable_summary(summary) == 180.0


def test_virt_tl_from_sellable_summary_empty():
    assert virt_tl_from_sellable_summary({}) == 0.0
    assert virt_tl_from_sellable_summary(None) == 0.0
