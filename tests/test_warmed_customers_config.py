"""Item 4.1: WARMED_CUSTOMERS is env-configurable so ops can pre-warm more than
one customer (beyond the hard-coded "Boyner") without a code change.
"""
from src.services import db_service


def test_warmed_customers_default_when_unset(monkeypatch):
    monkeypatch.delenv("APP_WARMED_CUSTOMERS", raising=False)
    assert db_service._load_warmed_customers() == ("Boyner",)


def test_warmed_customers_parsed_from_env(monkeypatch):
    monkeypatch.setenv("APP_WARMED_CUSTOMERS", "Boyner, Acme ,Globex")
    assert db_service._load_warmed_customers() == ("Boyner", "Acme", "Globex")


def test_warmed_customers_blank_env_falls_back(monkeypatch):
    monkeypatch.setenv("APP_WARMED_CUSTOMERS", "   ")
    assert db_service._load_warmed_customers() == ("Boyner",)
