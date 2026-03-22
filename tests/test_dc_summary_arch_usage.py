"""
Unit tests for architecture-specific usage fields in DC summary and DC Summary panel rendering.
DB calls are mocked; no live database required.
"""

import unittest
from unittest.mock import MagicMock, patch

with patch("psycopg2.pool.ThreadedConnectionPool"):
    from src.services.db_service import DatabaseService

from src.services import cache_service as cache
from src.utils.time_range import default_time_range


class TestDcSummaryArchUsage(unittest.TestCase):
    def setUp(self):
        cache.clear()

    def test_rebuild_summary_includes_arch_usage(self):
        svc = DatabaseService()
        tr = default_time_range()

        # Prepare minimal all_dc_data with classic/hyperconv/power sections
        dc_code = "DC11"
        all_dc_data = {
            dc_code: {
                "meta": {"name": dc_code, "location": "Istanbul"},
                "classic": {
                    "hosts": 1,
                    "vms": 2,
                    "cpu_cap": 10.0,
                    "cpu_used": 5.0,
                    "cpu_pct": 50.0,
                    "mem_cap": 20.0,
                    "mem_used": 10.0,
                    "mem_pct": 50.0,
                    "stor_cap": 4.0,
                    "stor_used": 2.0,
                },
                "hyperconv": {
                    "hosts": 1,
                    "vms": 2,
                    "cpu_cap": 8.0,
                    "cpu_used": 4.0,
                    "cpu_pct": 50.0,
                    "mem_cap": 16.0,
                    "mem_used": 8.0,
                    "mem_pct": 50.0,
                    "stor_cap": 2.0,
                    "stor_used": 1.0,
                },
                "intel": {
                    "clusters": 1,
                    "hosts": 2,
                    "vms": 4,
                    "cpu_cap": 18.0,
                    "cpu_used": 9.0,
                    "ram_cap": 36.0,
                    "ram_used": 18.0,
                    "storage_cap": 6.0,
                    "storage_used": 3.0,
                },
                "power": {
                    "hosts": 0,
                    "vms": 0,
                    "vios": 0,
                    "lpar_count": 0,
                    "cpu_used": 0.0,
                    "cpu_assigned": 0.0,
                    "memory_total": 0.0,
                    "memory_assigned": 0.0,
                },
                "energy": {
                    "total_kw": 0.0,
                    "ibm_kw": 0.0,
                    "vcenter_kw": 0.0,
                    "total_kwh": 0.0,
                    "ibm_kwh": 0.0,
                    "vcenter_kwh": 0.0,
                },
                "platforms": {
                    "nutanix": {"hosts": 0, "vms": 0},
                    "vmware": {"clusters": 1, "hosts": 2, "vms": 4},
                    "ibm": {"hosts": 0, "vios": 0, "lpars": 0},
                },
            }
        }

        # Patch internal batch fetch to return our fake data
        svc._load_dc_list = MagicMock(return_value=[dc_code])
        svc._fetch_all_batch = MagicMock(return_value=(all_dc_data, {dc_code: 1}))

        summary = svc._rebuild_summary(tr)
        self.assertEqual(len(summary), 1)
        stats = summary[0]["stats"]
        self.assertIn("arch_usage", stats)

        arch_usage = stats["arch_usage"]
        self.assertIn("classic", arch_usage)
        self.assertIn("hyperconv", arch_usage)
        self.assertIn("ibm", arch_usage)

        self.assertAlmostEqual(arch_usage["classic"]["cpu_pct"], 50.0, places=1)
        self.assertAlmostEqual(arch_usage["classic"]["ram_pct"], 50.0, places=1)
        self.assertAlmostEqual(arch_usage["classic"]["disk_pct"], 50.0, places=1)

if __name__ == "__main__":
    unittest.main()

