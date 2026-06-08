"""Unit tests for customers list page helpers and layout wiring."""

from __future__ import annotations

from src.pages import customers_list
from src.utils.customers_list_ui import (
    apply_vip_toggle_local,
    badge_color_for_mapping_status,
    filter_catalog_rows,
    format_revenue,
    group_catalog_rows,
    overuse_badge_props,
    page_count,
    paginate_rows,
)


def _sample_catalog() -> dict:
    return {
        "customers": [
            {
                "crm_accountid": "acc-boyner",
                "crm_account_name": "Boyner Holding",
                "display_name": "Boyner Holding",
                "is_vip": False,
                "mapped": True,
                "mapping_status": "seed",
                "real_data_cached": True,
                "overuse_status": "pending",
                "list_group": "mapped",
                "ytd_revenue": 1000.0,
                "active_order_value": 500.0,
                "active_order_count": 1,
                "currency": "TL",
            },
            {
                "crm_accountid": "acc-a",
                "crm_account_name": "Alpha Corp",
                "display_name": "Alpha Corp",
                "is_vip": False,
                "mapped": False,
                "mapping_status": "empty",
                "real_data_cached": False,
                "overuse_status": "not_applicable",
                "list_group": "unmapped",
                "ytd_revenue": 0.0,
                "currency": "TL",
            },
            {
                "crm_accountid": "acc-v",
                "crm_account_name": "VIP Corp",
                "display_name": "VIP Corp",
                "is_vip": True,
                "mapped": False,
                "mapping_status": "empty",
                "real_data_cached": False,
                "overuse_status": "not_applicable",
                "list_group": "vip",
                "ytd_revenue": 500.0,
                "currency": "TL",
            },
        ],
        "groups": {
            "vip": [],
            "mapped": [],
            "unmapped": [],
        },
        "overview": {
            "total_customers": 3,
            "mapped_count": 1,
            "unmapped_count": 1,
            "vip_count": 1,
            "total_revenue": 1500.0,
            "total_active_order_value": 500.0,
            "total_active_order_count": 1,
            "currency": "TL",
            "service_sales": [],
            "overuse_customer_count": 1,
        },
    }


def _sample_catalog_with_groups() -> dict:
    data = _sample_catalog()
    data["groups"] = group_catalog_rows(data["customers"])
    return data


def test_load_page_data_uses_catalog_and_overview(monkeypatch):
    monkeypatch.setattr(customers_list.api, "get_customer_catalog", lambda: {"customers": [{"crm_accountid": "a"}], "groups": {"vip": [], "mapped": [{"crm_accountid": "a"}], "unmapped": []}})
    monkeypatch.setattr(customers_list.api, "get_customer_overview", lambda: {"total_customers": 1})

    data = customers_list._load_page_data()

    assert data["customers"] == [{"crm_accountid": "a"}]
    assert data["overview"]["total_customers"] == 1


def test_can_manage_vip_requires_permission_edit():
    assert customers_list._can_manage_vip(None) is True
    assert customers_list._can_manage_vip({"action:customer_view:vip_manage": {"edit": True}}) is True
    assert customers_list._can_manage_vip({"action:customer_view:vip_manage": {"view": True}}) is True
    assert customers_list._can_manage_vip({"action:customer_view:vip_manage": {}}) is False


def test_build_customers_list_contains_catalog_stores(monkeypatch):
    monkeypatch.setattr(customers_list, "_load_page_data", _sample_catalog)
    layout = customers_list.build_customers_list()
    store_ids = [child.id for child in layout.children if getattr(child, "id", None)]
    assert "customer-catalog-store" in store_ids
    assert "customer-section-pages" in store_ids
    assert "customer-vip-pending" in store_ids
    assert "customer-accordion-open" in store_ids


def test_filter_catalog_rows_matches_display_name():
    rows = _sample_catalog()["customers"]
    filtered = filter_catalog_rows(rows, "alpha")
    assert len(filtered) == 1
    assert filtered[0]["crm_account_name"] == "Alpha Corp"


def test_pagination_helpers():
    rows = list(range(10))
    assert page_count(10, 4) == 3
    assert paginate_rows(rows, 1, 4) == [4, 5, 6, 7]


def test_compact_customer_card_shows_active_value():
    card = customers_list._compact_customer_card(
        {
            "display_name": "3S Sigorta",
            "crm_accountid": "acc-3s",
            "ytd_revenue": 0.0,
            "active_order_value": 3788.42,
            "currency": "TRY",
            "mapped": False,
            "is_vip": False,
        },
        allow_vip_toggle=False,
    )
    text = str(card)
    assert "Active" in text
    assert "3.8K TRY" in text or "3,788" in text
    assert "Open" not in text
    assert "customer-view" in text


def test_compact_customer_card_clickable_with_star_overlay():
    card = customers_list._compact_customer_card(
        {
            "display_name": "Alpha Corp",
            "crm_accountid": "acc-a",
            "ytd_revenue": 0.0,
            "active_order_value": 0.0,
            "currency": "TL",
            "mapped": True,
            "is_vip": False,
        },
        allow_vip_toggle=True,
    )
    text = str(card)
    assert "Open" not in text
    assert "customer-list-card--clickable" in text
    assert "customer-list-card__vip-toggle" in text
    assert "customer-vip-toggle" in text


def test_pending_account_id_from_dict_or_legacy_string():
    assert customers_list._pending_account_id({"account_id": "acc-a", "is_vip": True}) == "acc-a"
    assert customers_list._pending_account_id("acc-a") == "acc-a"
    assert customers_list._pending_account_id(None) is None


def test_build_vip_pending_request_ignores_zero_clicks():
    data = _sample_catalog_with_groups()
    assert (
        customers_list._build_vip_pending_request(
            {"type": "customer-vip-toggle", "account": "acc-a"},
            data,
            click_count=0,
        )
        is None
    )


def test_build_vip_pending_request_returns_explicit_intent():
    data = _sample_catalog_with_groups()
    result = customers_list._build_vip_pending_request(
        {"type": "customer-vip-toggle", "account": "acc-a"},
        data,
        click_count=1,
    )
    assert result == {"account_id": "acc-a", "is_vip": True}


def test_complete_customer_vip_toggle_uses_explicit_is_vip(monkeypatch):
    calls: list[tuple[str, bool]] = []

    def _set_vip(account_id: str, *, is_vip: bool):
        calls.append((account_id, is_vip))
        return {"status": "ok"}

    monkeypatch.setattr(customers_list.api, "set_customer_vip", _set_vip)
    data = _sample_catalog_with_groups()
    updated, alert, pending = customers_list.complete_customer_vip_toggle(
        {"account_id": "acc-a", "is_vip": True},
        data,
    )
    assert calls == [("acc-a", True)]
    assert pending is None
    assert updated["overview"]["vip_count"] == 2
    assert alert is not None
    assert "added to VIP" in str(alert)


def test_format_revenue_and_badges():
    assert "1.5K" in format_revenue(1500, "TL")
    assert badge_color_for_mapping_status("seed") == "blue"
    label, color = overuse_badge_props("pending")
    assert label == "Comparison pending"
    assert color == "orange"


def test_overview_strip_includes_active_orders_kpi():
    strip = customers_list._overview_strip(
        {
            "total_active_order_value": 3788.42,
            "total_active_order_count": 1,
            "currency": "TRY",
            "total_customers": 10,
            "mapped_count": 5,
            "unmapped_count": 4,
            "vip_count": 1,
            "total_revenue": 0.0,
            "overuse_customer_count": 0,
        }
    )
    text = str(strip)
    assert "ACTIVE ORDERS" in text
    assert "1 open order" in text


def test_apply_vip_toggle_local_moves_customer_between_groups():
    data = _sample_catalog_with_groups()
    updated = apply_vip_toggle_local(data, "acc-a", is_vip=True)
    assert updated["overview"]["vip_count"] == 2
    assert updated["overview"]["unmapped_count"] == 0
    vip_names = [r["crm_account_name"] for r in updated["groups"]["vip"]]
    assert "Alpha Corp" in vip_names


def test_section_refresh_outputs_updates_pagination_without_full_accordion():
    data = _sample_catalog_with_groups()
    outputs = customers_list._section_refresh_outputs(
        data,
        "",
        {"vip": 0, "mapped": 0, "unmapped": 0},
        allow_vip_toggle=True,
    )
    cards, page_totals, page_values, count_badges, total_labels, page_store, overview = outputs
    assert len(cards) == 3
    assert len(page_totals) == 3
    assert page_store["mapped"] == 0
    assert "ACTIVE ORDERS" in str(overview)
    assert count_badges[1] == "1"
