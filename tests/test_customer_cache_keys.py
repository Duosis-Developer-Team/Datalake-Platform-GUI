"""Tests for customer assets cache key versioning."""
from __future__ import annotations

import unittest

from shared.customer.cache_keys import CUSTOMER_ASSETS_CACHE_VERSION, customer_assets_cache_key


class TestCustomerAssetsCacheKey(unittest.TestCase):
    def test_key_includes_version(self):
        key = customer_assets_cache_key("Boyner", "2026-01-01", "2026-01-31")
        self.assertIn(CUSTOMER_ASSETS_CACHE_VERSION, key)
        self.assertEqual(key, f"customer_assets:{CUSTOMER_ASSETS_CACHE_VERSION}:Boyner:2026-01-01:2026-01-31")


if __name__ == "__main__":
    unittest.main()
