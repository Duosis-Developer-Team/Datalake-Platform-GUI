"""Tests for VMware-primary / Nutanix-fallback CPU/RAM merge queries and aggregation."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.db.queries import virt_compute as vcq
from app.services.dc_service import DatabaseService


class TestVirtComputeSqlShape(unittest.TestCase):
    def test_classic_merge_has_vmware_priority_case(self):
        sql = vcq.CLASSIC_CPU_MEM_MERGED
        self.assertIn("cpu_ghz_capacity", sql)
        self.assertIn("nutanix_cluster_metrics", sql)
        self.assertIn("cluster ILIKE '%%KM%%'", sql)
        self.assertIn("cluster_name ILIKE '%%KM%%'", sql)
        self.assertIn("UNION", sql)
        self.assertIn("memory_capacity_gb, 0) > 0", sql)

    def test_hyperconv_merge_excludes_km_on_vmware(self):
        sql = vcq.HYPERCONV_CPU_MEM_MERGED
        self.assertIn("cluster NOT ILIKE '%%KM%%'", sql)
        self.assertIn("nutanix_cluster_metrics", sql)

    def test_filtered_classic_includes_cluster_array(self):
        sql = vcq.CLASSIC_CPU_MEM_MERGED_FILTERED
        self.assertIn("unnest(%s::text[])", sql)
        self.assertIn("cluster = ANY(%s::text[])", sql)

    def test_batch_merge_uses_dc_code_grouping(self):
        sql = vcq.BATCH_HYPERCONV_CPU_MEM_MERGED
        self.assertIn("GROUP BY m.dc_code", sql)
        self.assertIn("unnest(%s::text[]", sql)

    def test_avg30_merged_uses_used_over_capacity(self):
        sql = vcq.CLASSIC_AVG30_MERGED
        self.assertIn("cpu_used_ghz / cpu_cap_ghz", sql)
        self.assertIn("mem_used_gb / mem_cap_gb", sql)


class TestAggregateDcMergedHyperconv(unittest.TestCase):
    def _agg(self, **overrides):
        base = dict(
            dc_code="TEST",
            nutanix_host_count=0,
            nutanix_vms=0,
            nutanix_mem=(0, 0),
            nutanix_storage=(0, 0),
            nutanix_cpu=(0, 0),
            vmware_counts=(0, 0, 0),
            vmware_mem=(0, 0),
            vmware_storage=(0, 0),
            vmware_cpu=(0, 0),
            power_hosts=0,
            power_vios=0,
            power_lpar_count=0,
            power_mem=(0, 0, 0),
            power_cpu=(0, 0, 0, 0),
            ibm_w=0,
            vcenter_w=0,
            classic_row=(0,) * 8,
            classic_avg30=None,
            hyperconv_row=(0,) * 8,
            hyperconv_avg30=None,
        )
        base.update(overrides)
        return DatabaseService._aggregate_dc(**base)

    def test_hyperconv_cpu_cap_from_merged_row_not_dc_wide_nutanix(self):
        # Merged row already carries Nutanix fallback (200 GHz cap, 50 used).
        result = self._agg(
            nutanix_host_count=9,
            nutanix_cpu=(999.0, 999.0),
            nutanix_mem=(99.0, 99.0),
            hyperconv_row=(0, 0, 200.0, 50.0, 10240.0, 5120.0, 0.0, 0.0),
        )
        hyperconv = result["hyperconv"]
        assert hyperconv["cpu_cap"] == 200.0
        assert hyperconv["cpu_used"] == 50.0
        assert hyperconv["mem_cap"] == 10240.0
        assert hyperconv["cpu_pct_live"] == 25.0
        assert hyperconv["ram_pct_live"] == 50.0

    def test_hyperconv_live_pct_no_double_count_with_nutanix_intel(self):
        result = self._agg(
            hyperconv_row=(3, 50, 100.0, 20.0, 400.0, 100.0, 0.0, 0.0),
            nutanix_cpu=(100.0, 80.0),
            nutanix_mem=(10.0, 5.0),
        )
        hyperconv = result["hyperconv"]
        # Live pct from merged hyperconv_row only (20/100), not (20+80)/(100+100).
        assert hyperconv["cpu_pct_live"] == 20.0
        assert hyperconv["ram_pct_live"] == 25.0

    def test_classic_merge_row_populates_cpu_mem(self):
        result = self._agg(
            classic_row=(4, 20, 80.0, 24.0, 1600.0, 640.0, 0.0, 0.0),
            classic_avg30=(30.0, 40.0, 35.0, 45.0, 25.0, 35.0),
        )
        classic = result["classic"]
        assert classic["cpu_cap"] == 80.0
        assert classic["mem_cap"] == 1600.0
        assert classic["cpu_pct_live"] == 30.0


class TestDcServiceWiring(unittest.TestCase):
    def test_get_classic_metrics_uses_merge_query(self):
        svc = DatabaseService()
        cursor = MagicMock()
        with patch.object(svc, "_run_row", return_value=(1, 2, 3.0, 1.0, 4.0, 2.0, 0.0, 0.0)) as run:
            row = svc.get_classic_metrics(cursor, "%DC11%", "s", "e", dc_code="DC11")
        assert row[2] == 3.0
        assert run.call_args[0][1] is vcq.CLASSIC_CPU_MEM_MERGED
        assert run.call_args[0][2] == ("%DC11%", "s", "e", "DC11", "s", "e")

    def test_get_hyperconv_metrics_filtered_uses_merge_avg30(self):
        svc = DatabaseService()
        fake_row = (0, 10, 200.0, 50.0, 1024.0, 512.0, 0.0, 0.0)
        fake_avg = (25.0, 50.0, 30.0, 55.0, 20.0, 45.0)
        with patch.object(svc, "_get_connection") as conn_ctx, \
             patch.object(svc, "get_hyperconv_storage_vm", return_value={}), \
             patch.object(svc, "get_hyperconv_mem_peak_raw", return_value=(0.0, 0.0, 0.0)), \
             patch.object(svc, "get_unit_prices_tl", return_value={}):
            cur = MagicMock()
            conn_ctx.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = cur
            with patch.object(svc, "_run_row", side_effect=[fake_row, fake_avg, (0, 0), (50.0,)]) as run_row, \
                 patch.object(svc, "_run_value", return_value=3):
                section = svc.get_hyperconv_metrics_filtered(
                    "AZ11", ["AZ11-HCI"], {"start": "2026-01-01", "end": "2026-01-31"}
                )
        assert section["cpu_cap"] == 200.0
        assert section["cpu_pct"] == 25.0
        sql_calls = [c[0][1] for c in run_row.call_args_list]
        assert vcq.HYPERCONV_CPU_MEM_MERGED_FILTERED in sql_calls
        assert vcq.HYPERCONV_AVG30_MERGED_FILTERED in sql_calls


if __name__ == "__main__":
    unittest.main()
