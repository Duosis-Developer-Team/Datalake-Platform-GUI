"""VM CPU percent normalization in customer CRM queries."""

import re

from app.db.queries import customer as cq


def _count_psycopg2_placeholders(sql: str) -> int:
    """Count %s placeholders (ignore %% escapes)."""
    return len(re.findall(r"(?<!%)%s", sql))


def test_classic_vm_list_uses_vmware_cpu_usage_as_percent():
    sql = cq.CUSTOMER_CLASSIC_VM_LIST
    assert "cpu_usage_min_mhz" in sql
    assert "100.0 * COALESCE(a.cpu_mhz_min" not in sql
    assert '"CPU min pct"' in sql
    assert _count_psycopg2_placeholders(sql) == 6
    assert re.search(r"(?<!%)%(?!s)", sql.replace("%%", "")) is None


def test_hyperconv_vmware_cpu_usage_as_percent_nutanix_divided_by_10000():
    sql = cq.CUSTOMER_HYPERCONV_VM_LIST
    assert "cpu_usage_min / 10000.0" in sql
    assert "na.cpu_pct_min" in sql
    assert "WHEN v.vmname IS NOT NULL THEN va.cpu_mhz_max" in sql
    assert "100.0 * va.cpu_mhz_max" not in sql


def test_pure_nutanix_cpu_divided_by_10000():
    sql = cq.CUSTOMER_PURE_NUTANIX_VM_LIST
    assert "cpu_usage_min / 10000.0" in sql
    assert "a.cpu_pct_min" in sql
    assert '"CPU max pct"' in sql
