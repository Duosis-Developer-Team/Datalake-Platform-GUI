"""Unit tests for CSV/Excel export helpers and page export builders."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from src.utils.export_helpers import (
    build_report_info_df,
    csv_bytes_with_report_header,
    dataframes_to_excel_with_meta,
    records_to_dataframe,
)
from src.pages.global_view import _global_export_table
from src.pages.dc_view import _build_dc_export_sheets
from src.pages.customer_view import _build_customer_export_sheets


def test_build_report_info_df_contains_range_and_page():
    tr = {"start": "2025-01-01", "end": "2025-01-07", "preset": "7d"}
    df = build_report_info_df(tr, "Test_Page", {"filter_a": "x"})
    assert "page" in df["key"].values
    assert "range_start" in df["key"].values
    assert "filter_a" in df["key"].values


def test_dataframes_to_excel_with_meta_has_report_info_sheet():
    pytest.importorskip("openpyxl")
    tr = {"start": "2025-01-01", "end": "2025-01-07", "preset": "7d"}
    sheets = {"Data": pd.DataFrame([{"a": 1}])}
    raw = dataframes_to_excel_with_meta(sheets, tr, "P", None)
    assert isinstance(raw, bytes)
    assert len(raw) > 100
    xdf = pd.read_excel(io.BytesIO(raw), sheet_name="Report_Info")
    assert not xdf.empty


def test_csv_bytes_with_report_header_sections():
    tr = {"start": "2025-01-01", "end": "2025-01-07", "preset": "7d"}
    ri = build_report_info_df(tr, "P", None)
    body = csv_bytes_with_report_header(
        ri,
        [("BlockA", pd.DataFrame([{"x": 1}])), ("BlockB", pd.DataFrame([{"y": 2}]))],
    )
    text = body.decode("utf-8-sig")
    assert "# Report_Info" in text
    assert "# BlockA" in text
    assert "# BlockB" in text


def test_global_export_table_wide_rows():
    summaries = [
        {
            "id": "DC1",
            "site_name": "ISTANBUL",
            "location": "Istanbul",
            "host_count": 10,
            "vm_count": 20,
            "cluster_count": 2,
            "platform_count": 3,
            "stats": {"used_cpu_pct": 40.0, "used_ram_pct": 50.0, "total_energy_kw": 100.0, "ibm_kw": 10.0},
        }
    ]
    rows = _global_export_table(summaries)
    assert len(rows) == 1
    assert rows[0]["DC_ID"] == "DC1"
    assert rows[0]["VMs"] == 20
    assert rows[0]["CPU_Used_pct"] == 40.0


def test_build_dc_export_sheets_structure():
    data = {
        "meta": {"name": "N", "location": "L"},
        "classic": {"hosts": 1, "vms": 2},
        "hyperconv": {},
        "power": {"hosts": 0},
        "energy": {"total_kw": 1.5},
        "intel": {"vms": 2},
    }
    phys = {"by_role": [{"role": "Server", "count": 5}]}
    net = {"items": [{"interface_name": "eth0", "speed_gbps": 10}]}
    nb = {"pools": [{"name": "p1", "size_gib": 100}]}
    zerto = {"sites": []}
    veeam = {"repos": []}
    sheets = _build_dc_export_sheets("DC1", data, phys, net, nb, zerto, veeam)
    assert "Meta" in sheets
    assert "Classic_Metrics" in sheets
    assert "Network_Interfaces" in sheets
    assert "Backup" in sheets
    df_meta = records_to_dataframe(sheets["Meta"])
    assert not df_meta.empty


def test_build_customer_export_sheets_has_core_tabs():
    totals = {"vms_total": 10, "intel_vms_total": 8}
    backup_totals = {"veeam_defined_sessions": 3}
    assets = {
        "classic": {"vm_count": 4, "vm_list": [{"name": "a"}]},
        "hyperconv": {"vm_list": []},
        "pure_nutanix": {},
        "power": {"lpar_count": 1, "vm_list": [{"lpar": "p1"}]},
        "intel": {"vm_list": []},
        "backup": {"veeam": {"k": 1}},
    }
    sheets = _build_customer_export_sheets(
        "Acme",
        totals,
        backup_totals,
        assets,
        assets["classic"],
        assets["hyperconv"],
        assets["pure_nutanix"],
        assets["power"],
        {"vaults": [{"pool": "x"}]},
        [{"name": "dev1", "device_role_name": "r"}],
    )
    assert "Customer_Meta" in sheets
    assert "Classic_VMs" in sheets
    assert len(sheets["Classic_VMs"]) >= 1
    assert "S3_Vaults" in sheets
