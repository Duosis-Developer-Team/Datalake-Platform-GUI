"""Platform-wide licence unit price, used when a customer has no price of their own."""
from __future__ import annotations

from app.db.queries import crm_sales as sq


def test_platform_price_converts_currencies_before_averaging():
    """`extendedamount` is stored in the order's currency and the same product is
    sold in several: MS Windows Lisans has 287 TL lines, 7 USD and 2 EUR
    (2026-07-27). Summing them raw reported 446.63 "TL" for a product whose real
    weighted price is 471.41 TL."""
    sql = sq.PLATFORM_UNIT_PRICE_BY_PRODUCT
    assert "discovery_crm_pricelevels" in sql
    assert "exchangerate" in sql
    assert "extendedamount / fx.rate" in sql


def test_platform_price_drops_lines_it_cannot_convert():
    """An inner join, not a left join: a line whose currency has no active rate
    must not be averaged in as though it were already TL."""
    sql = sq.PLATFORM_UNIT_PRICE_BY_PRODUCT
    assert "JOIN   fx ON" in sql
    assert "LEFT JOIN   fx" not in sql


def test_platform_price_uses_the_entitlement_order_scope():
    sql = sq.PLATFORM_UNIT_PRICE_BY_PRODUCT
    assert "statecode IN (0, 1, 3, 4)" in sql
    assert "quantity > 0" in sql
