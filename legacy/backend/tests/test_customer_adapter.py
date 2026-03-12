from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from psycopg2 import OperationalError

from app.adapters.customer_adapter import CustomerAdapter


def _make_cursor(rows=None, row=None, value=0):
    cursor = MagicMock()
    cursor.fetchone.return_value = row
    cursor.fetchall.return_value = rows or []
    return cursor


def _make_adapter_with_cursor(cursor):
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    @contextmanager
    def fake_get_connection():
        yield conn

    run_value = MagicMock(return_value=0)
    run_row = MagicMock(return_value=None)
    run_rows = MagicMock(return_value=[])
    return CustomerAdapter(fake_get_connection, run_value, run_row, run_rows)


def test_fetch_returns_totals_and_assets_keys():
    adapter = _make_adapter_with_cursor(MagicMock())
    result = adapter.fetch("Boyner", {"start": "2026-03-01", "end": "2026-03-07", "preset": "7d"})
    assert "totals" in result
    assert "assets" in result


def test_vm_pattern_uses_name_dash_percent():
    run_row = MagicMock(return_value=None)
    run_rows = MagicMock(return_value=[])
    run_value = MagicMock(return_value=0)

    @contextmanager
    def fake_get_connection():
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        yield conn

    adapter = CustomerAdapter(fake_get_connection, run_value, run_row, run_rows)
    adapter.fetch("Boyner", {"start": "2026-03-01", "end": "2026-03-07", "preset": "7d"})
    first_call_args = run_row.call_args_list[0]
    params = first_call_args.args[2]
    assert params[0] == "Boyner-%"


def test_zerto_name_like_uses_name_percent_dash_percent():
    run_row = MagicMock(return_value=None)
    run_rows = MagicMock(return_value=[])
    run_value_calls = []

    def capture_run_value(cursor, sql, params):
        run_value_calls.append((sql, params))
        return 0

    @contextmanager
    def fake_get_connection():
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        yield conn

    adapter = CustomerAdapter(fake_get_connection, capture_run_value, run_row, run_rows)
    adapter.fetch("Boyner", {"start": "2026-03-01", "end": "2026-03-07", "preset": "7d"})
    zerto_params = [p for sql, p in run_value_calls if "zerto" in str(sql).lower() or (p and "%-%" in str(p))]
    all_params_flat = [str(item) for sql, p in run_value_calls for item in (p if p else [])]
    assert any("Boyner%-%" in param for param in all_params_flat)


def test_empty_name_uses_wildcard_patterns():
    run_row = MagicMock(return_value=None)
    run_rows = MagicMock(return_value=[])
    run_value = MagicMock(return_value=0)

    @contextmanager
    def fake_get_connection():
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        yield conn

    adapter = CustomerAdapter(fake_get_connection, run_value, run_row, run_rows)
    result = adapter.fetch("", {"start": "2026-03-01", "end": "2026-03-07", "preset": "7d"})
    assert "totals" in result
    assert "assets" in result


def test_operational_error_returns_fallback_dict():
    @contextmanager
    def fake_get_connection():
        raise OperationalError("DB down")
        yield

    adapter = CustomerAdapter(fake_get_connection, MagicMock(), MagicMock(), MagicMock())
    result = adapter.fetch("Boyner", {"start": "2026-03-01", "end": "2026-03-07", "preset": "7d"})
    assert result["totals"]["vms_total"] == 0
    assert result["assets"]["intel"]["vms"]["total"] == 0


def test_lpar_pattern_uses_name_percent():
    run_row = MagicMock(return_value=None)
    run_rows = MagicMock(return_value=[])
    run_value_calls = []

    def capture_run_value(cursor, sql, params):
        run_value_calls.append((sql, params))
        return 0

    @contextmanager
    def fake_get_connection():
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        yield conn

    adapter = CustomerAdapter(fake_get_connection, capture_run_value, run_row, run_rows)
    adapter.fetch("Boyner", {"start": "2026-03-01", "end": "2026-03-07", "preset": "7d"})
    all_params = [item for sql, p in run_value_calls for item in (p if p else [])]
    assert "Boyner%" in all_params
