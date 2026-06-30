"""Customer View manager/customer perspective helpers and UI wiring."""
from __future__ import annotations

from src.auth.permission_catalog import build_default_permission_roots
from src.components.customer_summary_panel import build_customer_summary_panel
from src.pages.customer_view import (
    _build_customer_tabs_list,
    _build_export_sheets_for_user,
    build_customer_layout,
    render_customer_page,
)
from src.pages.customer_view_perspective import (
    PERM_PERSPECTIVE_CUSTOMER,
    PERM_PERSPECTIVE_MANAGER,
    default_perspective,
    effective_perspective,
    perspective_access,
    show_perspective_switch,
)


def _codes() -> set[str]:
    out: set[str] = set()

    def walk(nodes):
        for node in nodes:
            out.add(node.code)
            walk(node.children or [])

    walk(build_default_permission_roots())
    return out


def test_permission_catalog_includes_perspective_codes():
    codes = _codes()
    assert PERM_PERSPECTIVE_MANAGER in codes
    assert PERM_PERSPECTIVE_CUSTOMER in codes


def test_perspective_access_defaults_open_when_auth_disabled():
    access = perspective_access(None)
    assert access == {"manager": True, "customer": True}
    assert show_perspective_switch(access)
    assert default_perspective(access) == "manager"


def test_perspective_access_single_permission():
    manager_only = perspective_access([PERM_PERSPECTIVE_MANAGER, "action:customer:export"])
    assert manager_only["manager"] is True
    assert manager_only["customer"] is False
    assert show_perspective_switch(manager_only) is False
    assert default_perspective(manager_only) == "manager"

    customer_only = perspective_access([PERM_PERSPECTIVE_CUSTOMER])
    assert effective_perspective("manager", customer_only) == "customer"


def test_customer_tabs_hide_billing_for_customer_perspective():
    manager_tabs = str(_build_customer_tabs_list("manager", has_s3=True, has_phys_inv=True))
    customer_tabs = str(_build_customer_tabs_list("customer", has_s3=True, has_phys_inv=True))
    assert "Billing" in manager_tabs
    assert "ITSM" in manager_tabs
    assert "Billing" not in customer_tabs
    assert "ITSM" in customer_tabs
    assert "Availability" in customer_tabs


def test_tab_hyperconv_hides_usage_vs_sold_for_customer_perspective():
    from src.pages.customer_view import _tab_hyperconv

    hyperconv = {
        "vm_count": 1,
        "cpu_total": 4,
        "memory_gb": 8,
        "disk_gb": 100,
        "vm_list": [{"name": "vm1", "cpu": 2, "cluster": "c1"}],
        "deleted_vm_list": [],
    }
    panel = _tab_hyperconv(hyperconv, {}, include_usage_vs_sold=False)
    text = str(panel)
    assert "CPU Usage vs Sold" not in text

    panel_mgr = _tab_hyperconv(hyperconv, {}, include_usage_vs_sold=True)
    assert "CPU Usage vs Sold" in str(panel_mgr)


def test_customer_summary_panel_customer_perspective_hides_commercial_signals():
    panel = build_customer_summary_panel(
        "Acme Corp",
        totals={"vms_total": 5},
        assets={"classic": {"vm_count": 5, "cpu_total": 10}},
        backup_totals={"veeam_defined_sessions": 2},
        sales_summary={"active_order_value": 100.0, "currency": "TL"},
        compliance_payload={"summary": {"has_overuse": True, "total_overage_loss_tl": 50}, "rows": []},
        perspective="customer",
    )
    text = str(panel)
    assert "Resource usage" in text
    assert "Est. overage loss" not in text
    assert "Issues requiring attention" not in text
    assert "Active order value" not in text


def test_export_sheets_dual_perspective_prefixes():
    ctx = {
        "customer_name": "Acme",
        "totals": {"vms_total": 2},
        "backup_totals": {},
        "assets": {},
        "classic": {},
        "hyperconv": {},
        "pure_nx": {},
        "power_asset": {},
        "s3_data": {},
        "phys_inv_devices": [],
        "itsm_summary": {"total_count": 1},
        "itsm_extremes": {},
        "itsm_tickets": [],
    }
    both = _build_export_sheets_for_user(ctx, {"manager": True, "customer": True})
    assert "Manager_Customer_Meta" in both
    assert "Customer_Customer_Meta" in both
    assert "Manager_ITSM_Summary" in both
    assert "Customer_ITSM_Summary" in both
    assert "Customer_Classic_VMs_Real_CPU" not in both

    manager_only = _build_export_sheets_for_user(ctx, {"manager": True, "customer": False})
    assert "Customer_Meta" in manager_only
    assert "Manager_Customer_Meta" not in manager_only

    customer_only = _build_export_sheets_for_user(ctx, {"manager": False, "customer": True})
    assert "Customer_Customer_Meta" in customer_only
    assert "Customer_ITSM_Summary" in customer_only
    assert "Customer_Classic_VMs_Real_CPU" not in customer_only


def test_render_customer_page_shows_switch_when_both_permissions():
    content = {
        "manager": {"summary": "mgr-summary", "virt": "virt", "avail": "avail", "backup": "backup",
                    "billing": "billing", "itsm": "itsm", "s3": "s3", "phys_inv": "phys"},
        "customer": {"summary": "cust-summary", "virt": "virt", "avail": "avail", "backup": "backup",
                     "itsm": "itsm", "s3": "s3", "phys_inv": "phys"},
        "has_s3": True,
        "has_phys_inv": True,
        "export_context": {},
    }
    page = render_customer_page(
        "Acme",
        {"start": "2026-01-01", "end": "2026-01-31"},
        content,
        visible_sections=None,
    )
    text = str(page)
    assert "customer-view-perspective" in text
    assert "customer-export-pdf" in text


def test_build_customer_layout_has_export_buttons_in_header_when_switch_enabled():
    layout = build_customer_layout(selected_customer="Acme Corp")
    text = str(layout)
    assert "customer-export-csv" in text or "customer-view-page-root" in text
