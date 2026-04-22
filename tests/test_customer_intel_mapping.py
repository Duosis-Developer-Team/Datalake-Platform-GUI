"""Unit tests for customer-api assets.intel mapping in customer_view."""

from src.pages.customer_view import _backup_storage_volume_gb, _intel_vm_cpu_breakdown


def test_intel_breakdown_reads_nested_vms_cpu():
    totals = {"intel_vms_total": 100, "intel_cpu_total": 50.5}
    intel_asset = {
        "vms": {"vmware": 60, "nutanix": 40, "total": 100},
        "cpu": {"vmware": 30.0, "nutanix": 20.5, "total": 50.5},
    }
    vm, cpu = _intel_vm_cpu_breakdown(totals, intel_asset)
    assert vm["total"] == 100
    assert vm["vmware"] == 60
    assert vm["nutanix"] == 40
    assert cpu["total"] == 50.5
    assert cpu["vmware"] == 30.0
    assert cpu["nutanix"] == 20.5


def test_intel_breakdown_empty_intel_asset():
    totals = {"intel_vms_total": 0, "intel_cpu_total": 0.0}
    vm, cpu = _intel_vm_cpu_breakdown(totals, {})
    assert vm == {"total": 0, "vmware": 0, "nutanix": 0}
    assert cpu == {"total": 0.0, "vmware": 0.0, "nutanix": 0.0}


def test_backup_storage_volume_gb_primary_key():
    assert _backup_storage_volume_gb({"storage_volume_gb": 12.5}) == 12.5


def test_backup_storage_volume_gb_legacy_fallback():
    assert _backup_storage_volume_gb({"ibm_storage_volume_gb": 9.0}) == 9.0


def test_backup_storage_volume_gb_missing():
    assert _backup_storage_volume_gb({}) == 0.0
