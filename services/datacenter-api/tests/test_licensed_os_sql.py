from app.db.queries import licensed_os as lq


def test_global_sql_reads_config_columns_and_excludes_templates():
    sql = lq.VM_OS_CONFIG_LATEST
    assert "raw_vmware_vm_config" in sql
    assert "guest_id" in sql
    assert "guest_full_name" in sql
    assert "DISTINCT ON (vm_moid, vcenter_uuid)" in sql
    assert "collection_timestamp BETWEEN %s AND %s" in sql
    assert "COALESCE(template, false) = false" in sql


def test_global_sql_coalesces_runtime_tools_field():
    sql = lq.VM_OS_CONFIG_LATEST
    assert "raw_vmware_vm_runtime" in sql
    assert "guest_guest_full_name" in sql


def test_customer_sql_adds_name_ilike():
    sql = lq.VM_OS_CONFIG_LATEST_FOR_CUSTOMER
    assert "name ILIKE %s" in sql
    assert "raw_vmware_vm_config" in sql


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
