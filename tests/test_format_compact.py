"""Tests for compact vs full number formatting."""

from __future__ import annotations

from src.utils.format_units import (
    format_compact_decimal,
    format_compact_money_tl,
    format_full_decimal,
)


def test_format_compact_decimal_abbreviates_large_values():
    assert format_compact_decimal(5000) == "5.00K"
    assert format_compact_decimal(1_655_600) == "1.66M"


def test_format_full_decimal_keeps_precision():
    assert format_full_decimal(1655600.0, decimals=2) == "1,655,600.00"
    assert format_full_decimal(331.12, decimals=4) == "331.1200"


def test_format_compact_money_tl():
    assert format_compact_money_tl(1655600.0) == "1.66M TL"


def test_backbone_table_rows_use_compact_display():
    from src.pages import dc_view

    rows = dc_view._interface_table_rows(
        [
            {
                "host": "sw-01",
                "interface_name": "eth0",
                "p95_rx_bps": 1e9,
                "p95_tx_bps": 2e9,
                "p95_total_bps": 3e9,
                "speed_bps": 10e9,
                "utilization_pct": 30.0,
                "p95_billable_mbit": 5000.0,
                "unit_price_tl_per_mbit": 331.12,
                "estimated_cost_tl": 1655600.0,
            }
        ],
        interface_scope="backbone",
    )
    assert rows[0]["p95_billable_mbit"] == "5.00K"
    assert rows[0]["estimated_cost_tl"] == "1.66M TL"
    assert rows[0]["unit_price_tl_per_mbit"] == "331.1200"
