"""Pure-python unit tests for shared/sellable/computation.py.

These cover the math the SellableService leans on but require no DB
or framework wiring — they should run in milliseconds even on CI.
"""
from __future__ import annotations

from shared.sellable.computation import (
    apply_threshold,
    compute_potential_tl,
    constrain_by_ratio,
    convert_unit,
)
from shared.sellable.models import PanelResult, ResourceRatio, UnitConversion


# ---------------------------------------------------------------- convert_unit


def test_convert_unit_identity_when_no_conversion():
    assert convert_unit(123.0, None) == 123.0


def test_convert_unit_none_input_collapses_to_zero():
    assert convert_unit(None, UnitConversion("Hz", "GHz", 1e9)) == 0.0


def test_convert_unit_divide_no_ceil_for_hz_to_ghz():
    conv = UnitConversion(from_unit="Hz", to_unit="GHz", factor=1e9, operation="divide")
    assert convert_unit(2_500_000_000, conv) == 2.5


def test_convert_unit_divide_with_ceil_for_ghz_to_vcpu():
    """1 vCPU = 8 GHz, fractional rounds UP — see ADR-0014."""
    conv = UnitConversion(from_unit="GHz", to_unit="vCPU", factor=8.0, operation="divide", ceil_result=True)
    assert convert_unit(63.5, conv) == 8.0
    assert convert_unit(64.0, conv) == 8.0
    assert convert_unit(64.1, conv) == 9.0


def test_convert_unit_multiply_for_tb_to_gb():
    conv = UnitConversion(from_unit="TB", to_unit="GB", factor=1024.0, operation="multiply")
    assert convert_unit(1.5, conv) == 1.5 * 1024.0


def test_convert_unit_zero_factor_collapses_to_zero():
    conv = UnitConversion(from_unit="X", to_unit="Y", factor=0.0)
    assert convert_unit(100.0, conv) == 0.0


# ------------------------------------------------------------ apply_threshold


def test_apply_threshold_default_80pct_minus_allocated():
    # capacity 100, allocated 50, threshold 80% -> sellable = 80 - 50 = 30
    assert apply_threshold(100.0, 50.0, 80.0) == 30.0


def test_apply_threshold_clamps_at_zero_when_overcommitted():
    assert apply_threshold(100.0, 95.0, 80.0) == 0.0
    assert apply_threshold(100.0, 100.0, 80.0) == 0.0


def test_apply_threshold_zero_capacity_is_zero():
    assert apply_threshold(0.0, 0.0, 80.0) == 0.0


def test_apply_threshold_negative_pct_treated_as_zero():
    assert apply_threshold(100.0, 0.0, -5.0) == 0.0


# ------------------------------------------------------- constrain_by_ratio


def _panel(kind: str, raw: float, price: float = 0.0, family: str = "virt_hyperconverged") -> PanelResult:
    return PanelResult(
        panel_key=f"{family}_{kind}",
        label=f"X {kind}",
        family=family,
        resource_kind=kind,
        display_unit="vCPU" if kind == "cpu" else "GB",
        sellable_raw=raw,
        unit_price_tl=price,
    )


def test_constrain_by_ratio_picks_scarce_resource_as_n():
    # Plan exactly the example from ADR-0014:
    # raw cpu=4 vCPU, ram=24 GB, storage=500 GB; ratio 1:8:100
    # -> n = min(4, 3, 5) = 3
    # -> constrained cpu=3, ram=24, storage=300
    panels = [_panel("cpu", 4.0), _panel("ram", 24.0), _panel("storage", 500.0)]
    ratio = ResourceRatio(family="virt_hyperconverged", cpu_per_unit=1.0, ram_gb_per_unit=8.0, storage_gb_per_unit=100.0)

    out = {p.resource_kind: p for p in constrain_by_ratio(panels, ratio)}

    assert out["cpu"].sellable_constrained == 3.0
    assert out["ram"].sellable_constrained == 24.0
    assert out["storage"].sellable_constrained == 300.0
    assert out["cpu"].ratio_bound is True
    assert out["ram"].ratio_bound is False
    assert out["storage"].ratio_bound is True


def test_constrain_by_ratio_zero_when_any_resource_is_zero():
    panels = [_panel("cpu", 4.0), _panel("ram", 0.0), _panel("storage", 500.0)]
    ratio = ResourceRatio(family="virt_hyperconverged", cpu_per_unit=1.0, ram_gb_per_unit=8.0, storage_gb_per_unit=100.0)
    out = {p.resource_kind: p for p in constrain_by_ratio(panels, ratio)}
    assert out["cpu"].sellable_constrained == 0.0
    assert out["ram"].sellable_constrained == 0.0
    assert out["storage"].sellable_constrained == 0.0
    assert out["cpu"].ratio_bound is True
    assert out["storage"].ratio_bound is True


def test_constrain_by_ratio_other_kind_is_passthrough():
    panels = [_panel("other", 7.0, family="firewall")]
    ratio = ResourceRatio(family="firewall")
    out = constrain_by_ratio(panels, ratio)
    assert out[0].sellable_constrained == 7.0
    assert out[0].ratio_bound is False


def test_constrain_by_ratio_only_cpu_present_keeps_cpu_raw():
    """When only one resource exists for the family, n is unconstrained
    by the missing resources and the panel keeps its raw value."""
    panels = [_panel("cpu", 16.0)]
    ratio = ResourceRatio(family="virt_classic", cpu_per_unit=1.0, ram_gb_per_unit=4.0, storage_gb_per_unit=100.0)
    out = constrain_by_ratio(panels, ratio)
    assert out[0].sellable_constrained == 16.0
    assert out[0].ratio_bound is False


# ----------------------------------------------------- compute_potential_tl


def test_compute_potential_tl_basic_multiplication():
    assert compute_potential_tl(10.0, 250.0) == 2500.0


def test_compute_potential_tl_negative_inputs_collapse_to_zero():
    assert compute_potential_tl(-5.0, 100.0) == 0.0
    assert compute_potential_tl(5.0, -100.0) == 0.0
