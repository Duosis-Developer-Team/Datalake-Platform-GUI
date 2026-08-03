"""CRM Inventory OS Lisans grouping + licence-gap helpers."""
from __future__ import annotations

from app.services.inventory_overview_service import (
    _INVENTORY_GROUP_OS_LICENCE,
    _INVENTORY_GROUP_OS_LICENCE_LABEL,
    _apply_os_licence_fields,
    _is_os_licence_row,
    _regroup_backup_families,
    _regroup_os_licence_families,
)


def _licence_row(
    panel_key: str,
    *,
    family: str,
    total: float,
    sold: float,
    price: float | None = 100.0,
    has_price: bool = True,
    label: str | None = None,
) -> dict:
    return {
        "panel_key": panel_key,
        "family": family,
        "family_label": family,
        "service_label": label or panel_key,
        "total": total,
        "crm_sold_qty": sold,
        "crm_sold_tl": sold * (price or 0),
        "unit_price_tl": price,
        "has_price": has_price,
        "has_infra_source": True,
        "sellable_qty": 0.0,
        "potential_tl": 999.0,
        "used_qty": total,
        "free_qty": 0.0,
        "unsold_qty": 0.0,
    }


def test_is_os_licence_row_only_three_skus():
    assert _is_os_licence_row({"panel_key": "license_windows_os"})
    assert _is_os_licence_row({"panel_key": "license_redhat"})
    assert _is_os_licence_row({"panel_key": "license_suse"})
    assert not _is_os_licence_row({"panel_key": "mgmt_os_windows"})
    assert not _is_os_licence_row({"panel_key": "virt_classic_cpu"})


def test_apply_os_licence_fields_gap_math():
    row = _apply_os_licence_fields(
        _licence_row("license_windows_os", family="license_os", total=8084.0, sold=1294.4, price=417.39)
    )
    assert row["sellable_profile"] == "os_licence"
    assert row["licence_detected_qty"] == 8084.0
    assert abs(row["licence_gap_qty"] - 6789.6) < 1e-9
    assert abs(row["licence_gap_tl"] - (6789.6 * 417.39)) < 0.01
    assert row["sellable_qty"] is None
    assert float(row["potential_tl"] or 0) == 0.0
    assert row["used_qty"] is None
    assert row["free_qty"] is None
    assert row["unsold_qty"] is None


def test_apply_os_licence_gap_zero_when_over_licensed():
    row = _apply_os_licence_fields(
        _licence_row("license_redhat", family="license_redhat", total=10.0, sold=12.0, price=500.0)
    )
    assert row["licence_gap_qty"] == 0.0
    assert row["licence_gap_tl"] is None or float(row["licence_gap_tl"]) == 0.0


def test_apply_os_licence_gap_tl_none_without_price():
    row = _apply_os_licence_fields(
        _licence_row(
            "license_suse",
            family="license_other",
            total=805.0,
            sold=6.1,
            price=None,
            has_price=False,
        )
    )
    assert abs(row["licence_gap_qty"] - 798.9) < 1e-9
    assert row["licence_gap_tl"] is None


def test_apply_os_licence_ignores_non_licence_rows():
    raw = {"panel_key": "mgmt_os_windows", "total": 100, "crm_sold_qty": 10, "potential_tl": 50}
    assert _apply_os_licence_fields(raw) is raw


def test_regroup_os_licence_single_family():
    families = [
        {
            "family": "image_backup",
            "family_label": "Image Backup",
            "panels": [
                {"panel_key": "backup_netbackup_image", "family": "backup_netbackup", "service_label": "Image"},
            ],
            "panel_count": 1,
        },
        {
            "family": "license_os",
            "family_label": "Os",
            "panels": [
                _licence_row("license_windows_os", family="license_os", total=10, sold=4, label="Windows"),
            ],
            "panel_count": 1,
        },
        {
            "family": "license_redhat",
            "family_label": "Redhat",
            "panels": [
                _licence_row("license_redhat", family="license_redhat", total=5, sold=0, label="RHEL"),
            ],
            "panel_count": 1,
        },
        {
            "family": "license_other",
            "family_label": "Suse",
            "panels": [
                _licence_row("license_suse", family="license_other", total=3, sold=1, label="SUSE"),
            ],
            "panel_count": 1,
        },
        {
            "family": "mgmt_os",
            "family_label": "Os",
            "panels": [
                {
                    "panel_key": "mgmt_os_windows",
                    "family": "mgmt_os",
                    "service_label": "Windows Yönetim",
                    "has_infra_source": False,
                },
            ],
            "panel_count": 1,
        },
        {
            "family": "virt_classic",
            "family_label": "Klasik Mimari",
            "panels": [
                {"panel_key": "virt_classic_cpu", "family": "virt_classic", "service_label": "CPU"},
            ],
            "panel_count": 1,
        },
    ]
    out = _regroup_os_licence_families(families)
    labels = [f["family_label"] for f in out]
    assert labels[0] == "Image Backup"
    assert "OS Lisans" in labels
    assert labels.count("Os") == 1  # only mgmt_os remains as Os if still present
    assert "Redhat" not in labels
    assert "Suse" not in labels
    os_fam = next(f for f in out if f["family"] == _INVENTORY_GROUP_OS_LICENCE)
    assert os_fam["family_label"] == _INVENTORY_GROUP_OS_LICENCE_LABEL
    assert os_fam["sellable_profile"] == "os_licence"
    assert os_fam["panel_count"] == 3
    assert {p["panel_key"] for p in os_fam["panels"]} == {
        "license_windows_os",
        "license_redhat",
        "license_suse",
    }
    # Alphabetically among passthrough: Klasik Mimari, Os (mgmt), OS Lisans
    non_backup = [f for f in out if f["family"] != "image_backup"]
    non_backup_labels = [f["family_label"] for f in non_backup]
    assert non_backup_labels == sorted(non_backup_labels, key=str.lower)


def test_regroup_after_backup_preserves_order():
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
            "family": "license_os",
            "family_label": "Os",
            "panels": [
                _licence_row("license_windows_os", family="license_os", total=1, sold=0, label="Win"),
            ],
        },
    ]
    out = _regroup_os_licence_families(_regroup_backup_families(families))
    assert out[0]["family"] == "image_backup"
    assert out[1]["family"] == "application_backup"
    assert any(f["family"] == "os_licence" for f in out)
