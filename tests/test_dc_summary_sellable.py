"""Tests for DC Summary sellable executive section."""
from __future__ import annotations

from src.pages.dc_summary_sellable import build_summary_sellable_section, _fmt_tl_range


def test_fmt_tl_range_shows_bounds():
    text = _fmt_tl_range(1000.0, 2000.0)
    assert "–" in text or "-" in text


def test_build_summary_sellable_section_with_mock_summary():
    summary = {
        "total_potential_tl": 150000.0,
        "total_potential_tl_min": 100000.0,
        "total_potential_tl_max": 200000.0,
        "constrained_loss_tl": 5000.0,
        "unmapped_product_count": 2,
        "mapped_panel_count": 8,
        "computation_modes": {"virt_classic": "host_based"},
        "families": [
            {
                "family": "virt_classic",
                "label": "Classic",
                "panels": [
                    {
                        "resource_kind": "cpu",
                        "display_unit": "vCPU",
                        "total": 1000,
                        "allocated": 800,
                        "sellable_constrained": 180,
                        "sellable_physical": 450.0,
                        "sellable_effective": 180.0,
                        "threshold_pct": 80,
                        "computation_mode": "host_based",
                    },
                    {
                        "resource_kind": "ram",
                        "display_unit": "GB",
                        "sellable_constrained": 11502,
                    },
                    {
                        "resource_kind": "storage",
                        "display_unit": "GB",
                        "sellable_min": 100000,
                        "sellable_max": 143781,
                        "potential_tl_min": 500000,
                        "potential_tl_max": 800000,
                    },
                ],
            },
            {
                "family": "backup_zerto_replication_cpu",
                "label": "Zerto",
                "panels": [
                    {"resource_kind": "cpu", "display_unit": "vCPU", "sellable_constrained": 10, "potential_tl": 5000, "has_infra_source": True},
                ],
            },
        ],
    }
    block = build_summary_sellable_section("DC13", summary)
    assert block is not None
    assert block.id == "dc-summary-sellable-root"
