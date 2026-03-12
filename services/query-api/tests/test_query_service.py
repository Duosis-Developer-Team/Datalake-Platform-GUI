from unittest.mock import patch

from psycopg2 import OperationalError

from app.services.query_service import QueryService


def test_pool_is_none_when_db_unavailable():
    with patch("app.services.query_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = QueryService()
    assert svc._pool is None


def test_execute_registered_query_returns_error_when_pool_none():
    with patch("app.services.query_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = QueryService()
    result = svc.execute_registered_query("nutanix_host_count", "DC11")
    assert "error" in result


def test_execute_registered_query_unknown_key():
    with patch("app.services.query_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = QueryService()
    result = svc.execute_registered_query("nonexistent_query_key_xyz", "")
    assert "error" in result
    assert "nonexistent_query_key_xyz" in result["error"]


def test_prepare_params_wildcard():
    with patch("app.services.query_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = QueryService()
    result = svc._prepare_params("wildcard", "DC11")
    assert result == ("%DC11%",)


def test_prepare_params_wildcard_pair():
    with patch("app.services.query_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = QueryService()
    result = svc._prepare_params("wildcard_pair", "DC11")
    assert result == ("%DC11%", "%DC11%")


def test_prepare_params_array_wildcard():
    with patch("app.services.query_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = QueryService()
    result = svc._prepare_params("array_wildcard", "DC11,DC12")
    assert result == (["%DC11%", "%DC12%"],)


def test_prepare_params_array_exact():
    with patch("app.services.query_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = QueryService()
    result = svc._prepare_params("array_exact", "DC11,DC12")
    assert result == (["DC11", "DC12"],)


def test_prepare_params_exact():
    with patch("app.services.query_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = QueryService()
    result = svc._prepare_params("exact", "  DC11  ")
    assert result == ("DC11",)
