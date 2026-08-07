"""UI columns and header badges for the OS Lisans inventory group."""
from __future__ import annotations

from src.components.crm_inventory_report import (
    _OS_LICENCE_TOOLTIP,
    _family_free_tooltip,
    _family_sellable_profile,
    _header_money_badges,
    columns_for_family,
    prepare_service_row,
)


def test_columns_for_os_licence_profile():  # TEST-U-006 (REQ-F-005)
    # os_licence reuses spine slot 3 (Total) for Tespit Edilen and slot 6
    # (Unsold) for Lisanslanmalı; Used/Free have no override and stay as dead
    # "—" columns (ADR-001) rather than being dropped — dropping them is what
    # bumped Birim Fiyat off the end (REQ-F-003) and shifted every column
    # after it.
    cols = columns_for_family("os_licence")
    ids = [c["id"] for c in cols]
    assert "sellable_alloc_fmt" not in ids
    assert ids == [
        "service_label",
        "display_unit",
        "crm_sold_fmt",
        "licence_detected_fmt",
        "used_fmt",
        "free_fmt",
        "licence_gap_fmt",
        "licence_gap_tl_fmt",
        "unit_price_fmt",
    ]
    assert ids[-1] == "unit_price_fmt"  # Birim Fiyat is last for every profile (REQ-F-003)


def test_family_sellable_profile_os_licence():
    fam = {"family": "os_licence", "sellable_profile": "os_licence"}
    panels = [{"panel_key": "license_windows_os", "sellable_profile": "os_licence"}]
    assert _family_sellable_profile(fam, panels) == "os_licence"


def test_header_badges_os_licence_no_sellable():
    panels = [
        {
            "crm_sold_tl": 578120.15,
            "licence_gap_qty": 6789.6,
            "licence_gap_tl": 2834000.0,
            "panel_key": "license_windows_os",
        },
        {
            "crm_sold_tl": 0.0,
            "licence_gap_qty": 523.0,
            "licence_gap_tl": 277800.0,
            "panel_key": "license_redhat",
        },
    ]
    badges = _header_money_badges(panels, profile="os_licence")
    texts = []
    for b in badges:
        # dmc.Badge stores children as the label string
        child = getattr(b, "children", None)
        if child is None and hasattr(b, "props"):
            child = b.props.get("children")
        texts.append(str(child))
    joined = " | ".join(texts)
    assert "CRM Sold" in joined
    assert "Eksik lisans" in joined
    assert "Lisanslanmalı" in joined
    assert "Sellable" not in joined


def test_os_licence_tooltip():
    assert "guest OS" in _family_free_tooltip(profile="os_licence", family_key="os_licence")
    assert _family_free_tooltip(profile="os_licence", family_key="os_licence") == _OS_LICENCE_TOOLTIP


def test_prepare_service_row_os_licence_fields():
    row = prepare_service_row({
        "panel_key": "license_windows_os",
        "service_label": "MS Windows Lisans",
        "family": "license_os",
        "display_unit": "per VM",
        "sellable_profile": "os_licence",
        "has_infra_source": True,
        "has_price": True,
        "crm_sold_qty": 1294.4,
        "crm_sold_tl": 578120.15,
        "licence_detected_qty": 8084.0,
        "licence_gap_qty": 6789.6,
        "licence_gap_tl": 2834000.0,
        "unit_price_tl": 417.39,
        "status": "over",
    })
    assert "8,084" in row["licence_detected_fmt"] or "8084" in row["licence_detected_fmt"]
    assert "6,790" in row["licence_gap_fmt"] or "6789" in row["licence_gap_fmt"] or "6,789" in row["licence_gap_fmt"]
    assert "TL" in row["licence_gap_tl_fmt"]
    assert "TL" in row["unit_price_fmt"]
