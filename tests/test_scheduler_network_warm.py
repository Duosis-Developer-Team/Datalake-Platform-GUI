"""Tests for GUI scheduler network cache warm helpers."""

from __future__ import annotations

from unittest.mock import patch

from src.services import scheduler_service


def test_warm_dc_network_for_range_skips_dc_without_manufacturers():
    summaries = [{"id": "DC11"}, {"id": "DC13"}]

    with patch.object(scheduler_service.api, "get_all_datacenters_summary", return_value=summaries), \
         patch.object(scheduler_service.api, "get_dc_network_filters") as p_filters, \
         patch.object(scheduler_service.api, "get_dc_network_port_summary") as p_summary:
        p_filters.return_value = {"manufacturers": []}

        scheduler_service._warm_dc_network_for_range({"preset": "7d"})

    assert p_filters.call_count == 2
    p_summary.assert_not_called()


def test_warm_dc_network_for_range_calls_all_endpoints():
    summaries = [{"id": "DC11"}]

    with patch.object(scheduler_service.api, "get_all_datacenters_summary", return_value=summaries), \
         patch.object(scheduler_service.api, "get_dc_network_filters") as p_filters, \
         patch.object(scheduler_service.api, "get_dc_network_port_summary") as p_summary, \
         patch.object(scheduler_service.api, "get_dc_network_95th_percentile") as p_p95, \
         patch.object(scheduler_service.api, "get_dc_network_interface_table") as p_table:
        p_filters.return_value = {"manufacturers": ["Fortinet"]}

        scheduler_service._warm_dc_network_for_range({"preset": "7d"})

    p_summary.assert_called_once()
    p_p95.assert_called_once()
    p_table.assert_called_once()
