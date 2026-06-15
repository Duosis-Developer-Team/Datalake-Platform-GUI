"""SQL shape tests for time-series memory avg/peak queries."""
from __future__ import annotations

import unittest

from app.db.queries import vmware as vq


class TestMemTsSql(unittest.TestCase):
    def test_classic_mem_peak_uses_timestamp_agg(self):
        self.assertIn("GROUP BY timestamp", vq.CLASSIC_MEM_PEAK_RAW)
        self.assertIn("SUM(memory_used_gb)", vq.CLASSIC_MEM_PEAK_RAW)
        self.assertIn("ORDER BY used_gb DESC", vq.CLASSIC_MEM_PEAK_RAW)

    def test_classic_mem_avg_ts_uses_same_cte_pattern(self):
        self.assertIn("GROUP BY timestamp", vq.CLASSIC_MEM_AVG_TS_RAW)
        self.assertIn("AVG(100.0 * used_gb", vq.CLASSIC_MEM_AVG_TS_RAW)

    def test_filtered_variants_use_cluster_array(self):
        self.assertIn("= ANY(%s::text[])", vq.CLASSIC_MEM_PEAK_RAW_FILTERED)
        self.assertIn("= ANY(%s::text[])", vq.CLASSIC_MEM_AVG_TS_RAW_FILTERED)

    def test_hyperconv_mem_avg_ts_present(self):
        self.assertIn("cluster NOT ILIKE", vq.HYPERCONV_MEM_AVG_TS_RAW)


if __name__ == "__main__":
    unittest.main()
