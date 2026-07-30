"""Host payload enrichment for the avg track and the corrected CPU peak."""
from app.services.dc_service import DatabaseService


class TestHostAvgMap:
    def test_indexes_by_short_hostname(self):
        rows = [("esx01.bulut.local", 12.0, 40.0, 30.0, 100.0, 512.0, 19.5)]
        out = DatabaseService._host_avg_map(rows)
        assert set(out) == {"esx01"}
        assert out["esx01"]["cpu_used_ghz_avg"] == 12.0
        assert out["esx01"]["cpu_cap_ghz_avg"] == 40.0
        assert out["esx01"]["cpu_avg_util_pct"] == 30.0
        assert out["esx01"]["mem_used_gb_avg"] == 100.0
        assert out["esx01"]["mem_cap_gb_avg"] == 512.0
        assert out["esx01"]["mem_avg_util_pct"] == 19.5

    def test_skips_rows_without_hostname(self):
        assert DatabaseService._host_avg_map([(None, 1, 2, 3, 4, 5, 6), ("", 1, 2, 3, 4, 5, 6)]) == {}

    def test_handles_none_metrics_as_zero(self):
        out = DatabaseService._host_avg_map([("h1", None, None, None, None, None, None)])
        assert out["h1"]["cpu_used_ghz_avg"] == 0.0


class TestApplyHostAvg:
    def test_attaches_all_six_fields(self):
        payload = {"host": "esx01", "cpu_cap_ghz": 40.0}
        out = DatabaseService._apply_host_avg(payload, {
            "cpu_used_ghz_avg": 12.0, "cpu_cap_ghz_avg": 40.0, "cpu_avg_util_pct": 30.0,
            "mem_used_gb_avg": 100.0, "mem_cap_gb_avg": 512.0, "mem_avg_util_pct": 19.5,
        })
        assert out["cpu_used_ghz_avg"] == 12.0
        assert out["mem_avg_util_pct"] == 19.5

    def test_noop_when_avg_missing(self):
        """Missing avg data must leave the payload alone, never write 0 --
        a zero would read as 'nothing used, sell everything'."""
        payload = {"host": "esx01", "cpu_cap_ghz": 40.0}
        assert DatabaseService._apply_host_avg(payload, None) == payload
        assert "cpu_used_ghz_avg" not in DatabaseService._apply_host_avg(payload, None)

    def test_noop_when_all_values_zero(self):
        payload = {"host": "esx01"}
        out = DatabaseService._apply_host_avg(payload, {
            "cpu_used_ghz_avg": 0.0, "cpu_cap_ghz_avg": 0.0, "cpu_avg_util_pct": 0.0,
            "mem_used_gb_avg": 0.0, "mem_cap_gb_avg": 0.0, "mem_avg_util_pct": 0.0,
        })
        assert "cpu_used_ghz_avg" not in out

    def test_does_not_mutate_input(self):
        payload = {"host": "esx01"}
        DatabaseService._apply_host_avg(payload, {
            "cpu_used_ghz_avg": 1.0, "cpu_cap_ghz_avg": 2.0, "cpu_avg_util_pct": 50.0,
            "mem_used_gb_avg": 3.0, "mem_cap_gb_avg": 4.0, "mem_avg_util_pct": 75.0,
        })
        assert payload == {"host": "esx01"}


class TestApplyHostCpuPeak:
    def test_attaches_peak_fields(self):
        out = DatabaseService._apply_host_cpu_peak({"host": "esx01"}, (26.0, 40.0, 65.0))
        assert out["cpu_used_ghz_peak"] == 26.0
        assert out["cpu_cap_ghz_at_peak"] == 40.0
        assert out["cpu_peak_util_pct"] == 65.0

    def test_noop_when_peak_missing_or_empty(self):
        payload = {"host": "esx01"}
        assert DatabaseService._apply_host_cpu_peak(payload, None) == payload
        assert DatabaseService._apply_host_cpu_peak(payload, (0.0, 0.0, 0.0)) == payload
