"""Customer view export callback guards and static toolbar wiring."""
from __future__ import annotations

import pytest


def test_export_customer_view_prevents_without_clicks():
    from src.pages.customer_view import export_customer_view
    import dash

    with pytest.raises(dash.exceptions.PreventUpdate):
        export_customer_view(None, None, {"customer": "Acme", "export_context": {}}, {})


def test_build_customer_layout_has_static_export_buttons():
    from src.pages.customer_view import build_customer_layout

    layout = build_customer_layout(selected_customer="Acme Corp")
    text = str(layout)
    assert "customer-export-toolbar" in text
    assert "customer-export-csv" in text
    assert "customer-export-xlsx" in text


def test_export_sheets_built_from_context_on_demand():
    from src.pages.customer_view import _export_sheets_from_store

    sheets = _export_sheets_from_store(
        {
            "customer": "Acme Corp",
            "export_context": {
                "customer_name": "Acme Corp",
                "totals": {"vms_total": 2},
                "backup_totals": {},
                "assets": {},
                "classic": {},
                "hyperconv": {},
                "pure_nx": {},
                "power_asset": {},
                "s3_data": {},
                "phys_inv_devices": [],
            },
        }
    )
    assert "Customer_Meta" in sheets
    assert sheets["Customer_Meta"][0]["customer"] == "Acme Corp"
