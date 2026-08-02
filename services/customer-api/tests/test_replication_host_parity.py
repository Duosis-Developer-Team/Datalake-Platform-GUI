"""Replication Classic/HC CPU/RAM use virt host SoT (ADR-0032 §37)."""
from __future__ import annotations

from app.services.sellable_service import (
    SellableService,
    _HOST_BASED_FAMILIES,
    _HOST_COMPUTE_ONLY_FAMILIES,
    _REPLICATION_HOST_SOURCE_FAMILY,
)  # noqa: WPS433
from shared.sellable.models import PanelResult


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
