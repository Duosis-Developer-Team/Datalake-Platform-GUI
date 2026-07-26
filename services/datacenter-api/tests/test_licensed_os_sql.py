from app.db.queries import licensed_os as lq


def test_global_sql_reads_netbox_guest_os():
    # Source switched from the dead raw_vmware_vm_config (135d stale, TASK-81
    # follow-up) to the live NetBox VM snapshot's guest-OS custom field.
    sql = lq.VM_OS_NETBOX
    assert "discovery_netbox_virtualization_vm" in sql
    assert "custom_fields_guest_os" in sql
    assert "guest_full_name" in sql
    # the dead VMware raw tables must no longer be the source
    assert "raw_vmware_vm_config" not in sql
    assert "raw_vmware_vm_runtime" not in sql


def test_customer_sql_adds_name_ilike():
    sql = lq.VM_OS_NETBOX_FOR_CUSTOMER
    assert "name ILIKE %s" in sql
    assert "discovery_netbox_virtualization_vm" in sql


class _FakeCur:
    def __init__(self, rows): self._rows = rows
    def execute(self, *a, **k): pass
    def fetchall(self): return self._rows
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_tally_classifies_and_counts():
    from app.services.dc_service import DatabaseService
    db = DatabaseService.__new__(DatabaseService)  # no pool needed for _tally_os_rows
    rows = [
        ("web-01", "rhel8_64Guest", "Red Hat Enterprise Linux 8 (64-bit)"),
        ("db-02", "sles15_64Guest", "SUSE Linux Enterprise 15"),
        ("ad-03", "windows2019srv_64Guest", "Microsoft Windows Server 2019"),
        ("app-04", "ubuntu64Guest", "Ubuntu Linux (64-bit)"),
        ("x-05", "otherLinux64Guest", "Other Linux (64-bit)"),
    ]
    out = db._tally_os_rows(rows)
    assert out["families"] == {"rhel": 1, "suse": 1, "windows": 1, "free": 1, "unknown": 1}
    assert out["total"] == 5
    assert out["unknown_samples"] == ["Other Linux (64-bit)"]
