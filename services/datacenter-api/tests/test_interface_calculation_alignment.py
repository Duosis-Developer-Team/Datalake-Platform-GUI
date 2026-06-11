"""Tests for backbone billing alignment with interface_calculation.py."""

from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.db.queries import zabbix_network as znq
from shared.network.backbone_billing import estimate_backbone_cost_tl, p95_bps_to_mbit


class InterfaceCalculationAlignmentTests(unittest.TestCase):
    def test_p95_sql_uses_total_bps_percentile_not_sum_of_rx_tx(self):
        sql = znq.build_interface_bandwidth_table_p95_sql("backbone")
        self.assertIn(
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY (avg_rx_bps + avg_tx_bps)) AS p95_total_bps",
            sql,
        )
        self.assertNotIn("COALESCE(p95_rx_bps, 0) + COALESCE(p95_tx_bps, 0) AS p95_total_bps", sql)

    def test_mbit_conversion_matches_reference_script(self):
        # interface_calculation.py: p95_bps / 1_000_000 -> Mbps
        self.assertEqual(p95_bps_to_mbit(10_000_000_000), 10_000.0)

    def test_cost_formula_mbit_times_unit_price(self):
        self.assertEqual(estimate_backbone_cost_tl(5_000_000_000, 331.12), 1_655_600.0)


if __name__ == "__main__":
    unittest.main()
