"""Unit tests for customer VM table metric formatting (readability refactor)."""

from dash import html

from src.pages.customer_view import _vm_metric_td, format_vm_metric_value


def test_format_vm_metric_value_defaults():
    assert format_vm_metric_value(None) == "0.0"
    assert format_vm_metric_value(0) == "0.0"


def test_format_vm_metric_value_percent_suffix():
    assert format_vm_metric_value(12.34, decimals=1, suffix="%") == "12.3%"


def test_format_vm_metric_value_plain_suffix():
    assert format_vm_metric_value(100.5, decimals=1, suffix=" MHz") == "100.5 MHz"
    assert format_vm_metric_value(1.25, decimals=2, suffix=" GiB") == "1.25 GiB"


def test_format_vm_metric_value_integer_decimals():
    assert format_vm_metric_value(8, decimals=0) == "8"
    assert format_vm_metric_value(8.9, decimals=0) == "9"


def test_vm_metric_td_aligns_and_formats():
    td = _vm_metric_td(10.2, suffix="%")
    assert isinstance(td, html.Td)
    assert td.children == "10.2%"
    assert td.style["textAlign"] == "right"
    assert td.style["fontVariantNumeric"] == "tabular-nums"
