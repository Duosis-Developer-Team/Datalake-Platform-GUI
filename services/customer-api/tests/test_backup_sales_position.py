"""Backup compliance + replication footprint used qty."""
from __future__ import annotations

from app.utils.efficiency_usage import resolve_used_quantity
from app.utils.usage_comparison import (
    BACKUP_COMPARISON_CATEGORIES,
    aggregate_entitled_by_category,
    build_backup_compliance,
    catalog_product_names_for_compliance,
    resolve_unit_price_tl,
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


def test_catalog_product_names_include_backup_and_licence_skus():
    names = catalog_product_names_for_compliance()
    assert "Klasik Mimari NetBackup VMware" in names
    assert "Klasik Mimari Veeam Replication CPU" in names
    assert "MS Windows Lisans" in names
    assert "SUSE Lisans Bedeli" in names
    assert "Hyperconverged Mimari Intel CPU" in names


def test_unsold_backup_uses_catalog_product_name_unit_price():
    """Unsold usage has no product_ids — price must resolve via catalog SKU name."""
    catalog = {
        "Klasik Mimari NetBackup VMware": 12.5,
        "Klasik Mimari Veeam Replication CPU": 100.0,
    }
    price, src = resolve_unit_price_tl(
        category_code="backup_netbackup_image",
        product_ids=[],
        weighted_prices={},
        price_overrides={},
        catalog_by_productid={},
        catalog_by_name=catalog,
    )
    assert price == 12.5
    assert src == "catalog_name"

    rows, _ = build_backup_compliance(
        entitled_agg={},
        assets={},
        totals={
            "backup": {
                "netbackup_pre_dedup_gib": 100.0,
                "replication_resources": {
                    "veeam_dr": {"cpu": 4, "memory_gb": 0, "disk_gb": 0},
                    "zerto": {"cpu": 0, "memory_gb": 0, "disk_gb": 0},
                },
            }
        },
        weighted_prices={},
        price_overrides={},
        catalog_by_productid={},
        catalog_by_name=catalog,
    )
    by_code = {r["category_code"]: r for r in rows}
    nb = by_code["backup_netbackup_image"]
    assert nb["unit_price_tl"] == 12.5
    assert nb["price_source"] == "catalog_name"
    assert nb["overage_loss_tl"] == 1250.0
    assert by_code["backup_veeam_replication_cpu"]["overage_loss_tl"] == 400.0


def test_unsold_windows_licence_uses_catalog_product_name():
    price, src = resolve_unit_price_tl(
        category_code="license_windows_os",
        product_ids=[],
        weighted_prices={},
        price_overrides={},
        catalog_by_productid={},
        catalog_by_name={"MS Windows Lisans": 446.63},
    )
    assert price == 446.63
    assert src == "catalog_name"
