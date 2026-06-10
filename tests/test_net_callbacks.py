"""Network dashboard callback tests (scope-aware API mapping)."""

from __future__ import annotations

from unittest.mock import patch


def test_update_net_kpis_passes_interface_scope_for_backbone():
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
            "switch",
            "backbone",
            None,
            None,
            {"preset": "last_7d"},
            "/datacenter/DC13",
        )

        mock_api.get_dc_network_port_summary.assert_called_once()
        mock_api.get_dc_network_95th_percentile.assert_called_once()
        _, kwargs = mock_api.get_dc_network_port_summary.call_args
        assert kwargs.get("interface_scope") == "backbone"
        _, pct_kwargs = mock_api.get_dc_network_95th_percentile.call_args
        assert pct_kwargs.get("interface_scope") == "backbone"
        assert kpis is not None
        assert donut_active is not None
        assert donut_util is not None
        assert donut_icmp is not None
        assert bar_fig is not None


def test_update_net_interface_table_passes_interface_scope():
    import app as app_module

    with patch.object(app_module, "api") as mock_api:
        mock_api.get_dc_network_interface_table.return_value = {
            "items": [
                {
                    "host": "sw-01",
                    "interface_name": "eth0",
                    "interface_alias": "",
                    "p95_rx_bps": 2_000_000_000,
                    "p95_tx_bps": 3_000_000_000,
                    "p95_total_bps": 5_000_000_000,
                    "speed_bps": 10_000_000_000,
                    "utilization_pct": 50.0,
                }
            ]
        }

        rows, columns = app_module.update_net_interface_table(
            "router_uplink",
            None,
            None,
            None,
            "",
            0,
            50,
            {"preset": "last_7d"},
            "/datacenter/DC13",
        )

        mock_api.get_dc_network_interface_table.assert_called_once()
        _, kwargs = mock_api.get_dc_network_interface_table.call_args
        assert kwargs.get("interface_scope") == "router_uplink"
        assert len(rows) == 1
        assert rows[0]["interface_name"] == "eth0"
        assert any(c["id"] == "p95_total_gbps" for c in columns)
