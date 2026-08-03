"""CRM Inventory backup grouping + Nutanix comparison-only helpers."""
from __future__ import annotations

from app.services.inventory_overview_service import (
    _INVENTORY_GROUP_LABELS,
    _apply_comparison_only_fields,
    _inventory_group_for_row,
    _regroup_backup_families,
)


def test_inventory_group_netbackup_image_vs_application():
    assert _inventory_group_for_row({
        "panel_key": "backup_netbackup_image",
        "family": "backup_netbackup",
    }) == "image_backup"
    assert _inventory_group_for_row({
        "panel_key": "backup_netbackup_application",
        "family": "backup_netbackup",
    }) == "application_backup"


def test_inventory_group_nutanix_and_replication():
    assert _inventory_group_for_row({
        "panel_key": "backup_image_hyperconverged",
        "family": "backup_image",
    }) == "image_backup"
    assert _inventory_group_for_row({
        "panel_key": "backup_zerto_replication_storage",
        "family": "backup_zerto_replication",
    }) == "replication"
    assert _inventory_group_for_row({
        "panel_key": "backup_replication_cpu",
        "family": "backup_replication",
    }) == "replication"


def test_comparison_only_clears_sellable():
    row = _apply_comparison_only_fields({
        "panel_key": "backup_image_hyperconverged",
        "family": "backup_image",
        "sellable_qty": 100.0,
        "potential_tl": 999.0,
        "crm_sold_qty": 50.0,
        "used_qty": 60.0,
    })
    assert row["sellable_profile"] == "comparison_only"
    assert row["sellable_qty"] is None
    assert float(row["potential_tl"] or 0) == 0.0
    assert row["crm_sold_qty"] == 50.0


def test_regroup_backup_families_three_top_groups():
    families = [
        {
            "family": "backup_netbackup",
            "family_label": "NetBackup",
            "panels": [
                {"panel_key": "backup_netbackup_image", "family": "backup_netbackup", "service_label": "Image"},
                {"panel_key": "backup_netbackup_application", "family": "backup_netbackup", "service_label": "App"},
            ],
        },
        {
            "family": "backup_image",
            "family_label": "Image",
            "panels": [
                {"panel_key": "backup_image_hyperconverged", "family": "backup_image", "service_label": "Nutanix"},
            ],
        },
        {
            "family": "backup_zerto_replication",
            "family_label": "Zerto",
            "panels": [
                {"panel_key": "backup_zerto_replication_storage", "family": "backup_zerto_replication", "service_label": "Zerto"},
            ],
        },
        {
            "family": "virt_classic",
            "family_label": "Klasik Mimari",
            "panels": [
                {"panel_key": "virt_classic_cpu", "family": "virt_classic", "service_label": "CPU"},
            ],
        },
    ]
    out = _regroup_backup_families(families)
    labels = [f["family_label"] for f in out]
    assert labels[0] == "Image Backup"
    assert labels[1] == "Application Backup"
    assert labels[2] == "Replication"
    assert "Klasik Mimari" in labels
    assert "NetBackup" not in labels
    image = next(f for f in out if f["family"] == "image_backup")
    assert {p["panel_key"] for p in image["panels"]} == {
        "backup_netbackup_image",
        "backup_image_hyperconverged",
    }
    assert set(_INVENTORY_GROUP_LABELS.values()) == {
        "Image Backup", "Application Backup", "Replication",
    }


def test_hide_empty_offsite_remote():
    families = [
        {
            "family": "backup_remote",
            "family_label": "Remote",
            "panels": [
                {
                    "panel_key": "backup_remote_nutanix",
                    "family": "backup_remote",
                    "crm_sold_qty": 0,
                    "has_infra_source": False,
                    "service_label": "Remote",
                },
            ],
        },
    ]
    out = _regroup_backup_families(families)
    assert not any(f["family"] == "image_backup" for f in out)
