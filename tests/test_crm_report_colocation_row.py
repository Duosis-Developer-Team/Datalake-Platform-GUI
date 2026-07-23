"""dc_hosting_u colocation row in the CRM inventory report.

`prepare_service_row(row: dict) -> dict` (src/components/crm_inventory_report.py:272)
returns a dict of *display strings* keyed by column id (e.g. "free_fmt",
"used_fmt") — it does not build a Dash component. When a dc_hosting_u row
carries real infra telemetry (has_infra_source=True), the prepared dict must
surface the actual U quantities (used/total) and the sellable-derived Free
figure rather than collapsing to the "CRM entitled — infra telemetry
pending" placeholder that applies when infra data is absent.

The live classifier (inventory_overview_service._ALLOC_ONLY_FAMILIES) does
NOT include family="dc_hosting", so a real dc_hosting_u row carries
sellable_profile="standard" and a sellable_qty. Under that "standard"
profile, prepare_service_row REPLACES free_display_qty with sellable_qty
(src/components/crm_inventory_report.py:331-335) — so production's Free cell
shows the sellable figure (~1,076 U), not raw physical free (1,799 U). This
fixture mirrors that live shape so the test guards the seam it claims to.
"""
from __future__ import annotations

from src.components.crm_inventory_report import prepare_service_row


def _dc_hosting_u_row(**overrides):
    """A populated dc_hosting_u row, matching the real backend/classifier shape.

    Values mirror services/customer-api/tests/test_colocation_panel_result.py
    (total=3616, used=1817, sellable=apply_threshold(3616,1817,80)=1075.8,
    free=total-used=1799), plus a positive crm_sold_tl so the "infra telemetry
    pending" hint has something to fire on when has_infra_source is False.

    sellable_profile is intentionally omitted — family="dc_hosting" is not in
    _ALLOC_ONLY_FAMILIES, so the live classifier leaves it unset and
    prepare_service_row defaults to the "standard" profile.
    """
    row = {
        "panel_key": "dc_hosting_u",
        "service_label": "DC Barındırma — U",
        "family": "dc_hosting",
        "family_label": "DC Barındırma",
        "display_unit": "U",
        "total": 3616.0,
        "used_qty": 1817.0,
        "free_qty": 1799.0,
        "crm_sold_qty": 2.0,
        "crm_sold_tl": 12000.0,
        "sellable_qty": 1075.8,
        "unit_price_tl": 0.0,
        "has_infra_source": True,
    }
    row.update(overrides)
    return row


def test_dc_hosting_u_row_surfaces_u_quantities_when_infra_present():
    """Populated infra (has_infra_source=True) -> real Used/Total U figures and
    the sellable-derived Free figure (standard profile), no pending hint."""
    comp = prepare_service_row(_dc_hosting_u_row())

    # The service label is untouched - no "CRM entitled" / "telemetry pending" wording.
    assert comp["service_label"] == "DC Barındırma — U"
    assert "telemetry pending" not in comp["service_label"].lower()

    # Total/Used carry the real U figures (not em-dash placeholders).
    assert comp["total_fmt"] == "3,616 U"
    assert comp["used_fmt"] == "1,817 U\n—"

    # Free is REPLACED by the sellable quantity under the standard profile
    # (1,075.8 -> rounds to 1,076 U), not the raw physical free (1,799 U).
    assert comp["free_fmt"] == "1,076 U\n—"
    assert "1,799" not in comp["free_fmt"]

    assert comp["display_unit"] == "U"
    assert comp["has_infra_source"] is True

    # Sanity: these would fail if used/total got swapped or the row were
    # mishandled as a crm-only / infra-absent row.
    assert "1,817" in comp["used_fmt"]
    assert "3,616" in comp["total_fmt"]
    assert "1,817" not in comp["free_fmt"]
    assert "1,076" not in comp["used_fmt"]


def test_dc_hosting_u_row_without_infra_falls_back_to_pending_hint():
    """Same row, has_infra_source=False -> CRM-entitled/pending path, U figures hidden.

    This is the contrast case: it proves the first test's assertions are
    exercising the has_infra_source branch and not merely echoing whatever
    numbers were put in the row.
    """
    comp = prepare_service_row(_dc_hosting_u_row(has_infra_source=False))

    assert comp["has_infra_source"] is False
    assert "CRM entitled — infra telemetry pending" in comp["service_label"]

    # Quantities collapse to the placeholder - the real U figures must not leak through.
    assert comp["free_fmt"] == "—\n—"
    assert comp["used_fmt"] == "—\n—"
    assert comp["total_fmt"] == "—"
    assert "1,799" not in comp["free_fmt"]
    assert "1,076" not in comp["free_fmt"]
    assert "1,817" not in comp["used_fmt"]
