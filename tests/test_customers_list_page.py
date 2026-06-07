"""Unit tests for customers list page helpers and layout wiring."""

from __future__ import annotations

from src.pages import customers_list
from src.utils.customers_list_ui import (
    badge_color_for_mapping_status,
    filter_catalog_rows,
    format_revenue,
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
            "currency": "TL",
            "service_sales": [],
            "overuse_customer_count": 1,
        },
    }


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


def test_filter_catalog_rows_matches_display_name():
    rows = _sample_catalog()["customers"]
    filtered = filter_catalog_rows(rows, "alpha")
    assert len(filtered) == 1
    assert filtered[0]["crm_account_name"] == "Alpha Corp"


def test_pagination_helpers():
    rows = list(range(10))
    assert page_count(10, 4) == 3
    assert paginate_rows(rows, 1, 4) == [4, 5, 6, 7]


def test_format_revenue_and_badges():
    assert "1.5K" in format_revenue(1500, "TL")
    assert badge_color_for_mapping_status("seed") == "blue"
    label, color = overuse_badge_props("pending")
    assert label == "Comparison pending"
    assert color == "orange"
