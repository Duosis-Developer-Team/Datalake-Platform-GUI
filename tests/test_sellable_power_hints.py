"""Tests for IBM Power sellable constraint hint messages."""

from src.utils.sellable_power_hints import power_sellable_constraint_hints


def test_no_hints_for_non_power_family():
    assert power_sellable_constraint_hints(
        ["virt_classic"],
        cpu_raw=100.0,
        cpu_constrained=0.0,
        ram_raw=0.0,
        ram_total=20.0,
        ram_allocated=16.0,
    ) == []


def test_ram_threshold_bound_when_operational_free_but_zero_sellable():
    hints = power_sellable_constraint_hints(
        ["virt_power"],
        cpu_raw=0.0,
        cpu_constrained=0.0,
        ram_raw=0.0,
        ram_total=20.0,
        ram_allocated=16.0,
        ram_threshold_pct=80.0,
    )
    assert len(hints) == 1
    assert "4 GB free operationally" in hints[0]
    assert "80% ceiling" in hints[0]


def test_cpu_blocked_by_ram_ratio():
    hints = power_sellable_constraint_hints(
        ["virt_power"],
        cpu_raw=3716.0,
        cpu_constrained=0.0,
        ram_raw=0.0,
        ram_total=100.0,
        ram_allocated=90.0,
    )
    assert any("CPU blocked by RAM ratio" in h for h in hints)
    assert any("16 GB" in h for h in hints)


def test_power_hana_uses_32gb_ratio_hint():
    hints = power_sellable_constraint_hints(
        ["virt_power_hana"],
        cpu_raw=10.0,
        cpu_constrained=0.0,
        ram_raw=0.0,
        ram_total=50.0,
        ram_allocated=40.0,
    )
    assert any("32 GB" in h for h in hints)
