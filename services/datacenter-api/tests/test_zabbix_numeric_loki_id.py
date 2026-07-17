"""Tests for numeric-only loki_id SQL guards (VFW_* firewall aliases)."""
from __future__ import annotations

import unittest

from app.db.queries import zabbix_network as znq


class ZabbixNumericLokiIdTests(unittest.TestCase):
    def test_numeric_predicate_matches_digits_only(self):
        self.assertEqual(znq.numeric_loki_id_predicate("fm.loki_id"), "fm.loki_id ~ '^[0-9]+$'")

    def test_firewall_summary_filters_non_numeric_loki_ids(self):
        self.assertIn("fm.loki_id ~ '^[0-9]+$'", znq.FIREWALL_SUMMARY_LATEST)

    def test_load_balancer_summary_filters_non_numeric_loki_ids(self):
        self.assertIn("dh.loki_id ~ '^[0-9]+$'", znq.LOAD_BALANCER_SUMMARY_LATEST)


if __name__ == "__main__":
    unittest.main()
