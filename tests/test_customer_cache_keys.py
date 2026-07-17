"""Tests for customer assets cache key versioning."""
from __future__ import annotations

import unittest

from shared.customer.cache_keys import CUSTOMER_ASSETS_CACHE_VERSION, customer_assets_cache_key


class TestCustomerAssetsCacheKey(unittest.TestCase):
    def test_key_includes_version(self):
        key = customer_assets_cache_key("Boyner", "2026-01-01", "2026-01-31")
        self.assertIn(CUSTOMER_ASSETS_CACHE_VERSION, key)
        self.assertEqual(key, f"customer_assets:{CUSTOMER_ASSETS_CACHE_VERSION}:Boyner:2026-01-01:2026-01-31")

    def test_api_client_key_shares_the_version_token(self):
        """The GUI's response cache must invalidate on a payload-shape bump too.

        It once hardcoded its own copy of the token, so bumping the shared version
        left the front-end serving the pre-bump payload shape.
        """
        from src.services.api_client import _customer_resources_ck

        key = _customer_resources_ck("Boyner", {"preset": "7d"})
        self.assertIn(CUSTOMER_ASSETS_CACHE_VERSION, key)


if __name__ == "__main__":
    unittest.main()
