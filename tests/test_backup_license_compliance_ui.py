"""Tests for backup license compliance strip and NetBackup KPI helpers."""
from __future__ import annotations

from src.components.backup_license_compliance import (
    build_backup_kpi_strip,
    build_license_compliance_strip,
    build_netbackup_kpi_defs,
    filter_netbackup_efficiency_rows,
    license_badge_color,
    license_badge_label,
    visible_compliance_rows,
)
from src.pages.customer_view_perspective import (
    PERSPECTIVE_CUSTOMER,
    PERSPECTIVE_MANAGER,
    include_sold_vs_used,
    show_post_dedup,
)


def test_visible_compliance_rows_only_usage_ok_or_no_license():
    rows = [
        {"category": "veeam_backup", "status": "ok", "usage_qty": 5, "sold_qty": 3},
        {"category": "zerto", "status": "unsold_usage", "usage_qty": 2, "sold_qty": 0},
        {"category": "veeam_replication", "status": "crm_only", "usage_qty": 0, "sold_qty": 4},
        {"category": "veeam_backup", "status": "no_usage", "usage_qty": 0, "sold_qty": 0},
        {"category": "zerto", "status": "ok", "usage_qty": 0, "sold_qty": 1},
    ]
    visible = visible_compliance_rows(rows)
    assert len(visible) == 2
    assert {r["category"] for r in visible} == {"veeam_backup", "zerto"}


def test_license_badge_labels_and_colors():
    assert license_badge_label("ok") == "OK"
    assert license_badge_label("unsold_usage") == "No license"
    assert license_badge_color("ok") == "green"
    assert license_badge_color("unsold_usage") == "red"


def test_build_license_compliance_strip_renders_ok_and_no_license():
    strip = build_license_compliance_strip(
        [
            {"category": "veeam_backup", "status": "ok", "usage_qty": 3, "sold_qty": 3},
            {"category": "zerto", "status": "unsold_usage", "usage_qty": 1, "sold_qty": 0},
        ]
    )
    text = str(strip)
    assert "Backup license compliance" in text
    assert "OK" in text
    assert "No license" in text
    assert "Veeam Backup" in text
    assert "Zerto" in text


def test_build_license_compliance_strip_empty_when_no_usage():
    strip = build_license_compliance_strip(
        [{"category": "zerto", "status": "crm_only", "usage_qty": 0, "sold_qty": 2}]
    )
    assert strip.children is None or strip.children == [] or not getattr(strip, "children", None)


def test_filter_netbackup_efficiency_prefers_specific_binding():
    rows = [
        {
            "gui_tab_binding": "backup.netbackup.image",
            "category_code": "backup_netbackup_image",
            "sold_qty": 10,
            "used_qty": 8,
        },
        {
            "gui_tab_binding": "backup.netbackup",
            "category_code": "backup_netbackup_storage",
            "sold_qty": 99,
            "used_qty": 99,
        },
    ]
    out = filter_netbackup_efficiency_rows(rows, "image")
    assert len(out) == 1
    assert out[0]["sold_qty"] == 10


def test_filter_netbackup_efficiency_matches_category_code_on_legacy_binding():
    rows = [
        {
            "gui_tab_binding": "backup.netbackup",
            "category_code": "backup_netbackup_application",
            "category_label": "NetBackup — Application",
            "sold_qty": 5,
            "used_qty": 4,
        },
        {
            "gui_tab_binding": "backup.netbackup",
            "category_code": "backup_netbackup_image",
            "category_label": "NetBackup — Image",
            "sold_qty": 7,
            "used_qty": 6,
        },
    ]
    app = filter_netbackup_efficiency_rows(rows, "application")
    assert len(app) == 1
    assert app[0]["sold_qty"] == 5


def test_netbackup_kpi_defs_manager_includes_post_margin():
    assets = {
        "netbackup": {
            "image": {"pre_dedup_size_gib": 100.0, "post_dedup_size_gib": 40.0},
            "application": {"pre_dedup_size_gib": 50.0, "post_dedup_size_gib": 20.0},
        }
    }
    rows = [
        {
            "gui_tab_binding": "backup.netbackup",
            "category_code": "backup_netbackup_image",
            "category_label": "NetBackup — Image",
            "sold_qty": 120.0,
            "used_qty": 100.0,
        },
        {
            "gui_tab_binding": "backup.netbackup",
            "category_code": "backup_netbackup_application",
            "category_label": "NetBackup — Application",
            "sold_qty": 60.0,
            "used_qty": 50.0,
        },
    ]
    defs = build_netbackup_kpi_defs(rows, assets, show_post_dedup=True)
    by_cat = {d["category"]: d for d in defs}
    assert by_cat["image"]["sold"] == 120.0
    assert by_cat["image"]["used_pre"] == 100.0
    assert by_cat["image"]["post"] == 40.0
    assert by_cat["image"]["margin"] == 60.0
    assert by_cat["application"]["post"] == 20.0


def test_netbackup_kpi_defs_customer_strips_post():
    assets = {
        "netbackup": {
            "image": {"pre_dedup_size_gib": 10.0, "post_dedup_size_gib": 4.0},
        }
    }
    defs = build_netbackup_kpi_defs([], assets, show_post_dedup=False)
    image = next(d for d in defs if d["category"] == "image")
    assert image["used_pre"] == 10.0
    assert image["post"] is None
    assert image["margin"] is None


def test_backup_kpi_strip_deeplink_and_perspective_copy():
    defs = [
        {
            "category": "image",
            "label": "Image Backup",
            "sold": 10,
            "used_pre": 8,
            "post": 3,
            "margin": 5,
            "savings_pct": 62.5,
            "has_signal": True,
        }
    ]
    mgr = str(build_backup_kpi_strip(defs, show_post_dedup=True))
    assert "Open in Backup" in mgr
    assert "Post" in mgr
    assert "Margin" in mgr

    cust = str(build_backup_kpi_strip(defs, show_post_dedup=False))
    assert "Used (pre)" in cust
    assert "Post" not in cust


def test_perspective_gates_sold_vs_used_and_post_dedup():
    assert include_sold_vs_used(PERSPECTIVE_MANAGER) is True
    assert include_sold_vs_used(PERSPECTIVE_CUSTOMER) is False
    assert show_post_dedup(PERSPECTIVE_MANAGER) is True
    assert show_post_dedup(PERSPECTIVE_CUSTOMER) is False


def test_tab_netbackup_category_strips_post_for_customer():
    from src.components.backup_license_compliance import netbackup_category_table_rows

    cust = netbackup_category_table_rows(
        pre_gib=12.5,
        post_gib=5.0,
        dedup_fact="2.5x",
        show_post_dedup=False,
    )
    labels = [r[0] for r in cust]
    assert "Pre-Dedup Size" in labels
    assert "Post-Dedup Size" not in labels
    assert "Dedup Margin" not in labels

    mgr = netbackup_category_table_rows(
        pre_gib=12.5,
        post_gib=5.0,
        dedup_fact="2.5x",
        show_post_dedup=True,
    )
    labels_m = [r[0] for r in mgr]
    assert "Post-Dedup Size" in labels_m
    assert "Dedup Margin" in labels_m


def test_summary_panel_includes_license_strip_not_on_empty():
    from src.components.customer_summary_panel import build_customer_summary_panel

    panel = build_customer_summary_panel(
        "Acme",
        totals={"vms_total": 1},
        assets={
            "classic": {"vm_count": 1, "cpu_total": 2},
            "backup": {
                "license_compliance": [
                    {
                        "category": "veeam_backup",
                        "status": "unsold_usage",
                        "usage_qty": 4,
                        "sold_qty": 0,
                    }
                ],
                "netbackup": {
                    "image": {"pre_dedup_size_gib": 1.0, "post_dedup_size_gib": 0.4},
                },
            },
        },
        backup_totals={},
        perspective="manager",
        efficiency_rows=[
            {
                "gui_tab_binding": "backup.netbackup",
                "category_code": "backup_netbackup_image",
                "category_label": "NetBackup — Image",
                "sold_qty": 2.0,
                "used_qty": 1.0,
            }
        ],
    )
    text = str(panel)
    assert "Backup license compliance" in text
    assert "No license" in text
    assert "Backup — sold vs used" in text
    assert "Open in Backup" in text
