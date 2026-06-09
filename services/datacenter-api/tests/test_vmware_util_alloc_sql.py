"""SQL shape tests for VMware utilization stats queries."""
from __future__ import annotations

import unittest

from app.db.queries import vmware as vq


class TestVmwareUtilStatsSql(unittest.TestCase):
    def test_classic_avg30_uses_used_over_capacity(self):
        sql = vq.CLASSIC_AVG30
        self.assertIn("cpu_ghz_used / cpu_ghz_capacity", sql)
        self.assertIn("memory_used_gb / memory_capacity_gb", sql)
        self.assertNotIn("cpu_usage_avg_perc", sql)

    def test_hyperconv_avg30_uses_used_over_capacity(self):
        sql = vq.HYPERCONV_AVG30
        self.assertIn("cpu_ghz_used / cpu_ghz_capacity", sql)
        self.assertNotIn("memory_usage_avg_perc", sql)

    def test_vm_allocation_rows_include_cluster_filter(self):
        self.assertIn("cardinality(%s::text[])", vq.CLASSIC_VM_ALLOCATION_ROWS)
        self.assertIn("number_of_cpus", vq.CLASSIC_VM_ALLOCATION_ROWS)

    def test_netbox_host_query_present(self):
        self.assertIn("discovery_netbox_inventory_device", vq.NETBOX_HOST_CPU_STRINGS)
        self.assertIn("custom_fields", vq.NETBOX_HOST_CPU_STRINGS)


if __name__ == "__main__":
    unittest.main()
