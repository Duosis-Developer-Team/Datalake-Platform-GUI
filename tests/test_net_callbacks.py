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


def test_update_net_interface_table_returns_footer_and_page_count():
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
                    "p95_billable_mbit": 5000.0,
                    "unit_price_tl_per_mbit": 331.12,
                    "estimated_cost_tl": 1_655_600.0,
                }
            ],
            "total": 42,
            "billing": {
                "enabled": True,
                "has_price": True,
                "unit_price_tl": 331.12,
                "price_source": "catalog",
            },
        }

        rows, columns, page_size, page_count, page_current, footer = app_module.update_net_interface_table(
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
        assert rows[0]["estimated_cost_tl"] == 1_655_600.0
        assert page_size == 50
        assert page_count == 1
        assert page_current == 0
        assert "42" in footer
        assert "Page est. cost" in footer


def test_update_net_interface_table_page_count_for_multiple_pages():
    import app as app_module

    with patch.object(app_module, "api") as mock_api:
        mock_api.get_dc_network_interface_table.return_value = {
            "items": [],
            "total": 100,
        }

        _, _, _, page_count, _, _ = app_module.update_net_interface_table(
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

        assert page_count == 2
