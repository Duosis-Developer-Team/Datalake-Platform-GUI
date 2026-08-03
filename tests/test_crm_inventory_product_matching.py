"""UI helpers for CRM inventory product matching section."""
from __future__ import annotations

from src.components.crm_inventory_report import (
    _PRODUCT_MATCHING_COLUMNS,
    build_product_matching_section,
    filter_product_matching_rows,
    prepare_product_matching_row,
)


def test_prepare_and_filter_product_matching_rows():
    rows = [
        {
            "productnumber": "000BLT-46",
            "product_name": "HC CPU",
            "crm_sold_qty": 10,
            "crm_sold_tl": 100,
            "match_status": "capacity",
            "usage_source": "Loki",
            "matching_rule": "cpu total",
            "infra_tables": ["nutanix_vm_metrics"],
            "infra_total": 20,
            "infra_used": 5,
            "in_registry": True,
        },
        {
            "productnumber": "000BLT-123",
            "product_name": "Sophos",
            "crm_sold_qty": 2,
            "crm_sold_tl": 40,
            "match_status": "documented",
            "usage_source": "Firewall",
            "matching_rule": "FW x adet",
            "infra_tables": [],
        },
    ]
    prepared = prepare_product_matching_row(rows[0])
    assert "10.0" in prepared["crm_sold_fmt"]
    assert prepared["infra_tables_fmt"] == "nutanix_vm_metrics"
    assert prepared["usage_source"] == "Loki"
    assert prepared["infra_total_fmt"] == "20.0"
    assert prepared["infra_used_fmt"] == "5.0"
    assert prepared["in_registry_fmt"] == "yes"
    assert prepared["match_approved"] is True
    assert "Matched" in prepared["match_status"]
    assert "Matched via Loki" in prepared["notes"]
    assert "nutanix_vm_metrics" in prepared["notes"]

    only_cap = filter_product_matching_rows(rows, "capacity", None)
    assert len(only_cap) == 1
    assert only_cap[0]["productnumber"] == "000BLT-46"

    searched = filter_product_matching_rows(rows, "all", "sophos")
    assert len(searched) == 1

    section = build_product_matching_section({"products": rows, "summary": {"capacity_count": 1}})
    assert section is not None
    assert section.value == "product-matching"


def test_checklist_columns_include_infra_and_usage_source():
    """Product Matching checklist keeps usage_source / infra totals (no hide)."""
    screen_ids = {c["id"] for c in _PRODUCT_MATCHING_COLUMNS}
    assert "usage_source" in screen_ids
    assert "infra_total_fmt" in screen_ids
    assert "infra_used_fmt" in screen_ids
    assert "infra_tables_fmt" in screen_ids
    assert "notes" in screen_ids


def test_search_still_matches_usage_source():
    rows = [
        {
            "productnumber": "000BLT-46",
            "product_name": "HC CPU",
            "match_status": "capacity",
            "usage_source": "Loki-special",
            "matching_rule": "cpu",
        },
    ]
    searched = filter_product_matching_rows(rows, "all", "loki-special")
    assert len(searched) == 1
