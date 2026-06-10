"""Network dashboard callback tests (role-specific pages)."""

from __future__ import annotations

from unittest.mock import patch


def test_update_net_kpis_skips_firewall_tab():
    import app as app_module

    with patch.object(app_module, "api") as mock_api:
        result = app_module.update_net_kpis_and_charts(
            "firewall",
            None,
            None,
            None,
            {"preset": "last_7d"},
            "/datacenter/DC13",
        )
        assert result == (app_module.dash.no_update,) * 6
        mock_api.get_dc_network_port_summary.assert_not_called()


def test_update_net_interface_table_returns_footer_with_total():
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
            ],
            "total": 42,
        }

        rows, columns, page_size, footer = app_module.update_net_interface_table(
            "switch",
            "backbone",
            None,
            None,
            "",
            0,
            "50",
            {"preset": "last_7d"},
            "/datacenter/DC13",
        )

        mock_api.get_dc_network_interface_table.assert_called_once()
        assert len(rows) == 1
        assert page_size == 50
        assert "42" in footer
