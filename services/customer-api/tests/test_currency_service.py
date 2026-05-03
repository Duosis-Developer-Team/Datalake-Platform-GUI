"""CurrencyService — TL conversion + cache TTL."""
from __future__ import annotations

import time
from contextlib import contextmanager
from unittest.mock import MagicMock

from app.services.currency_service import CurrencyService


@contextmanager
def _mock_conn(rows):
    """Yield a fake CustomerService whose `_get_connection()` returns a
    cursor with `_run_rows` -> ``rows``. Mirrors the real attribute names
    so we don't hide drift behind a mock."""
    svc = MagicMock()
    cur = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = None
    svc._get_connection.return_value.__enter__.return_value = conn
    svc._get_connection.return_value.__exit__.return_value = None
    svc._run_rows.return_value = rows
    yield svc


def test_tl_passthrough_no_db_call():
    with _mock_conn([]) as svc:
        cs = CurrencyService(svc)
        assert cs.to_tl(123.4, "TL") == 123.4
        assert svc._get_connection.call_count == 0


def test_usd_to_tl_uses_rate():
    """rate stored as base_per_foreign -> tl = amount / rate."""
    with _mock_conn([("USD", 0.025), ("EUR", 0.022)]) as svc:
        cs = CurrencyService(svc, ttl_seconds=60)
        cs.refresh(force=True)
        # 100 USD with rate 0.025 -> 4000 TL
        assert cs.to_tl(100.0, "USD") == 4000.0
        # 100 EUR with rate 0.022 -> ~4545.45 TL
        assert abs(cs.to_tl(100.0, "EUR") - (100.0 / 0.022)) < 1e-6


def test_unknown_currency_returns_none():
    with _mock_conn([("USD", 0.025)]) as svc:
        cs = CurrencyService(svc, ttl_seconds=60)
        cs.refresh(force=True)
        assert cs.to_tl(100.0, "ZWD") is None


def test_zero_rate_treated_as_unknown():
    with _mock_conn([("XXX", 0.0), ("USD", 0.0)]) as svc:
        cs = CurrencyService(svc, ttl_seconds=60)
        cs.refresh(force=True)
        # Both filtered out at refresh time -> not present
        assert cs.to_tl(100.0, "USD") is None
        assert cs.to_tl(100.0, "XXX") is None


def test_none_amount_returns_none():
    with _mock_conn([]) as svc:
        cs = CurrencyService(svc)
        assert cs.to_tl(None, "TL") is None


def test_refresh_respects_ttl():
    """A second refresh inside the TTL window must NOT hit the DB."""
    with _mock_conn([("USD", 0.025)]) as svc:
        cs = CurrencyService(svc, ttl_seconds=10)
        cs.refresh(force=True)
        first_calls = svc._run_rows.call_count
        # Inside TTL -> no extra call
        cs.refresh()
        assert svc._run_rows.call_count == first_calls


def test_refresh_force_invalidates_cache():
    with _mock_conn([("USD", 0.025)]) as svc:
        cs = CurrencyService(svc, ttl_seconds=3600)
        cs.refresh(force=True)
        first_calls = svc._run_rows.call_count
        cs.refresh(force=True)
        assert svc._run_rows.call_count == first_calls + 1


def test_get_rate_for_none_currency_returns_one():
    with _mock_conn([]) as svc:
        cs = CurrencyService(svc)
        assert cs.get_rate(None) == 1.0
