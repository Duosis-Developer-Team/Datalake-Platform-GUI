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


# ---------------------------------------------------------------------------
# Singleflight integration tests
# ---------------------------------------------------------------------------

def test_get_all_datacenters_summary_cache_miss_uses_singleflight():
    """Cache miss must route through cache.run_singleflight, not call _rebuild_summary directly."""
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()

    fake_summary = [{"id": "DC11", "name": "DC11"}]
    with patch("app.services.dc_service.cache.get", return_value=None), \
         patch("app.services.dc_service.cache.run_singleflight", return_value=fake_summary) as sf:
        result = svc.get_all_datacenters_summary({"start": "2026-04-01", "end": "2026-04-30"})

    assert result == fake_summary
    assert sf.call_count == 1
    key_arg = sf.call_args[0][0]
    assert key_arg == "all_dc_summary:2026-04-01:2026-04-30"


def test_get_dc_details_cache_miss_uses_singleflight():
    """Cache miss must route through cache.run_singleflight; OperationalError fallback must not be cached."""
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()

    fake_details = _EMPTY_DC("DC11")
    fake_details["meta"]["name"] = "DC11-patched"
    with patch("app.services.dc_service.cache.get", return_value=None), \
         patch("app.services.dc_service.cache.run_singleflight", return_value=fake_details) as sf:
        result = svc.get_dc_details("DC11", {"start": "2026-04-01", "end": "2026-04-30"})

    assert result["meta"]["name"] == "DC11-patched"
    assert sf.call_count == 1
    key_arg = sf.call_args[0][0]
    assert key_arg == "dc_details:DC11:2026-04-01:2026-04-30"


def test_get_dc_details_singleflight_raises_returns_empty_dc():
    """When singleflight raises OperationalError the method must return _EMPTY_DC without re-raising."""
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()

    with patch("app.services.dc_service.cache.get", return_value=None), \
         patch("app.services.dc_service.cache.run_singleflight", side_effect=OperationalError("db down")):
        result = svc.get_dc_details("DC11")

    assert result["meta"]["name"] == "DC11"
    assert result["intel"]["hosts"] == 0


def test_get_dc_racks_cache_miss_uses_singleflight_with_6h_ttl():
    """get_dc_racks cache miss must call run_singleflight with ttl=21600."""
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()

    fake_racks = {"racks": [], "summary": {"total_racks": 0, "active_racks": 0, "total_u_height": 0, "racks_with_energy": 0, "racks_with_pdu": 0}}
    with patch("app.services.dc_service.cache.get", return_value=None), \
         patch("app.services.dc_service.cache.run_singleflight", return_value=fake_racks) as sf:
        result = svc.get_dc_racks("DC11")

    assert result == fake_racks
    assert sf.call_count == 1
    _, _, kwargs = sf.call_args[0][0], sf.call_args[0][1], sf.call_args[1]
    assert kwargs.get("ttl") == 21600


def test_get_rack_devices_cache_miss_uses_singleflight_with_6h_ttl():
    """get_rack_devices cache miss must call run_singleflight with ttl=21600."""
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()

    fake_devices = {"devices": []}
    with patch("app.services.dc_service.cache.get", return_value=None), \
         patch("app.services.dc_service.cache.run_singleflight", return_value=fake_devices) as sf:
        result = svc.get_rack_devices("rack-01")

    assert result == fake_devices
    assert sf.call_count == 1
    _, _, kwargs = sf.call_args[0][0], sf.call_args[0][1], sf.call_args[1]
    assert kwargs.get("ttl") == 21600
