"""Tests for customer name extraction and fuzzy catalog matching."""

from app.services import customer_resolver

_CATALOG = {
    "customers": [
        {"display_name": "Boyner Büyük Mağazacılık A.Ş.", "crm_account_name": "Boyner"},
        {"display_name": "ASELSANNET", "crm_account_name": "ASELSANNET"},
    ],
}


def test_extract_customer_from_label_lowercase():
    names = customer_resolver.extract_customer_candidates("boyner müşterisi hakkında bilgi")
    assert names
    assert names[0].casefold() == "boyner"


def test_extract_customer_from_possessive():
    names = customer_resolver.extract_customer_candidates("Boyner'in aktif siparişleri")
    assert "Boyner" in names


def test_fuzzy_match_typo_boynr():
    matched = customer_resolver.fuzzy_match_customer(
        "Boynr müşterisi özeti",
        _CATALOG,
        min_score=0.72,
    )
    assert matched in ("Boyner", "Boyner Büyük Mağazacılık A.Ş.")


def test_resolve_prefers_explicit_label():
    resolved = customer_resolver.resolve_customer_name(
        "aselsan müşterisi özeti",
        catalog_payload=_CATALOG,
    )
    assert resolved is not None
    assert "aselsan" in resolved.casefold()


def test_normalize_customer_tool_args():
    args = customer_resolver.normalize_customer_tool_args(
        {"customer_name": "boyner", "days": 7},
        "Boyner Büyük Mağazacılık A.Ş.",
    )
    assert args["customer_name"] == "Boyner Büyük Mağazacılık A.Ş."
    assert args["days"] == 7
