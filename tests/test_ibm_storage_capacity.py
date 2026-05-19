"""Unit tests for IBM Storage physical vs efficient capacity calculations."""

from __future__ import annotations

import pytest

from src.utils.format_units import parse_storage_string
from src.utils.ibm_storage_capacity import (
    aggregate_ibm_storage_capacities,
    compute_system_capacities_gb,
    topology_divisor,
)


def test_topology_divisor_standard():
    assert topology_divisor("standard") == 1.0
    assert topology_divisor("Standard") == 1.0
    assert topology_divisor(None) == 1.0


def test_topology_divisor_hyperswap():
    assert topology_divisor("hyperswap") == 2.0
    assert topology_divisor("Hyperswap") == 2.0


def test_compute_system_capacities_standard():
    system = {
        "topology": "standard",
        "physical_capacity": "100.00 TB",
        "physical_free_capacity": "40.00 TB",
        "total_mdisk_capacity": "120.00 TB",
        "total_free_space": "50.00 TB",
    }
    caps = compute_system_capacities_gb(system, parse_storage_string)
    assert caps["phys_total_gb"] == pytest.approx(102400.0)
    assert caps["phys_free_gb"] == pytest.approx(40960.0)
    assert caps["phys_used_gb"] == pytest.approx(61440.0)
    assert caps["eff_total_gb"] == pytest.approx(20480.0)
    assert caps["eff_free_gb"] == pytest.approx(10240.0)
    assert caps["eff_used_gb"] == pytest.approx(10240.0)


def test_compute_system_capacities_hyperswap_halves_physical():
    system = {
        "topology": "hyperswap",
        "physical_capacity": "200.00 TB",
        "physical_free_capacity": "80.00 TB",
        "total_mdisk_capacity": "220.00 TB",
        "total_free_space": "90.00 TB",
    }
    caps = compute_system_capacities_gb(system, parse_storage_string)
    assert caps["phys_total_gb"] == pytest.approx(102400.0)
    assert caps["phys_free_gb"] == pytest.approx(40960.0)
    assert caps["eff_total_gb"] == pytest.approx(20480.0)
    assert caps["eff_free_gb"] == pytest.approx(10240.0)


def test_aggregate_ibm_storage_capacities_multiple_systems():
    systems = [
        {
            "topology": "standard",
            "physical_capacity": "10.00 TB",
            "physical_free_capacity": "4.00 TB",
            "total_mdisk_capacity": "12.00 TB",
            "total_free_space": "5.00 TB",
        },
        {
            "topology": "hyperswap",
            "physical_capacity": "20.00 TB",
            "physical_free_capacity": "8.00 TB",
            "total_mdisk_capacity": "24.00 TB",
            "total_free_space": "10.00 TB",
        },
    ]
    agg = aggregate_ibm_storage_capacities(systems, parse_storage_string)
    assert agg["phys_total_gb"] == pytest.approx(10240.0 + 10240.0)
    assert agg["phys_free_gb"] == pytest.approx(4096.0 + 4096.0)
    assert agg["phys_used_gb"] == pytest.approx(agg["phys_total_gb"] - agg["phys_free_gb"])
    assert agg["eff_total_gb"] == pytest.approx(2048.0 + 4096.0)
    assert agg["utilization_pct"] == pytest.approx(60.0)


def test_build_ibm_storage_subtab_renders_without_san_bottleneck():
    from src.pages import dc_view

    node = dc_view._build_ibm_storage_subtab(
        {
            "systems": [
                {
                    "name": "IBM-TEST",
                    "topology": "standard",
                    "layer": "storage",
                    "physical_capacity": "100.00 TB",
                    "physical_free_capacity": "30.00 TB",
                    "total_mdisk_capacity": "110.00 TB",
                    "total_free_space": "35.00 TB",
                }
            ]
        },
        {"series": [{"iops": 100, "throughput_mb": 50, "latency_ms": 2}]},
    )
    assert node is not None
    serialized = str(node)
    assert "SAN Bottleneck" not in serialized
    assert "Physical Total" in serialized
    assert "Efficient Total" in serialized
