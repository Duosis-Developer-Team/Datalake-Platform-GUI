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


@patch("src.pages.customer_view.api.get_customer_efficiency_by_category", return_value=[])
@patch("src.pages.customer_view.api.get_customer_sales_summary", return_value={"ytd_revenue_total": 0, "invoice_count": 0})
@patch("src.pages.customer_view.api.get_customer_itsm_tickets", return_value=[])
@patch("src.pages.customer_view.api.get_customer_itsm_extremes", return_value={})
@patch("src.pages.customer_view.api.get_customer_itsm_summary", return_value={})
@patch("src.pages.customer_view.api.get_physical_inventory_customer", return_value=[])
@patch("src.pages.customer_view.api.get_customer_s3_vaults", return_value={})
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
def test_customer_content_has_no_sales_key(_a, _b, _c, _d, _e, _f, _g, _h, _i):
    from src.pages.customer_view import _customer_content

    content = _customer_content("Acme", {"preset": "30d"})
    assert "sales" not in content
    assert "billing" in content
    assert "virt" in content
