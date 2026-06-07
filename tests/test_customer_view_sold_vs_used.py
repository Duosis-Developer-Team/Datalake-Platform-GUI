"""Customer view: CRM efficiency panels and removal of Sales tab keys."""
from __future__ import annotations

from unittest.mock import patch


def test_crm_rows_outside_virt_backup():
    from src.pages.customer_view import _crm_rows_outside_virt_backup

    rows = [
        {"gui_tab_binding": "virtualization.classic", "x": 1},
        {"gui_tab_binding": "backup.veeam", "x": 2},
        {"gui_tab_binding": "licensing.microsoft", "x": 3},
        {"gui_tab_binding": "storage.s3", "x": 4},
    ]
    out = _crm_rows_outside_virt_backup(rows)
    assert len(out) == 2
    assert {r["x"] for r in out} == {3, 4}


@patch("src.pages.customer_view.api.get_customer_sales_service_breakdown", return_value=[])
@patch("src.pages.customer_view.api.get_customer_sales_active_items", return_value=[])
@patch("src.pages.customer_view.api.get_customer_sales_active_orders", return_value=[])
@patch("src.pages.customer_view.api.get_customer_sales_items", return_value=[])
@patch("src.pages.customer_view.api.get_customer_efficiency_by_category", return_value=[])
@patch(
    "src.pages.customer_view.api.get_customer_sales_summary",
    return_value={
        "ytd_revenue_total": 100.0,
        "lifetime_revenue_total": 250.0,
        "invoice_count": 2,
        "lifetime_order_count": 5,
        "currency": "TRY",
    },
)
@patch("src.pages.customer_view.api.get_customer_itsm_tickets", return_value=[])
@patch("src.pages.customer_view.api.get_customer_itsm_extremes", return_value={})
@patch("src.pages.customer_view.api.get_customer_itsm_summary", return_value={})
@patch("src.pages.customer_view.api.get_physical_inventory_customer", return_value=[])
@patch("src.pages.customer_view.api.get_customer_s3_vaults", return_value={})
@patch("src.pages.customer_view.aura.get_dc_services_availability", return_value=[])
@patch("src.pages.customer_view.api.get_customer_availability_bundle", return_value={})
@patch(
    "src.pages.customer_view.api.get_customer_resources",
    return_value={
        "totals": {"backup": {}, "vms_total": 0, "cpu_total": 0.0, "power_lpar_total": 0, "power_cpu_total": 0.0},
        "assets": {
            "classic": {"vm_count": 0, "cpu_total": 0, "memory_gb": 0, "disk_gb": 0, "vm_list": [], "deleted_vm_list": []},
            "hyperconv": {"vm_count": 0, "cpu_total": 0, "memory_gb": 0, "disk_gb": 0, "vm_list": [], "deleted_vm_list": []},
            "pure_nutanix": {"vm_count": 0, "cpu_total": 0, "memory_gb": 0, "disk_gb": 0, "vm_list": [], "deleted_vm_list": []},
            "power": {"lpar_count": 0, "cpu_total": 0, "memory_total_gb": 0, "vm_list": [], "deleted_vm_list": []},
            "intel": {"vms": {}, "cpu": {}, "memory_gb": {}, "disk_gb": {}, "vm_list": []},
            "backup": {},
        },
    },
)
def test_customer_content_has_crm_summary_sections(_a, _b, _c, _d, _e, _f, _g, _h, _i, _j, _k, _l, _m, _n):
    from src.pages.customer_view import _customer_content

    content = _customer_content("Acme", {"preset": "30d"})
    assert "sales" not in content
    assert "intro_card" not in content
    assert "billing" in content
    assert "virt" in content
    summary_text = str(content.get("summary"))
    billing_text = str(content.get("billing"))
    assert "Customer signals" in summary_text or "No summary data" in summary_text
    assert "CRM Sales Summary" not in summary_text
    assert "Active Orders" not in summary_text
    assert "Invoiced Orders" not in summary_text
    assert "CRM" in billing_text or "realized" in billing_text.lower()
    assert "CRM sales summary" in billing_text or "YTD Revenue" in billing_text


@patch("src.pages.customer_view.api.get_customer_sales_service_breakdown", return_value=[])
@patch("src.pages.customer_view.api.get_customer_sales_active_items", return_value=[])
@patch("src.pages.customer_view.api.get_customer_sales_active_orders", return_value=[])
@patch("src.pages.customer_view.api.get_customer_sales_items", return_value=[])
@patch("src.pages.customer_view.api.get_customer_efficiency_by_category", return_value=[])
@patch(
    "src.pages.customer_view.api.get_customer_sales_summary",
    return_value={"currency": "TRY"},
)
@patch("src.pages.customer_view.api.get_customer_itsm_tickets", return_value=[])
@patch("src.pages.customer_view.api.get_customer_itsm_extremes", return_value={})
@patch("src.pages.customer_view.api.get_customer_itsm_summary", return_value={})
@patch("src.pages.customer_view.api.get_physical_inventory_customer", return_value=[])
@patch("src.pages.customer_view.api.get_customer_s3_vaults", return_value={})
@patch("src.pages.customer_view.api.get_customer_availability_bundle", return_value={})
@patch("src.pages.customer_view.aura.get_dc_services_availability", return_value=[])
@patch(
    "src.pages.customer_view.api.get_customer_resources",
    return_value={
        "totals": {"backup": {}, "vms_total": 3, "cpu_total": 4.0},
        "assets": {
            "classic": {
                "vm_count": 3,
                "cpu_total": 4,
                "memory_gb": 8,
                "disk_gb": 100,
                "vm_list": [{"name": "vm1"}],
                "deleted_vm_list": [],
            },
            "hyperconv": {"vm_count": 0, "cpu_total": 0, "memory_gb": 0, "disk_gb": 0, "vm_list": [], "deleted_vm_list": []},
            "pure_nutanix": {"vm_count": 0, "cpu_total": 0, "memory_gb": 0, "disk_gb": 0, "vm_list": [], "deleted_vm_list": []},
            "power": {"lpar_count": 0, "cpu_total": 0, "memory_total_gb": 0, "vm_list": [], "deleted_vm_list": []},
            "intel": {"vms": {}, "cpu": {}, "memory_gb": {}, "disk_gb": {}, "vm_list": []},
            "backup": {},
        },
    },
)
@patch(
    "src.pages.customer_view.api.get_customer_resource_compliance",
    return_value={"summary": {}, "rows": []},
)
def test_virt_tab_has_no_compliance_gauges(_a, _b, _c, _d, _e, _f, _g, _h, _i, _j, _k, _l, _m, _n, _o):
    from src.pages.customer_view import _customer_content

    content = _customer_content("Acme", {"preset": "30d"})
    virt_text = str(content.get("virt"))
    assert "create_premium_gauge_chart" not in virt_text
    assert "Used / sold" not in virt_text
