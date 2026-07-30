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
    def test_avg_track_blocked_when_both_tracks_exceed_threshold(self):
        """Average used can never truly exceed peak used, so a fixture that
        blocks avg must block max too -- otherwise the clamp (correctly) lifts
        avg back to the max value and the test would assert a physical
        impossibility."""
        host = {**HOST,
                "cpu_used_ghz_avg": 95.0, "cpu_avg_util_pct": 95.0,
                "cpu_used_ghz_peak": 97.0, "cpu_peak_util_pct": 97.0}
        assert host_raw_headroom(host, resource="cpu", threshold_pct=80.0,
                                 cpu_track="max") == 0.0
        assert host_raw_headroom(host, resource="cpu", threshold_pct=80.0,
                                 cpu_track="avg") == 0.0

    def test_utilisation_argument_is_wired_to_the_matching_track(self):
        """The util argument must come from the same track as the used value.
        Without this, zeroing either branch's util leaves every other test green.
        Here the used value alone would not trip the gate -- only the
        utilisation percentage does."""
        host = {"cpu_cap_ghz": 100.0, "cpu_alloc_ghz": 10.0,
                "cpu_used_ghz": 10.0, "cpu_used_pct": 10.0,
                "cpu_used_ghz_peak": 10.0, "cpu_peak_util_pct": 95.0,
                "cpu_used_ghz_avg": 8.0, "cpu_avg_util_pct": 95.0}
        assert host_raw_headroom(host, resource="cpu", threshold_pct=80.0,
                                 cpu_track="max") == 0.0
        assert host_raw_headroom(host, resource="cpu", threshold_pct=80.0,
                                 cpu_track="avg") == 0.0


class TestInvariantUnderDataPathologies:
    """Three shapes that broke n_avg >= n_max before the clamp existed. Each was
    reproduced against the pre-clamp code; they are the regression net."""

    def test_ram_capacity_drift_does_not_invert_the_ordering(self):
        """Collector emitted memory_capacity_gb = 0 rows for part of the window.
        CLASSIC_HOST_AVG has no `cap > 0` filter while CLASSIC_HOST_MEM_PEAK
        does, so average capacity lands below peak capacity and shrinks avg
        headroom multiplicatively. Pre-clamp: max 109.600 vs avg 76.720."""
        host = {"mem_cap_gb_at_peak": 512.0, "mem_used_gb_peak": 300.0,
                "mem_peak_util_pct": 58.6,
                "mem_cap_gb_avg": 358.4, "mem_used_gb_avg": 210.0,
                "mem_avg_util_pct": 58.6,
                "mem_cap_gb": 512.0, "mem_alloc_gb": 300.0, "mem_used_pct": 58.6}
        mx = host_raw_headroom(host, resource="ram", threshold_pct=80.0,
                               ram_track="max")
        avg = host_raw_headroom(host, resource="ram", threshold_pct=80.0,
                                ram_track="avg")
        assert avg >= mx

    def test_genuine_zero_average_used_is_honoured_not_skipped(self):
        """COALESCE(AVG(memory_used_gb), 0) yields a real 0.0 when every usage
        sample is NULL while capacity still averages fine. An `or` chain
        discarded that zero and paired average capacity with peak used.
        Pre-clamp: max 109.600 vs avg 20.000."""
        host = {"mem_cap_gb_at_peak": 512.0, "mem_used_gb_peak": 300.0,
                "mem_peak_util_pct": 58.6,
                "mem_cap_gb_avg": 400.0, "mem_used_gb_avg": 0.0,
                "mem_avg_util_pct": 0.0,
                "mem_cap_gb": 512.0, "mem_alloc_gb": 300.0, "mem_used_pct": 58.6}
        mx = host_raw_headroom(host, resource="ram", threshold_pct=80.0,
                               ram_track="max")
        avg = host_raw_headroom(host, resource="ram", threshold_pct=80.0,
                                ram_track="avg")
        assert avg >= mx
        # The zero is honoured: headroom reflects 0 used against avg capacity,
        # i.e. at least the full thresholded average capacity.
        assert avg >= 400.0 * 0.8 - 1e-9

    def test_ratio_selected_cpu_peak_does_not_invert_the_ordering(self):
        """*_CPU_PEAK picks the highest-utilisation row, not the highest-usage
        row, so with varying capacity the average used can exceed the peak used
        against a shared denominator. Pre-clamp: max 152.000 vs avg 106.000."""
        host = {"cpu_cap_ghz": 200.0, "cpu_used_ghz_peak": 8.0,
                "cpu_peak_util_pct": 80.0,
                "cpu_used_ghz_avg": 54.0, "cpu_avg_util_pct": 51.4,
                "cpu_alloc_ghz": 100.0, "cpu_used_ghz": 8.0, "cpu_used_pct": 80.0}
        mx = host_raw_headroom(host, resource="cpu", threshold_pct=80.0,
                               cpu_track="max")
        avg = host_raw_headroom(host, resource="cpu", threshold_pct=80.0,
                                cpu_track="avg")
        assert avg >= mx

    def test_idle_host_with_zero_cpu_average_gets_full_credit(self):
        """A genuinely idle host must be credited for its idleness, not have its
        real 0.0 average discarded in favour of its peak."""
        host = {"cpu_cap_ghz": 100.0, "cpu_alloc_ghz": 10.0,
                "cpu_used_ghz": 10.0, "cpu_used_pct": 10.0,
                "cpu_used_ghz_peak": 40.0, "cpu_peak_util_pct": 40.0,
                "cpu_used_ghz_avg": 0.0, "cpu_avg_util_pct": 0.0}
        assert host_raw_headroom(host, resource="cpu", threshold_pct=80.0,
                                 cpu_track="avg") == 80.0
