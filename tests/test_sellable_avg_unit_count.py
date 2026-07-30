"""n_avg: the third unit count, and the ratio coupling it must preserve."""
from shared.sellable.computation import (
    constrain_by_ratio_per_host_dual,
    constrain_by_ratio_per_host_triple_dual,
)
from shared.sellable.models import PanelResult, ResourceRatio


def _ratio() -> ResourceRatio:
    # 1 unit = 1 vCPU + 2 GB RAM + 100 GB storage (the Hyperconverged shape).
    return ResourceRatio(family="virt_classic", cpu_per_unit=1.0, ram_gb_per_unit=2.0,
                          storage_gb_per_unit=100.0)


def _panels() -> list[PanelResult]:
    def p(kind, unit):
        return PanelResult(panel_key=f"p_{kind}", label=kind, family="virt_classic",
                           resource_kind=kind, display_unit=unit, sellable_raw=1e9)
    return [p("cpu", "vCPU"), p("ram", "GB"), p("storage", "GB")]


def _host() -> dict:
    """allocated 70 GHz > peak 40 > avg 25; RAM allocated 400 > peak 300 > avg 180."""
    return {
        "host": "esx01", "cluster": "KM01",
        "cpu_cap_ghz": 100.0, "cpu_total": 100.0,
        "cpu_alloc_ghz": 70.0, "cpu_alloc": 70.0,
        "cpu_used_ghz": 30.0,
        "cpu_used_ghz_peak": 40.0, "cpu_cap_ghz_at_peak": 100.0, "cpu_peak_util_pct": 40.0,
        "cpu_used_ghz_avg": 25.0, "cpu_cap_ghz_avg": 100.0, "cpu_avg_util_pct": 25.0,
        "cpu_used_pct": 30.0,
        "mem_cap_gb": 512.0, "ram_total": 512.0,
        "mem_alloc_gb": 400.0, "ram_alloc": 400.0, "mem_used_pct": 50.0,
        "mem_cap_gb_at_peak": 512.0, "mem_used_gb_peak": 300.0, "mem_peak_util_pct": 58.6,
        "mem_cap_gb_avg": 512.0, "mem_used_gb_avg": 180.0, "mem_avg_util_pct": 35.2,
        "stor_cap_gb": 100000.0, "stor_provisioned_gb": 10000.0, "stor_used_pct": 10.0,
        "stor_exclusive_free_gb": 90000.0,
    }


def _by_kind(panels):
    return {p.resource_kind: p for p in panels}


class TestTripleDual:
    def test_all_three_tracks_populated(self):
        out = _by_kind(constrain_by_ratio_per_host_triple_dual(
            _panels(), _ratio(), [_host()],
            cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
        ))
        for kind in ("cpu", "ram", "storage"):
            assert out[kind].sellable_avg_util is not None, kind
            assert out[kind].sellable_max_util is not None, kind
            assert out[kind].sellable_allocation is not None, kind

    def test_avg_exceeds_max_exceeds_alloc_on_every_row(self):
        out = _by_kind(constrain_by_ratio_per_host_triple_dual(
            _panels(), _ratio(), [_host()],
            cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
        ))
        for kind in ("cpu", "ram", "storage"):
            p = out[kind]
            assert p.sellable_allocation < p.sellable_max_util < p.sellable_avg_util, kind

    def test_ratio_coupling_identical_across_resources(self):
        """The three rows are one unit count times the ratio, so avg/alloc must
        match across CPU, RAM and Storage. This is the invariant that proves the
        triple-min chain was not broken."""
        out = _by_kind(constrain_by_ratio_per_host_triple_dual(
            _panels(), _ratio(), [_host()],
            cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
        ))
        ratios = [
            out[k].sellable_avg_util / out[k].sellable_allocation
            for k in ("cpu", "ram", "storage")
        ]
        assert max(ratios) - min(ratios) < 1e-6, ratios

    def test_storage_avg_comes_from_unit_count_not_storage_average(self):
        """Storage has no average of its own: its avg cell is n_avg * ratio."""
        out = _by_kind(constrain_by_ratio_per_host_triple_dual(
            _panels(), _ratio(), [_host()],
            cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
        ))
        n_avg = out["cpu"].sellable_avg_util / 1.0        # cpu_per_unit
        assert abs(out["storage"].sellable_avg_util - n_avg * 100.0) < 1e-6


class TestEmptyHostsFallback:
    def test_avg_is_zero_not_none_when_no_hosts(self):
        """No hosts is 'nothing sellable', not 'unknown'."""
        out = _by_kind(constrain_by_ratio_per_host_triple_dual(
            _panels(), _ratio(), [],
            cpu_threshold_pct=80.0, ram_threshold_pct=80.0,
        ))
        assert out["cpu"].sellable_avg_util == 0.0
        assert out["ram"].sellable_avg_util == 0.0

class TestPartialAvgData:
    def test_host_missing_ram_average_still_keeps_avg_above_max(self):
        """The regression this branch's own review uncovered.

        The SQL wraps averages in COALESCE(..., 0), so a host whose memory
        columns are NULL across the window arrives with mem_used_gb_avg == 0
        beside a good CPU average. If that host contributed 0 units to n_avg,
        the family's avg column could sink below its max column -- reproducing
        the very defect being fixed. The peak fallback prevents it.
        """
        h = {k: v for k, v in _host().items() if k != "mem_used_gb_avg"}
        out = _by_kind(constrain_by_ratio_per_host_triple_dual(
            _panels(), _ratio(), [h],
            cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
        ))
        for kind in ("cpu", "ram", "storage"):
            p = out[kind]
            assert p.sellable_avg_util >= p.sellable_max_util, kind
            assert p.sellable_avg_util > 0.0, kind

    def test_mixed_fleet_one_host_without_averages(self):
        """A fleet where only some hosts have averages must still satisfy the
        invariant -- this is the realistic collector-gap shape."""
        good = _host()
        gap = {k: v for k, v in _host().items()
               if k not in ("mem_used_gb_avg", "cpu_used_ghz_avg")}
        gap["host"] = "esx02"
        out = _by_kind(constrain_by_ratio_per_host_triple_dual(
            _panels(), _ratio(), [good, gap],
            cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
        ))
        for kind in ("cpu", "ram", "storage"):
            assert out[kind].sellable_avg_util >= out[kind].sellable_max_util, kind


class TestEmptyHostsFallbackContinued:
    def test_dual_path_populates_avg_directly(self):
        out = _by_kind(constrain_by_ratio_per_host_dual(
            _panels(), _ratio(), [_host()],
            cpu_threshold_pct=80.0, ram_threshold_pct=80.0,
        ))
        assert out["cpu"].sellable_avg_util is not None
        assert out["cpu"].sellable_allocation < out["cpu"].sellable_avg_util


class TestClusterFallbackEntryPoint:
    def test_cluster_fallback_sets_avg_equal_to_max(self):
        # The third entry point fires when host rows are unavailable -- what a
        # collector gap produces. Without the avg field these panels render a
        # real number in Max beside an em-dash in Ort.
        from shared.sellable.computation import constrain_by_ratio_dual_cpu_cluster
        out = {p.resource_kind: p for p in constrain_by_ratio_dual_cpu_cluster(
            _panels(), _ratio(),
            cpu_raw_physical=800.0, cpu_raw_effective=800.0, cpu_raw_max=900.0,
            ram_raw_physical=1600.0, ram_raw_peak=1800.0,
        )}
        for kind in ("cpu", "ram"):
            assert out[kind].sellable_avg_util is not None, kind
            assert out[kind].sellable_avg_util == out[kind].sellable_max_util, kind


class TestHostEffectiveUnitsAvgHardening:
    def test_missing_cpu_average_does_not_fabricate_idle_headroom(self):
        # A near-saturated host with no average must not read as idle.
        from shared.sellable.computation import host_effective_units
        h = {"cpu_total": 100.0, "cpu_alloc": 90.0, "cpu_util_pct": 90.0,
             "cpu_used_ghz_peak": 90.0, "cpu_peak_util_pct": 90.0,
             "ram_total": 512.0, "ram_alloc": 400.0, "ram_util_pct": 78.0,
             "mem_cap_gb_at_peak": 512.0, "mem_used_gb_peak": 400.0,
             "mem_peak_util_pct": 78.0}
        n_avg = host_effective_units([h], _ratio(), cpu_threshold_pct=95.0,
                                     ram_threshold_pct=95.0,
                                     cpu_track="avg", ram_track="avg")
        n_max = host_effective_units([h], _ratio(), cpu_threshold_pct=95.0,
                                     ram_threshold_pct=95.0,
                                     cpu_track="max", ram_track="max")
        assert n_avg == n_max

    def test_genuine_zero_cpu_average_is_honoured(self):
        from shared.sellable.computation import host_effective_units
        h = {"cpu_total": 100.0, "cpu_alloc": 10.0, "cpu_util_pct": 10.0,
             "cpu_used_ghz_avg": 0.0, "cpu_avg_util_pct": 0.0,
             "cpu_used_ghz_peak": 40.0, "cpu_peak_util_pct": 40.0,
             "ram_total": 512.0, "ram_alloc": 100.0, "ram_util_pct": 20.0,
             "mem_cap_gb_avg": 512.0, "mem_used_gb_avg": 100.0,
             "mem_avg_util_pct": 20.0}
        n_avg = host_effective_units([h], _ratio(), cpu_threshold_pct=80.0,
                                     ram_threshold_pct=80.0,
                                     cpu_track="avg", ram_track="avg")
        n_max = host_effective_units([h], _ratio(), cpu_threshold_pct=80.0,
                                     ram_threshold_pct=80.0,
                                     cpu_track="max", ram_track="max")
        assert n_avg > n_max
