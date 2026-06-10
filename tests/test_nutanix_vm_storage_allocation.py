"""Tests for Nutanix VM storage allocation query selection (AZ11 cluster_name fix)."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import psycopg2

with patch("psycopg2.pool.ThreadedConnectionPool"):
    from src.services.db_service import DatabaseService

from src.queries import nutanix as nq
from src.services import cache_service as cache
from src.utils.time_range import default_time_range


def _make_service():
    with patch("psycopg2.pool.ThreadedConnectionPool"):
        svc = DatabaseService()
    svc._pool = MagicMock()
    return svc


class TestRunNutanixVmStorage(unittest.TestCase):
    def setUp(self):
        cache.clear()

    def test_unfiltered_uses_cluster_name_query(self):
        svc = _make_service()
        cursor = MagicMock()
        svc._run_row = MagicMock(return_value=(100.0, 50.0, 793, 1864.0))

        row = svc._run_nutanix_vm_storage(cursor, "AZ11")

        svc._run_row.assert_called_once_with(cursor, nq.NUTANIX_VM_STORAGE, ("AZ11",))
        self.assertEqual(row[2], 793)

    def test_filtered_uses_cluster_filter_query(self):
        svc = _make_service()
        cursor = MagicMock()
        svc._run_row = MagicMock(return_value=(80.0, 40.0, 600, 1500.0))
        clusters = ["PRISM-AZ11-SSD"]

        row = svc._run_nutanix_vm_storage(cursor, "AZ11", clusters)

        svc._run_row.assert_called_once_with(
            cursor, nq.NUTANIX_VM_STORAGE_FILTERED, ("AZ11", clusters)
        )
        self.assertEqual(row[0], 80.0)

    def test_get_hyperconv_storage_vm_passes_dc_code_and_clusters(self):
        svc = _make_service()
        cursor = MagicMock()
        svc._compute_vmware_vm_allocation = MagicMock(
            return_value={
                "stor_provisioned_gb": 0.0,
                "stor_actual_used_gb": 0.0,
                "cpu_alloc_ghz_vm": 0.0,
                "cpu_alloc_ghz_sales": 0.0,
                "mem_alloc_gb_vm": 0.0,
                "cpu_alloc_hosts_resolved": 0,
                "cpu_alloc_hosts_fallback_default": 0,
            }
        )
        svc._run_nutanix_vm_storage = MagicMock(return_value=(91946.0, 18000.0, 793, 1864.0))

        result = svc.get_hyperconv_storage_vm(cursor, "AZ11", ["PRISM-AZ11-SSD"])

        svc._run_nutanix_vm_storage.assert_called_once_with(
            cursor, "AZ11", ["PRISM-AZ11-SSD"]
        )
        self.assertEqual(result["cpu_alloc_ghz_vm"], 793.0)
        self.assertEqual(result["mem_alloc_gb_vm"], 1864.0)
        self.assertEqual(result["stor_provisioned_gb"], 91946.0)


class TestHyperconvMetricsFilteredStorageVm(unittest.TestCase):
    def setUp(self):
        cache.clear()

    def test_filtered_path_requests_storage_with_clusters(self):
        svc = _make_service()
        tr = default_time_range()
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        svc._get_connection = MagicMock()
        svc._get_connection.return_value.__enter__ = MagicMock(return_value=conn)
        svc._get_connection.return_value.__exit__ = MagicMock(return_value=False)
        svc._run_value = MagicMock(side_effect=[5, 120])
        bytes_256_gb = 256 * (1024**3)
        bytes_128_gb = 128 * (1024**3)
        cpu_cap_hz = 728.0 * 1_000_000_000
        cpu_used_hz = 78.62 * 1_000_000_000
        bytes_165_tb = 165.97 * (1024**4)
        bytes_19_tb = 18.986 * (1024**4)
        svc._run_row = MagicMock(
            side_effect=[
                (float(bytes_256_gb), float(bytes_128_gb)),
                (cpu_cap_hz, cpu_used_hz),
                (bytes_165_tb, bytes_19_tb),
                (10.8, 24.3, 10.8, 24.3, 0, 0),
            ]
        )
        svc.get_hyperconv_storage_vm = MagicMock(
            return_value={
                "stor_provisioned_gb": 91946.0,
                "stor_actual_used_gb": 18000.0,
                "cpu_alloc_ghz_vm": 793.0,
                "cpu_alloc_ghz_sales": 793.0,
                "mem_alloc_gb_vm": 1864.0,
                "cpu_alloc_hosts_resolved": 0,
                "cpu_alloc_hosts_fallback_default": 0,
            }
        )
        svc.get_unit_prices_tl = MagicMock(return_value={"cpu_vcpu": 0, "ram_gb": 0, "storage_gb": 0})

        svc.get_hyperconv_metrics_filtered("AZ11", ["PRISM-AZ11-SSD"], tr)

        svc.get_hyperconv_storage_vm.assert_called_once_with(
            cur, "AZ11", ["PRISM-AZ11-SSD"]
        )


if __name__ == "__main__":
    unittest.main()
