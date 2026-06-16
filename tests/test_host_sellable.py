"""Unit tests for per-host triple-min sellable computation."""
from __future__ import annotations

from shared.sellable.host_sellable import (
    aggregate_family_storage_range,
    compute_host_sellable_units,
    host_storage_free_gb,
    host_storage_in_triple,
)
from shared.sellable.models import ResourceRatio


RATIO = ResourceRatio(
    family="virt_classic",
    cpu_per_unit=1.0,
    ram_gb_per_unit=4.0,
    storage_gb_per_unit=50.0,
)


def _operator_example_host() -> dict:
    """Headroom after gates: 4 GHz CPU, 56 GB RAM, 800 GB storage."""
    return {
        "host": "hv-example",
        "cluster": "KM-CLS",
        "cpu_cap_ghz": 100.0,
        "cpu_alloc_ghz": 76.0,
        "cpu_used_pct": 10.0,
        "mem_cap_gb": 100.0,
        "mem_alloc_gb": 24.0,
        "mem_used_pct": 10.0,
        "stor_cap_gb": 1000.0,
        "stor_provisioned_gb": 0.0,
        "stor_used_pct": 5.0,
        "stor_exclusive_free_gb": 800.0,
    }


def test_host_sellable_example_4_56_800():
    result = compute_host_sellable_units(
        _operator_example_host(),
        RATIO,
        cpu_threshold_pct=80.0,
        ram_threshold_pct=80.0,
        storage_threshold_pct=85.0,
    )
    assert result.n_units_min == 4.0
    assert result.ram_constrained == 16.0
    assert result.stor_constrained_min == 200.0
    assert "40 GB RAM ratio-bound" in result.constraint_tags
    assert "600 GB Storage ratio-bound" in result.constraint_tags


def test_host_storage_free_gb_exclusive_vs_shared():
    host = {
        "stor_exclusive_free_gb": 100.0,
        "datastore_mounts": [
            {"shared": True, "free_gb": 300.0},
            {"shared": False, "free_gb": 50.0},
        ],
    }
    assert host_storage_free_gb(host, include_shared=False) == 100.0
    assert host_storage_free_gb(host, include_shared=True) == 400.0


def test_gate_blocked_yields_zero_units():
    host = {
        "cpu_cap_ghz": 100.0,
        "cpu_alloc_ghz": 90.0,
        "cpu_used_pct": 95.0,
        "mem_cap_gb": 100.0,
        "mem_alloc_gb": 90.0,
        "mem_used_pct": 95.0,
        "stor_cap_gb": 1000.0,
        "stor_provisioned_gb": 950.0,
        "stor_used_pct": 95.0,
        "stor_exclusive_free_gb": 50.0,
    }
    result = compute_host_sellable_units(
        host, RATIO, cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
    )
    assert result.n_units_min == 0.0
    assert result.constraint_tags == []


def test_cpu_gate_blocked_zeros_units_despite_storage_headroom():
    """Overallocated CPU must zero triple-min even when storage headroom is large."""
    host = {
        "cpu_cap_ghz": 143.6,
        "cpu_alloc_ghz": 258.0,
        "cpu_used_pct": 89.6,
        "mem_cap_gb": 1535.7,
        "mem_alloc_gb": 622.9,
        "mem_used_pct": 40.6,
        "stor_cap_gb": 445756.0,
        "stor_provisioned_gb": 1000.0,
        "stor_used_pct": 10.0,
        "stor_exclusive_free_gb": 400000.0,
    }
    result = compute_host_sellable_units(
        host, RATIO, cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
    )
    assert result.n_units_min == 0.0


def test_ram_gate_blocked_zeros_units_despite_storage_headroom():
    host = {
        "cpu_cap_ghz": 100.0,
        "cpu_alloc_ghz": 20.0,
        "cpu_used_pct": 10.0,
        "mem_cap_gb": 100.0,
        "mem_alloc_gb": 95.0,
        "mem_used_pct": 95.0,
        "stor_cap_gb": 10000.0,
        "stor_provisioned_gb": 100.0,
        "stor_used_pct": 5.0,
        "stor_exclusive_free_gb": 9000.0,
    }
    result = compute_host_sellable_units(
        host, RATIO, cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
    )
    assert result.n_units_min == 0.0


def test_shared_pool_max_band_can_exceed_min():
    host = _operator_example_host()
    host["datastore_mounts"] = [{"shared": True, "free_gb": 2000.0}]
    min_res = compute_host_sellable_units(
        host, RATIO, cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
        storage_include_shared=False,
    )
    max_res = compute_host_sellable_units(
        host, RATIO, cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
        storage_include_shared=True,
    )
    assert max_res.n_units_max >= min_res.n_units_min


def test_aggregate_family_storage_range_uses_host_results():
    from shared.sellable.host_sellable import HostSellableResult

    results = [
        HostSellableResult(stor_constrained_min=100.0, stor_constrained_max=200.0),
        HostSellableResult(stor_constrained_min=50.0, stor_constrained_max=150.0),
    ]
    lo, hi = aggregate_family_storage_range(results, [], RATIO)
    assert lo == 150.0
    assert hi >= 150.0


def test_host_storage_in_triple_false_for_km_shared_lun():
    host = {"km_shared_storage": True, "stor_cap_gb": 1000.0}
    assert host_storage_in_triple(host) is False


def test_km_shared_storage_host_cpu_ram_units_without_storage_triple():
    """DC13-like: storage gate blocked on mount max pct but CPU/RAM headroom remains."""
    host = {
        "cpu_cap_ghz": 229.8,
        "cpu_alloc_ghz": 180.0,
        "cpu_used_ghz": 67.8,
        "cpu_used_pct": 29.5,
        "mem_cap_gb": 6143.7,
        "mem_alloc_gb": 4300.0,
        "mem_used_pct": 70.5,
        "mem_cap_gb_at_peak": 6143.7,
        "mem_used_gb_peak": 4329.5,
        "mem_peak_util_pct": 70.5,
        "stor_cap_gb": 318873.6,
        "stor_provisioned_gb": 29360.0,
        "stor_used_pct": 95.0,
        "stor_exclusive_free_gb": 0.0,
        "km_shared_storage": True,
        "datastore_mounts": [{"shared": True, "free_gb": 110379.0}],
    }
    blocked = compute_host_sellable_units(
        host, RATIO, cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
    )
    assert blocked.n_units_min == 0.0
    decoupled = compute_host_sellable_units(
        host, RATIO,
        cpu_threshold_pct=80.0, ram_threshold_pct=80.0, storage_threshold_pct=85.0,
        cpu_track="max", ram_track="max",
        storage_in_triple=False,
    )
    assert decoupled.n_units_min > 0.0
