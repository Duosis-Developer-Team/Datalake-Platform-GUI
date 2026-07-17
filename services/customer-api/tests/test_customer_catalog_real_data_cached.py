"""Tests for customer catalog real_data_cached badge logic."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import customer_catalog as cc


class TestRealDataCached(unittest.TestCase):
    def test_empty_primary_and_last_good_miss_is_not_cached(self):
        with patch.object(cc.cache, "get_with_stale", return_value=({"totals": {}, "assets": {}}, False)), \
             patch.object(cc.cache, "get_last_good", return_value=None):
            self.assertFalse(cc._real_data_cached("Boyner"))

    def test_payload_with_totals_is_cached(self):
        with patch.object(cc.cache, "get_with_stale", return_value=({"totals": {"vm_count": 3}, "assets": {}}, False)), \
             patch.object(cc.cache, "get_last_good", return_value=None):
            self.assertTrue(cc._real_data_cached("Boyner"))

    def test_empty_primary_with_last_good_is_cached(self):
        with patch.object(cc.cache, "get_with_stale", return_value=({"totals": {}, "assets": {}}, False)), \
             patch.object(
                 cc.cache,
                 "get_last_good",
                 return_value={"totals": {"vm_count": 2}, "assets": {"vm": []}},
             ):
            self.assertTrue(cc._real_data_cached("Boyner"))

    def test_last_good_only_hit_is_cached(self):
        with patch.object(
            cc.cache,
            "get_with_stale",
            return_value=({"totals": {"cpu": 1}, "assets": {}}, True),
        ), patch.object(cc.cache, "get_last_good", return_value=None):
            self.assertTrue(cc._real_data_cached("Boyner"))

    def test_wrong_preset_key_can_be_checked_explicitly(self):
        tr = {"start": "2026-06-01", "end": "2026-06-30", "preset": "30d"}
        with patch.object(
            cc.cache,
            "get_with_stale",
            return_value=({"totals": {"vm_count": 1}, "assets": {}}, False),
        ) as get_with_stale, patch.object(cc.cache, "get_last_good", return_value=None):
            self.assertTrue(cc._real_data_cached("Boyner", tr))
        cache_key = get_with_stale.call_args[0][0]
        self.assertIn("2026-06-01", cache_key)
        self.assertIn("2026-06-30", cache_key)


if __name__ == "__main__":
    unittest.main()
