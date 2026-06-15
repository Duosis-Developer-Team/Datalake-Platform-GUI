"""Unit tests for the host-based sellable computation and the
architecture-aware storage range model (shared/sellable/computation.py).

A VM is provisioned on a single host, so sellable capacity must respect
per-host fragmentation; IBM storage free space is shared between KM
datastores and native Power storage, so storage sellables are ranges.
"""
from __future__ import annotations

from shared.sellable.computation import (
    apply_storage_ratio_cap,
    apply_utilization_gate,
    compute_storage_range,
    constrain_by_ratio_per_host,
    constrain_by_ratio_per_host_dual,
    constrain_by_ratio_per_host_triple_dual,
    host_effective_units,
    utilization_gate_blocked,
)
from shared.sellable.host_sellable import compute_host_sellable_units
from shared.sellable.models import PanelResult, ResourceRatio


def _ratio(cpu: float = 1.0, ram: float = 4.0, storage: float = 100.0) -> ResourceRatio:
    return ResourceRatio(
        family="virt_classic",
        cpu_per_unit=cpu,
        ram_gb_per_unit=ram,
        storage_gb_per_unit=storage,
    )


def _host(cpu_total: float, cpu_alloc: float, ram_total: float, ram_alloc: float) -> dict:
    return {
        "cpu_total": cpu_total,
        "cpu_alloc": cpu_alloc,
        "ram_total": ram_total,
        "ram_alloc": ram_alloc,
    }


def _panel(kind: str, raw: float = 0.0) -> PanelResult:
    return PanelResult(
        panel_key=f"virt_classic_{kind}",
        label=f"X {kind}",
        family="virt_classic",
        resource_kind=kind,
        display_unit="GHz" if kind == "cpu" else "GB",
        sellable_raw=raw,
        sellable_constrained=raw,
    )


# ------------------------------------------------------- host_effective_units


def test_host_effective_units_single_host():
    # 1 host: free cpu 10 GHz, free ram 80 GB; ratio 1:4 -> min(10, 20) = 10
    n = host_effective_units([_host(10.0, 0.0, 80.0, 0.0)], _ratio())
    assert n == 10.0


def test_host_effective_units_respects_per_host_fragmentation():
    """Aggregate free space can NOT be pooled across hosts.

    Host A: cpu-rich / ram-starved, Host B: ram-rich / cpu-starved.
    Aggregate min() would report 10 units; host-based must report less.
    """
    hosts = [
        _host(20.0, 0.0, 4.0, 0.0),   # min(20, 1) = 1 unit
        _host(2.0, 0.0, 200.0, 0.0),  # min(2, 50) = 2 units
    ]
    n = host_effective_units(hosts, _ratio())
    assert n == 3.0
    # Aggregate (pooled) math would give min(22, 51) = 22 — fragmentation matters.


def test_host_effective_units_applies_thresholds_per_host():
    # capacity 100 GHz, alloc 50 -> 80% threshold leaves 30 GHz sellable
    hosts = [_host(100.0, 50.0, 400.0, 0.0)]
    n = host_effective_units(hosts, _ratio(), cpu_threshold_pct=80.0, ram_threshold_pct=80.0)
    # cpu raw = 30, ram raw = 320 / 4 = 80 -> min = 30
    assert n == 30.0


def test_host_effective_units_overcommitted_host_contributes_zero():
    hosts = [
        _host(10.0, 12.0, 100.0, 0.0),  # cpu overcommitted -> 0 units
        _host(10.0, 0.0, 100.0, 0.0),   # min(10, 25) = 10 units
    ]
    assert host_effective_units(hosts, _ratio()) == 10.0


def test_host_effective_units_zero_ratio_returns_zero():
    assert host_effective_units([_host(10, 0, 80, 0)], _ratio(cpu=0.0)) == 0.0


# ------------------------------------------------ constrain_by_ratio_per_host


def test_constrain_by_ratio_per_host_sets_cpu_ram_from_units():
    hosts = [_host(20.0, 0.0, 4.0, 0.0), _host(2.0, 0.0, 200.0, 0.0)]  # n = 3
    panels = [_panel("cpu", raw=22.0), _panel("ram", raw=204.0)]
    out = {p.resource_kind: p for p in constrain_by_ratio_per_host(panels, _ratio(), hosts)}
    assert out["cpu"].sellable_constrained == 3.0
    assert out["ram"].sellable_constrained == 12.0
    assert out["cpu"].ratio_bound is True
    assert out["ram"].ratio_bound is True


def test_constrain_by_ratio_per_host_storage_capped_by_compute_bottleneck():
    """Storage passthrough from per-host step is capped by compute bottleneck."""
    hosts = [_host(10.0, 0.0, 80.0, 0.0)]
    panels = [_panel("cpu"), _panel("ram"), _panel("storage", raw=500.0)]
    interim = constrain_by_ratio_per_host(panels, _ratio(), hosts)
    out = {p.resource_kind: p for p in apply_storage_ratio_cap(interim, _ratio())}
    assert out["storage"].sellable_constrained == 500.0  # 10 units * 100 GB cap
    assert out["storage"].ratio_bound is False

    cpu = _panel("cpu", raw=10.0)
    cpu.sellable_constrained = 0.0
    ram = _panel("ram", raw=40.0)
    ram.sellable_constrained = 0.0
    sto = _panel("storage", raw=500.0)
    capped = apply_storage_ratio_cap([cpu, ram, sto], _ratio())
    sto_out = next(p for p in capped if p.resource_kind == "storage")
    assert sto_out.sellable_constrained == 0.0
    assert sto_out.constraint_reason == "compute_bottleneck"


def test_constrain_by_ratio_per_host_empty_hosts_zero_units():
    panels = [_panel("cpu", raw=10.0), _panel("ram", raw=40.0)]
    out = {p.resource_kind: p for p in constrain_by_ratio_per_host(panels, _ratio(), [])}
    assert out["cpu"].sellable_constrained == 0.0
    assert out["ram"].sellable_constrained == 0.0


# ------------------------------------------------------ compute_storage_range


def test_compute_storage_range_km_and_power_formulas():
    rng = compute_storage_range(
        intel_free=100.0,
        ibm_backed_datastore_free=40.0,
        ibm_storage_free=120.0,
    )
    # KM: min = Intel only, max = Intel + IBM-backed datastore free.
    assert rng["km_min"] == 100.0
    assert rng["km_max"] == 140.0
    # Power: min = IBM free minus KM-exposed share, max = full IBM free.
    assert rng["power_min"] == 80.0
    assert rng["power_max"] == 120.0


def test_compute_storage_range_power_min_clamps_at_zero():
    rng = compute_storage_range(
        intel_free=0.0,
        ibm_backed_datastore_free=200.0,
        ibm_storage_free=120.0,
    )
    assert rng["power_min"] == 0.0
    assert rng["power_max"] == 120.0


def test_compute_storage_range_negative_inputs_clamp():
    rng = compute_storage_range(
        intel_free=-5.0,
        ibm_backed_datastore_free=-1.0,
        ibm_storage_free=-2.0,
    )
    assert rng == {"km_min": 0.0, "km_max": 0.0, "power_min": 0.0, "power_max": 0.0}


def test_compute_storage_range_no_ibm_means_degenerate_range():
    rng = compute_storage_range(
        intel_free=50.0,
        ibm_backed_datastore_free=0.0,
        ibm_storage_free=0.0,
    )
    assert rng["km_min"] == rng["km_max"] == 50.0
    assert rng["power_min"] == rng["power_max"] == 0.0


def test_host_effective_units_physical_track_uses_ghz_per_core():
    hosts = [{
        "cpu_total_phys": 20.0,
        "cpu_alloc_phys": 5.0,
        "ghz_per_core": 2.0,
        "ram_total": 80.0,
        "ram_alloc": 0.0,
    }]
    n = host_effective_units(hosts, _ratio(), cpu_track="physical")
    # raw cpu = 15 GHz -> 15 / (1*2) = 7.5 units
    assert n == 7.5


def test_constrain_by_ratio_per_host_dual_populates_tracks():
    hosts = [{
        "cpu_total": 20.0,
        "cpu_alloc": 0.0,
        "cpu_total_phys": 20.0,
        "cpu_alloc_phys": 0.0,
        "ghz_per_core": 2.0,
        "ram_total": 80.0,
        "ram_alloc": 0.0,
    }]
    panels = [_panel("cpu", raw=20.0), _panel("ram", raw=80.0)]
    out = {p.resource_kind: p for p in constrain_by_ratio_per_host_dual(panels, _ratio(), hosts)}
    assert out["cpu"].sellable_effective == 20.0
    assert out["cpu"].sellable_physical == 10.0
    assert out["cpu"].computation_mode == "host_based"


def test_utilization_gate_blocked_when_allocation_exceeds_threshold():
    assert utilization_gate_blocked(100.0, 90.0, 50.0, 80.0) is True
    assert apply_utilization_gate(100.0, 90.0, 50.0, 80.0) == 0.0


def test_host_effective_units_ram_peak_track_uses_cluster_peak_fields():
    hosts = [{
        "cpu_total": 10.0,
        "cpu_alloc": 0.0,
        "ram_peak_total": 100.0,
        "ram_peak_used": 20.0,
        "ram_peak_util_pct": 25.0,
    }]
    n = host_effective_units(
        hosts, _ratio(ram=10.0), ram_track="peak", ram_threshold_pct=80.0
    )
    assert n == 6.0


def test_constrain_by_ratio_per_host_dual_ram_physical_vs_peak():
    hosts = [{
        "cpu_total": 100.0,
        "cpu_alloc": 0.0,
        "cpu_total_phys": 100.0,
        "cpu_alloc_phys": 0.0,
        "ghz_per_core": 1.0,
        "ram_total": 80.0,
        "ram_alloc": 0.0,
        "ram_peak_total": 100.0,
        "ram_peak_used": 90.0,
        "ram_peak_util_pct": 95.0,
    }]
    panels = [_panel("cpu", raw=100.0), _panel("ram", raw=80.0)]
    out = {p.resource_kind: p for p in constrain_by_ratio_per_host_dual(
        panels,
        _ratio(),
        hosts,
        cpu_threshold_pct=80.0,
        ram_threshold_pct=80.0,
        ram_raw_physical=80.0,
        ram_raw_peak=0.0,
    )}
    assert out["ram"].sellable_physical > 0
    assert out["ram"].sellable_effective == 0.0
    assert out["ram"].ratio_bound is True


def test_constrain_by_ratio_dual_cpu_cluster_storage_uses_effective_n():
    from shared.sellable.computation import constrain_by_ratio_dual_cpu_cluster

    panels = [
        _panel("cpu", raw=100.0),
        _panel("ram", raw=400.0),
        _panel("storage", raw=80000.0),
    ]
    out = {
        p.resource_kind: p
        for p in constrain_by_ratio_dual_cpu_cluster(
            panels,
            _ratio(cpu=1.0, ram=4.0, storage=100.0),
            cpu_raw_physical=100.0,
            cpu_raw_effective=100.0,
            ram_raw_physical=400.0,
            ram_raw_peak=400.0,
        )
    }
    # n = min(100, 100, 800) = 100 -> storage constrained = 100 * 100
    assert out["storage"].sellable_constrained == 10000.0
    assert out["storage"].ratio_bound is True


def test_triple_min_user_scenario_4_56_800():
    """Operator scenario: 4 GHz / 56 GB / 800 GB free → 4 units at 1:4:50."""
    host = {
        "cpu_cap_ghz": 100.0,
        "cpu_alloc_ghz": 96.0,
        "cpu_used_pct": 50.0,
        "mem_cap_gb": 100.0,
        "mem_alloc_gb": 44.0,
        "mem_used_pct": 44.0,
        "stor_cap_gb": 1000.0,
        "stor_provisioned_gb": 200.0,
        "stor_used_pct": 20.0,
        "stor_exclusive_free_gb": 800.0,
        "ghz_per_core": 1.0,
    }
    ratio = _ratio(cpu=1.0, ram=4.0, storage=50.0)
    result = compute_host_sellable_units(
        host,
        ratio,
        cpu_threshold_pct=100.0,
        ram_threshold_pct=100.0,
        storage_threshold_pct=100.0,
    )
    assert result.n_units_min == 4.0
    assert result.cpu_constrained == 4.0
    assert result.ram_constrained == 16.0
    assert result.stor_constrained_min == 200.0
    assert abs(result.waste_ram - 40.0) < 1e-6
    assert abs(result.waste_stor_min - 600.0) < 1e-6
    assert any("RAM" in t for t in result.constraint_tags)
    assert any("storage" in t for t in result.constraint_tags)


def test_shared_datastore_not_double_counted_in_family_range():
    """Two hosts mounting the same shared pool → family max uses pool once."""
    from shared.sellable.host_sellable import aggregate_family_storage_range

    ratio = _ratio(cpu=1.0, ram=4.0, storage=100.0)
    mount = {"shared": True, "free_gb": 500.0}
    host_a = {
        "cpu_cap_ghz": 100.0, "cpu_alloc_ghz": 0.0, "cpu_used_pct": 10.0,
        "mem_cap_gb": 400.0, "mem_alloc_gb": 0.0, "mem_used_pct": 10.0,
        "stor_cap_gb": 1000.0, "stor_provisioned_gb": 0.0, "stor_used_pct": 10.0,
        "stor_exclusive_free_gb": 0.0, "datastore_mounts": [mount],
    }
    host_b = dict(host_a)
    shared_pools = [{"shared": True, "free_gb": 500.0}]
    r_a_min = compute_host_sellable_units(
        host_a, ratio, cpu_threshold_pct=100.0, ram_threshold_pct=100.0,
        storage_threshold_pct=100.0, storage_include_shared=False,
    )
    r_b_min = compute_host_sellable_units(
        host_b, ratio, cpu_threshold_pct=100.0, ram_threshold_pct=100.0,
        storage_threshold_pct=100.0, storage_include_shared=False,
    )
    r_a_max = compute_host_sellable_units(
        host_a, ratio, cpu_threshold_pct=100.0, ram_threshold_pct=100.0,
        storage_threshold_pct=100.0, storage_include_shared=True,
    )
    r_b_max = compute_host_sellable_units(
        host_b, ratio, cpu_threshold_pct=100.0, ram_threshold_pct=100.0,
        storage_threshold_pct=100.0, storage_include_shared=True,
    )
    lo, _ = aggregate_family_storage_range([r_a_min, r_b_min], shared_pools, ratio)
    _, hi = aggregate_family_storage_range([r_a_max, r_b_max], shared_pools, ratio)
    assert lo == 0.0
    assert hi <= 500.0 + 1e-6
