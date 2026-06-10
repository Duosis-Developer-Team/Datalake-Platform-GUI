"""Unit tests for VMware host CPU GHz parsing and VM allocation aggregation."""
from __future__ import annotations

import unittest

from shared.vmware.host_cpu_ghz import (
    aggregate_vm_allocation,
    build_host_ghz_map,
    clear_host_map_cache,
    compute_cpu_overalloc_flags,
    compute_cpu_usage_vs_sold,
    enrich_customer_vm_cpu_list,
    enrich_vm_cpu_sales_fields,
    parse_cpu_ghz_from_text,
    resolve_host_ghz,
    sum_cpu_real_total,
    sum_cpu_used_ghz_avg_total,
    sum_cpu_used_ghz_max_total,
)


class TestParseCpuGhz(unittest.TestCase):
    def test_xeon_at_format(self):
        self.assertAlmostEqual(
            parse_cpu_ghz_from_text("Intel(R) Xeon(R) Gold 6248 CPU @ 2.50GHz"),
            2.5,
        )

    def test_compact_ghz_format(self):
        self.assertAlmostEqual(parse_cpu_ghz_from_text("2.1GHz/16-core"), 2.1)

    def test_empty_returns_none(self):
        self.assertIsNone(parse_cpu_ghz_from_text(None))
        self.assertIsNone(parse_cpu_ghz_from_text("no clock here"))


class TestHostGhzMap(unittest.TestCase):
    def test_build_map_from_netbox_rows(self):
        rows = [
            ("g1ahv2dc13", "Intel(R) Xeon(R) Gold 6248 CPU @ 2.50GHz", None),
            ("eng1hv1ict21.blt.vc", None, "Intel Xeon 2.60GHz"),
        ]
        mapping = build_host_ghz_map(rows)
        self.assertAlmostEqual(mapping["g1ahv2dc13"], 2.5)
        self.assertAlmostEqual(mapping["eng1hv1ict21.blt.vc"], 2.6)


class TestAggregateVmAllocation(unittest.TestCase):
    def setUp(self):
        clear_host_map_cache()

    def test_sums_vcpu_times_host_ghz(self):
        rows = [
            ("host-a", 4, 16.0, 100.0, 40.0),
            ("host-a", 2, 8.0, 50.0, 20.0),
            ("host-b", 8, 32.0, 200.0, 80.0),
        ]
        host_map = {"host-a": 2.5, "host-b": 2.6}
        result = aggregate_vm_allocation(rows, host_map, default_ghz=2.0)
        self.assertAlmostEqual(result["cpu_alloc_ghz_vm"], 4 * 2.5 + 2 * 2.5 + 8 * 2.6)
        self.assertAlmostEqual(result["cpu_alloc_ghz_sales"], 4 + 2 + 8)
        self.assertAlmostEqual(result["mem_alloc_gb_vm"], 56.0)
        self.assertEqual(result["cpu_alloc_hosts_resolved"], 2)

    def test_default_ghz_when_host_missing(self):
        rows = [("unknown-host", 2, 4.0, 10.0, 5.0)]
        result = aggregate_vm_allocation(rows, {}, default_ghz=2.0)
        self.assertAlmostEqual(result["cpu_alloc_ghz_vm"], 4.0)
        self.assertEqual(result["cpu_alloc_hosts_fallback_default"], 1)


class TestResolveHostGhz(unittest.TestCase):
    def test_netbox_then_default(self):
        ghz, src = resolve_host_ghz("h1", {"h1": 2.5}, default_ghz=2.0)
        self.assertEqual(src, "netbox")
        self.assertAlmostEqual(ghz, 2.5)
        ghz2, src2 = resolve_host_ghz("missing", {}, default_ghz=2.0)
        self.assertEqual(src2, "default")
        self.assertAlmostEqual(ghz2, 2.0)


class TestCustomerVmEnrichment(unittest.TestCase):
    def test_enrich_vmware_row_exceeds_sales_limit(self):
        host_map = {"host-a": 2.5}
        row = enrich_vm_cpu_sales_fields("host-a", 4, host_map, default_ghz=2.0)
        self.assertAlmostEqual(row["cpu_ghz_sales"], 4.0)
        self.assertAlmostEqual(row["cpu_ghz_real"], 10.0)
        self.assertTrue(row["cpu_exceeds_sales_limit"])

    def test_enrich_nutanix_row_sales_equals_real(self):
        row = enrich_vm_cpu_sales_fields(None, 8, {}, is_nutanix=True)
        self.assertAlmostEqual(row["cpu_ghz_sales"], 8.0)
        self.assertAlmostEqual(row["cpu_ghz_real"], 8.0)
        self.assertFalse(row["cpu_exceeds_sales_limit"])

    def test_enrich_customer_vm_list_and_total(self):
        vms = [
            {
                "name": "vm1",
                "source": "Classic",
                "cluster": "KM-1",
                "vmhost": "h1",
                "cpu": 4.0,
                "cpu_pct_avg": 40.0,
                "cpu_pct_max": 60.0,
            },
            {"name": "vm2", "source": "Nutanix", "cluster": "NX-1", "vmhost": None, "cpu": 4.0, "cpu_pct_max": 50.0},
        ]
        enriched = enrich_customer_vm_cpu_list(vms, {"h1": 3.0})
        self.assertAlmostEqual(enriched[0]["cpu_ghz_real"], 12.0)
        self.assertAlmostEqual(enriched[0]["cpu_used_ghz_avg"], 4.8)
        self.assertAlmostEqual(enriched[0]["cpu_used_ghz_max"], 7.2)
        self.assertTrue(enriched[0]["cpu_usage_exceeds_sold_avg"])
        self.assertTrue(enriched[0]["cpu_usage_exceeds_sold_max"])
        self.assertAlmostEqual(enriched[1]["cpu_used_ghz_max"], 2.0)
        self.assertFalse(enriched[1]["cpu_usage_exceeds_sold_max"])
        self.assertAlmostEqual(sum_cpu_used_ghz_max_total(enriched), 9.2)


class TestCpuUsageVsSold(unittest.TestCase):
    def test_avg_exceeds_sold(self):
        out = compute_cpu_usage_vs_sold(4.0, 12.0, 40.0, 25.0)
        self.assertAlmostEqual(out["cpu_used_ghz_avg"], 4.8)
        self.assertAlmostEqual(out["cpu_used_ghz_max"], 3.0)
        self.assertTrue(out["cpu_usage_exceeds_sold_avg"])
        self.assertFalse(out["cpu_usage_exceeds_sold_max"])

    def test_max_exceeds_sold(self):
        out = compute_cpu_usage_vs_sold(4.0, 12.0, 20.0, 60.0)
        self.assertAlmostEqual(out["cpu_used_ghz_max"], 7.2)
        self.assertTrue(out["cpu_usage_exceeds_sold_max"])

    def test_nutanix_peak_over_100_pct(self):
        out = compute_cpu_usage_vs_sold(8.0, 8.0, 90.0, 110.0)
        self.assertAlmostEqual(out["cpu_used_ghz_max"], 8.8)
        self.assertTrue(out["cpu_usage_exceeds_sold_max"])


class TestCpuOverallocFlags(unittest.TestCase):
    def test_sales_and_real_flags(self):
        flags = compute_cpu_overalloc_flags(100.0, 120.0, 80.0)
        self.assertTrue(flags["cpu_overallocated_sales"])
        self.assertFalse(flags["cpu_overallocated_real"])

        flags2 = compute_cpu_overalloc_flags(100.0, 80.0, 150.0)
        self.assertFalse(flags2["cpu_overallocated_sales"])
        self.assertTrue(flags2["cpu_overallocated_real"])


if __name__ == "__main__":
    unittest.main()
