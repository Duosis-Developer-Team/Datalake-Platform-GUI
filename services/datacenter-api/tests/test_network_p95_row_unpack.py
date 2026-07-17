"""Tests for safe network p95 row unpacking."""
from __future__ import annotations

import unittest

from app.services.dc_service import DatabaseService


class NetworkP95RowUnpackTests(unittest.TestCase):
    def test_short_row_is_skipped_without_exception(self):
        items, total = DatabaseService._network_p95_rows_to_items([(1, 2, 3)], include_total=True)
        self.assertEqual(items, [])
        self.assertEqual(total, 0)

    def test_six_column_row_unpacks_without_host(self):
        row = ("eth0", "alias", 1.0, 2.0, 3.0, 1000.0)
        items, _ = DatabaseService._network_p95_rows_to_items([row], include_total=False)
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]["host"])
        self.assertEqual(items[0]["interface_name"], "eth0")


if __name__ == "__main__":
    unittest.main()
