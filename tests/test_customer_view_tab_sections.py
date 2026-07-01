"""Item 3.1/3.2: per-tab render functions that fetch only their own data and
render, so each tab can load independently (item 3.3/3.4). Covers the
independent tabs (availability, physical inventory, ITSM, S3) and the coupled
tabs (virtualization, backup, summary, billing).
"""
import contextlib
from unittest.mock import patch

from src.pages import customer_view as cv


def _tr():
    return {"start": "2024-06-01", "end": "2024-06-07", "preset": "7d"}


_RESOURCES = {
    "totals": {"backup": {}, "vms_total": 0, "cpu_total": 0.0},
    "assets": {
        "classic": {"vm_count": 0, "cpu_total": 0, "memory_gb": 0, "disk_gb": 0, "vm_list": [], "deleted_vm_list": []},
        "hyperconv": {"vm_count": 0, "cpu_total": 0, "memory_gb": 0, "disk_gb": 0, "vm_list": [], "deleted_vm_list": []},
        "pure_nutanix": {"vm_count": 0, "cpu_total": 0, "memory_gb": 0, "disk_gb": 0, "vm_list": [], "deleted_vm_list": []},
        "power": {"lpar_count": 0, "cpu_total": 0, "memory_total_gb": 0, "vm_list": [], "deleted_vm_list": []},
        "intel": {"vms": {}, "cpu": {}, "memory_gb": {}, "disk_gb": {}, "vm_list": []},
        "backup": {},
    },
}


def _patch_all_getters(stack):
    def p(name, value):
        stack.enter_context(patch.object(cv.api, name, return_value=value))

    p("get_customer_resources", _RESOURCES)
    p("get_customer_availability_bundle", {"vm_outage_counts": {}})
    p("get_customer_sales_summary", {"currency": "TRY"})
    p("get_customer_efficiency_by_category", [])
    p("get_customer_resource_compliance", {"summary": {}, "rows": []})
    p("get_customer_itsm_summary", {})
    p("get_customer_sales_service_breakdown", [])
    p("get_customer_s3_vaults", {})
    p("get_customer_sales_items", [])
    p("get_customer_sales_active_orders", [])
    p("get_customer_sales_active_items", [])
    stack.enter_context(patch.object(cv.aura, "get_dc_services_availability", return_value=[]))


def test_render_virtualization_tab_both_perspectives():
    with contextlib.ExitStack() as s:
        _patch_all_getters(s)
        assert cv.render_virtualization_tab("Acme", _tr(), cv.PERSPECTIVE_MANAGER) is not None
        assert cv.render_virtualization_tab("Acme", _tr(), cv.PERSPECTIVE_CUSTOMER) is not None


def test_render_backup_tab_both_perspectives():
    with contextlib.ExitStack() as s:
        _patch_all_getters(s)
        assert cv.render_backup_tab("Acme", _tr(), cv.PERSPECTIVE_MANAGER) is not None
        assert cv.render_backup_tab("Acme", _tr(), cv.PERSPECTIVE_CUSTOMER) is not None


def test_render_summary_tab_both_perspectives():
    with contextlib.ExitStack() as s:
        _patch_all_getters(s)
        assert cv.render_summary_tab("Acme", _tr(), cv.PERSPECTIVE_MANAGER) is not None
        assert cv.render_summary_tab("Acme", _tr(), cv.PERSPECTIVE_CUSTOMER) is not None


def test_render_billing_tab():
    with contextlib.ExitStack() as s:
        _patch_all_getters(s)
        assert cv.render_billing_tab("Acme", _tr()) is not None


def test_render_availability_tab_fetches_only_availability():
    bundle = {"service_downtimes": [], "vm_downtimes": [], "vm_outage_counts": {}}
    with patch.object(cv.api, "get_customer_availability_bundle", return_value=bundle) as m:
        out = cv.render_availability_tab("Acme", _tr())
    m.assert_called_once_with("Acme", _tr())
    assert out is not None


def test_render_physical_inventory_tab_fetches_only_phys():
    with patch.object(cv.api, "get_physical_inventory_customer", return_value=[]) as m:
        out = cv.render_physical_inventory_tab("Acme")
    m.assert_called_once_with("Acme")
    assert out is not None


def test_render_itsm_tab_fetches_only_itsm_calls():
    with patch.object(cv.api, "get_customer_itsm_summary", return_value={}) as m1, \
         patch.object(cv.api, "get_customer_itsm_extremes", return_value={}) as m2, \
         patch.object(cv.api, "get_customer_itsm_tickets", return_value=[]) as m3:
        out = cv.render_itsm_tab("Acme", _tr())
    m1.assert_called_once()
    m2.assert_called_once()
    m3.assert_called_once()
    assert out is not None


def test_render_s3_tab_fetches_only_s3():
    with patch.object(cv.api, "get_customer_s3_vaults", return_value={"vaults": []}) as m:
        out = cv.render_s3_tab("Acme", _tr())
    m.assert_called_once_with("Acme", _tr())
    assert out is not None
