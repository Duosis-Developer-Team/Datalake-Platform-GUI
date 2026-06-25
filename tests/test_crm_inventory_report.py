"""Tests for CRM inventory report component."""
from __future__ import annotations

from src.components.crm_inventory_report import (
    build_report_body,
    filter_by_search,
    filter_service_rows,
    prepare_service_row,
)


def _sample_row(**kwargs):
    base = {
        "panel_key": "virt_classic_cpu",
        "service_label": "Klasik Mimari — CPU",
        "family_label": "Klasik Mimari",
        "display_unit": "vCPU",
        "total": 100.0,
        "crm_sold_qty": 30.0,
        "used_qty": 40.0,
        "free_qty": 60.0,
        "sellable_qty": 20.0,
        "delta_used_vs_crm": 10.0,
        "status": "over",
        "potential_tl": 30000.0,
        "has_infra_source": True,
        "infra_binding": "bound",
    }
    base.update(kwargs)
    return base


def test_prepare_service_row_formats_columns():
    row = prepare_service_row(_sample_row())
    assert row["service_label"] == "Klasik Mimari — CPU"
    assert row["free_fmt"] == "60 vCPU"
    assert row["status"] == "over"
    assert row["status_label"] == "Overage"
    assert "█" in row["utilization_fmt"]


def test_prepare_service_row_marks_suspect_data_quality():
    row = prepare_service_row(_sample_row(data_quality="suspect"))
    assert "Check data" in row["status_label"]
    assert row["data_quality"] == "suspect"


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
