"""Edge-case coverage for `convert_unit` — keeps the Sellable Potential
pipeline honest about Hz/GHz/vCPU/bytes/GB juggling.

These complement test_sellable_computation.py with the specific
conversion identities the seed in
009_seed_unit_conversions.sql relies on.
"""
from __future__ import annotations

import math

from shared.sellable.computation import convert_unit
from shared.sellable.models import UnitConversion


def _conv(from_u: str, to_u: str, factor: float, *, op: str = "divide", ceil: bool = False) -> UnitConversion:
    return UnitConversion(from_unit=from_u, to_unit=to_u, factor=factor, operation=op, ceil_result=ceil)


def test_hz_to_ghz_no_ceil():
    """1 GHz = 1e9 Hz (Nutanix collector emits Hz at the cluster level)."""
    assert convert_unit(2_500_000_000, _conv("Hz", "GHz", 1e9)) == 2.5
    assert convert_unit(0, _conv("Hz", "GHz", 1e9)) == 0.0


def test_ghz_to_vcpu_8_to_1_with_ceil():
    """1 vCPU = 8 GHz; fractional always rounds UP per ADR-0014.

    These are the canonical assertions called out in the plan:
      63.5 GHz / 8 = 7.94 -> 8 vCPU
      64.0 GHz / 8 = 8.00 -> 8 vCPU
      64.1 GHz / 8 = 8.01 -> 9 vCPU
    """
    c = _conv("GHz", "vCPU", 8.0, ceil=True)
    assert convert_unit(63.5, c) == 8.0
    assert convert_unit(64.0, c) == 8.0
    assert convert_unit(64.1, c) == 9.0
    assert convert_unit(0, c) == 0.0


def test_bytes_to_gb_1024_pow_3():
    factor = float(1024 ** 3)
    c = _conv("bytes", "GB", factor)
    assert math.isclose(convert_unit(factor, c), 1.0)
    assert math.isclose(convert_unit(2 * factor, c), 2.0)


def test_mb_to_gb_divide_by_1024():
    c = _conv("MB", "GB", 1024.0)
    assert math.isclose(convert_unit(2048, c), 2.0)


def test_tb_to_gb_multiply_by_1024():
    c = _conv("TB", "GB", 1024.0, op="multiply")
    assert math.isclose(convert_unit(1.5, c), 1536.0)


def test_core_to_vcpu_passthrough():
    c = _conv("Core", "vCPU", 1.0)
    assert convert_unit(8, c) == 8.0


def test_unknown_or_missing_conversion_is_identity():
    """When the SellableService cannot find a (from,to) entry it falls back
    to ``None`` and ``convert_unit`` must behave as the identity, NOT
    crash. This protects panels whose total_unit already matches
    display_unit (e.g. NetBackup pool reports GB directly)."""
    assert convert_unit(123.456, None) == 123.456
