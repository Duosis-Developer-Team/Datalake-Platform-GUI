"""Replication Classic/HC CPU/RAM use virt host SoT (ADR-0032 §37)."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.services.sellable_service import (
    SellableService,
    _HOST_BASED_FAMILIES,
    _HOST_COMPUTE_ONLY_FAMILIES,
    _REPLICATION_HOST_SOURCE_FAMILY,
)  # noqa: WPS433
from shared.sellable.models import PanelResult, ResourceRatio, UnitConversion


def test_replication_classic_hc_map_to_virt_host_families():
    assert _REPLICATION_HOST_SOURCE_FAMILY["backup_veeam_replication_classic"] == "virt_classic"
    assert _REPLICATION_HOST_SOURCE_FAMILY["backup_zerto_replication_classic"] == "virt_classic"
    assert (
        _REPLICATION_HOST_SOURCE_FAMILY["backup_veeam_replication_hyperconverged"]
        == "virt_hyperconverged"
    )
    assert (
        _REPLICATION_HOST_SOURCE_FAMILY["backup_zerto_replication_hyperconverged"]
        == "virt_hyperconverged"
    )
    for fam in _REPLICATION_HOST_SOURCE_FAMILY:
        assert fam in _HOST_BASED_FAMILIES
        assert fam in _HOST_COMPUTE_ONLY_FAMILIES


def test_apply_replication_alternate_preserves_allocation_triad():
    panel = PanelResult(
        panel_key="backup_veeam_replication_classic_cpu",
        label="Veeam Classic CPU",
        family="backup_veeam_replication_classic",
        resource_kind="cpu",
        display_unit="vCPU",
        dc_code="DC13",
        total=100.0,
        allocated=40.0,
        threshold_pct=80.0,
        sellable_raw=50.0,
        sellable_constrained=50.0,
        unit_price_tl=10.0,
        potential_tl=500.0,
        has_infra_source=True,
        has_price=True,
        sellable_allocation=50.0,
        sellable_max_util=45.0,
        sellable_avg_util=40.0,
    )
    svc = SellableService.__new__(SellableService)
    svc._apply_replication_alternate_ranges([panel])
    assert panel.sellable_min == 0.0
    assert panel.sellable_max == 50.0
    assert panel.sellable_allocation == 50.0
    assert panel.sellable_max_util == 45.0
    assert panel.sellable_avg_util == 40.0


def test_subtract_replica_allocation_from_virt():
    svc = SellableService.__new__(SellableService)
    svc._dc_api_url = "http://example"  # type: ignore[attr-defined]
    cpu = PanelResult(
        panel_key="virt_classic_cpu",
        label="CPU",
        family="virt_classic",
        resource_kind="cpu",
        display_unit="vCPU",
        dc_code="DC13",
        total=100.0,
        allocated=80.0,
        threshold_pct=80.0,
        sellable_raw=20.0,
        sellable_constrained=20.0,
        sellable_allocation=20.0,
        unit_price_tl=1.0,
        potential_tl=20.0,
        has_infra_source=True,
        has_price=True,
    )
    svc._fetch_replica_allocation_offset = (  # type: ignore[method-assign]
        lambda dc, fam: {"cpu_vcpu": 10.0, "ram_gb": 0.0, "vm_count": 2}
    )
    out = svc._subtract_replica_allocation_from_virt([cpu], "DC13", "virt_classic")
    assert out[0].allocated == 70.0
    assert out[0].sellable_allocation == 30.0
    assert any("replica/Zerto" in n for n in (out[0].notes or []))


def test_host_based_constraints_marks_infra_source_true():
    """Global inventory starts replication panels with has_infra=False; host path must flip it."""
    cpu = PanelResult(
        panel_key="backup_veeam_replication_classic_cpu",
        label="Veeam Classic CPU",
        family="backup_veeam_replication_classic",
        resource_kind="cpu",
        display_unit="vCPU",
        dc_code="*",
        total=0.0,
        allocated=0.0,
        threshold_pct=80.0,
        sellable_raw=0.0,
        sellable_constrained=0.0,
        has_infra_source=False,
        has_price=True,
        unit_price_tl=1.0,
        potential_tl=0.0,
    )
    ram = PanelResult(
        panel_key="backup_veeam_replication_classic_ram",
        label="Veeam Classic RAM",
        family="backup_veeam_replication_classic",
        resource_kind="ram",
        display_unit="GB",
        dc_code="*",
        total=0.0,
        allocated=0.0,
        threshold_pct=80.0,
        sellable_raw=0.0,
        sellable_constrained=0.0,
        has_infra_source=False,
        has_price=True,
        unit_price_tl=1.0,
        potential_tl=0.0,
    )
    host_rows = [{
        "cpu_cap_ghz": 80.0,
        "cpu_alloc_ghz_sales": 20.0,
        "cpu_used_pct": 25.0,
        "mem_cap_gb": 256.0,
        "mem_alloc_gb_vm": 64.0,
        "mem_used_pct": 25.0,
        "mem_cap_gb_at_peak": 256.0,
        "mem_used_gb_peak": 64.0,
        "stor_cap_gb": 0.0,
        "stor_provisioned_gb": 0.0,
        "stor_used_pct": 0.0,
        "cluster": "KM-1",
    }]
    ratio = ResourceRatio(
        family="backup_veeam_replication_classic",
        cpu_per_unit=1.0,
        ram_gb_per_unit=4.0,
        storage_gb_per_unit=50.0,
    )
    unit_lookup = {
        ("GHz", "vCPU"): UnitConversion("GHz", "vCPU", 8.0, "divide", True),
        ("GB", "GB"): UnitConversion("GB", "GB", 1.0),
    }
    svc = SellableService.__new__(SellableService)
    out = svc._apply_host_based_constraints(
        [cpu, ram],
        ratio,
        host_rows,
        unit_lookup,
        dc_code="*",
        family="virt_classic",
        host_cpu_unit="GHz",
    )
    assert all(p.has_infra_source for p in out if p.resource_kind in ("cpu", "ram"))
    assert next(p for p in out if p.resource_kind == "cpu").total > 0


def test_recompute_with_infra_dcs_flips_replication_has_infra():
    """Final global inventory recompute must promote CRM-only replication to bound infra."""
    cpu = PanelResult(
        panel_key="backup_veeam_replication_classic_cpu",
        label="Veeam Classic CPU",
        family="backup_veeam_replication_classic",
        resource_kind="cpu",
        display_unit="vCPU",
        dc_code="*",
        total=0.0,
        allocated=0.0,
        threshold_pct=80.0,
        sellable_raw=0.0,
        sellable_constrained=0.0,
        has_infra_source=False,
        has_price=True,
        unit_price_tl=1.0,
        potential_tl=0.0,
        notes=["infra-source missing — configure in Settings"],
    )
    ram = PanelResult(
        panel_key="backup_veeam_replication_classic_ram",
        label="Veeam Classic RAM",
        family="backup_veeam_replication_classic",
        resource_kind="ram",
        display_unit="GB",
        dc_code="*",
        total=0.0,
        allocated=0.0,
        threshold_pct=80.0,
        sellable_raw=0.0,
        sellable_constrained=0.0,
        has_infra_source=False,
        has_price=True,
        unit_price_tl=1.0,
        potential_tl=0.0,
    )
    sto = PanelResult(
        panel_key="backup_veeam_replication_classic_storage",
        label="Veeam Classic Storage",
        family="backup_veeam_replication_classic",
        resource_kind="storage",
        display_unit="GB",
        dc_code="*",
        total=0.0,
        allocated=0.0,
        threshold_pct=85.0,
        sellable_raw=0.0,
        sellable_constrained=0.0,
        has_infra_source=False,
        has_price=True,
        unit_price_tl=1.0,
        potential_tl=0.0,
    )
    host_rows = [{
        "cpu_cap_ghz": 80.0,
        "cpu_alloc_ghz_sales": 20.0,
        "cpu_used_pct": 25.0,
        "mem_cap_gb": 256.0,
        "mem_alloc_gb_vm": 64.0,
        "mem_used_pct": 25.0,
        "mem_cap_gb_at_peak": 256.0,
        "mem_used_gb_peak": 64.0,
        "stor_cap_gb": 0.0,
        "stor_provisioned_gb": 0.0,
        "stor_used_pct": 0.0,
        "cluster": "KM-1",
    }]
    svc = SellableService.__new__(SellableService)
    svc.list_ratios = MagicMock(return_value=[  # type: ignore[method-assign]
        ResourceRatio(
            family="backup_veeam_replication_classic",
            cpu_per_unit=1.0,
            ram_gb_per_unit=4.0,
            storage_gb_per_unit=50.0,
        ),
    ])
    svc._build_unit_lookup = MagicMock(return_value={  # type: ignore[method-assign]
        ("GHz", "vCPU"): UnitConversion("GHz", "vCPU", 8.0, "divide", True),
        ("GB", "GB"): UnitConversion("GB", "GB", 1.0),
    })
    svc._build_coupling_lookup = MagicMock(return_value={})  # type: ignore[method-assign]
    svc.resolve_storage_coupling = MagicMock(return_value="auto")  # type: ignore[method-assign]
    svc.build_host_coupling_resolver = MagicMock(return_value=None)  # type: ignore[method-assign]
    svc._get_sellable_calc_config = MagicMock(return_value={  # type: ignore[method-assign]
        "effective_ghz_per_unit": 1.0,
        "physical_price_unit": "GHz",
        "power_core_to_ghz": 3.3,
    })
    svc._fetch_host_rows_multi = MagicMock(  # type: ignore[method-assign]
        return_value=(host_rows, "ok", []),
    )
    svc._apply_replication_alternate_ranges = lambda group: group  # type: ignore[method-assign]
    svc._refresh_group_sellable_from_totals = lambda group, **kw: group  # type: ignore[method-assign]

    out = svc.recompute_family_constraints(
        [cpu, ram, sto],
        dc_code="*",
        infra_dc_codes=["DC13", "DC14"],
    )
    svc._fetch_host_rows_multi.assert_called_once()
    cpu_out = next(p for p in out if p.resource_kind == "cpu")
    ram_out = next(p for p in out if p.resource_kind == "ram")
    assert cpu_out.has_infra_source is True
    assert ram_out.has_infra_source is True
    assert cpu_out.total > 0
