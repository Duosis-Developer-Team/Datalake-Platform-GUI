"""Tests for backbone P95 row-level TL billing enrichment."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.services.dc_service import DatabaseService


class BackboneBillingEnrichmentTests(unittest.TestCase):
    def test_apply_backbone_billing_math(self):
        items = [{"host": "sw-01", "p95_total_bps": 10_000_000_000}]
        price_meta = {
            "unit_price_tl": 331.12,
            "has_price": True,
            "productid": "e2f585bb-c2e0-f011-8406-6045bd9c244d",
        }
        enriched = DatabaseService._apply_backbone_billing(items, price_meta)
        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0]["p95_billable_mbit"], 10000.0)
        self.assertEqual(enriched[0]["unit_price_tl_per_mbit"], 331.12)
        self.assertEqual(enriched[0]["estimated_cost_tl"], 3_311_200.0)

    def test_apply_backbone_billing_without_price(self):
        items = [{"host": "sw-01", "p95_total_bps": 5_000_000}]
        price_meta = {"unit_price_tl": 0.0, "has_price": False}
        enriched = DatabaseService._apply_backbone_billing(items, price_meta)
        self.assertEqual(enriched[0]["p95_billable_mbit"], 5.0)
        self.assertIsNone(enriched[0]["unit_price_tl_per_mbit"])
        self.assertIsNone(enriched[0]["estimated_cost_tl"])

    def test_backbone_billing_response_meta(self):
        meta = DatabaseService._backbone_billing_response_meta(
            {
                "productid": "e2f585bb-c2e0-f011-8406-6045bd9c244d",
                "product_name": "Veri Merkezi Erişim ve L3 DDoS Hizmeti",
                "resource_unit": "Mbit",
                "unit_price_tl": 331.12,
                "price_source": "catalog",
                "has_price": True,
            }
        )
        self.assertTrue(meta["enabled"])
        self.assertTrue(meta["has_price"])
        self.assertEqual(meta["price_source"], "catalog")
        self.assertEqual(meta["unit_price_tl"], 331.12)

    @patch.object(DatabaseService, "_get_connection")
    def test_get_network_dc_access_unit_price_from_catalog(self, mock_conn):
        svc = DatabaseService()
        svc._webui = MagicMock(is_available=False)

        cursor = MagicMock()
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor
        svc._run_row = MagicMock(return_value=(331.12, "Turkish Lira"))

        meta = svc.get_network_dc_access_unit_price_tl()
        self.assertTrue(meta["has_price"])
        self.assertEqual(meta["unit_price_tl"], 331.12)
        self.assertEqual(meta["price_source"], "catalog")

    def test_non_backbone_scope_has_no_billing_in_items_by_default(self):
        items, _ = DatabaseService._network_p95_rows_to_items(
            [("sw-01", "eth0", "", 1e9, 2e9, 3e9, 10e9)],
            include_total=False,
        )
        self.assertNotIn("estimated_cost_tl", items[0])
        self.assertNotIn("p95_billable_mbit", items[0])


if __name__ == "__main__":
    unittest.main()
