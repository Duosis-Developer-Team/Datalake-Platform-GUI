"""Unit tests for customers list page behaviour."""

import dash_mantine_components as dmc

from src.pages import customers_list


def test_load_customers_filters_to_warmed(monkeypatch):
    monkeypatch.setattr(
        customers_list.api,
        "get_customer_list",
        lambda: ["Boyner", "Another Customer"],
    )

    result = customers_list._load_customers()

    assert result == ["Boyner"]


def test_build_customer_cards_returns_alert_when_no_match():
    out = customers_list._build_customer_cards(["Boyner"], "zzz")
    assert isinstance(out, dmc.Alert)


def test_filter_customer_cards_uses_search_query():
    out = customers_list.filter_customer_cards("boy", ["Boyner", "Acme"])
    # No strict class import required; grid has generated Dash props.
    assert getattr(out, "children", None)
