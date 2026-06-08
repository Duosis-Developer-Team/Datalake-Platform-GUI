"""Network dashboard callback tests (no tab lazy-load guard)."""

from __future__ import annotations

from unittest.mock import patch


def test_update_net_kpis_fetches_without_main_tab_guard():
    import app as app_module

    with patch.object(app_module, "api") as mock_api:
        mock_api.get_dc_network_port_summary.return_value = {
            "device_count": 2,
            "total_ports": 100,
            "active_ports": 80,
            "avg_icmp_loss_pct": 1.0,
        }
        mock_api.get_dc_network_95th_percentile.return_value = {
            "overall_port_utilization_pct": 40.0,
            "top_interfaces": [],
        }

        kpis, donut_active, donut_util, donut_icmp, bar_fig = app_module.update_net_kpis_and_charts(
            None,
            None,
            None,
            None,
            "/datacenter/DC13",
        )

        mock_api.get_dc_network_port_summary.assert_called_once()
        mock_api.get_dc_network_95th_percentile.assert_called_once()
        assert kpis is not None
        assert donut_active is not None
        assert donut_util is not None
        assert donut_icmp is not None
        assert bar_fig is not None


def test_update_net_interface_table_fetches_without_main_tab_guard():
    import app as app_module

    with patch.object(app_module, "api") as mock_api:
        mock_api.get_dc_network_interface_table.return_value = {
            "items": [
                {
                    "interface_name": "eth0",
                    "interface_alias": "",
                    "p95_total_bps": 5_000_000_000,
                    "speed_bps": 10_000_000_000,
                    "utilization_pct": 50.0,
                }
            ]
        }

        rows = app_module.update_net_interface_table(
            None,
            None,
            None,
            "",
            0,
            50,
            None,
            "/datacenter/DC13",
        )

        mock_api.get_dc_network_interface_table.assert_called_once()
        assert len(rows) == 1
        assert rows[0]["interface_name"] == "eth0"
