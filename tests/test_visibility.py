"""Unit tests for visibility helpers."""

from __future__ import annotations

from src.utils.visibility import (
    asset_has_usage,
    backup_vendor_has_data,
    compute_sla_compliance_pct,
    count_outage_vms,
    filter_compliance_rows_for_display,
    filter_efficiency_rows_for_display,
    filter_overusage_rows,
    is_meaningful_value,
    visible_kv_rows,
    visible_metrics,
)


def test_is_meaningful_value_rejects_zero_and_empty():
    assert is_meaningful_value(None) is False
    assert is_meaningful_value(0) is False
    assert is_meaningful_value(0.0) is False
    assert is_meaningful_value("-") is False
    assert is_meaningful_value("N/A") is False
    assert is_meaningful_value([]) is False
    assert is_meaningful_value(1) is True
    assert is_meaningful_value(0.5) is True
    assert is_meaningful_value("Active") is True


def test_visible_kv_rows_filters_zeros():
    rows = visible_kv_rows(
        [
            ("YTD Revenue", 0),
            ("Active orders", 1),
            ("Currency", "TL"),
        ]
    )
    assert len(rows) == 2
    assert rows[0][0] == "Active orders"


def test_visible_metrics_filters_empty_values():
    metrics = visible_metrics(
        [
            {"title": "A", "value": 0},
            {"title": "B", "value": "12"},
        ]
    )
    assert len(metrics) == 1
    assert metrics[0]["title"] == "B"


def test_asset_has_usage_detects_vms_and_cpu():
    assert asset_has_usage({"vm_count": 0, "cpu_total": 0}) is False
    assert asset_has_usage({"vm_count": 3}) is True
    assert asset_has_usage({"cpu_total": 4.0}) is True


def test_backup_vendor_has_data():
    totals = {"veeam_defined_sessions": 0, "zerto_protected_vms": 2}
    assets = {"veeam": {"session_types": []}, "zerto": {"vpgs": []}}
    assert backup_vendor_has_data(totals, assets, "veeam") is False
    assert backup_vendor_has_data(totals, assets, "zerto") is True


def test_filter_compliance_rows_for_display():
    rows = [
        {"status": "no_usage", "entitled_qty": 0, "used_qty": 0, "overage_qty": 0},
        {"status": "over", "entitled_qty": 10, "used_qty": 20, "overage_qty": 10},
    ]
    out = filter_compliance_rows_for_display(rows)
    assert len(out) == 1
    assert out[0]["status"] == "over"


def test_filter_efficiency_rows_for_display():
    rows = [
        {"status": "no_sales", "sold_qty": 0, "used_qty": 0, "overage_qty": 0},
        {"status": "unsold_usage", "sold_qty": 0, "used_qty": 42, "overage_qty": 42},
    ]
    out = filter_efficiency_rows_for_display(rows)
    assert len(out) == 1
    assert out[0]["status"] == "unsold_usage"


def test_count_outage_vms():
    assert count_outage_vms({"vm-a": 0, "vm-b": 2, "vm-c": 1}) == 2
    assert count_outage_vms({}) == 0


def test_filter_overusage_rows():
    rows = filter_overusage_rows([{"status": "optimal"}, {"status": "over", "overage_qty": 1}])
    assert len(rows) == 1
    assert rows[0]["status"] == "over"


def test_compute_sla_compliance_pct():
    assert compute_sla_compliance_pct({"total_count": 4, "sla_breach_count": 1}) == 75.0
