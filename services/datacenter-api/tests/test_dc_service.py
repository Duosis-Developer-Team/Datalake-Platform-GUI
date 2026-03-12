from unittest.mock import patch

from psycopg2 import OperationalError

from app.services.dc_service import DatabaseService, DC_LOCATIONS, _DC_CODE_RE, _EMPTY_DC


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


def test_dc_locations_ict11_is_almanya():
    assert DC_LOCATIONS["ICT11"] == "Almanya"


def test_dc_locations_dc11_is_istanbul():
    assert DC_LOCATIONS["DC11"] == "Istanbul"


def test_dc_code_re_matches_dc_codes():
    import re
    assert _DC_CODE_RE.search("DC11-SERVER") is not None
    assert _DC_CODE_RE.search("AZ11-SERVER") is not None
    assert _DC_CODE_RE.search("ICT11-SERVER") is not None


def test_dc_code_re_does_not_match_random_strings():
    assert _DC_CODE_RE.search("RANDOM-TEXT") is None


def test_get_dc_details_returns_empty_dc_when_pool_is_none():
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    assert svc._pool is None
    result = svc.get_dc_details("DC11")
    assert result["meta"]["name"] == "DC11"
    assert result["intel"]["hosts"] == 0


def test_get_all_datacenters_summary_returns_empty_list_when_pool_is_none():
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    result = svc.get_all_datacenters_summary()
    assert isinstance(result, list)
    assert len(result) == 0


def test_get_global_overview_returns_dict_with_totals_when_pool_is_none():
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    result = svc.get_global_overview()
    assert "total_hosts" in result
    assert "dc_count" in result
    assert result["dc_count"] == 0


def test_get_global_dashboard_returns_dict_with_overview_when_pool_is_none():
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    result = svc.get_global_dashboard()
    assert "overview" in result
    assert "platforms" in result


def test_dc_list_property_returns_fallback_when_pool_is_none():
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    dc_list = svc.dc_list
    assert isinstance(dc_list, list)
    assert len(dc_list) > 0


def test_fetch_all_batch_returns_empty_list_when_pool_unavailable():
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    result = svc.get_all_datacenters_summary()
    assert result == []
