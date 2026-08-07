"""Export smoke tests for CRM inventory overview."""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from src.components.crm_inventory_report import flat_columns
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


def test_build_inventory_export_sheets_respects_filter():  # TEST-C-007 (REQ-F-009)
    """A column-shape refactor of the export sheets must not change which
    rows the active screen filter includes."""
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
    assert sheets["Services"].iloc[0]["Service"] == "NetBackup — Storage"
    assert len(sheets["Services_raw"]) == 1
    assert sheets["Services_raw"].iloc[0]["panel_key"] == "backup_netbackup_storage"


def test_services_sheet_columns_match_flat_columns_headers_and_order():  # TEST-C-003 (AC-005)
    """The Services sheet must mirror the screen's flat view exactly — same
    columns, same order, same screen headers — not the raw field ids
    (crm_sold_fmt) the report used to leak into Excel headers."""
    sheets = crm_inventory_overview._build_inventory_export_sheets(_fake_store())
    assert list(sheets["Services"].columns) == [c["name"] for c in flat_columns()]


def test_services_sheet_excludes_internal_fields():  # TEST-C-004 (AC-005)
    """Internal bookkeeping fields must not leak into the customer-facing
    Services sheet."""
    sheets = crm_inventory_overview._build_inventory_export_sheets(_fake_store())
    internal_fields = {
        "panel_key", "sellable_profile", "has_infra_source",
        "inventory_free_mode", "data_quality", "used_is_allocation",
    }
    assert not (internal_fields & set(sheets["Services"].columns))


def test_services_raw_sheet_keeps_raw_fields():  # TEST-C-005 (AC-006)
    """Raw numbers must stay reachable for analysis once Services becomes a
    formatted, filtered view — that's what Services_raw is for."""
    sheets = crm_inventory_overview._build_inventory_export_sheets(_fake_store())
    raw = sheets["Services_raw"]
    assert len(raw) == 1
    assert raw.iloc[0]["panel_key"] == "backup_netbackup_storage"
    assert raw.iloc[0]["total"] == 100.0
    assert raw.iloc[0]["crm_sold_qty"] == 50.0


def test_services_sheet_cells_have_no_newlines():  # TEST-C-006 (D-11)
    """A qty/TL block that renders as two lines on screen (whiteSpace:
    pre-line) must not carry a literal "\\n" into the export — Excel breaks
    the cell mid-value and PDF's cell() renders it wrong."""
    sheets = crm_inventory_overview._build_inventory_export_sheets(_fake_store())
    crm_sold_cell = sheets["Services"].iloc[0]["CRM Sold"]
    assert "\n" not in crm_sold_cell
    assert " · " in crm_sold_cell


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
