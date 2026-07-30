"""The avg utilization track, and the corrected CPU max track.

Ordering invariant under test: allocated >= peak used >= avg used, therefore
sellable(alloc) <= sellable(max) <= sellable(avg).
"""
from shared.sellable.host_sellable import host_raw_headroom

# 100 GHz / 512 GB host at an 80% threshold.
# VMs are ALLOCATED 70 GHz, PEAK at 40 GHz, AVERAGE 25 GHz.
HOST = {
    "cpu_cap_ghz": 100.0,
    "cpu_alloc_ghz": 70.0,
    "cpu_used_ghz": 30.0,          # latest sample -- what "max" wrongly used
    "cpu_used_ghz_peak": 40.0,     # real window peak
    "cpu_cap_ghz_at_peak": 100.0,
    "cpu_peak_util_pct": 40.0,
    "cpu_used_ghz_avg": 25.0,
    "cpu_cap_ghz_avg": 100.0,
    "cpu_avg_util_pct": 25.0,
    "cpu_used_pct": 30.0,
    "mem_cap_gb": 512.0,
    "mem_alloc_gb": 400.0,
    "mem_used_pct": 50.0,
    "mem_cap_gb_at_peak": 512.0,
    "mem_used_gb_peak": 300.0,
    "mem_peak_util_pct": 58.6,
    "mem_cap_gb_avg": 512.0,
    "mem_used_gb_avg": 180.0,
    "mem_avg_util_pct": 35.2,
}


class TestCpuTracks:
    def test_alloc_track_uses_allocated_ghz(self):
        # 100 * 0.8 - 70 = 10
        assert host_raw_headroom(HOST, resource="cpu", threshold_pct=80.0,
                                 cpu_track="effective") == 10.0

    def test_max_track_uses_window_peak_not_latest_sample(self):
        # 100 * 0.8 - 40 (peak) = 40, NOT 80 - 30 (latest) = 50
        assert host_raw_headroom(HOST, resource="cpu", threshold_pct=80.0,
                                 cpu_track="max") == 40.0

    def test_max_track_falls_back_to_latest_when_no_peak(self):
        host = {k: v for k, v in HOST.items() if k != "cpu_used_ghz_peak"}
        assert host_raw_headroom(host, resource="cpu", threshold_pct=80.0,
                                 cpu_track="max") == 50.0

    def test_avg_track_uses_window_average(self):
        # 100 * 0.8 - 25 = 55
        assert host_raw_headroom(HOST, resource="cpu", threshold_pct=80.0,
                                 cpu_track="avg") == 55.0

    def test_avg_exceeds_max_exceeds_alloc(self):
        kw = dict(resource="cpu", threshold_pct=80.0)
        alloc = host_raw_headroom(HOST, cpu_track="effective", **kw)
        mx = host_raw_headroom(HOST, cpu_track="max", **kw)
        avg = host_raw_headroom(HOST, cpu_track="avg", **kw)
        assert alloc < mx < avg

    def test_avg_track_falls_back_to_peak_when_no_average(self):
        """No CPU average -> use the peak. Never more headroom than the max
        track would give, and the host still contributes so n_avg >= n_max."""
        host = {k: v for k, v in HOST.items() if k != "cpu_used_ghz_avg"}
        avg = host_raw_headroom(host, resource="cpu", threshold_pct=80.0,
                                cpu_track="avg")
        mx = host_raw_headroom(host, resource="cpu", threshold_pct=80.0,
                               cpu_track="max")
        assert avg == mx == 40.0

    def test_avg_track_falls_back_to_latest_when_no_average_and_no_peak(self):
        host = {"cpu_cap_ghz": 100.0, "cpu_alloc_ghz": 70.0,
                "cpu_used_ghz": 30.0, "cpu_used_pct": 30.0}
        assert host_raw_headroom(host, resource="cpu", threshold_pct=80.0,
                                 cpu_track="avg") == 50.0

    def test_avg_never_claims_more_than_max_on_any_data_shape(self):
        """The load-bearing invariant, checked across completeness scenarios."""
        shapes = [
            HOST,
            {k: v for k, v in HOST.items() if k != "cpu_used_ghz_avg"},
            {k: v for k, v in HOST.items()
             if k not in ("cpu_used_ghz_avg", "cpu_used_ghz_peak")},
        ]
        for h in shapes:
            avg = host_raw_headroom(h, resource="cpu", threshold_pct=80.0,
                                    cpu_track="avg")
            mx = host_raw_headroom(h, resource="cpu", threshold_pct=80.0,
                                   cpu_track="max")
            assert avg >= mx, h.get("cpu_used_ghz_avg")


class TestRamTracks:
    def test_alloc_track_uses_allocated_gb(self):
        # 512 * 0.8 - 400 = 9.6
        assert host_raw_headroom(HOST, resource="ram", threshold_pct=80.0,
                                 ram_track="physical") == 512.0 * 0.8 - 400.0

    def test_max_track_uses_peak(self):
        assert host_raw_headroom(HOST, resource="ram", threshold_pct=80.0,
                                 ram_track="max") == 512.0 * 0.8 - 300.0

    def test_avg_track_uses_average_used_and_average_cap(self):
        assert host_raw_headroom(HOST, resource="ram", threshold_pct=80.0,
                                 ram_track="avg") == 512.0 * 0.8 - 180.0

    def test_avg_exceeds_max_exceeds_alloc(self):
        kw = dict(resource="ram", threshold_pct=80.0)
        alloc = host_raw_headroom(HOST, ram_track="physical", **kw)
        mx = host_raw_headroom(HOST, ram_track="max", **kw)
        avg = host_raw_headroom(HOST, ram_track="avg", **kw)
        assert alloc < mx < avg


class TestStorageUnaffected:
    def test_storage_ignores_track_arguments(self):
        """Storage has no time dimension: identical across all tracks."""
        host = {**HOST, "stor_cap_gb": 1000.0, "stor_provisioned_gb": 500.0,
                "stor_used_pct": 50.0}
        vals = {
            host_raw_headroom(host, resource="storage", threshold_pct=85.0,
                              cpu_track=t, ram_track=t)
            for t in ("effective", "max", "avg")
        }
        assert len(vals) == 1


class TestGateStillApplies:
    def test_avg_track_blocked_when_average_exceeds_threshold(self):
        host = {**HOST, "cpu_used_ghz_avg": 95.0, "cpu_avg_util_pct": 95.0}
        assert host_raw_headroom(host, resource="cpu", threshold_pct=80.0,
                                 cpu_track="avg") == 0.0
