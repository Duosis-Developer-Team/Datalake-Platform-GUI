"""
Unit tests for cluster filter feature: cluster list and filtered metrics.
DB calls are mocked; no live database required.
"""

import unittest
from unittest.mock import MagicMock, patch

import psycopg2

with patch("psycopg2.pool.ThreadedConnectionPool"):
    from src.services.db_service import DatabaseService

from src.services import cache_service as cache
from src.utils.time_range import default_time_range


def _make_service():
    with patch("psycopg2.pool.ThreadedConnectionPool"):
        svc = DatabaseService()
    svc._pool = MagicMock()
    return svc


class TestClassicClusterList(unittest.TestCase):

    def setUp(self):
        cache.clear()

    def test_returns_list_of_cluster_names(self):
        svc = _make_service()
        tr = default_time_range()
        mock_rows = [("DC11-KM-01",), ("DC11-KM-02",)]
        svc._run_rows = MagicMock(return_value=mock_rows)
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        svc._get_connection = MagicMock()
        svc._get_connection.return_value.__enter__ = MagicMock(return_value=conn)
        svc._get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = svc.get_classic_cluster_list("DC11", tr)
        self.assertEqual(result, ["DC11-KM-01", "DC11-KM-02"])

    def test_returns_empty_list_on_operational_error(self):
        svc = _make_service()
        tr = default_time_range()
        svc._get_connection = MagicMock(side_effect=psycopg2.OperationalError("DB error"))
        result = svc.get_classic_cluster_list("DC11", tr)
        self.assertEqual(result, [])


class TestHyperconvClusterList(unittest.TestCase):

    def setUp(self):
        cache.clear()

    def test_returns_list_of_nutanix_cluster_names(self):
        svc = _make_service()
        tr = default_time_range()
        mock_rows = [("AZ11-Nutanix-1",), ("AZ11-Nutanix-2",)]
        svc._run_rows = MagicMock(return_value=mock_rows)
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        svc._get_connection = MagicMock()
        svc._get_connection.return_value.__enter__ = MagicMock(return_value=conn)
        svc._get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = svc.get_hyperconv_cluster_list("AZ11", tr)
        self.assertEqual(result, ["AZ11-Nutanix-1", "AZ11-Nutanix-2"])


class TestClassicMetricsFiltered(unittest.TestCase):

    def setUp(self):
        cache.clear()

    def test_empty_selection_returns_full_classic_from_dc_details(self):
        svc = _make_service()
        tr = default_time_range()
        fake_classic = {"hosts": 5, "vms": 10, "cpu_cap": 100.0, "cpu_used": 50.0}
        svc.get_dc_details = MagicMock(return_value={"classic": fake_classic})

        result = svc.get_classic_metrics_filtered("DC11", None, tr)
        self.assertEqual(result["hosts"], 5)
        self.assertEqual(result["cpu_cap"], 100.0)

    def test_empty_list_selection_returns_full_classic(self):
        svc = _make_service()
        tr = default_time_range()
        fake_classic = {"hosts": 3, "vms": 8}
        svc.get_dc_details = MagicMock(return_value={"classic": fake_classic})

        result = svc.get_classic_metrics_filtered("DC11", [], tr)
        self.assertEqual(result["hosts"], 3)

    def test_filtered_returns_aggregate_from_db(self):
        svc = _make_service()
        tr = default_time_range()
        svc._run_row = MagicMock(
            side_effect=[
                (2, 4, 50.0, 25.0, 256.0, 128.0, 1024.0, 512.0),
                (30.0, 45.0),
            ]
        )
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        svc._get_connection = MagicMock()
        svc._get_connection.return_value.__enter__ = MagicMock(return_value=conn)
        svc._get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = svc.get_classic_metrics_filtered("DC11", ["DC11-KM-01"], tr)
        self.assertEqual(result["hosts"], 2)
        self.assertEqual(result["vms"], 4)
        self.assertEqual(result["cpu_cap"], 50.0)
        self.assertEqual(result["cpu_pct"], 30.0)
        self.assertEqual(result["mem_pct"], 45.0)


class TestHyperconvMetricsFiltered(unittest.TestCase):

    def setUp(self):
        cache.clear()

    def test_empty_selection_returns_full_hyperconv_from_dc_details(self):
        svc = _make_service()
        tr = default_time_range()
        fake_hyperconv = {"hosts": 4, "vms": 12, "stor_cap": 20.0}
        svc.get_dc_details = MagicMock(return_value={"hyperconv": fake_hyperconv})

        result = svc.get_hyperconv_metrics_filtered("AZ11", None, tr)
        self.assertEqual(result["hosts"], 4)
        self.assertEqual(result["stor_cap"], 20.0)

    def test_filtered_returns_dict_with_expected_keys(self):
        svc = _make_service()
        tr = default_time_range()
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        svc._get_connection = MagicMock(return_value=conn)
        svc._run_value = MagicMock(side_effect=[3, 6])
        # Memory: nutanix_cluster_metrics returns bytes; 256 GB and 128 GB in bytes
        bytes_256_gb = 256 * (1024**3)
        bytes_128_gb = 128 * (1024**3)
        # CPU: nutanix_cluster_metrics returns Hz; 200 GHz and 80 GHz in Hz
        cpu_cap_hz = 200.0 * 1_000_000_000
        cpu_used_hz = 80.0 * 1_000_000_000
        # Storage: nutanix_cluster_metrics returns bytes; 5 TB and 2 TB in bytes
        bytes_5_tb = 5.0 * (1024**4)
        bytes_2_tb = 2.0 * (1024**4)
        svc._run_row = MagicMock(
            side_effect=[
                (float(bytes_256_gb), float(bytes_128_gb)),
                (cpu_cap_hz, cpu_used_hz),
                (bytes_5_tb, bytes_2_tb),
                # HYPERCONV_AVG30_FILTERED — zeros => fallback to capacity-based pct
                (0, 0, 0, 0),
            ]
        )

        result = svc.get_hyperconv_metrics_filtered("AZ11", ["AZ11-Nutanix-1"], tr)
        self.assertEqual(result["hosts"], 3)
        self.assertEqual(result["vms"], 6)
        self.assertIn("cpu_cap", result)
        self.assertIn("mem_cap", result)
        self.assertIn("stor_cap", result)
        self.assertIn("cpu_pct", result)
        self.assertIn("mem_pct", result)
        self.assertIn("cpu_pct_max", result)
        self.assertIn("mem_pct_max", result)
        # Memory converted from bytes to GB (no * 1024 inflation)
        self.assertAlmostEqual(result["mem_cap"], 256.0, places=1)
        self.assertAlmostEqual(result["mem_used"], 128.0, places=1)
        # CPU converted from Hz to GHz (Nutanix schema)
        self.assertAlmostEqual(result["cpu_cap"], 200.0, places=1)
        self.assertAlmostEqual(result["cpu_used"], 80.0, places=1)
        # Storage converted from bytes to TB (Nutanix schema)
        self.assertAlmostEqual(result["stor_cap"], 5.0, places=2)
        self.assertAlmostEqual(result["stor_used"], 2.0, places=2)


if __name__ == "__main__":
    unittest.main()
