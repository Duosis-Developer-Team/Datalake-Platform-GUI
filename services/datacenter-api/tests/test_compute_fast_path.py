"""Tests for compute metrics fast path and cache helpers."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.services.dc_service import DatabaseService


class TestComputeFastPath(unittest.TestCase):
    def test_is_full_cluster_selection_true_when_sets_match(self):
        svc = DatabaseService.__new__(DatabaseService)
        with patch.object(svc, "get_classic_cluster_list", return_value=["A", "B"]):
            self.assertTrue(svc._is_full_cluster_selection("DC13", ["A", "B"], "classic", {}))

    def test_is_full_cluster_selection_false_for_partial(self):
        svc = DatabaseService.__new__(DatabaseService)
        with patch.object(svc, "get_classic_cluster_list", return_value=["A", "B"]):
            self.assertFalse(svc._is_full_cluster_selection("DC13", ["A"], "classic", {}))

    def test_apply_mem_avg_ts_overwrites_mem_util_pct(self):
        out = DatabaseService._apply_mem_avg_ts({"mem_util_pct": 50.0, "mem_pct": 50.0}, 72.5)
        self.assertEqual(out["mem_util_pct"], 72.5)
        self.assertEqual(out["mem_pct"], 72.5)

    def test_apply_mem_peak_raw_sets_max_util_fields(self):
        out = DatabaseService._apply_mem_peak_raw(
            {"mem_util_pct_max": 50.0, "mem_pct_max": 50.0},
            (800.0, 1000.0, 80.0),
        )
        self.assertEqual(out["mem_util_pct_max"], 80.0)
        self.assertEqual(out["mem_used_gb_peak"], 800.0)

    def test_mem_peak_pct_should_exceed_or_match_avg_invariant(self):
        """Peak util% (max ratio) must be >= time-series average util%."""
        ts_points = [
            (1000.0, 2000.0),  # 50% — highest used_gb but not highest util
            (700.0, 1000.0),   # 70% — peak util
            (650.0, 1000.0),   # 65%
        ]
        avg_pct = sum(100.0 * u / c for u, c in ts_points) / len(ts_points)
        peak_pct = max(100.0 * u / c for u, c in ts_points)
        self.assertGreaterEqual(peak_pct, avg_pct)
        self.assertAlmostEqual(peak_pct, 70.0)
        self.assertAlmostEqual(avg_pct, 61.666, places=2)

    def test_get_classic_metrics_filtered_uses_unfiltered_when_all_selected(self):
        svc = DatabaseService.__new__(DatabaseService)
        full = {"classic": {"hosts": 9, "mem_util_pct": 61.0}}
        with patch.object(svc, "_is_full_cluster_selection", return_value=True):
            with patch.object(svc, "get_dc_details", return_value=full) as mock_details:
                out = svc.get_classic_metrics_filtered("DC13", ["KM-1", "KM-2"], {})
        self.assertEqual(out["hosts"], 9)
        mock_details.assert_called_once()

    def test_get_backup_netbackup_compute_maps_pool_bytes(self):
        svc = DatabaseService.__new__(DatabaseService)
        usable = 2 * (1024 ** 4)  # 2 TB
        used = 512 * (1024 ** 3)  # 512 GB
        pools = {
            "pools": ["Pool-A"],
            "rows": [
                {"usablesizebytes": usable, "usedcapacitybytes": used},
            ],
        }
        with patch.object(svc, "get_dc_netbackup_pools", return_value=pools):
            out = svc.get_backup_netbackup_compute("DC13", {})
        self.assertEqual(out["stor_cap"], 2.0)
        self.assertEqual(out["stor_provisioned_gb"], 512.0)
        self.assertAlmostEqual(out["stor_pct"], 25.0)
        self.assertEqual(out["pools"], ["Pool-A"])

    def test_get_backup_netbackup_compute_empty_pools(self):
        svc = DatabaseService.__new__(DatabaseService)
        with patch.object(svc, "get_dc_netbackup_pools", return_value={"pools": [], "rows": []}):
            out = svc.get_backup_netbackup_compute("DC13", {})
        self.assertEqual(out["stor_cap"], 0.0)
        self.assertEqual(out["stor_provisioned_gb"], 0.0)
        self.assertEqual(out["stor_pct"], 0.0)

    def test_get_backup_replication_compute_reuses_classic_metrics(self):
        svc = DatabaseService.__new__(DatabaseService)
        classic = {
            "cpu_cap": 100.0,
            "cpu_alloc_ghz_sales": 60.0,
            "mem_cap": 512.0,
            "mem_alloc_gb_vm": 256.0,
            "stor_cap": 20.0,
            "stor_provisioned_gb": 10240.0,
            "stor_pct": 50.0,
        }
        with patch.object(svc, "get_classic_metrics_filtered", return_value=classic) as get_classic:
            out = svc.get_backup_replication_compute("DC13", ["KM-1"], {"preset": "7d"})

        self.assertEqual(out["cpu_cap"], 100.0)
        self.assertEqual(out["mem_cap"], 512.0)
        self.assertEqual(out["stor_cap"], 0.0)
        self.assertEqual(out["stor_provisioned_gb"], 0.0)
        self.assertEqual(out["stor_pct"], 0.0)
        self.assertTrue(any("CPU/RAM only" in n for n in out.get("notes") or []))
        get_classic.assert_called_once_with("DC13", ["KM-1"], {"preset": "7d"})

    def test_get_veeam_replication_datastore_compute_sums_bytes(self):
        svc = DatabaseService.__new__(DatabaseService)
        _tb = 1024 ** 4
        rows = [
            ("moid-1", "DC13-veeam-repo1", "DC13-KM", 2 * _tb, 0.5 * _tb, 1.5 * _tb),
            ("moid-2", "other-veeam-ds", "DC13-KM", 1 * _tb, 0.2 * _tb, 0.8 * _tb),
        ]

        class _Cur:
            pass

        class _Conn:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def cursor(self):
                return _Ctx()

        class _Ctx:
            def __enter__(self):
                return _Cur()

            def __exit__(self, *a):
                return False

        with patch.object(svc, "_get_connection", return_value=_Conn()), \
             patch.object(svc, "_run_rows", return_value=rows):
            out = svc.get_veeam_replication_datastore_compute("DC13", {"preset": "7d"})

        self.assertAlmostEqual(out["stor_cap"], 3.0)
        self.assertEqual(out["datastore_count"], 2)
        self.assertEqual(out["source"], "vmware_datastore_veeam_eligible")

    def test_get_backup_nutanix_compute_reuses_hyperconv_metrics(self):
        svc = DatabaseService.__new__(DatabaseService)
        hyperconv = {
            "stor_cap": 42.0,
            "stor_provisioned_gb": 21504.0,
            "stor_pct": 50.0,
        }
        with patch.object(svc, "get_hyperconv_metrics_filtered", return_value=hyperconv) as get_hyperconv:
            out = svc.get_backup_nutanix_compute("DC13", ["NTNX-1"], {"preset": "7d"})

        self.assertIs(out, hyperconv)
        get_hyperconv.assert_called_once_with("DC13", ["NTNX-1"], {"preset": "7d"})


if __name__ == "__main__":
    unittest.main()
