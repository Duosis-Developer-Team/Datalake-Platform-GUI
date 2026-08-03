"""Panel mapping: classic vs HC Veeam/Zerto replication keys."""
from __future__ import annotations

from shared.sellable.panel_mapping import classify


def test_veeam_replication_classic_vs_hc():
    assert (
        classify("Klasik Mimari Veeam Replication vCpu")
        == "backup_veeam_replication_classic_cpu"
    )
    assert (
        classify("Hyperconverged Mimari Veeam Replication RAM")
        == "backup_veeam_replication_hyperconverged_ram"
    )
    assert (
        classify("Klasik Mimari Veeam Replication Disk - NVMe")
        == "backup_veeam_replication_classic_storage"
    )


def test_zerto_replication_classic_vs_hc():
    assert (
        classify("Klasik Mimari Zerto Replication vCpu")
        == "backup_zerto_replication_classic_cpu"
    )
    assert (
        classify("Hyperconverged Mimari Zerto Replication Disk - SSD")
        == "backup_zerto_replication_hyperconverged_storage"
    )
    assert (
        classify("Hyperconverged Mimari Zerto Replication RAM")
        == "backup_zerto_replication_hyperconverged_ram"
    )


def test_legacy_replication_keys_still_classify():
    """Legacy combined keys remain fallback when architecture is absent."""
    assert classify("Veeam Replication vCpu") == "backup_veeam_replication_cpu"
    assert classify("Zerto Replication RAM") == "backup_zerto_replication_ram"
