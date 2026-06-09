"""Unit tests for VMware host CPU GHz parsing and VM allocation aggregation."""
from __future__ import annotations

import unittest

from shared.vmware.host_cpu_ghz import (
    aggregate_vm_allocation,
    build_host_ghz_map,
    clear_host_map_cache,
    parse_cpu_ghz_from_text,
    resolve_host_ghz,
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


if __name__ == "__main__":
    unittest.main()
