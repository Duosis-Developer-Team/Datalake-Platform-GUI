from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from psycopg2 import OperationalError

from app.services.db_service import (
    DatabaseService,
    DC_LOCATIONS,
    _DC_CODE_RE,
    _EMPTY_DC,
)


def test_empty_dc_returns_meta_with_name_and_location():
    result = _EMPTY_DC("DC11")
    assert result["meta"]["name"] == "DC11"
    assert result["meta"]["location"] == "Istanbul"


def test_empty_dc_unknown_code_falls_back_to_unknown_data_center():
    result = _EMPTY_DC("DC99")
    assert result["meta"]["location"] == "Unknown Data Center"


def test_empty_dc_has_zero_intel_hosts():
    result = _EMPTY_DC("DC11")
    assert result["intel"]["hosts"] == 0
    assert result["intel"]["vms"] == 0
    assert result["intel"]["clusters"] == 0


def test_empty_dc_has_zero_energy():
    result = _EMPTY_DC("DC11")
    assert result["energy"]["total_kw"] == 0.0


def test_empty_dc_has_all_platform_entries():
    result = _EMPTY_DC("DC11")
    assert "nutanix" in result["platforms"]
    assert "vmware" in result["platforms"]
    assert "ibm" in result["platforms"]


def test_dc_locations_does_not_contain_duplicate_ict11_ingiltere():
    locations_values = list(DC_LOCATIONS.values())
    assert locations_values.count("İngiltere") == 0


def test_dc_locations_ict11_is_almanya():
    assert DC_LOCATIONS["ICT11"] == "Almanya"


def test_dc_locations_dc11_is_istanbul():
    assert DC_LOCATIONS["DC11"] == "Istanbul"


def test_prepare_params_wildcard_wraps_input_with_percent():
    result = DatabaseService._prepare_params("wildcard", "foo")
    assert result == ("%foo%",)


def test_prepare_params_wildcard_pair_returns_two_items():
    result = DatabaseService._prepare_params("wildcard_pair", "bar")
    assert result == ("%bar%", "%bar%")


def test_prepare_params_array_wildcard_splits_by_comma():
    result = DatabaseService._prepare_params("array_wildcard", "a,b,c")
    assert result == (["%a%", "%b%", "%c%"],)


def test_prepare_params_array_exact_splits_without_wildcard():
    result = DatabaseService._prepare_params("array_exact", "x,y")
    assert result == (["x", "y"],)


def test_prepare_params_exact_returns_stripped_string():
    result = DatabaseService._prepare_params("exact", "  hello  ")
    assert result == ("hello",)


def test_get_dc_details_returns_empty_dc_when_pool_is_none():
    with patch("app.services.db_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    assert svc._pool is None
    result = svc.get_dc_details("DC11")
    assert result["meta"]["name"] == "DC11"
    assert result["intel"]["hosts"] == 0


def test_get_all_datacenters_summary_returns_empty_list_when_pool_is_none():
    with patch("app.services.db_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    result = svc.get_all_datacenters_summary()
    assert isinstance(result, list)
    assert len(result) == 0


def test_get_global_overview_returns_dict_with_totals_when_pool_is_none():
    with patch("app.services.db_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    result = svc.get_global_overview()
    assert "total_hosts" in result
    assert "dc_count" in result
    assert result["dc_count"] == 0


def test_get_global_dashboard_returns_dict_with_overview_when_pool_is_none():
    with patch("app.services.db_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    result = svc.get_global_dashboard()
    assert "overview" in result
    assert "platforms" in result


def test_dc_list_property_returns_fallback_when_pool_is_none():
    with patch("app.services.db_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    dc_list = svc.dc_list
    assert isinstance(dc_list, list)
    assert len(dc_list) > 0


def test_get_customer_list_always_returns_boyner():
    with patch("app.services.db_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    assert svc.get_customer_list() == ["Boyner"]


def test_fetch_all_batch_returns_empty_dicts_for_each_dc_when_pool_unavailable():
    with patch("app.services.db_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    result = svc.get_all_datacenters_summary()
    assert result == []
