"""Unit tests for customer VM table metric formatting (readability refactor)."""

from dash import html

from src.pages.customer_view import _vm_metric_td, _vm_table, format_vm_metric_value


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


def _dummy_row(_r):
    return html.Tr([html.Td("x")])


def test_vm_table_comfortable_adds_wrap_class():
    out = _vm_table(
        [],
        ["A", "B"],
        _dummy_row,
        empty_cols=2,
        comfortable=True,
    )
    assert isinstance(out, html.Div)
    assert out.className == "customer-vm-table-wrap"
    table = out.children[0]
    assert getattr(table, "className", None) == "customer-vm-table"


def test_vm_table_default_no_wrap_class():
    out = _vm_table(
        [],
        ["A", "B"],
        _dummy_row,
        empty_cols=2,
        comfortable=False,
    )
    assert isinstance(out, html.Div)
    assert getattr(out, "className", None) in (None, "")
