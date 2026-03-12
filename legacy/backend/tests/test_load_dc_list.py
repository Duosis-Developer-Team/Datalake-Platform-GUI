from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from psycopg2 import OperationalError

from app.services.db_service import DatabaseService, _FALLBACK_DC_LIST


def _make_cur():
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.description = [("name",)]
    return cur


def _make_conn(cur):
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn


def _make_svc(mock_conn):
    with patch("app.services.db_service.pg_pool.ThreadedConnectionPool") as cls:
        pool = MagicMock()
        pool.getconn.return_value = mock_conn
        cls.return_value = pool
        svc = DatabaseService()

    @contextmanager
    def fake_conn():
        yield mock_conn

    svc._get_connection = fake_conn
    return svc


def test_load_dc_list_returns_names_from_db_when_status_query_succeeds():
    cur = _make_cur()
    cur.fetchall.side_effect = [[("DC11",), ("DC12",)]]
    svc = _make_svc(_make_conn(cur))
    result = svc._load_dc_list()
    assert result == ["DC11", "DC12"]


def test_load_dc_list_retries_without_status_when_first_query_empty():
    cur = _make_cur()
    cur.fetchall.side_effect = [[], [("AZ11",)]]
    svc = _make_svc(_make_conn(cur))
    result = svc._load_dc_list()
    assert result == ["AZ11"]


def test_load_dc_list_returns_fallback_when_both_queries_empty():
    cur = _make_cur()
    cur.fetchall.side_effect = [[], []]
    svc = _make_svc(_make_conn(cur))
    result = svc._load_dc_list()
    assert result == _FALLBACK_DC_LIST


def test_load_dc_list_returns_fallback_on_operational_error():
    cur = _make_cur()
    svc = _make_svc(_make_conn(cur))
    svc._get_connection = MagicMock(side_effect=OperationalError("db down"))
    result = svc._load_dc_list()
    assert result == _FALLBACK_DC_LIST
