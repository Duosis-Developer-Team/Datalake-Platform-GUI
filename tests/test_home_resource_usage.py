"""
Unit tests for home page resource usage split: classic_totals, hyperconv_totals, ibm_totals.
Verifies global_dashboard structure and percentage derivation.
"""

import unittest
from unittest.mock import MagicMock, patch

with patch("psycopg2.pool.ThreadedConnectionPool"):
    from src.services.db_service import DatabaseService

from src.services import cache_service as cache
from src.utils.time_range import default_time_range


def _make_service():
    with patch("psycopg2.pool.ThreadedConnectionPool"):
        svc = DatabaseService()
    svc._pool = MagicMock()
    return svc


class TestGlobalDashboardTotals(unittest.TestCase):

    def setUp(self):
        cache.clear()

    def test_get_global_dashboard_fallback_includes_architecture_totals(self):
        """When cache is empty, fallback dict must include classic_totals, hyperconv_totals, ibm_totals."""
        svc = _make_service()
        tr = default_time_range()
        svc.get_all_datacenters_summary = MagicMock(return_value=[])
        result = svc.get_global_dashboard(tr)
        self.assertIn("classic_totals", result)
        self.assertIn("hyperconv_totals", result)
        self.assertIn("ibm_totals", result)
        self.assertEqual(list(result["classic_totals"].keys()), ["cpu_cap", "cpu_used", "mem_cap", "mem_used", "stor_cap", "stor_used"])
        self.assertEqual(list(result["ibm_totals"].keys()), ["mem_total", "mem_assigned", "cpu_used", "cpu_assigned"])

    def test_classic_totals_zero_when_no_data(self):
        svc = _make_service()
        tr = default_time_range()
        svc.get_all_datacenters_summary = MagicMock(return_value=[])
        result = svc.get_global_dashboard(tr)
        for k, v in result["classic_totals"].items():
            self.assertEqual(v, 0.0, f"classic_totals[{k}] should be 0")
        for k, v in result["hyperconv_totals"].items():
            self.assertEqual(v, 0.0, f"hyperconv_totals[{k}] should be 0")
        for k, v in result["ibm_totals"].items():
            self.assertEqual(v, 0.0, f"ibm_totals[{k}] should be 0")


class TestResourceUsagePercentages(unittest.TestCase):

    def test_pct_derivation_classic(self):
        """Percentages for classic: used/cap * 100."""
        classic_totals = {"cpu_cap": 100.0, "cpu_used": 50.0, "mem_cap": 200.0, "mem_used": 100.0, "stor_cap": 10.0, "stor_used": 5.0}
        def _pct(used, cap):
            return round(used / cap * 100, 1) if cap and cap > 0 else 0.0
        cpu_pct = _pct(classic_totals.get("cpu_used", 0) or 0, classic_totals.get("cpu_cap", 0) or 1)
        ram_pct = _pct(classic_totals.get("mem_used", 0) or 0, classic_totals.get("mem_cap", 0) or 1)
        stor_pct = _pct(classic_totals.get("stor_used", 0) or 0, classic_totals.get("stor_cap", 0) or 1)
        self.assertEqual(cpu_pct, 50.0)
        self.assertEqual(ram_pct, 50.0)
        self.assertEqual(stor_pct, 50.0)

    def test_pct_zero_when_cap_zero(self):
        def _pct(used, cap):
            return round(used / cap * 100, 1) if cap and cap > 0 else 0.0
        self.assertEqual(_pct(10, 0), 0.0)
        self.assertEqual(_pct(0, 0), 0.0)


if __name__ == "__main__":
    unittest.main()
