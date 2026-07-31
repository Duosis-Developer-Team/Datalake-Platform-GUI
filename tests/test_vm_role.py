"""Unit tests for VM role annotation and billable virt exclusion."""
from __future__ import annotations

from shared.backup.vm_role import (
    annotate_vm_roles,
    exclude_non_billable_virt,
    resolve_vm_role,
    sum_billable_virt_resources,
)


def test_resolve_vm_role_zerto_precedence():
    assert resolve_vm_role("prod-01", zerto_names=["prod-01"]) == "zerto"


def test_resolve_vm_role_veeam_dr_suffix():
    assert resolve_vm_role("app_dr") == "veeam_dr"


def test_resolve_vm_role_billable_default():
    assert resolve_vm_role("app-prod-01") == "billable"


def test_annotate_vm_roles_adds_badge_fields():
    rows = annotate_vm_roles([{"name": "app_dr", "cpu": 4, "memory_gb": 8, "disk_gb": 100}])
    assert rows[0]["role"] == "veeam_dr"
    assert rows[0]["role_label"] == "Veeam DR"
    assert rows[0]["virt_billable"] is False


def test_veeam_backup_tag_stays_billable():
    rows = annotate_vm_roles(
        [{"name": "app-01", "cpu": 2, "memory_gb": 4, "disk_gb": 50}],
        veeam_backup_names=["app-01"],
    )
    assert rows[0]["role"] == "veeam_backup"
    assert rows[0]["virt_billable"] is True


def test_exclude_non_billable_virt_drops_replicas():
    annotated = annotate_vm_roles(
        [
            {"name": "app-prod", "cpu": 2, "memory_gb": 4, "disk_gb": 50},
            {"name": "app_dr", "cpu": 4, "memory_gb": 8, "disk_gb": 100},
        ]
    )
    billable = exclude_non_billable_virt(annotated)
    assert len(billable) == 1
    assert billable[0]["name"] == "app-prod"


def test_sum_billable_virt_resources():
    annotated = annotate_vm_roles(
        [
            {"name": "app-prod", "cpu": 2, "memory_gb": 4, "disk_gb": 50},
            {"name": "app_dr", "cpu": 4, "memory_gb": 8, "disk_gb": 100},
        ]
    )
    totals = sum_billable_virt_resources(annotated)
    assert totals["vm_count"] == 1
    assert totals["cpu"] == 2.0
    assert totals["memory_gb"] == 4.0
    assert totals["disk_gb"] == 50.0
