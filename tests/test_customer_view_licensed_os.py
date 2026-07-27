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


def test_detected_counts_are_read_off_the_compliance_rows():
    """The Billing panel used to call the datacenter-api per-customer endpoint,
    which matches a VM *name* against the customer's full CRM legal name and so
    resolved almost nothing (GAMA ENERJİ A.Ş. -> 0 guests). The counts now come
    from the compliance payload, computed in customer-api from the very VM lists
    this page renders — so the Billing panel and the summary overusage table can
    never show different numbers."""
    from src.pages.customer_view import _detected_families_from_compliance

    payload = {"rows": [
        {"category_code": "license_windows_os", "detected": 15, "entitled_qty": 10},
        {"category_code": "license_suse", "detected": 300, "entitled_qty": 6},
        {"category_code": "virt_classic_cpu", "used_qty": 40},
    ]}
    assert _detected_families_from_compliance(payload) == {"windows": 15, "suse": 300}


def test_detected_counts_tolerate_a_missing_or_empty_payload():
    from src.pages.customer_view import _detected_families_from_compliance

    assert _detected_families_from_compliance(None) == {}
    assert _detected_families_from_compliance({}) == {}
    assert _detected_families_from_compliance({"rows": []}) == {}


def test_merge_falls_back_to_the_original_rows_when_nothing_was_detected():
    from src.pages.customer_view import _eff_rows_with_licensed_os

    rows = [{"category_code": "firewall_fortigate", "entitled_qty": 2, "used_qty": 2}]
    assert _eff_rows_with_licensed_os(rows, None) == rows


def test_billing_panel_uses_the_priced_compliance_rows_verbatim():
    """The Billing panel re-derived its licence rows from a family tally, so they
    lost the fields the summary table shows — the same SUSE gap read
    "288,131.93 TL" on the summary and "Est. loss: –" on Billing. One fact
    priced on one page and unpriced on another is a bug, not a view difference."""
    from src.pages.customer_view import _eff_rows_with_licensed_os

    compliance = {"rows": [
        {"category_code": "license_suse", "category_label": "SUSE Lisans",
         "resource_unit": "Adet", "entitled_qty": 0, "used_qty": 55, "detected": 55,
         "overage_qty": 55, "overage_loss_tl": 288131.93, "status": "unsold_usage",
         "gui_tab_binding": "licensing.os"},
    ]}
    out = _eff_rows_with_licensed_os([], compliance)
    suse = next(r for r in out if r.get("category_code") == "license_suse")
    assert suse["overage_loss_tl"] == 288131.93
    assert suse["resource_unit"] == "Adet"
    assert suse["status"] == "unsold_usage"


def test_raw_licence_rows_are_not_shown_twice():
    from src.pages.customer_view import _eff_rows_with_licensed_os

    compliance = {"rows": [
        {"category_code": "license_windows_os", "category_label": "Windows Lisans",
         "resource_unit": "per VM", "entitled_qty": 10, "used_qty": 15, "detected": 15,
         "overage_qty": 5, "overage_loss_tl": 2357.05, "status": "over",
         "gui_tab_binding": "licensing.os"},
    ]}
    eff = [{"category_code": "license_windows_os", "entitled_qty": 10, "used_qty": 0}]
    out = _eff_rows_with_licensed_os(eff, compliance)
    assert sum(1 for r in out if r.get("category_code") == "license_windows_os") == 1
    assert out[0]["overage_loss_tl"] == 2357.05


def test_unrelated_rows_survive_untouched():
    from src.pages.customer_view import _eff_rows_with_licensed_os

    fw = {"category_code": "firewall_fortigate", "entitled_qty": 2, "used_qty": 2}
    out = _eff_rows_with_licensed_os([fw], {"rows": []})
    assert fw in out
