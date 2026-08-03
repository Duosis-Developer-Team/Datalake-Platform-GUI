"""Unit tests for platform-wide Potential Sales aggregation."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from shared.sellable.computation import dedupe_shared_pool_tl
from src.utils import platform_sellable_aggregate as psa


def test_module_imports_dedupe_shared_pool_tl():
    assert psa.dedupe_shared_pool_tl is dedupe_shared_pool_tl
    lo, hi = psa.dedupe_shared_pool_tl(10.0, 100.0, 20.0, 80.0)
    assert lo == 30.0
    assert hi == 100.0


def test_potential_sales_info_text_lists_service_groups():
    text = psa.potential_sales_info_text()
    assert text.startswith("Potential Sales includes sellable headroom across:")
    for group in psa.POTENTIAL_SALES_SERVICE_GROUPS:
        assert group in text
    assert "Colocation" in text
    assert "How capacity is calculated:" in text
    assert "NetBackup" in text
    assert "License headroom is not included" in text
    assert "Nutanix" in text
    assert "sold↔used" in text or "comparison" in text.lower()
    assert "unified" in text.lower() or "filter" in text.lower()


def test_backup_sellable_families_exclude_nutanix_and_classic_hc_dupes():
    fams = set(psa.BACKUP_SELLABLE_FAMILIES)
    assert fams == {
        "backup_netbackup",
        "backup_veeam_replication",
        "backup_zerto_replication",
    }
    assert "backup_image" not in fams
    assert "backup_veeam_replication_classic" not in fams
    assert "backup_zerto_replication_hyperconverged" not in fams


def test_platform_total_includes_colocation_tl():
    panels = [
        {
            "family": "virt_classic",
            "resource_kind": "cpu",
            "potential_tl": 1000.0,
            "potential_tl_min": 1000.0,
            "potential_tl_max": 1000.0,
        },
    ]
    total, lo, hi = psa.platform_total_potential_range(panels, colocation_tl=500.0)
    assert total == pytest.approx(1500.0)
    assert lo == pytest.approx(1500.0)
    assert hi == pytest.approx(1500.0)


def test_platform_total_netbackup_image_app_dedupe():
    panels = [
        {
            "panel_key": "backup_netbackup_image",
            "family": "backup_netbackup",
            "resource_kind": "storage",
            "potential_tl": 10.0,
            "potential_tl_min": 10.0,
            "potential_tl_max": 100.0,
        },
        {
            "panel_key": "backup_netbackup_application",
            "family": "backup_netbackup",
            "resource_kind": "storage",
            "potential_tl": 20.0,
            "potential_tl_min": 5.0,
            "potential_tl_max": 80.0,
        },
    ]
    total, lo, hi = psa.platform_total_potential_range(panels)
    assert lo == pytest.approx(15.0)
    assert hi == pytest.approx(100.0)
    assert total == pytest.approx(15.0)


def test_platform_total_virt_replication_kind_dedupe():
    panels = [
        {
            "family": "virt_classic",
            "resource_kind": "cpu",
            "potential_tl": 50.0,
            "potential_tl_min": 40.0,
            "potential_tl_max": 60.0,
        },
        {
            "family": "backup_veeam_replication",
            "resource_kind": "cpu",
            "potential_tl": 30.0,
            "potential_tl_min": 20.0,
            "potential_tl_max": 55.0,
        },
        {
            "family": "backup_netbackup",
            "panel_key": "backup_netbackup_image",
            "resource_kind": "storage",
            "potential_tl": 10.0,
            "potential_tl_min": 10.0,
            "potential_tl_max": 10.0,
        },
    ]
    total, lo, hi = psa.platform_total_potential_range(panels)
    # cpu: dedupe(40/60, 20/55) → lo=60, hi=max(60,55)=60; storage 10
    assert lo == pytest.approx(70.0)
    assert hi == pytest.approx(70.0)
    assert total == pytest.approx(70.0)


def test_platform_total_potential_range_always_orders_band():
    """Inverted dual-track mins/maxes must still yield lo <= hi after aggregation."""
    panels = [
        {
            "family": "virt_hyperconverged",
            "resource_kind": "cpu",
            "potential_tl": 462076.0,
            "potential_tl_min": 462076.0,
            "potential_tl_max": 59713.0,
        },
        {
            "family": "backup_veeam_replication",
            "resource_kind": "storage",
            "potential_tl": 100.0,
            "potential_tl_min": 80.0,
            "potential_tl_max": 120.0,
        },
    ]
    total, lo, hi = psa.platform_total_potential_range(panels)
    assert lo <= hi
    assert total == lo or lo <= total <= hi


def test_collect_backup_sellable_panels_fetches_all_families():
    seen: list[str] = []

    def fake_get(**kwargs):
        fam = kwargs["family"]
        seen.append(fam)
        return [{"family": fam, "resource_kind": "cpu", "potential_tl": 1.0}]

    with patch.object(psa.api, "get_sellable_by_panel", side_effect=fake_get):
        panels = psa.collect_backup_sellable_panels(
            "DC13",
            classic_clusters=["c1"],
            hyperconv_clusters=["h1"],
            max_family_workers=1,
        )
    assert set(seen) == set(psa.BACKUP_SELLABLE_FAMILIES)
    assert len(panels) == len(psa.BACKUP_SELLABLE_FAMILIES)
