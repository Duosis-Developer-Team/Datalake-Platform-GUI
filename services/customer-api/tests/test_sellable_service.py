"""SellableService — full pipeline integration test against mocked DB layers.

Exercises the canonical scenario from ADR-0014:

    Total                 cpu=10 vCPU, ram=80 GB,  storage=1000 GB
    Allocated             cpu= 4 vCPU, ram=40 GB,  storage= 300 GB
    Threshold             80%
        -> raw cpu=4 vCPU, ram=24 GB, storage=500 GB
    Ratio (1:8:100)
        n = min(4, 3, 5) = 3
        -> constrained cpu=3 vCPU, ram=24 GB, storage=300 GB
    Unit price            cpu=1500 TL, ram=20 TL, storage=2 TL
    Potential TL          3*1500 + 24*20 + 300*2 = 4500 + 480 + 600 = 5580
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.services.sellable_service import SellableService
from shared.sellable.models import (
    InfraSource,
    PanelDefinition,
    ResourceRatio,
    UnitConversion,
)


# Three panels — one per resource_kind in the same family.
HC_PANELS = [
    PanelDefinition("virt_hyperconverged_cpu",     "HC CPU",     "virt_hyperconverged", "cpu",     "vCPU"),
    PanelDefinition("virt_hyperconverged_ram",     "HC RAM",     "virt_hyperconverged", "ram",     "GB"),
    PanelDefinition("virt_hyperconverged_storage", "HC Storage", "virt_hyperconverged", "storage", "GB"),
]

INFRA = {
    "virt_hyperconverged_cpu":     (InfraSource("virt_hyperconverged_cpu",     "*", "nutanix_cluster_metrics", "total_cpu_capacity",  "vCPU", "nutanix_vm_metrics", "cpu_count",   "vCPU"), (10.0, 4.0)),
    "virt_hyperconverged_ram":     (InfraSource("virt_hyperconverged_ram",     "*", "nutanix_cluster_metrics", "total_memory_bytes",  "GB",   "nutanix_vm_metrics", "memory_bytes","GB"),   (80.0, 40.0)),
    "virt_hyperconverged_storage": (InfraSource("virt_hyperconverged_storage", "*", "nutanix_storage_pools",   "total_capacity",      "GB",   "nutanix_vm_metrics", "disk_bytes",  "GB"),   (1000.0, 300.0)),
}
RATIO = ResourceRatio(family="virt_hyperconverged", cpu_per_unit=1.0, ram_gb_per_unit=8.0, storage_gb_per_unit=100.0)
PRICES = {
    "virt_hyperconverged_cpu":     (1500.0, True),
    "virt_hyperconverged_ram":     (20.0,   True),
    "virt_hyperconverged_storage": (2.0,    True),
}


def _build_service() -> SellableService:
    customer = MagicMock()
    webui = MagicMock()
    webui.is_available = True
    customer._pool = MagicMock()
    config = MagicMock()
    currency = MagicMock()
    tagging = MagicMock()

    svc = SellableService(
        customer_service=customer,
        webui=webui,
        config_service=config,
        currency_service=currency,
        tagging_service=tagging,
    )
    # Patch every loader so we don't touch the DB.
    svc.list_panel_defs = lambda: HC_PANELS
    svc.list_unit_conversions = lambda: [
        UnitConversion("vCPU", "vCPU", 1.0),
    ]
    svc.list_ratios = lambda: [RATIO]
    svc.get_threshold = lambda panel_key, kind, dc: 80.0
    svc.get_unit_price_tl = lambda panel_key: PRICES[panel_key]
    svc.get_infra_source = lambda panel_key, dc="*": INFRA[panel_key][0]
    svc._query_total_allocated = lambda src, dc: INFRA[src.panel_key][1]  # type: ignore[attr-defined]
    svc._compute_ytd_sales_tl = lambda: 1234.5  # type: ignore[attr-defined]
    svc._count_unmapped_products = lambda: 0  # type: ignore[attr-defined]
    return svc


def test_compute_all_panels_constrained_matches_adr_example():
    svc = _build_service()
    panels = {p.resource_kind: p for p in svc.compute_all_panels(dc_code="*")}

    assert panels["cpu"].sellable_raw         == 4.0
    assert panels["ram"].sellable_raw         == 24.0
    assert panels["storage"].sellable_raw     == 500.0

    assert panels["cpu"].sellable_constrained     == 3.0
    assert panels["ram"].sellable_constrained     == 24.0
    assert panels["storage"].sellable_constrained == 300.0

    assert panels["cpu"].ratio_bound is True
    assert panels["ram"].ratio_bound is False
    assert panels["storage"].ratio_bound is True


def test_compute_all_panels_potential_tl_matches_constrained_value():
    svc = _build_service()
    panels = {p.resource_kind: p for p in svc.compute_all_panels(dc_code="*")}
    assert panels["cpu"].potential_tl     == 4500.0
    assert panels["ram"].potential_tl     == 480.0
    assert panels["storage"].potential_tl == 600.0


def test_compute_summary_aggregates_family_total_and_loss():
    svc = _build_service()
    summary = svc.compute_summary(dc_code="*")
    # Single-family setup -> totals == family totals.
    assert summary.dc_code == "*"
    assert summary.ytd_sales_tl == 1234.5
    assert summary.unmapped_product_count == 0
    assert len(summary.families) == 1
    fam = summary.families[0]
    assert fam.family == "virt_hyperconverged"
    assert fam.total_potential_tl == 4500.0 + 480.0 + 600.0
    # raw potential vs constrained potential = ratio loss
    raw_potential = 4.0 * 1500.0 + 24.0 * 20.0 + 500.0 * 2.0  # = 7480
    expected_loss = raw_potential - fam.total_potential_tl
    assert abs(fam.constrained_loss_tl - expected_loss) < 1e-6


def test_compute_summary_drops_to_zero_when_one_resource_unsold():
    """If RAM is fully allocated, ratio constraint cuts the entire family to 0."""
    svc = _build_service()
    INFRA["virt_hyperconverged_ram"] = (
        INFRA["virt_hyperconverged_ram"][0],
        (80.0, 80.0),  # 100% allocated -> raw=0
    )
    try:
        summary = svc.compute_summary(dc_code="*")
        fam = summary.families[0]
        for p in fam.panels:
            assert p.sellable_constrained == 0.0
        assert summary.total_potential_tl == 0.0
        # Raw potential for cpu/storage still exists -> constrained loss > 0
        assert fam.constrained_loss_tl > 0
    finally:
        # Restore for any subsequent tests in the file.
        INFRA["virt_hyperconverged_ram"] = (
            INFRA["virt_hyperconverged_ram"][0],
            (80.0, 40.0),
        )
