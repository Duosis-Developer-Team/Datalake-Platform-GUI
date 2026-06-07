"""VM CPU percent normalization in customer CRM queries."""

from app.db.queries import customer as cq


def test_classic_vm_list_converts_vmware_mhz_to_percent():
    sql = cq.CUSTOMER_CLASSIC_VM_LIST
    assert "total_cpu_capacity_mhz" in sql
    assert "100.0 * COALESCE(a.cpu_mhz_min" in sql
    assert '"CPU min pct"' in sql


def test_hyperconv_nutanix_cpu_divided_by_10000():
    sql = cq.CUSTOMER_HYPERCONV_VM_LIST
    assert "cpu_usage_min / 10000.0" in sql
    assert "na.cpu_pct_min" in sql
    assert "100.0 * va.cpu_mhz_max" in sql


def test_pure_nutanix_cpu_divided_by_10000():
    sql = cq.CUSTOMER_PURE_NUTANIX_VM_LIST
    assert "cpu_usage_min / 10000.0" in sql
    assert "a.cpu_pct_min" in sql
    assert '"CPU max pct"' in sql
