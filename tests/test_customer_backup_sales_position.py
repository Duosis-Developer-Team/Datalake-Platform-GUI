"""Customer Backup Sales Position — metrics, NetBackup defs, replication used qty."""
from __future__ import annotations

from shared.backup.license_compliance import LICENSE_COMPLIANCE_ENABLED
from src.components.backup_license_compliance import (
    build_backup_kpi_strip,
    build_license_compliance_strip,
    build_netbackup_kpi_defs,
)
from src.components.backup_sales_position import (
    build_netbackup_sales_position_from_kpi_def,
    build_sales_position_card,
    sales_position_metrics,
)
from src.pages import customer_view as cv
from tests.test_customer_view_tab_sections import _tr


def _walk(node):
    yield node
    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        for c in children:
            yield from _walk(c)
    elif children is not None:
        yield from _walk(children)


def _ids(node):
    return {getattr(n, "id", None) for n in _walk(node)}


def test_license_compliance_flag_hides_strip():
    assert LICENSE_COMPLIANCE_ENABLED is False
    strip = build_license_compliance_strip(
        [{"category": "veeam_backup", "status": "unsold_usage", "usage_qty": 3, "sold_qty": 0}]
    )
    assert strip.children is None or strip.children == [] or strip.children is False or not getattr(strip, "children", None)


def test_backup_kpi_strip_has_no_open_in_backup_deeplink():
    defs = [
        {
            "category": "image",
            "label": "Image Backup",
            "sold": 10,
            "used_pre": 12,
            "post": 8,
            "margin": 4,
            "savings_pct": 33.3,
            "needs_to_sell": 2,
            "headroom": 0,
            "has_signal": True,
        }
    ]
    out = build_backup_kpi_strip(defs, show_post_dedup=True, include_deeplink=False)
    text = str(out)
    assert "Open in Backup" not in text
    assert "nexus-card" in str(getattr(out, "className", "")) or "Backup — sold vs used" in text


def test_sales_position_metrics_needs_and_headroom():
    over = sales_position_metrics(sold=10, used=15, unit="GB")
    assert over["needs_to_sell"] == 5
    assert over["headroom"] == 0
    under = sales_position_metrics(sold=20, used=12, unit="GB")
    assert under["needs_to_sell"] == 0
    assert under["headroom"] == 8


def test_build_netbackup_kpi_defs_includes_needs_to_sell():
    assets = {
        "netbackup": {
            "image": {"pre_dedup_size_gib": 120, "post_dedup_size_gib": 40, "deduplication_factor": "3x"},
            "application": {"pre_dedup_size_gib": 0, "post_dedup_size_gib": 0},
        }
    }
    eff = [
        {
            "category_code": "backup_netbackup_image",
            "gui_tab_binding": "backup.netbackup.image",
            "sold_qty": 100,
            "used_qty": 120,
        }
    ]
    defs = build_netbackup_kpi_defs(eff, assets, show_post_dedup=True)
    image = next(d for d in defs if d["category"] == "image")
    assert image["needs_to_sell"] == 20
    assert image["headroom"] == 0
    card = build_netbackup_sales_position_from_kpi_def(image, dedup_ratio="3x")
    assert "Needs to be sold" in str(card) or "cust-sales-pos-nb-image" in _ids(card)


def test_sales_position_card_headroom_copy():
    card = build_sales_position_card(title="Demo", sold=50, used=30, unit="GiB")
    assert "Headroom" in str(card)


def test_replication_nested_tabs_id_present():
    assets = {
        "veeam": {"session_types": [{"type": "Replica", "count": 1}], "session_type_buckets": {"replica": [], "backup": []}},
        "zerto": {"vpgs": []},
        "netbackup": {},
        "license_compliance": [],
    }
    totals = {
        "veeam_defined_sessions": 1,
        "zerto_protected_vms": 0,
        "replication_resources": {
            "veeam_dr": {"vm_count": 1, "cpu": 4, "memory_gb": 8, "disk_gb": 100},
            "zerto": {"vm_count": 0, "cpu": 0, "memory_gb": 0, "disk_gb": 0},
            "altra_replica": {"vm_count": 0, "cpu": 0, "memory_gb": 0, "disk_gb": 0},
            "custom": {"vm_count": 0, "cpu": 0, "memory_gb": 0, "disk_gb": 0},
            "totals": {"vm_count": 1, "cpu": 4, "memory_gb": 8, "disk_gb": 100},
        },
    }
    out = cv._build_backup_tabs(
        assets,
        totals,
        [],
        include_sold_vs_used=True,
        show_post_dedup=True,
        replica_vm_list=[{"name": "X_DR", "role": "veeam_dr", "role_label": "Veeam DR", "cpu": 4}],
    )
    assert "customer-backup-replication-tabs" in _ids(out)


def test_sold_vs_used_panel_english_copy():
    from src.components.sold_vs_used_panel import _one_row_card

    card = _one_row_card(
        {
            "category_label": "Test",
            "resource_unit": "GB",
            "sold_qty": 0,
            "used_qty": 12,
            "efficiency_pct": None,
            "status": "unsold_usage",
        }
    )
    text = str(card)
    assert "in use, nothing sold" in text
    assert "kullanımda" not in text
