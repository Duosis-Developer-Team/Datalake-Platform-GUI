"""Guard: load_customer_view_data / toggle must raise dash.exceptions.PreventUpdate.

Regression for AttributeError: module 'dash' has no attribute 'PreventUpdate'
which 500'd every /_dash-update-component when pathname was not /customer-view.
"""
from __future__ import annotations

import pytest
from dash.exceptions import PreventUpdate

from src.pages.customer_view_callbacks import (
    load_customer_view_data,
    toggle_customer_perspective,
)


def test_load_customer_view_data_wrong_pathname_raises_prevent_update():
    with pytest.raises(PreventUpdate):
        load_customer_view_data("/customers", "?customer=Boyner", None, None)


def test_load_customer_view_data_missing_customer_raises_prevent_update():
    with pytest.raises(PreventUpdate):
        load_customer_view_data("/customer-view", "", None, None)


def test_load_customer_view_data_blank_customer_raises_prevent_update():
    with pytest.raises(PreventUpdate):
        load_customer_view_data("/customer-view", "?customer=%20", None, None)


def test_toggle_customer_perspective_missing_customer_raises_prevent_update():
    with pytest.raises(PreventUpdate):
        toggle_customer_perspective("manager", "", None, None)


def test_prevent_update_is_dash_exceptions_class():
    """Ensure we never regress to raise dash.PreventUpdate (missing attribute)."""
    import dash

    assert not hasattr(dash, "PreventUpdate")
    assert issubclass(PreventUpdate, Exception)
