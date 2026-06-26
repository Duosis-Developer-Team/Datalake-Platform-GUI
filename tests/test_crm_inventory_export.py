"""Export smoke tests for CRM inventory overview."""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from src.pages import crm_inventory_overview


def _fake_store() -> dict:
    return {
        "dc_code": "*",
        "summary": {"panel_count": 1, "crm_entitled_tl": 1000.0},
        "panels": [{
            "panel_key": "backup_netbackup_storage",
            "service_label": "NetBackup — Storage",
            "family": "backup_netbackup",
            "display_unit": "TB",
            "total": 100.0,
            "crm_sold_qty": 50.0,
            "crm_sold_tl": 500.0,
            "used_qty": 10.0,
            "sellable_qty": 20.0,
            "potential_tl": 200.0,
            "has_infra_source": True,
            "status": "ok",
            "sellable_profile": "standard",
        }],
        "crm_only_panels": [],
        "unmapped_products": [],
        "families": [],
    }


def test_export_inventory_pdf_returns_pdf_bytes():
    with patch(
        "src.pages.crm_inventory_overview.dataframes_to_pdf_with_meta",
        return_value=b"pdf-bytes",
    ) as mock_pdf:
        result = crm_inventory_overview._export_inventory_pdf(1, _fake_store(), "all", "", "grouped")
    assert result is not None
    mock_pdf.assert_called_once()


def test_build_inventory_export_sheets_respects_filter():
    store = _fake_store()
    store["panels"].append({
        "panel_key": "backup_veeam",
        "service_label": "Veeam",
        "family": "backup_veeam",
        "display_unit": "Adet",
        "has_infra_source": False,
        "infra_binding": "crm_only",
        "status": "crm_only",
        "sellable_profile": "standard",
    })
    sheets = crm_inventory_overview._build_inventory_export_sheets(store, filter_mode="infra")
    assert len(sheets["Services"]) == 1
    assert sheets["Services"].iloc[0]["panel_key"] == "backup_netbackup_storage"


def test_export_inventory_returns_excel_bytes():
    with patch(
        "src.pages.crm_inventory_overview.dataframes_to_excel_with_meta",
        return_value=b"excel-bytes",
    ) as mock_excel:
        result = crm_inventory_overview._export_inventory(1, _fake_store(), "all", "", "grouped")
    assert result is not None
    mock_excel.assert_called_once()
    kwargs = mock_excel.call_args.kwargs
    assert kwargs.get("page_name") == "CRM Inventory"
    sheets = mock_excel.call_args.args[0]
    assert "Services" in sheets
    assert isinstance(sheets["Services"], pd.DataFrame)
