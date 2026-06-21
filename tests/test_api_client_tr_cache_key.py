"""Tests for GUI api_client time-range cache key serialization."""
from __future__ import annotations

import unittest

from src.services import api_client as ac


class TestSerializeTrCacheKey(unittest.TestCase):
    def test_includes_start_end_for_preset(self):
        tr = {"start": "2026-06-15", "end": "2026-06-21", "preset": "7d"}
        key = ac._serialize_tr_cache_key(tr)
        self.assertIn("2026-06-15", key)
        self.assertIn("2026-06-21", key)
        self.assertIn("7d", key)

    def test_differs_from_api_params_only_key(self):
        tr = {"start": "2026-06-15", "end": "2026-06-21", "preset": "7d"}
        cache_key = ac._serialize_tr_cache_key(tr)
        api_key = ac._serialize_tr_params(tr)
        self.assertNotEqual(cache_key, api_key)
        self.assertIn("start", cache_key)


class TestShouldPersistApiCache(unittest.TestCase):
    def test_empty_customer_dict_not_persisted(self):
        empty = {"totals": {}, "assets": {}}
        self.assertFalse(ac._should_persist_api_cache(empty, empty))

    def test_non_empty_customer_persisted(self):
        payload = {"totals": {"vm_count": 1}, "assets": {}}
        empty = {"totals": {}, "assets": {}}
        self.assertTrue(ac._should_persist_api_cache(payload, empty))


if __name__ == "__main__":
    unittest.main()
