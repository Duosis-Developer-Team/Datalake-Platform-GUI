"""Unit tests for CRM sales panel builders."""
from __future__ import annotations

from src.components.crm_sales_panel import (
    build_crm_intro_card,
    build_crm_summary_kv_panel,
    crm_has_sales_data,
    format_crm_money,
)


def test_format_crm_money():
    assert format_crm_money(1234.5, "TRY") == "1,234.50 TRY"
    assert format_crm_money(None, "TL") == "-"


def test_crm_has_sales_data_true_when_ytd_positive():
    assert crm_has_sales_data({"ytd_revenue_total": 10.0}) is True


def test_crm_has_sales_data_false_when_empty():
    assert crm_has_sales_data({}) is False


def test_build_crm_summary_kv_panel_contains_customer_and_ytd():
    panel = build_crm_summary_kv_panel(
        "Acme Corp",
        {"ytd_revenue_total": 100.0, "lifetime_revenue_total": 200.0, "invoice_count": 2, "currency": "TRY"},
        [{"service_code": "virt", "service_label": "Virtualization", "amount_tl": 50.0}],
        [{"product_name": "RAM", "quantity": 1, "line_total": 50.0}],
    )
    assert panel is not None
    text = str(panel)
    assert "Acme Corp" in text
    assert "100.00 TRY" in text


def test_build_crm_intro_card_renders():
    card = build_crm_intro_card(
        "Acme Corp",
        {"ytd_revenue_total": 100.0, "lifetime_revenue_total": 200.0, "invoice_count": 1, "currency": "TRY"},
        [],
    )
    assert card is not None
    assert "CRM sales" in str(card)
