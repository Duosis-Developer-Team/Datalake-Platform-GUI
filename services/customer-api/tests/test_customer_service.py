from unittest.mock import patch

from psycopg2 import OperationalError

from app.services.customer_service import CustomerService


def test_get_customer_list_returns_boyner():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    result = svc.get_customer_list()
    assert isinstance(result, list)
    assert "Boyner" in result


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
    assert "power_lpar_total" in totals
    assert "backup" in totals


def test_get_customer_resources_assets_structure_when_pool_none():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    result = svc.get_customer_resources("Boyner")
    assets = result["assets"]
    assert "intel" in assets
    assert "power" in assets
    assert "backup" in assets


def test_pool_is_none_when_db_unavailable():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    assert svc._pool is None
