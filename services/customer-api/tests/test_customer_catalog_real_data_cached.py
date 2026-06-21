"""Tests for customer catalog real_data_cached badge logic."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import customer_catalog as cc


class TestRealDataCached(unittest.TestCase):
    def test_empty_payload_is_not_cached(self):
        with patch.object(cc.cache, "get", return_value={"totals": {}, "assets": {}}):
            self.assertFalse(cc._real_data_cached("Boyner"))

    def test_payload_with_totals_is_cached(self):
        with patch.object(cc.cache, "get", return_value={"totals": {"vm_count": 3}, "assets": {}}):
            self.assertTrue(cc._real_data_cached("Boyner"))


if __name__ == "__main__":
    unittest.main()
