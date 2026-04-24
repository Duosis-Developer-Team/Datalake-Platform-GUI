"""Unit tests for customer_needle.py — Turkish character normalization."""
import pytest
from app.utils.customer_needle import customer_to_email_needle


@pytest.mark.parametrize("name,expected", [
    ("Boyner",        "%@%boyner%"),
    ("BOYNER",        "%@%boyner%"),
    # Turkish character mapping
    ("Türk Telekom",  "%@%turk telekom%"),
    ("İş Bankası",    "%@%is bankasi%"),
    ("Çelebi",        "%@%celebi%"),
    ("Şeker Sigorta", "%@%seker sigorta%"),
    ("Güneş",         "%@%gunes%"),
    # Noise chars collapsed to space
    ("A-B",           "%@%a b%"),
    ("A_B",           "%@%a b%"),
    # Empty / None
    ("",              "%@%%"),
    (None,            "%@%%"),
])
def test_customer_to_email_needle(name, expected):
    assert customer_to_email_needle(name) == expected
