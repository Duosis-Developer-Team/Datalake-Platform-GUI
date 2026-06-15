"""Customer name resolution helpers."""

from __future__ import annotations

from app.services import customer_resolver


def test_extract_possessive_and_label_patterns():
    text = 'Boyner\'in aktif siparişleri ve Akbank müşterisi'
    candidates = customer_resolver.extract_customer_candidates(text)
    assert "Boyner" in candidates
    assert "Akbank" in candidates


def test_fuzzy_match_against_catalog():
    catalog = {
        "customers": [
            {"display_name": "Boyner Holding", "crm_account_name": "BOYNER"},
            {"display_name": "Akbank", "crm_account_name": "AKBANK"},
        ]
    }
    matched = customer_resolver.fuzzy_match_customer("boyner holding sipariş", catalog)
    assert matched == "Boyner Holding"


def test_resolve_customer_name_prefers_explicit_candidate():
    resolved = customer_resolver.resolve_customer_name(
        "Akbank müşterisi satış özeti",
        selected_customer="Boyner",
    )
    assert resolved == "Akbank"
