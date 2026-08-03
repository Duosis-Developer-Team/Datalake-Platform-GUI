"""Customer adapter splits billable virt VMs from replica/DR machines."""
from __future__ import annotations

from app.adapters.customer_adapter import CustomerAdapter


def test_apply_vm_roles_splits_billable_and_replica():
    adapter = CustomerAdapter(lambda: None, lambda *a, **k: None, lambda *a, **k: None, lambda *a, **k: None)
    rows = [
        {"name": "AppVM01", "cpu": 4, "memory_gb": 8, "disk_gb": 100},
        {"name": "AppVM01_DR", "cpu": 4, "memory_gb": 8, "disk_gb": 100},
        {"name": "ZertoProtected", "cpu": 2, "memory_gb": 4, "disk_gb": 50},
    ]
    billable, replicas, totals, replica_by_role = adapter._apply_vm_roles_and_billable_totals(
        rows, zerto_names=["ZertoProtected"]
    )
    assert [r["name"] for r in billable] == ["AppVM01"]
    assert {r["name"] for r in replicas} == {"AppVM01_DR", "ZertoProtected"}
    assert totals["vm_count"] == 1
    assert totals["cpu"] == 4.0
    roles = {r["name"]: r["role"] for r in replicas}
    assert roles["AppVM01_DR"] == "veeam_dr"
    assert roles["ZertoProtected"] == "zerto"
    assert replica_by_role["veeam_dr"]["vm_count"] == 1
    assert replica_by_role["zerto"]["cpu"] == 2.0
    assert replica_by_role["totals"]["vm_count"] == 2


def test_customer_zerto_vm_names_sql_exists():
    from app.db.queries import customer as cq

    assert "raw_zerto_vm_metrics" in cq.CUSTOMER_ZERTO_VM_NAMES
    assert "raw_zerto_vpg_metrics" in cq.CUSTOMER_ZERTO_VM_NAMES
