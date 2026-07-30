"""host_units must carry RAM avg fields converted into panel display units."""
from app.services.sellable_service import SellableService
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
