"""Tests for interface table total count and export SQL builders."""

from __future__ import annotations

import unittest

from app.db.queries import zabbix_network as znq


class InterfaceExportSqlTests(unittest.TestCase):
    def test_table_sql_includes_total_count_window(self):
        sql = znq.build_interface_bandwidth_table_p95_sql("backbone")
        self.assertIn("COUNT(*) OVER()", sql)
        self.assertIn("LIMIT %s OFFSET %s", sql)

    def test_export_sql_has_cap_no_offset(self):
        sql = znq.build_interface_bandwidth_table_p95_export_sql("router_uplink")
        self.assertIn("LIMIT %s", sql)
        self.assertNotIn("OFFSET", sql)
        self.assertEqual(znq.INTERFACE_EXPORT_MAX_ROWS, 5000)


if __name__ == "__main__":
    unittest.main()
