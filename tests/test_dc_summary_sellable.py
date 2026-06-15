"""Tests for DC Summary sellable executive section."""
from __future__ import annotations

from unittest.mock import patch

from src.pages.dc_summary_sellable import (
    build_sellable_executive_strip,
    build_summary_sellable_section,
    build_virt_compute_block,
    build_virt_storage_block,
    _fmt_tl_range,
)
from src.utils.virt_sellable_aggregate import merge_power_panels_for_summary


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
    virt_panels = [
        {
            "family": "virt_classic",
            "resource_kind": "cpu",
            "potential_tl": 100000.0,
            "potential_tl_min": 90000.0,
            "potential_tl_max": 110000.0,
            "sellable_raw": 200.0,
            "sellable_constrained": 180.0,
            "unit_price_tl": 500.0,
            "has_infra_source": True,
            "computation_mode": "host_based",
            "display_unit": "vCPU",
            "total": 1000,
            "allocated": 800,
            "sellable_physical": 450.0,
            "sellable_effective": 180.0,
            "threshold_pct": 80,
        },
        {
            "family": "virt_classic",
            "resource_kind": "ram",
            "potential_tl": 50000.0,
            "sellable_constrained": 11502,
            "display_unit": "GB",
            "has_infra_source": True,
        },
        {
            "family": "virt_classic",
            "resource_kind": "storage",
            "potential_tl": 650000.0,
            "potential_tl_min": 500000.0,
            "potential_tl_max": 800000.0,
            "sellable_min": 100000,
            "sellable_max": 143781,
            "display_unit": "GB",
            "has_price": True,
        },
    ]

    with patch(
        "src.pages.dc_summary_sellable._resolve_virt_panels",
        return_value=virt_panels,
    ):
        block = build_summary_sellable_section("DC13", summary)
    assert block is not None
    assert block.id == "dc-summary-sellable-root"


def test_executive_strip_uses_virt_panels_not_full_crm_rollup():
    panels = [
        {
            "family": "virt_classic",
            "resource_kind": "cpu",
            "potential_tl": 1000.0,
            "potential_tl_min": 900.0,
            "potential_tl_max": 1100.0,
            "sellable_raw": 10.0,
            "sellable_constrained": 8.0,
            "unit_price_tl": 100.0,
            "has_infra_source": True,
            "computation_mode": "host_based",
        },
    ]
    strip = build_sellable_executive_strip(
        {"unmapped_product_count": 99, "total_potential_tl_max": 9e12},
        virt_panels=panels,
    )
    text = str(strip)
    assert "Virt tab parity" in text
    assert "9" not in text or "Milyon" not in text


def test_merge_power_panels_collapses_hana_into_power():
    merged = merge_power_panels_for_summary([
        {"family": "virt_power", "resource_kind": "cpu", "sellable_constrained": 10, "potential_tl": 100, "total": 7904, "allocated": 324},
        {"family": "virt_power_hana", "resource_kind": "cpu", "sellable_constrained": 5, "potential_tl": 50, "total": 7904, "allocated": 324},
    ])
    power_cpu = [p for p in merged if p.get("family") == "virt_power" and p.get("resource_kind") == "cpu"]
    assert len(power_cpu) == 1
    assert power_cpu[0]["sellable_constrained"] == 15
    assert power_cpu[0]["potential_tl"] == 150
    assert power_cpu[0]["total"] == 7904
    assert power_cpu[0]["allocated"] == 324


def test_merge_power_single_panel_preserves_optional_tl_fields():
    """Single virt_power row must not get potential_tl_min/max zeroed by merge."""
    merged = merge_power_panels_for_summary([
        {"family": "virt_power", "resource_kind": "cpu", "potential_tl": 100.0},
    ])
    assert len(merged) == 1
    assert "potential_tl_min" not in merged[0] or merged[0].get("potential_tl_min") is None


def test_merge_power_infra_fields_use_max_not_sum():
    """virt_power_hana aliases same IBM Power infra — Cap/Alloc must not double-count."""
    merged = merge_power_panels_for_summary([
        {"family": "virt_power", "resource_kind": "ram", "total": 174080, "allocated": 145856, "sellable_constrained": 0},
        {"family": "virt_power_hana", "resource_kind": "ram", "total": 174080, "allocated": 145856, "sellable_constrained": 0},
    ])
    power_ram = [p for p in merged if p.get("family") == "virt_power" and p.get("resource_kind") == "ram"]
    assert len(power_ram) == 1
    assert power_ram[0]["total"] == 174080
    assert power_ram[0]["allocated"] == 145856


def test_virt_compute_block_has_no_power_hana_card():
    panels = merge_power_panels_for_summary([
        {"family": "virt_classic", "resource_kind": "cpu", "sellable_constrained": 1, "computation_mode": "host_based", "display_unit": "vCPU", "total": 10, "allocated": 5, "threshold_pct": 80},
        {"family": "virt_classic", "resource_kind": "ram", "sellable_constrained": 2, "display_unit": "GB"},
        {"family": "virt_power", "resource_kind": "cpu", "sellable_constrained": 3, "computation_mode": "aggregate", "display_unit": "Core", "total": 20, "allocated": 10, "threshold_pct": 80},
        {"family": "virt_power", "resource_kind": "ram", "sellable_constrained": 4, "display_unit": "GB"},
    ])
    block = build_virt_compute_block(panels=panels)
    text = str(block)
    assert "Power HANA" not in text
    assert "Power" in text


def test_storage_block_renders_three_architectures():
    panels = merge_power_panels_for_summary([
        {
            "family": "virt_classic",
            "resource_kind": "storage",
            "sellable_constrained": 100.0,
            "potential_tl": 500.0,
            "display_unit": "GB",
        },
        {
            "family": "virt_hyperconverged",
            "resource_kind": "storage",
            "sellable_constrained": 12400.0,
            "potential_tl": 22_800.0,
            "display_unit": "GB",
        },
        {
            "family": "virt_power",
            "resource_kind": "storage",
            "sellable_min": 50.0,
            "sellable_max": 150.0,
            "sellable_constrained": 50.0,
            "potential_tl_min": 100.0,
            "potential_tl_max": 300.0,
            "display_unit": "GB",
        },
    ])
    block = build_virt_storage_block(panels=panels)
    text = str(block)
    assert "Hyperconverged Storage Sellable" in text
    assert "KM (Classic) Storage Sellable" in text
    assert "Power Storage Sellable" in text
    assert "Nutanix pool" in text


def test_storage_block_hides_tl_when_constrained_zero():
    block = build_virt_storage_block(panels=[
        {
            "family": "virt_hyperconverged",
            "resource_kind": "storage",
            "sellable_constrained": 0.0,
            "potential_tl": 50_000.0,
            "constraint_reason": "compute_bottleneck",
            "display_unit": "GB",
        },
    ])
    text = str(block)
    assert "Hyperconverged Storage Sellable" in text
    assert "—" in text


def test_merge_power_constraint_metadata_prefers_compute_bottleneck():
    merged = merge_power_panels_for_summary([
        {
            "family": "virt_power",
            "resource_kind": "storage",
            "sellable_constrained": 0.0,
            "constraint_reason": "none",
            "ratio_bound": False,
        },
        {
            "family": "virt_power_hana",
            "resource_kind": "storage",
            "sellable_constrained": 0.0,
            "constraint_reason": "compute_bottleneck",
            "ratio_bound": True,
            "bottleneck_kind": "cpu",
            "bottleneck_units": 0.0,
        },
    ])
    sto = merged[0]
    assert sto["constraint_reason"] == "compute_bottleneck"
    assert sto["ratio_bound"] is True
    assert sto["bottleneck_kind"] == "cpu"
