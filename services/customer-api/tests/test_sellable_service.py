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

import json
from unittest.mock import MagicMock, patch

from app.services.sellable_service import (
    SellableService,
    _VM_COLUMN_TO_REDIS_FIELD,
    _VM_TABLE_DC_SECTION,
    _VM_TABLE_GLOBAL_SECTION,
)
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


def test_lookup_conversion_case_insensitive():
    from shared.sellable.models import UnitConversion

    lu = {
        ("Hz", "vCPU"): UnitConversion("Hz", "vCPU", 8e9, "divide", True),
    }
    c = SellableService._lookup_conversion(lu, "hz", "vcpu")
    assert c is not None
    assert c.factor == 8e9


def test_sum_sql_datacenter_metrics_wraps_latest_per_dc():
    """Infra uses table datacenter_metrics — SQL must DISTINCT ON before SUM (WebUI lineage)."""
    svc = SellableService.__new__(SellableService)
    sql, params = SellableService._sum_sql(
        svc,
        column="total_cpu_ghz_capacity",
        physical_table="public.datacenter_metrics",
        where_sql=" WHERE datacenter ILIKE %s",
        params=["%x%"],
    )
    assert "DISTINCT ON (dc, datacenter)" in sql
    assert "_infra_dm.total_cpu_ghz_capacity" in sql
    assert params == ["%x%"]


def test_sum_sql_cluster_metrics_wraps_latest_per_cluster():
    svc = SellableService.__new__(SellableService)
    sql, _params = SellableService._sum_sql(
        svc,
        column="cpu_ghz_capacity",
        physical_table="cluster_metrics",
        where_sql="",
        params=[],
    )
    assert "DISTINCT ON (cluster, datacenter)" in sql
    assert "_infra_cm.cpu_ghz_capacity" in sql


def test_sum_sql_nutanix_cluster_metrics_wraps_latest_per_cluster_uuid():
    svc = SellableService.__new__(SellableService)
    sql, _params = SellableService._sum_sql(
        svc,
        column="total_cpu_capacity",
        physical_table="nutanix_cluster_metrics",
        where_sql="",
        params=[],
    )
    assert "DISTINCT ON (cluster_uuid)" in sql
    assert "_infra_ncm.total_cpu_capacity" in sql


# ---------------------------------------------------------------------------
# Redis-backed allocated fetch tests
# ---------------------------------------------------------------------------

def _make_svc_with_redis(dc_redis=None, dc_api_url="") -> SellableService:
    svc = SellableService.__new__(SellableService)
    svc._dc_redis = dc_redis
    svc._dc_api_url = dc_api_url
    return svc


def _dc_details_payload(cpu_used=32.0, mem_used=128.0, stor_used=5.0) -> dict:
    return {
        "classic": {
            "cpu_cap": 200.0, "cpu_used": cpu_used,
            "mem_cap": 512.0, "mem_used": mem_used,
            "stor_cap": 50.0, "stor_used": stor_used,
        },
        "hyperconv": {
            "cpu_cap": 100.0, "cpu_used": cpu_used,
            "mem_cap": 256.0, "mem_used": mem_used,
            "stor_cap": 20.0, "stor_used": stor_used,
        },
    }


def _global_dashboard_payload(cpu_used=64.0, mem_used=256.0, stor_used=10.0) -> dict:
    return {
        "classic_totals": {
            "cpu_cap": 400.0, "cpu_used": cpu_used,
            "mem_cap": 1024.0, "mem_used": mem_used,
            "stor_cap": 100.0, "stor_used": stor_used,
        },
        "hyperconv_totals": {
            "cpu_cap": 200.0, "cpu_used": cpu_used,
            "mem_cap": 512.0, "mem_used": mem_used,
            "stor_cap": 40.0, "stor_used": stor_used,
        },
    }


def test_vm_column_to_redis_field_covers_all_supported_columns():
    """Every allocated_column used in the seed must be mapped to a Redis field."""
    expected = {
        "number_of_cpus", "total_memory_capacity_gb", "provisioned_space_gb",
        "cpu_count", "memory_capacity", "disk_capacity",
    }
    assert expected == set(_VM_COLUMN_TO_REDIS_FIELD.keys())


def test_vm_table_section_maps_both_tables():
    assert _VM_TABLE_DC_SECTION["vm_metrics"] == "classic"
    assert _VM_TABLE_DC_SECTION["nutanix_vm_metrics"] == "hyperconv"
    assert _VM_TABLE_GLOBAL_SECTION["vm_metrics"] == "classic_totals"
    assert _VM_TABLE_GLOBAL_SECTION["nutanix_vm_metrics"] == "hyperconv_totals"


def test_fetch_allocated_from_redis_classic_cpu_hit():
    """Redis hit: vm_metrics + number_of_cpus → classic.cpu_used."""
    redis_mock = MagicMock()
    redis_mock.get.return_value = json.dumps(_dc_details_payload(cpu_used=32.0))
    svc = _make_svc_with_redis(dc_redis=redis_mock)

    src = InfraSource("virt_classic_cpu", "IST1", allocated_table="vm_metrics", allocated_column="number_of_cpus")
    val = svc._fetch_allocated_from_redis(src, "IST1")

    assert val == 32.0
    called_key = redis_mock.get.call_args[0][0]
    assert called_key.startswith("dc_details:IST1:")


def test_fetch_allocated_from_redis_hyperconv_mem_hit():
    """Redis hit: nutanix_vm_metrics + memory_capacity → hyperconv.mem_used."""
    redis_mock = MagicMock()
    redis_mock.get.return_value = json.dumps(_dc_details_payload(mem_used=128.0))
    svc = _make_svc_with_redis(dc_redis=redis_mock)

    src = InfraSource("virt_hyperconverged_ram", "DC2", allocated_table="nutanix_vm_metrics", allocated_column="memory_capacity")
    val = svc._fetch_allocated_from_redis(src, "DC2")

    assert val == 128.0


def test_fetch_allocated_from_redis_global_uses_global_dashboard_key():
    """dc_code='*' must read global_dashboard key, not dc_details."""
    redis_mock = MagicMock()
    redis_mock.get.return_value = json.dumps(_global_dashboard_payload(cpu_used=64.0))
    svc = _make_svc_with_redis(dc_redis=redis_mock)

    src = InfraSource("virt_classic_cpu", "*", allocated_table="vm_metrics", allocated_column="number_of_cpus")
    val = svc._fetch_allocated_from_redis(src, "*")

    assert val == 64.0
    called_key = redis_mock.get.call_args[0][0]
    assert called_key.startswith("global_dashboard:")


def test_fetch_allocated_from_redis_cache_miss_calls_http_fallback():
    """Redis miss → HTTP GET to datacenter-api URL."""
    redis_mock = MagicMock()
    redis_mock.get.return_value = None
    svc = _make_svc_with_redis(dc_redis=redis_mock, dc_api_url="http://dc-api:8000")

    src = InfraSource("virt_km_cpu", "IST1", allocated_table="vm_metrics", allocated_column="number_of_cpus")

    mock_resp = MagicMock()
    mock_resp.json.return_value = _dc_details_payload(cpu_used=16.0)
    mock_resp.raise_for_status = MagicMock()

    with patch("app.services.sellable_service.httpx.get", return_value=mock_resp) as mock_get:
        val = svc._fetch_allocated_from_redis(src, "IST1")

    assert val == 16.0
    call_url = mock_get.call_args[0][0]
    assert "datacenter" in call_url or "dc-api" in call_url
    assert "IST1" in call_url


def test_fetch_allocated_from_redis_no_redis_no_url_returns_zero():
    """No Redis client and no API URL → 0.0, no exception."""
    svc = _make_svc_with_redis(dc_redis=None, dc_api_url="")
    src = InfraSource("x", "DC1", allocated_table="vm_metrics", allocated_column="number_of_cpus")
    assert svc._fetch_allocated_from_redis(src, "DC1") == 0.0


def test_fetch_allocated_from_redis_unknown_column_returns_zero():
    """Unmapped column name → 0.0 without crashing."""
    redis_mock = MagicMock()
    redis_mock.get.return_value = json.dumps(_dc_details_payload())
    svc = _make_svc_with_redis(dc_redis=redis_mock)
    src = InfraSource("x", "DC1", allocated_table="vm_metrics", allocated_column="unknown_col")
    assert svc._fetch_allocated_from_redis(src, "DC1") == 0.0
