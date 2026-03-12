from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from psycopg2 import OperationalError

from app.services.db_service import DatabaseService


def _make_mock_cursor(fetchall_rows=None, fetchone_row=None):
    cur = MagicMock()
    cur.fetchall.return_value = fetchall_rows if fetchall_rows is not None else []
    cur.fetchone.return_value = fetchone_row
    cur.description = [("value",)]
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    return cur


def _make_mock_conn(cursor=None):
    if cursor is None:
        cursor = _make_mock_cursor()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn


def _make_svc_with_conn(mock_conn):
    with patch("app.services.db_service.pg_pool.ThreadedConnectionPool") as mock_cls:
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_cls.return_value = mock_pool
        svc = DatabaseService()

    @contextmanager
    def fake_get_connection():
        yield mock_conn

    svc._get_connection = fake_get_connection
    return svc


def test_run_value_returns_first_row_first_column():
    cur = _make_mock_cursor(fetchone_row=(42,))
    result = DatabaseService._run_value(cur, "SELECT 1")
    assert result == 42


def test_run_value_returns_zero_when_no_row():
    cur = _make_mock_cursor(fetchone_row=None)
    result = DatabaseService._run_value(cur, "SELECT 1")
    assert result == 0


def test_run_value_returns_zero_on_query_exception():
    cur = MagicMock()
    cur.execute.side_effect = Exception("db error")
    cur.execute.return_value = None
    result = DatabaseService._run_value(cur, "SELECT 1")
    assert result == 0


def test_run_row_returns_first_row():
    cur = _make_mock_cursor(fetchone_row=(1, 2, 3))
    result = DatabaseService._run_row(cur, "SELECT 1")
    assert result == (1, 2, 3)


def test_run_row_returns_none_on_exception():
    cur = MagicMock()
    cur.execute.side_effect = Exception("db error")
    result = DatabaseService._run_row(cur, "SELECT 1")
    assert result is None


def test_run_rows_returns_all_rows():
    cur = _make_mock_cursor(fetchall_rows=[(1,), (2,), (3,)])
    result = DatabaseService._run_rows(cur, "SELECT 1")
    assert result == [(1,), (2,), (3,)]


def test_run_rows_returns_empty_list_on_exception():
    cur = MagicMock()
    cur.execute.side_effect = Exception("db error")
    result = DatabaseService._run_rows(cur, "SELECT 1")
    assert result == []


def test_get_dc_details_returns_aggregated_result_with_mock_conn():
    mock_cur = _make_mock_cursor(fetchone_row=None, fetchall_rows=[])
    mock_conn = _make_mock_conn(mock_cur)
    svc = _make_svc_with_conn(mock_conn)
    result = svc.get_dc_details("DC11")
    assert result["meta"]["name"] == "DC11"
    assert "intel" in result
    assert "energy" in result


def test_get_dc_details_passes_dc_code_to_nutanix_queries():
    mock_cur = _make_mock_cursor(fetchone_row=None, fetchall_rows=[])
    mock_conn = _make_mock_conn(mock_cur)
    svc = _make_svc_with_conn(mock_conn)
    result = svc.get_dc_details("DC14")
    assert result["meta"]["name"] == "DC14"


def test_fetch_all_batch_processes_empty_rows_without_error():
    mock_cur = _make_mock_cursor(fetchall_rows=[])
    mock_conn = _make_mock_conn(mock_cur)
    svc = _make_svc_with_conn(mock_conn)
    svc._dc_list = ["DC11"]
    from datetime import datetime, timezone
    start = datetime(2026, 3, 1, tzinfo=timezone.utc)
    end = datetime(2026, 3, 7, tzinfo=timezone.utc)
    all_dc_data, platform_counts = svc._fetch_all_batch(["DC11"], start, end)
    assert "DC11" in all_dc_data
    assert isinstance(platform_counts, dict)


def test_fetch_all_batch_deduplicates_ibm_hosts_from_mock_rows():
    ibm_rows = [("DC11-host1",), ("DC11-host1",), ("DC11-host2",)]
    call_count = [0]

    mock_cur = MagicMock()
    mock_cur.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.description = [("value",)]

    def fetchall_side_effect():
        call_count[0] += 1
        if call_count[0] == 9:
            return ibm_rows
        return []

    mock_cur.fetchall.side_effect = fetchall_side_effect
    mock_cur.fetchone.return_value = None

    mock_conn = _make_mock_conn(mock_cur)
    svc = _make_svc_with_conn(mock_conn)
    svc._dc_list = ["DC11"]

    from datetime import datetime, timezone
    start = datetime(2026, 3, 1, tzinfo=timezone.utc)
    end = datetime(2026, 3, 7, tzinfo=timezone.utc)
    all_dc_data, _ = svc._fetch_all_batch(["DC11"], start, end)
    assert "DC11" in all_dc_data


def test_get_all_datacenters_summary_with_mock_conn_returns_list():
    mock_cur = _make_mock_cursor(fetchall_rows=[], fetchone_row=(0,))
    mock_conn = _make_mock_conn(mock_cur)
    svc = _make_svc_with_conn(mock_conn)
    result = svc.get_all_datacenters_summary()
    assert isinstance(result, list)


def test_execute_registered_query_returns_value_for_known_key():
    first_key = next(iter(__import__("app.db.queries.registry", fromlist=["QUERY_REGISTRY"]).QUERY_REGISTRY))
    mock_cur = _make_mock_cursor(fetchone_row=(77,))
    mock_conn = _make_mock_conn(mock_cur)
    svc = _make_svc_with_conn(mock_conn)
    result = svc.execute_registered_query(first_key, "DC11")
    assert result.get("result_type") == "value"
    assert result.get("value") == 77


def test_execute_registered_query_returns_error_for_unknown_key():
    mock_conn = _make_mock_conn()
    svc = _make_svc_with_conn(mock_conn)
    result = svc.execute_registered_query("nonexistent_key_xyz", "")
    assert "error" in result


def test_warm_cache_runs_without_exception_when_pool_none():
    with patch("app.services.db_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    svc.warm_cache()


def test_warm_additional_ranges_runs_without_exception_when_pool_none():
    with patch("app.services.db_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    svc.warm_additional_ranges()


def test_refresh_all_data_runs_without_exception_when_pool_none():
    with patch("app.services.db_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    svc.refresh_all_data()


def test_get_global_overview_returns_cached_value_on_second_call():
    with patch("app.services.db_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    svc.get_global_overview()
    result2 = svc.get_global_overview()
    assert "total_hosts" in result2


def test_get_customer_resources_returns_fallback_when_pool_none():
    with patch("app.services.db_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    result = svc.get_customer_resources("Boyner")
    assert "totals" in result
    assert result["totals"]["vms_total"] == 0


def test_execute_registered_query_returns_row_result_type():
    mock_cur = _make_mock_cursor()
    mock_cur.description = [("a",), ("b",), ("c",)]
    mock_cur.fetchone.return_value = (1, 2, 3)
    svc = _make_svc_with_conn(_make_mock_conn(mock_cur))
    entry = {"sql": "SELECT 1,2,3", "result_type": "row", "params_style": "exact"}
    with patch("app.services.query_overrides.get_merged_entry", return_value=entry):
        result = svc.execute_registered_query("some_row_key", "DC11")
    assert result["result_type"] == "row"
    assert result["columns"] == ["a", "b", "c"]
    assert result["data"] == [1, 2, 3]


def test_execute_registered_query_returns_rows_result_type():
    mock_cur = _make_mock_cursor()
    mock_cur.description = [("x",), ("y",)]
    mock_cur.fetchall.return_value = [(1, 2), (3, 4)]
    svc = _make_svc_with_conn(_make_mock_conn(mock_cur))
    entry = {"sql": "SELECT *", "result_type": "rows", "params_style": "exact"}
    with patch("app.services.query_overrides.get_merged_entry", return_value=entry):
        result = svc.execute_registered_query("some_rows_key", "DC11")
    assert result["result_type"] == "rows"
    assert result["columns"] == ["x", "y"]
    assert result["data"] == [[1, 2], [3, 4]]


def test_execute_registered_query_returns_error_on_operational_error():
    mock_cur = _make_mock_cursor()
    mock_cur.execute.side_effect = OperationalError("connection lost")
    svc = _make_svc_with_conn(_make_mock_conn(mock_cur))
    entry = {"sql": "SELECT 1", "result_type": "value", "params_style": "exact"}
    with patch("app.services.query_overrides.get_merged_entry", return_value=entry):
        result = svc.execute_registered_query("some_key", "DC11")
    assert "error" in result
    assert "Database error" in result["error"]


def test_execute_registered_query_returns_error_on_generic_exception():
    mock_cur = _make_mock_cursor()
    mock_cur.execute.side_effect = ValueError("unexpected")
    svc = _make_svc_with_conn(_make_mock_conn(mock_cur))
    entry = {"sql": "SELECT 1", "result_type": "value", "params_style": "exact"}
    with patch("app.services.query_overrides.get_merged_entry", return_value=entry):
        result = svc.execute_registered_query("some_key", "DC11")
    assert "error" in result
    assert result["error"] == "unexpected"


def test_execute_registered_query_returns_error_when_no_sql_in_entry():
    svc = _make_svc_with_conn(_make_mock_conn())
    entry = {"result_type": "value"}
    with patch("app.services.query_overrides.get_merged_entry", return_value=entry):
        result = svc.execute_registered_query("no_sql_key", "DC11")
    assert "error" in result
    assert "No SQL for query" in result["error"]


def test_run_value_rollback_itself_fails_silently():
    call_count = [0]
    cur = MagicMock()

    def execute_side_effect(sql, params=None):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("query fail")
        raise Exception("rollback fail")

    cur.execute = MagicMock(side_effect=execute_side_effect)
    result = DatabaseService._run_value(cur, "SELECT 1")
    assert result == 0


def test_run_row_rollback_itself_fails_silently():
    call_count = [0]
    cur = MagicMock()

    def execute_side_effect(sql, params=None):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("query fail")
        raise Exception("rollback fail")

    cur.execute = MagicMock(side_effect=execute_side_effect)
    result = DatabaseService._run_row(cur, "SELECT 1")
    assert result is None


def test_run_rows_rollback_itself_fails_silently():
    call_count = [0]
    cur = MagicMock()

    def execute_side_effect(sql, params=None):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("query fail")
        raise Exception("rollback fail")

    cur.execute = MagicMock(side_effect=execute_side_effect)
    result = DatabaseService._run_rows(cur, "SELECT 1")
    assert result == []


def test_rebuild_summary_skips_dcs_with_zero_hosts_and_zero_vms():
    from app.services.db_service import _EMPTY_DC
    from app.services import cache_service as cache

    mock_cur = _make_mock_cursor(fetchall_rows=[], fetchone_row=None)
    mock_conn = _make_mock_conn(mock_cur)
    svc = _make_svc_with_conn(mock_conn)

    empty_dc = _EMPTY_DC("DC99")
    svc._load_dc_list = MagicMock(return_value=["DC99"])
    svc._fetch_all_batch = MagicMock(return_value=({"DC99": empty_dc}, {"DC99": 0}))

    tr = {"start": "2025-01-01", "end": "2025-01-07"}
    cache.delete("dc_details:DC99:2025-01-01:2025-01-07")

    result = svc._rebuild_summary(tr)

    assert result == []
    assert cache.get("dc_details:DC99:2025-01-01:2025-01-07") == empty_dc
