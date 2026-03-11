"""
Unit tests for S3 (IBM iCOS) helpers.
All DB calls are mocked — tests only exercise helper logic and service wiring.
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

# Patch the pool init before importing the service so no real DB connection is attempted.
with patch("psycopg2.pool.ThreadedConnectionPool"):
    from src.services.db_service import DatabaseService, _s3_trend_interval_hours


class TestS3TrendInterval(unittest.TestCase):
    def test_interval_1_day(self):
        start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 1, 23, 59, tzinfo=timezone.utc)
        self.assertEqual(_s3_trend_interval_hours(start, end), 1)

    def test_interval_7_days(self):
        start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=6)
        self.assertEqual(_s3_trend_interval_hours(start, end), 6)

    def test_interval_30_days(self):
        start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=29)
        self.assertEqual(_s3_trend_interval_hours(start, end), 12)

    def test_interval_more_than_30_days(self):
        start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(days=40)
        self.assertEqual(_s3_trend_interval_hours(start, end), 24)

    def test_interval_handles_missing_dates(self):
        self.assertIsInstance(_s3_trend_interval_hours(None, None), int)


class TestS3ServiceHelpers(unittest.TestCase):
    def setUp(self):
        # Create a DatabaseService with a mocked pool and _get_connection.
        with patch("psycopg2.pool.ThreadedConnectionPool"):
            self.svc = DatabaseService()
        self.svc._pool = MagicMock()

    def test_get_dc_s3_pools_returns_empty_when_no_pools(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []  # POOL_LIST returns no rows

        conn = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        self.svc._get_connection = MagicMock()
        self.svc._get_connection.return_value.__enter__ = MagicMock(return_value=conn)
        self.svc._get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = self.svc.get_dc_s3_pools("DC99", {"start": "2025-01-01", "end": "2025-01-01"})
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("pools"), [])
        self.assertEqual(result.get("latest"), {})
        self.assertEqual(result.get("growth"), {})
        self.assertEqual(result.get("trend"), [])

    def test_get_customer_s3_vaults_returns_empty_when_no_vaults(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []  # VAULT_LIST returns no rows

        conn = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        self.svc._get_connection = MagicMock()
        self.svc._get_connection.return_value.__enter__ = MagicMock(return_value=conn)
        self.svc._get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = self.svc.get_customer_s3_vaults("SomeCustomer", {"start": "2025-01-01", "end": "2025-01-01"})
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("vaults"), [])
        self.assertEqual(result.get("latest"), {})
        self.assertEqual(result.get("growth"), {})
        self.assertEqual(result.get("trend"), [])


if __name__ == "__main__":
    unittest.main()

