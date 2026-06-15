"""Regression: hyperconv mem peak must keep dc_code in signature (Nutanix fallback)."""
from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

from app.services.dc_service import DatabaseService


class TestHyperconvMemPeakSignature(unittest.TestCase):
    def test_get_hyperconv_mem_peak_raw_accepts_dc_code(self):
        sig = inspect.signature(DatabaseService.get_hyperconv_mem_peak_raw)
        params = list(sig.parameters)
        self.assertIn("dc_code", params)
        idx_dc_code = params.index("dc_code")
        idx_start = params.index("start_ts")
        self.assertLess(idx_dc_code, idx_start)

    def test_only_one_hyperconv_mem_peak_definition(self):
        count = sum(
            1
            for name, fn in inspect.getmembers(DatabaseService, predicate=inspect.isfunction)
            if name == "get_hyperconv_mem_peak_raw"
        )
        self.assertEqual(count, 1)

    def test_classic_metrics_filtered_full_cluster_delegates_to_dc_details(self):
        svc = DatabaseService.__new__(DatabaseService)
        full = {"classic": {"hosts": 3, "mem_util_pct": 55.0}}
        with patch.object(svc, "_is_full_cluster_selection", return_value=True):
            with patch.object(svc, "get_dc_details", return_value=full) as mock_details:
                out = svc.get_classic_metrics_filtered("UZ11", ["UZ11-KM-CLS-NVME"], {})
        self.assertEqual(out["hosts"], 3)
        mock_details.assert_called_once()


if __name__ == "__main__":
    unittest.main()
