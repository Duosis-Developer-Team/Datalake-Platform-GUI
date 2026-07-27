"""Licensed-OS rows for the Resource Overusage table.

The shape the business asked for (Hizmet / Satılan / Kullanılan / Ekstra Kullanım):

    Windows Lisans | 10 | 15 | 5

i.e. entitled = CRM licence quantity, used = detected licensed guests,
overage = used - entitled when positive.

These rows ride the /sales/resource-compliance payload, NOT
/sales/efficiency-by-category: every CRM order in production sits at
statecode 0 (open), and efficiency-by-category filters on statecode IN (3,4), so
it returns zero rows live. resource-compliance uses the 0,1,3,4 entitlement
baseline and is the only hydrated path.
"""
from __future__ import annotations

from app.utils.usage_comparison import build_licensed_os_compliance


def _entitled(qty, *, label=None, product_ids=()):
    return {
        "entitled_qty": qty,
        "entitled_amount_tl": 0.0,
        "product_ids": list(product_ids),
        "category_label": label,
    }


def _prices():
    return {
        "weighted_prices": {},
        "price_overrides": {},
        "catalog_by_productid": {},
        "catalog_by_name": {},
    }


def test_overusage_row_matches_the_requested_shape():
    rows = build_licensed_os_compliance(
        entitled_agg={"license_windows_os": _entitled(10)},
        detected={"windows": 15, "rhel": 0, "suse": 0, "free": 0, "unknown": 0},
        **_prices(),
    )
    win = next(r for r in rows if r["category_code"] == "license_windows_os")
    assert win["entitled_qty"] == 10       # Satılan
    assert win["used_qty"] == 15           # Kullanılan
    assert win["overage_qty"] == 5         # Ekstra Kullanım
    assert win["status"] == "over"
    assert win["resource_unit"] == "per VM"


def test_no_overage_when_entitlement_covers_usage():
    rows = build_licensed_os_compliance(
        entitled_agg={"license_windows_os": _entitled(20)},
        detected={"windows": 15},
        **_prices(),
    )
    win = next(r for r in rows if r["category_code"] == "license_windows_os")
    assert win["overage_qty"] == 0
    assert win["status"] != "over"


def test_usage_with_no_sale_is_flagged_as_unsold_usage():
    """The 300 SUSE LPARs vs 6 sold licences case — the reason this feature exists."""
    rows = build_licensed_os_compliance(
        entitled_agg={},
        detected={"suse": 300},
        **_prices(),
    )
    suse = next(r for r in rows if r["category_code"] == "license_suse")
    assert suse["entitled_qty"] == 0
    assert suse["used_qty"] == 300
    assert suse["overage_qty"] == 300
    assert suse["status"] == "unsold_usage"


def test_families_with_neither_sales_nor_usage_are_dropped():
    rows = build_licensed_os_compliance(
        entitled_agg={"license_windows_os": _entitled(3)},
        detected={"windows": 3},
        **_prices(),
    )
    assert {r["category_code"] for r in rows} == {"license_windows_os"}


def test_unknown_guests_never_become_a_licence_family():
    rows = build_licensed_os_compliance(
        entitled_agg={},
        detected={"unknown": 1483, "free": 5813},
        **_prices(),
    )
    assert rows == []


def test_overage_loss_uses_the_resolved_unit_price():
    rows = build_licensed_os_compliance(
        entitled_agg={"license_windows_os": _entitled(1, product_ids=["p1"])},
        detected={"windows": 4},
        weighted_prices={"p1": 250.0},
        price_overrides={},
        catalog_by_productid={},
        catalog_by_name={},
    )
    win = rows[0]
    assert win["overage_qty"] == 3
    assert win["overage_loss_tl"] == 750.0


def test_rows_carry_a_licensing_tab_binding_so_the_gui_can_place_them():
    rows = build_licensed_os_compliance(
        entitled_agg={"license_windows_os": _entitled(1)},
        detected={"windows": 4},
        **_prices(),
    )
    assert rows[0]["gui_tab_binding"] == "licensing.os"


# --- pricing the gap ---------------------------------------------------------

def test_customer_who_never_bought_the_licence_still_gets_a_loss_figure():
    """The unit price is normally read off the customer's own orders. A customer
    who bought none has no orders, so the price resolved to 0 and the biggest leak
    on the platform — 300 SUSE guests against 6 sold licences — printed
    "0 TL lost". The platform-wide weighted average from real orders fills in."""
    rows = build_licensed_os_compliance(
        entitled_agg={},
        detected={"suse": 300},
        fallback_prices={"license_suse": 5238.76},
        **_prices(),
    )
    suse = next(r for r in rows if r["category_code"] == "license_suse")
    assert suse["overage_qty"] == 300
    assert suse["overage_loss_tl"] == round(300 * 5238.76, 2)
    assert suse["price_source"] == "platform_average"


def test_the_customers_own_price_still_wins_over_the_platform_average():
    """A price the customer actually paid is a fact; the average is an estimate."""
    rows = build_licensed_os_compliance(
        entitled_agg={"license_windows_os": _entitled(1, product_ids=["p1"])},
        detected={"windows": 4},
        weighted_prices={"p1": 250.0},
        price_overrides={},
        catalog_by_productid={},
        catalog_by_name={},
        fallback_prices={"license_windows_os": 446.63},
    )
    win = rows[0]
    assert win["overage_loss_tl"] == 750.0        # 3 x the customer's own 250
    assert win["price_source"] != "platform_average"


def test_no_fallback_price_available_leaves_the_loss_at_zero_not_invented():
    rows = build_licensed_os_compliance(
        entitled_agg={}, detected={"rhel": 523}, fallback_prices={}, **_prices(),
    )
    rhel = next(r for r in rows if r["category_code"] == "license_redhat")
    assert rhel["overage_qty"] == 523
    assert rhel["overage_loss_tl"] == 0.0
    assert rhel["price_source"] == "none"
