"""usage_comparison — CRM entitlement vs infrastructure virtualization compliance."""
from __future__ import annotations

from app.utils.efficiency_usage import efficiency_status
from app.utils.usage_comparison import (
    aggregate_entitled_by_category,
    build_virtualization_compliance,
    compliance_row_status,
    derive_catalog_overuse_status,
    group_entitled_by_customer,
    normalize_entitled_qty,
    summarize_compliance,
)


def _mapping() -> dict:
    return {
        "p-hc-cpu": {
            "category_code": "virt_hyperconverged_cpu",
            "category_label": "Hyperconverged Mimari — CPU",
            "gui_tab_binding": "virtualization.hyperconverged",
            "resource_unit": "vCPU",
        },
        "p-hc-ram": {
            "category_code": "virt_hyperconverged_ram",
            "category_label": "Hyperconverged Mimari — RAM",
            "gui_tab_binding": "virtualization.hyperconverged",
            "resource_unit": "GB",
        },
        "p-hc-disk": {
            "category_code": "virt_hyperconverged_storage",
            "category_label": "Hyperconverged Mimari — Storage",
            "gui_tab_binding": "virtualization.hyperconverged",
            "resource_unit": "GB",
        },
        "p-cl-cpu": {
            "category_code": "virt_classic_cpu",
            "category_label": "Klasik Mimari — CPU",
            "gui_tab_binding": "virtualization.classic",
            "resource_unit": "vCPU",
        },
    }


def test_normalize_gb_to_tb():
    assert normalize_entitled_qty(1024.0, "GB", "TB") == 1.0


def test_normalize_tb_to_gb():
    assert normalize_entitled_qty(1.0, "TB", "GB") == 1024.0


def test_aggregate_active_plus_invoiced_by_category():
    entitled_raw = [
        {
            "productid": "p-hc-cpu",
            "resource_unit": "vCPU",
            "entitled_qty": 10.0,
            "entitled_amount_tl": 100.0,
        },
        {
            "productid": "p-hc-cpu",
            "resource_unit": "vCPU",
            "entitled_qty": 8.0,
            "entitled_amount_tl": 80.0,
        },
    ]
    agg = aggregate_entitled_by_category(entitled_raw, _mapping())
    assert agg["virt_hyperconverged_cpu"]["entitled_qty"] == 18.0


def test_hyperconverged_cpu_overage_aselsannet_style():
    entitled_raw = [
        {"productid": "p-hc-cpu", "resource_unit": "vCPU", "entitled_qty": 18.0, "entitled_amount_tl": 0},
        {"productid": "p-hc-ram", "resource_unit": "GB", "entitled_qty": 128.0, "entitled_amount_tl": 0},
        {"productid": "p-hc-disk", "resource_unit": "GB", "entitled_qty": 1024.0, "entitled_amount_tl": 0},
    ]
    assets = {
        "hyperconv": {"cpu_total": 550.0, "memory_gb": 1996.8, "disk_gb": 35256.32, "vm_count": 70},
        "classic": {"cpu_total": 42.0, "memory_gb": 228.0, "disk_gb": 9379.84, "vm_count": 7},
    }
    agg = aggregate_entitled_by_category(entitled_raw, _mapping())
    rows, summary = build_virtualization_compliance(
        entitled_agg=agg,
        assets=assets,
        totals={},
        weighted_prices={"p-hc-cpu": 105.57, "p-hc-ram": 60.29, "p-hc-disk": 1.12},
        price_overrides={},
        catalog_by_productid={},
        catalog_by_name={"Klasik Mimari Intel CPU": 50.0},
    )
    cpu_row = next(r for r in rows if r["category_code"] == "virt_hyperconverged_cpu")
    assert cpu_row["overage_qty"] == 532.0
    assert cpu_row["status"] == "over"
    assert cpu_row["overage_loss_tl"] == round(532.0 * 105.57, 2)

    classic_row = next(r for r in rows if r["category_code"] == "virt_classic_cpu")
    assert classic_row["entitled_qty"] == 0.0
    assert classic_row["used_qty"] == 42.0
    assert classic_row["status"] == "unsold_usage"
    assert classic_row["overage_loss_tl"] == round(42.0 * 50.0, 2)
    assert summary["has_overuse"] is True


def test_all_within_limits_ok():
    entitled_raw = [
        {"productid": "p-hc-cpu", "resource_unit": "vCPU", "entitled_qty": 100.0, "entitled_amount_tl": 0},
    ]
    assets = {"hyperconv": {"cpu_total": 90.0, "memory_gb": 0, "disk_gb": 0}}
    agg = aggregate_entitled_by_category(entitled_raw, _mapping())
    rows, summary = build_virtualization_compliance(
        entitled_agg=agg,
        assets=assets,
        totals={},
        weighted_prices={},
        price_overrides={},
        catalog_by_productid={},
        catalog_by_name={},
        under_pct=80.0,
        over_pct=110.0,
    )
    cpu_row = next(r for r in rows if r["category_code"] == "virt_hyperconverged_cpu")
    assert cpu_row["status"] == "optimal"
    assert summary["overuse_status"] == "ok"


def test_compliance_row_status_unsold_usage():
    assert compliance_row_status(
        entitled_qty=0,
        used_qty=10,
        overage_qty=10,
        efficiency_pct=None,
        under_pct=80,
        over_pct=110,
    ) == "unsold_usage"


def test_efficiency_status_unsold_usage():
    assert efficiency_status(None, 0, used_qty=5) == "unsold_usage"


def test_derive_catalog_overuse_status():
    assert derive_catalog_overuse_status(mapped=False, has_infra_cache=True, compliance_summary=None) == "not_applicable"
    assert derive_catalog_overuse_status(mapped=True, has_infra_cache=False, compliance_summary=None) == "pending"
    assert derive_catalog_overuse_status(
        mapped=True,
        has_infra_cache=True,
        compliance_summary={"overuse_status": "overuse"},
    ) == "overuse"


def test_group_entitled_by_customer():
    rows = [
        {"crm_accountid": "a1", "productid": "p1", "entitled_qty": 1},
        {"crm_accountid": "a1", "productid": "p2", "entitled_qty": 2},
        {"crm_accountid": "a2", "productid": "p1", "entitled_qty": 3},
    ]
    grouped = group_entitled_by_customer(rows)
    assert len(grouped["a1"]) == 2
    assert grouped["a2"][0]["entitled_qty"] == 3


def test_summarize_compliance_counts_loss():
    rows = [
        {"category_code": "virt_classic_cpu", "status": "unsold_usage", "overage_loss_tl": 100.0},
        {"category_code": "virt_hyperconverged_cpu", "status": "optimal", "overage_loss_tl": 0.0},
    ]
    summary = summarize_compliance(rows)
    assert summary["has_overuse"] is True
    assert summary["total_overage_loss_tl"] == 100.0
    assert "virt_classic_cpu" in summary["overuse_categories"]
