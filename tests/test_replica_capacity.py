"""Unit tests for shared.backup.replica_capacity."""
from __future__ import annotations

from shared.backup.replica_capacity import sum_replica_resources


def test_sum_replica_resources_groups_classic_and_hc_by_cluster():
    rows = [
        {
            "name": "app01_DR",
            "cluster": "KM-1",
            "architecture": "classic",
            "cpu": 4.0,
            "memory_gb": 16.0,
            "disk_gb": 100.0,
        },
        {
            "name": "db01_replica",
            "cluster": "HC-A",
            "source": "nutanix",
            "cpu": 8.0,
            "memory_gb": 32.0,
            "disk_gb": 200.0,
        },
        {
            "name": "prod-web",  # billable — ignored
            "cluster": "KM-1",
            "architecture": "classic",
            "cpu": 2.0,
            "memory_gb": 8.0,
            "disk_gb": 50.0,
        },
        {
            "name": "silinecek-dr",  # silinecek — ignored
            "cluster": "KM-1",
            "architecture": "classic",
            "cpu": 1.0,
            "memory_gb": 2.0,
            "disk_gb": 10.0,
        },
    ]
    out = sum_replica_resources(rows)
    assert out["replica_vm_count"] == 2
    assert out["classic"]["by_cluster"]["KM-1"]["vm_count"] == 1
    assert out["classic"]["by_cluster"]["KM-1"]["cpu"] == 4.0
    assert out["hyperconverged"]["by_cluster"]["HC-A"]["disk_gb"] == 200.0
    assert out["totals"]["cpu"] == 12.0
    assert out["totals"]["memory_gb"] == 48.0
    assert out["totals"]["disk_gb"] == 300.0
    assert out["totals"]["vm_count"] == 2


def test_sum_replica_resources_empty():
    out = sum_replica_resources([])
    assert out["replica_vm_count"] == 0
    assert out["classic"]["by_cluster"] == {}
    assert out["hyperconverged"]["totals"]["vm_count"] == 0
