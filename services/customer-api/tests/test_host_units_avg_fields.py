"""host_units must carry RAM avg fields converted into panel display units."""
from app.services.sellable_service import SellableService
from shared.sellable.host_sellable import host_raw_headroom
from shared.sellable.models import UnitConversion

# GB -> TB, i.e. divide by 1024.
GB_TO_TB = UnitConversion(from_unit="GB", to_unit="TB", factor=1024.0, operation="divide")

HOST = {
    "host": "esx01", "cluster": "KM01", "ghz_per_core": 2.0,
    "cpu_cap_ghz": 100.0, "cpu_alloc_ghz": 70.0, "cpu_used_pct": 30.0,
    "mem_cap_gb": 1024.0, "mem_alloc_gb": 800.0, "mem_used_pct": 50.0,
    "mem_used_gb_peak": 600.0, "mem_cap_gb_at_peak": 1024.0, "mem_peak_util_pct": 58.6,
    "mem_used_gb_avg": 360.0, "mem_cap_gb_avg": 1024.0, "mem_avg_util_pct": 35.2,
    "cpu_used_ghz_avg": 25.0, "cpu_used_ghz_peak": 40.0,
    "stor_cap_gb": 0.0, "stor_provisioned_gb": 0.0, "stor_used_pct": 0.0,
}


def test_ram_avg_converted_like_ram_peak():
    """RAM avg is converted into display units exactly like RAM peak, because
    host_raw_headroom compares it against converted capacities."""
    u = SellableService._normalize_host_unit(
        HOST, cpu_conv=None, ram_conv=GB_TO_TB, sto_conv=None
    )
    assert abs(u["mem_used_gb_avg"] - 360.0 / 1024.0) < 1e-9
    assert abs(u["mem_cap_gb_avg"] - 1024.0 / 1024.0) < 1e-9
    assert u["mem_avg_util_pct"] == 35.2
    # Sanity: peak gets the identical treatment.
    assert abs(u["mem_used_gb_peak"] - 600.0 / 1024.0) < 1e-9


def test_cpu_avg_and_peak_pass_through_unconverted():
    """host_raw_headroom's CPU arm uses raw cpu_cap_ghz as its denominator, so
    the CPU avg/peak fields must ride the **h spread as raw GHz."""
    u = SellableService._normalize_host_unit(
        HOST, cpu_conv=None, ram_conv=GB_TO_TB, sto_conv=None
    )
    assert u["cpu_used_ghz_avg"] == 25.0
    assert u["cpu_used_ghz_peak"] == 40.0


def test_ram_avg_cap_falls_back_to_current_cap():
    """Only the used average has no fallback; the capacity denominator may fall
    back to current capacity so a partial metric still computes."""
    host = {k: v for k, v in HOST.items() if k != "mem_cap_gb_avg"}
    u = SellableService._normalize_host_unit(
        host, cpu_conv=None, ram_conv=GB_TO_TB, sto_conv=None
    )
    assert abs(u["mem_cap_gb_avg"] - 1024.0 / 1024.0) < 1e-9


def test_missing_ram_avg_stays_absent_not_present_zero():
    """C1 regression: a host with NO RAM average data at all (used, cap, and
    util all absent from the source row) must come out of
    _normalize_host_unit with the mem_*_avg keys still absent -- not written
    as a fabricated ``0.0``. A present-and-zero ``mem_used_gb_avg`` would be
    read by host_sellable._first_present as real data (a genuinely idle
    host) instead of falling back to the RAM peak."""
    host = {k: v for k, v in HOST.items()
            if k not in ("mem_used_gb_avg", "mem_cap_gb_avg", "mem_avg_util_pct")}
    u = SellableService._normalize_host_unit(
        host, cpu_conv=None, ram_conv=GB_TO_TB, sto_conv=None
    )
    assert "mem_used_gb_avg" not in u
    assert "mem_cap_gb_avg" not in u
    assert "mem_avg_util_pct" not in u


def test_missing_ram_avg_composes_to_avg_equal_max_not_inflated():
    """C1 end-to-end: normalize a saturated host (1000 GB RAM, 90% current
    usage, 95% peak, threshold 80%) whose RAM average is entirely absent,
    then feed the normalized dict through host_raw_headroom on both tracks.

    Before the fix, _normalize_host_unit wrote mem_used_gb_avg=0.0 (a
    fabricated present zero), which host_raw_headroom's avg arm honoured as
    real data: cap fell back to the full 1000 GB while used stayed at the
    fabricated 0, producing 800 GB of manufactured headroom on a host that is
    90% full and gate-blocked on every other track. After the fix, the
    absence must reach _first_present so it falls back to the RAM peak and
    the avg headroom equals the (correctly gate-blocked) max headroom."""
    host = {
        "mem_cap_gb": 1000.0, "mem_used_pct": 90.0,
        "mem_used_gb_peak": 950.0, "mem_cap_gb_at_peak": 1000.0,
        "mem_peak_util_pct": 95.0,
        # mem_used_gb_avg / mem_cap_gb_avg / mem_avg_util_pct: ABSENT
    }
    u = SellableService._normalize_host_unit(
        host, cpu_conv=None, ram_conv=None, sto_conv=None
    )
    avg_headroom = host_raw_headroom(
        u, resource="ram", threshold_pct=80.0, ram_track="avg"
    )
    max_headroom = host_raw_headroom(
        u, resource="ram", threshold_pct=80.0, ram_track="max"
    )
    assert max_headroom == 0.0, "gate should block: 95% used > 80% threshold"
    assert avg_headroom == max_headroom, (
        f"avg headroom {avg_headroom} must not exceed the gate-blocked max "
        f"({max_headroom}) just because the RAM average is missing"
    )
