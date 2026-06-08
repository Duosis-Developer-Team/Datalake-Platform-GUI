"""Tests for Zabbix network cache warm/refresh (scheduler integration)."""

from __future__ import annotations

from unittest.mock import patch

from psycopg2 import OperationalError

from app.services.dc_service import DatabaseService


def _make_service(dc_list=("DC11", "DC13")):
    with patch("app.services.dc_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = DatabaseService()
    svc._dc_list = list(dc_list)
    return svc


def test_warm_network_cache_skips_dc_without_devices():
    svc = _make_service(dc_list=("DC11", "DC13"))

    with patch.object(svc, "get_network_filters") as p_filters, \
         patch.object(svc, "get_network_port_summary") as p_summary, \
         patch.object(svc, "get_network_95th_percentile") as p_p95, \
         patch.object(svc, "get_network_interface_table") as p_table:
        p_filters.return_value = {"manufacturers": []}

        svc.warm_network_cache()

    assert p_filters.call_count == 2
    p_summary.assert_not_called()
    p_p95.assert_not_called()
    p_table.assert_not_called()


def test_warm_network_cache_warms_all_endpoints_for_dcs_with_devices():
    svc = _make_service(dc_list=("DC11",))

    with patch.object(svc, "get_network_filters") as p_filters, \
         patch.object(svc, "get_network_port_summary") as p_summary, \
         patch.object(svc, "get_network_95th_percentile") as p_p95, \
         patch.object(svc, "get_network_interface_table") as p_table:
        p_filters.return_value = {"manufacturers": ["Fortinet"]}

        svc.warm_network_cache()

    p_summary.assert_called_once_with("DC11", p_summary.call_args[0][1])
    p_p95.assert_called_once()
    assert p_p95.call_args.kwargs.get("top_n") == 20
    p_table.assert_called_once()
    assert p_table.call_args.kwargs.get("page") == 1
    assert p_table.call_args.kwargs.get("page_size") == 50


def test_warm_network_cache_tolerates_per_dc_failure():
    svc = _make_service(dc_list=("DC11", "DC13"))

    def _filters(dc_code, tr):
        if dc_code == "DC11":
            raise RuntimeError("boom")
        return {"manufacturers": ["Fortinet"]}

    with patch.object(svc, "get_network_filters", side_effect=_filters), \
         patch.object(svc, "get_network_port_summary") as p_summary, \
         patch.object(svc, "get_network_95th_percentile") as p_p95, \
         patch.object(svc, "get_network_interface_table") as p_table:

        svc.warm_network_cache()  # must not raise

    assert p_summary.call_count == 1
    assert p_p95.call_count == 1
    assert p_table.call_count == 1


def test_refresh_network_cache_iterates_standard_ranges():
    svc = _make_service(dc_list=("DC11",))

    ranges = [{"preset": "7d"}, {"preset": "30d"}]

    with patch("app.services.dc_service.cache_time_ranges", return_value=ranges), \
         patch.object(svc, "_warm_network_cache_for_range") as p_warm:

        svc.refresh_network_cache()

    assert p_warm.call_count == 2
    p_warm.assert_any_call(ranges[0])
    p_warm.assert_any_call(ranges[1])
