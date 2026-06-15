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

    def test_get_classic_metrics_filtered_uses_unfiltered_when_all_selected(self):
        svc = DatabaseService.__new__(DatabaseService)
        full = {"classic": {"hosts": 9, "mem_util_pct": 61.0}}
        with patch.object(svc, "_is_full_cluster_selection", return_value=True):
            with patch.object(svc, "get_dc_details", return_value=full) as mock_details:
                out = svc.get_classic_metrics_filtered("DC13", ["KM-1", "KM-2"], {})
        self.assertEqual(out["hosts"], 9)
        mock_details.assert_called_once()


if __name__ == "__main__":
    unittest.main()
