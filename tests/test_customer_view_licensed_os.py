"""Customer View: detected licensed-OS counts merged into the "Sold vs used
(other categories)" section (TASK-81 Task 6).
"""
from __future__ import annotations

import copy


def test_merge_licensed_os_rows_folds_license_rows_and_synthesizes_family_rows():
    from src.pages.customer_view import _merge_licensed_os_rows

    detected_families = {"rhel": 10, "suse": 2, "windows": 8}
    eff_by_cat = [
        {
            "category_code": "license_redhat",
            "category_label": "Red Hat Lisansı",
            "sold_qty": 4,
            "used_qty": 0,
            "overage_qty": 0,
            "resource_unit": "Adet",
            "status": "",
            "gui_tab_binding": "licensing.redhat",
        },
        {
            "category_code": "firewall_fortigate",
            "category_label": "Fortigate",
            "entitled_qty": 2,
            "used_qty": 2,
            "overage_qty": 0,
            "resource_unit": "Adet",
            "status": "",
            "gui_tab_binding": "licensing.firewall",
        },
    ]
    original = copy.deepcopy(eff_by_cat)

    result = _merge_licensed_os_rows(eff_by_cat, detected_families)

    # Input must not be mutated.
    assert eff_by_cat == original

    # Raw license category row must be folded away (no double-showing).
    codes = [r.get("category_code") for r in result]
    assert "license_redhat" not in codes

    # Synthesized RHEL family row present with expected fields.
    rhel_rows = [r for r in result if "RHEL" in str(r.get("category_label"))]
    assert len(rhel_rows) == 1
    rhel = rhel_rows[0]
    assert rhel["detected"] == 10
    assert rhel["entitled_qty"] == 4
    assert rhel["used_qty"] == 10

    # Unrelated non-license row is preserved unchanged.
    firewall_rows = [r for r in result if r.get("category_code") == "firewall_fortigate"]
    assert len(firewall_rows) == 1
    assert firewall_rows[0] == eff_by_cat[1]

    # Must survive the display filter (used_qty=detected keeps it visible).
    from src.utils.visibility import filter_efficiency_rows_for_display

    visible = filter_efficiency_rows_for_display(result)
    visible_rhel = [r for r in visible if "RHEL" in str(r.get("category_label"))]
    assert len(visible_rhel) == 1


def test_merge_licensed_os_rows_skips_families_with_no_signal():
    from src.pages.customer_view import _merge_licensed_os_rows

    # No detected counts and no sold rows at all for any family -> no synthesized rows.
    result = _merge_licensed_os_rows([], {})
    assert result == []


def test_one_row_card_without_detected_is_unchanged_smoke():
    from src.components.sold_vs_used_panel import _one_row_card

    row = {
        "category_label": "Fortigate",
        "entitled_qty": 2,
        "used_qty": 2,
        "overage_qty": 0,
        "resource_unit": "Adet",
        "status": "",
    }
    card = _one_row_card(row)
    assert card is not None
    text = str(card)
    assert "Fortigate" in text
    assert "Detected" not in text


def test_one_row_card_with_detected_renders_detected_value():
    from src.components.sold_vs_used_panel import _one_row_card

    row = {
        "category_label": "RHEL Lisans",
        "entitled_qty": 4,
        "used_qty": 10,
        "detected": 10,
        "overage_qty": 6,
        "resource_unit": "Adet",
        "status": "over",
    }
    card = _one_row_card(row)
    assert card is not None
    text = str(card)
    assert "RHEL Lisans" in text
    assert "Detected" in text
    assert "10" in text
