"""Tests for CRM inventory report component."""
from __future__ import annotations

from src.components.crm_inventory_report import (
    build_report_body,
    columns_for_family,
    filter_by_search,
    filter_service_rows,
    prepare_service_row,
)


def _sample_row(**kwargs):
    base = {
        "panel_key": "virt_classic_cpu",
        "service_label": "Klasik Mimari — CPU",
        "family_label": "Klasik Mimari",
        "family": "virt_classic",
        "display_unit": "vCPU",
        "total": 100.0,
        "crm_sold_qty": 30.0,
        "crm_sold_tl": 45000.0,
        "used_qty": 40.0,
        "used_tl": 60000.0,
        "free_qty": 60.0,
        "sellable_qty": 20.0,
        "potential_tl": 30000.0,
        "sellable_profile": "dual_track",
        "sellable_alloc_qty": 18.0,
        "sellable_max_qty": 22.0,
        "potential_tl_alloc": 27000.0,
        "potential_tl_max": 33000.0,
        "status": "over",
        "has_infra_source": True,
        "infra_binding": "bound",
    }
    base.update(kwargs)
    return base


def test_columns_for_family_profiles():
    assert len(columns_for_family("standard")) == 6
    assert len(columns_for_family("dual_track")) == 7
    assert len(columns_for_family("allocation_only")) == 6
    assert len(columns_for_family("virt_km", hide_used=True)) == 5


def test_prepare_service_row_formats_qty_tl_blocks():
    row = prepare_service_row(_sample_row(inventory_hide_used=True))
    assert row["service_label"] == "Klasik Mimari — CPU"
    assert "60 vCPU" in row["free_fmt"]
    assert "45,000 TL" in row["crm_sold_fmt"]
    assert row["used_fmt"] == "—\n—"
    assert "18 vCPU" in row["sellable_alloc_fmt"]
    assert "22 vCPU" in row["sellable_max_fmt"]


def test_prepare_service_row_marks_suspect_data_quality():
    row = prepare_service_row(_sample_row(data_quality="suspect"))
    assert row["service_label"].startswith("⚠")
    assert row["data_quality"] == "suspect"


def test_prepare_service_row_standard_free_shows_sellable_tl():
    row = prepare_service_row(_sample_row(
        sellable_profile="standard",
        sellable_alloc_qty=None,
        sellable_max_qty=None,
    ))
    assert "20 vCPU" in row["free_fmt"]
    assert "30,000 TL" in row["free_fmt"]
    assert row["sellable_alloc_fmt"] == "—\n—"


def test_prepare_service_row_s3_physical_free_not_sellable():
    row = prepare_service_row(_sample_row(
        panel_key="storage_s3_istanbul",
        family="storage_s3",
        display_unit="TB",
        sellable_profile="standard",
        total=2000.0,
        used_qty=800.0,
        free_qty=1200.0,
        free_tl=914400.0,
        sellable_qty=385.0,
        potential_tl=38500.0,
        inventory_free_mode="physical",
    ))
    assert "1,200 TB" in row["free_fmt"]
    assert "914,400 TL" in row["free_fmt"]
    assert "385 TB" not in row["free_fmt"]


def test_prepare_service_row_netbackup_used_dedup_block():
    row = prepare_service_row(_sample_row(
        panel_key="backup_netbackup_storage",
        family="backup_netbackup",
        display_unit="TB",
        sellable_profile="standard",
        crm_sold_qty=58.0,
        crm_sold_tl=23246.0,
        total=44069.0,
        used_qty=1229.0,
        used_tl=1720.0,
        pre_dedup_qty=411.0,
        dedup_savings_qty=406.0,
        dedup_savings_pct=98.8,
        dedup_factor=81.8,
        free_qty=42115.0,
        free_tl=58961.0,
        inventory_free_mode="physical",
    ))
    assert "58 TB" in row["crm_sold_fmt"]
    assert "23,246 TL" in row["crm_sold_fmt"]
    assert "44,069 TB" in row["total_fmt"]
    assert "23,246 TL" not in row["total_fmt"]
    assert "1,229 TB" in row["used_fmt"]
    assert "Pre: 411 TB" in row["used_fmt"]
    assert "Saved: 406 TB" in row["used_fmt"]
    assert "98.8%" in row["used_fmt"]
    assert "Dedup: 81.8x" in row["used_fmt"]
    assert "42,115 TB" in row["free_fmt"]
    assert "58,961 TL" in row["free_fmt"]
    assert "44,069 TB" not in row["used_fmt"]
    assert "58 TB" not in row["total_fmt"]


def test_columns_for_family_netbackup_includes_used():
    cols = columns_for_family("backup_netbackup")
    col_ids = [c["id"] for c in cols]
    assert col_ids == [
        "service_label", "display_unit", "crm_sold_fmt", "total_fmt", "used_fmt", "free_fmt",
    ]


def test_filter_by_search_matches_family():
    rows = [
        _sample_row(),
        _sample_row(panel_key="x", service_label="Veeam Backup", family_label="Veeam"),
    ]
    out = filter_by_search(rows, "veeam")
    assert len(out) == 1
    assert out[0]["panel_key"] == "x"


def test_build_report_body_flat_view():
    payload = {
        "families": [],
        "crm_only_panels": [],
        "unmapped_products": [],
        "panels": [_sample_row()],
        "summary": {"note": ""},
    }
    body = build_report_body(payload, filter_mode="all", view_mode="flat")
    assert len(body) >= 1


def test_filter_service_rows_issues():
    rows = [_sample_row(), _sample_row(panel_key="x", status="ok", infra_binding="crm_only", has_infra_source=False)]
    out = filter_service_rows(rows, "issues")
    assert len(out) == 1
    assert out[0]["status"] == "over"


def test_build_report_body_family_sections():
    payload = {
        "families": [{
            "family": "virt_classic",
            "family_label": "Klasik Mimari",
            "label": "Klasik Mimari",
            "has_infra": True,
            "panels": [_sample_row()],
        }],
        "crm_only_panels": [],
        "unmapped_products": [],
        "panels": [_sample_row()],
    }
    body = build_report_body(payload, filter_mode="all")
    assert len(body) >= 1


def test_prepare_service_row_crm_sub_line_km():
    row = prepare_service_row(_sample_row(
        crm_sold_qty=440.0,
        crm_sold_qty_general=440.0,
        crm_sold_qty_km=12.0,
        crm_sold_tl=660000.0,
        inventory_hide_used=True,
    ))
    assert "440 vCPU" in row["crm_sold_fmt"]
    assert "(KM: 12 vCPU)" in row["crm_sold_fmt"]
    assert "660,000 TL" in row["crm_sold_fmt"]


def test_prepare_service_row_crm_sub_line_hana():
    row = prepare_service_row(_sample_row(
        family="virt_power",
        display_unit="Core",
        crm_sold_qty=80.0,
        crm_sold_qty_general=50.0,
        crm_sold_qty_hana=30.0,
        crm_sold_tl=120000.0,
        sellable_profile="allocation_only",
        inventory_hide_used=True,
    ))
    assert "(HANA: 30 Core)" in row["crm_sold_fmt"]


def test_prepare_service_row_ignores_zero_km_sub_bucket():
    row = prepare_service_row(_sample_row(
        crm_sold_qty=58.0,
        crm_sold_qty_km=0.0,
        crm_sold_tl=23246.0,
        sellable_profile="standard",
        display_unit="TB",
        used_qty=5.0,
        free_qty=44000.0,
        sellable_qty=44000.0,
    ))
    assert "(KM:" not in row["crm_sold_fmt"]
    assert "58 TB" in row["crm_sold_fmt"]
    assert "23,246 TL" in row["crm_sold_fmt"]


def test_columns_for_family_includes_power_hana_virt():
    cols = columns_for_family("virt_power_hana", hide_used=True)
    col_ids = [c["id"] for c in cols]
    assert "used_fmt" not in col_ids
    assert "free_fmt" in col_ids
