"""Tests for role-based Zabbix network scope SQL builders."""

from __future__ import annotations

import unittest

from app.db.queries import zabbix_network as znq


class ZabbixNetworkScopeTests(unittest.TestCase):
    def test_resolve_interface_table_overview(self):
        self.assertEqual(
            znq.resolve_interface_table(None),
            "raw_zabbix_network_interface_metrics_v",
        )
        self.assertEqual(
            znq.resolve_interface_table("overview"),
            "raw_zabbix_network_interface_metrics_v",
        )

    def test_resolve_interface_table_shared(self):
        self.assertEqual(
            znq.resolve_interface_table("shared"),
            "raw_zabbix_network_switch_shared_interface_metrics",
        )

    def test_invalid_scope_raises(self):
        with self.assertRaises(ValueError):
            znq.resolve_interface_table("invalid")

    def test_leaf_sql_excludes_shared_overlap(self):
        sql = znq.build_interface_95th_percentile_sql("leaf")
        self.assertIn("raw_zabbix_network_leaf_interface_metrics", sql)
        self.assertIn("switch_shared_interface_metrics", sql)
        self.assertIn("host", sql)

    def test_shared_sql_uses_shared_table(self):
        sql = znq.build_interface_bandwidth_table_p95_sql("shared")
        self.assertIn("raw_zabbix_network_switch_shared_interface_metrics", sql)
        self.assertNotIn("switch_shared_interface_metrics s", sql)


if __name__ == "__main__":
    unittest.main()
