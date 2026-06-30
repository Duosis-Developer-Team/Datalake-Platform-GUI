"""Unit tests for unified Customer View summary panel."""

from __future__ import annotations

from src.components.customer_summary_panel import (
    aggregate_sla_categories,
    build_customer_summary_panel,
    collect_low_availability_services,
)
from src.components.sold_vs_used_panel import build_compliance_issue_table
from src.utils.visibility import compute_sla_compliance_pct, filter_overusage_rows


def test_filter_overusage_rows():
    rows = [
        {"status": "optimal", "overage_qty": 0},
        {"status": "over", "overage_qty": 5, "category_label": "CPU"},
        {"status": "unsold_usage", "overage_qty": 2},
    ]
    out = filter_overusage_rows(rows)
    assert len(out) == 2


def test_compute_sla_compliance_pct():
    assert compute_sla_compliance_pct({"total_count": 0}) is None
    assert compute_sla_compliance_pct({"total_count": 10, "sla_breach_count": 1}) == 90.0


def test_aggregate_sla_categories_dedupes():
    items = [
        {"categories": [{"category": "Backup", "availability_pct": 99.5}]},
        {"categories": [{"category": "backup", "availability_pct": 98.0}]},
        {"categories": [{"category": "VM", "availability_pct": 97.0}]},
    ]
    cats = aggregate_sla_categories(items)
    assert len(cats) == 2


def test_collect_low_availability_services():
    breakdown = [{"service_label": "Backup Service", "service_code": "backup"}]
    cats = [{"category": "Backup", "availability_pct": 97.5}]
    low = collect_low_availability_services(breakdown, cats, threshold=98.0)
    assert len(low) == 1
    assert low[0]["availability_pct"] == 97.5


def test_build_compliance_issue_table_renders_over_rows():
    table = build_compliance_issue_table(
        [
            {
                "category_label": "Classic CPU",
                "status": "over",
                "entitled_qty": 10,
                "used_qty": 20,
                "overage_qty": 10,
                "overage_loss_tl": 1000,
                "resource_unit": "vcpu",
            }
        ],
        currency="TL",
    )
    text = str(table)
    assert "Classic CPU" in text
    assert "20.00" in text
    assert "Over-utilized" in text or "over" in text.lower()


def test_build_customer_summary_panel_customer_perspective():
    panel = build_customer_summary_panel(
        "Acme Corp",
        totals={"vms_total": 5},
        assets={"classic": {"vm_count": 5, "cpu_total": 10}},
        backup_totals={"veeam_defined_sessions": 2},
        sales_summary={"active_order_value": 100.0, "currency": "TL"},
        compliance_payload={
            "summary": {"has_overuse": True, "total_overage_loss_tl": 50},
            "rows": [],
        },
        perspective="customer",
    )
    text = str(panel)
    assert "Resource usage" in text
    assert "Resource overusage" not in text


def test_build_customer_summary_panel_unified_layout():
    panel = build_customer_summary_panel(
        "Acme Corp",
        totals={"vms_total": 5, "backup": {"veeam_defined_sessions": 2}},
        assets={"classic": {"vm_count": 5, "cpu_total": 10}},
        backup_totals={"veeam_defined_sessions": 2},
        sales_summary={"active_order_value": 100.0, "currency": "TL"},
        compliance_payload={
            "summary": {"has_overuse": True, "total_overage_loss_tl": 50},
            "rows": [
                {
                    "category_label": "CPU",
                    "status": "over",
                    "entitled_qty": 1,
                    "used_qty": 2,
                    "overage_qty": 1,
                    "overage_loss_tl": 50,
                    "resource_unit": "vcpu",
                }
            ],
        },
        itsm_summary={"total_count": 10, "sla_breach_count": 1, "incident_open": 2, "sr_open": 1},
        vm_outage_counts={"vm-a": 1},
    )
    text = str(panel)
    assert "Acme Corp" in text
    assert "Customer signals" in text
    assert "Issues requiring attention" in text
    assert "Resource overusage" in text
    assert "Est. overage loss (total)" in text
    assert "Estimated total overage loss" in text
    assert "50.00 TL" in text
    assert "nexus-card" in text
