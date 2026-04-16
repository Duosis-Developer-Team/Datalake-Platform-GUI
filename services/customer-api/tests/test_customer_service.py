from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from psycopg2 import OperationalError

from app.db.queries import customer as cq
from app.services.customer_service import CustomerService


def test_get_customer_list_empty_without_db_and_no_env(monkeypatch):
    monkeypatch.delenv("WARMED_CUSTOMERS", raising=False)
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    assert svc.get_customer_list() == []


def test_get_customer_list_respects_warmed_customers_env(monkeypatch):
    monkeypatch.setenv("WARMED_CUSTOMERS", "Acme, Beta")
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    assert svc.get_customer_list() == ["Acme", "Beta"]


def test_get_customer_resources_returns_empty_when_pool_none():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    assert svc._pool is None
    result = svc.get_customer_resources("Boyner")
    assert "totals" in result
    assert "assets" in result
    assert result["totals"]["vms_total"] == 0


def test_get_customer_resources_totals_structure_when_pool_none():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    result = svc.get_customer_resources("Boyner")
    totals = result["totals"]
    assert "intel_vms_total" in totals
    assert "classic_vms_total" in totals
    assert "hyperconv_vms_total" in totals
    assert "pure_nutanix_vms_total" in totals
    assert "power_lpar_total" in totals
    assert "backup" in totals


def test_get_customer_resources_assets_structure_when_pool_none():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    result = svc.get_customer_resources("Boyner")
    assets = result["assets"]
    assert "intel" in assets
    assert "classic" in assets
    assert "hyperconv" in assets
    assert "pure_nutanix" in assets
    assert "power" in assets
    assert "backup" in assets


def test_pool_is_none_when_db_unavailable():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    assert svc._pool is None


def test_get_cluster_arch_map_does_not_cache_when_pool_none():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()

    with patch("app.services.customer_service.time_range_to_bounds", return_value=("start-ts", "end-ts")), \
         patch("app.services.customer_service.cache.run_singleflight") as sf_mock:
        result = svc._get_cluster_arch_map({"preset": "7d"})

    assert result == {"managed_nutanix": [], "pure_nutanix": []}
    sf_mock.assert_not_called()


def test_get_cluster_arch_map_uses_latest_fallback_when_range_clusters_missing():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    svc._pool = object()

    class _CursorCtx:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    class _ConnCtx:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return _CursorCtx()

    def _run_rows_side_effect(_cur, sql, params=None):
        if sql == cq.ALL_VMWARE_CLUSTER_NAMES:
            return [("vmw-cluster", "hyperconv")]
        if sql == cq.ALL_NUTANIX_CLUSTER_NAMES:
            return []
        if sql == cq.ALL_NUTANIX_CLUSTER_NAMES_LATEST:
            return [("ntx-cluster", "uuid-1")]
        return []

    with patch.object(svc, "_get_connection", return_value=_ConnCtx()), \
         patch.object(svc, "_run_rows", side_effect=_run_rows_side_effect) as run_rows_mock, \
         patch("app.services.customer_service.time_range_to_bounds", return_value=("start-ts", "end-ts")), \
         patch("app.core.cache_backend.cache_get", return_value=None), \
         patch("app.core.cache_backend.cache_set"), \
         patch("app.services.customer_service.build_cluster_arch_map", return_value={"managed_nutanix": ["ntx-cluster"], "pure_nutanix": []}):
        result = svc._get_cluster_arch_map({"preset": "7d"})

    assert result == {"managed_nutanix": ["ntx-cluster"], "pure_nutanix": []}
    queried_sql = [call.args[1] for call in run_rows_mock.call_args_list]
    assert cq.ALL_NUTANIX_CLUSTER_NAMES in queried_sql
    assert cq.ALL_NUTANIX_CLUSTER_NAMES_LATEST in queried_sql


def test_get_customer_resources_raises_503_when_db_error_not_cached():
    mock_pool = MagicMock()
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", return_value=mock_pool):
        svc = CustomerService()
    with patch("app.services.customer_service.cache.run_singleflight", side_effect=OperationalError("ssl eof")):
        with pytest.raises(HTTPException) as exc_info:
            svc.get_customer_resources("Boyner")
    assert exc_info.value.status_code == 503


def test_get_connection_discards_pool_conn_on_fatal_operational_error():
    mock_pool = MagicMock()
    conn = MagicMock()
    mock_pool.getconn.return_value = conn
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", return_value=mock_pool):
        svc = CustomerService()

    with pytest.raises(OperationalError):
        with svc._get_connection():
            raise OperationalError("SSL SYSCALL error: EOF detected")

    mock_pool.putconn.assert_called_once_with(conn, close=True)


def test_get_connection_returns_conn_to_pool_on_statement_timeout():
    mock_pool = MagicMock()
    conn = MagicMock()
    mock_pool.getconn.return_value = conn
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", return_value=mock_pool):
        svc = CustomerService()

    err = OperationalError("canceling statement due to statement timeout")
    with pytest.raises(OperationalError):
        with svc._get_connection():
            raise err

    mock_pool.putconn.assert_called_once_with(conn, close=False)
