"""Unit tests for HC Nutanix disk intersection helpers."""
from __future__ import annotations

from shared.backup.nutanix_intersection import (
    intersect_hc_nutanix_names,
    sum_nutanix_disk_for_names,
)


def test_intersect_requires_all_three_sets():
    assert intersect_hc_nutanix_names(["A", "B"], ["B", "C"], ["B"]) == {"b"}
    assert intersect_hc_nutanix_names(["A"], ["B"], ["B"]) == set()
    assert intersect_hc_nutanix_names([], ["B"], ["B"]) == set()


def test_intersect_case_insensitive():
    assert intersect_hc_nutanix_names(["vm-DR-01"], ["VM-DR-01"], ["vm-dr-01"]) == {
        "vm-dr-01"
    }


def test_sum_nutanix_disk_for_names():
    rows = [
        {"name": "vm-a", "disk_gb": 100.0},
        {"name": "VM-B", "disk_gb": 50.5},
        {"name": "vm-c", "disk_gb": 999.0},
    ]
    out = sum_nutanix_disk_for_names(rows, ["vm-a", "vm-b"])
    assert out["disk_gb"] == 150.5
    assert out["vm_count"] == 2


def test_sum_nutanix_disk_empty():
    assert sum_nutanix_disk_for_names([], []) == {"disk_gb": 0.0, "vm_count": 0}
