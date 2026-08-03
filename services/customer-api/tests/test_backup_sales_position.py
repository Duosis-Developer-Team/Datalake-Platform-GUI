"""Backup compliance + replication footprint used qty."""
from __future__ import annotations

from app.utils.efficiency_usage import resolve_used_quantity
from app.utils.usage_comparison import (
    BACKUP_COMPARISON_CATEGORIES,
    aggregate_entitled_by_category,
    build_backup_compliance,
)


def test_backup_comparison_categories_cover_netbackup_and_replication():
    codes = {c["category_code"] for c in BACKUP_COMPARISON_CATEGORIES}
    assert "backup_netbackup_image" in codes
    assert "backup_veeam_replication_cpu" in codes
    assert "backup_zerto_replication_storage" in codes


def test_resolve_used_quantity_reads_replication_resources():
    totals = {
        "backup": {
            "replication_resources": {
                "veeam_dr": {"vm_count": 2, "cpu": 8, "memory_gb": 32, "disk_gb": 500},
                "zerto": {"vm_count": 1, "cpu": 4, "memory_gb": 16, "disk_gb": 200},
            }
        }
    }
    cpu, _ = resolve_used_quantity(
        category_code="backup_veeam_replication_cpu",
        resource_unit="vCPU",
        assets={},
        totals=totals,
    )
    assert cpu == 8
    ram, _ = resolve_used_quantity(
        category_code="backup_zerto_replication_ram",
        resource_unit="GB",
        assets={},
        totals=totals,
    )
    assert ram == 16
    disk, _ = resolve_used_quantity(
        category_code="backup_veeam_replication_storage",
        resource_unit="GB",
        assets={},
        totals=totals,
    )
    assert disk == 500


def test_build_backup_compliance_rows_include_headroom():
    entitled_agg = {
        "backup_netbackup_image": {
            "category_code": "backup_netbackup_image",
            "category_label": "NetBackup Image",
            "gui_tab_binding": "backup.netbackup.image",
            "resource_unit": "GB",
            "entitled_qty": 200,
            "entitled_amount_tl": 1000,
            "product_ids": ["p1"],
        }
    }
    assets = {
        "backup": {
            "netbackup": {
                "image": {"pre_dedup_size_gib": 150, "post_dedup_size_gib": 50},
            }
        }
    }
    totals = {"backup": {"netbackup_pre_dedup_gib": 150}}
    rows, summary = build_backup_compliance(
        entitled_agg=entitled_agg,
        assets=assets,
        totals=totals,
        weighted_prices={"p1": 5.0},
        price_overrides={},
        catalog_by_productid={},
        catalog_by_name={},
    )
    assert len(rows) == 1
    assert rows[0]["headroom_qty"] == 50
    assert rows[0]["overage_qty"] == 0
    assert rows[0]["headroom_tl"] == 250.0


def test_aggregate_entitled_accepts_backup_categories():
    mapping = {
        "pid1": {
            "category_code": "backup_netbackup_image",
            "resource_unit": "GB",
        }
    }
    raw = [{"productid": "pid1", "entitled_qty": 10, "entitled_amount_tl": 50, "resource_unit": "GB"}]
    agg = aggregate_entitled_by_category(raw, mapping, categories=BACKUP_COMPARISON_CATEGORIES)
    assert "backup_netbackup_image" in agg
    assert agg["backup_netbackup_image"]["entitled_qty"] == 10
