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

import datetime
import json
import os

import pytest
from unittest.mock import MagicMock, patch

from app.services.sellable_service import (
    SellableService,
    SELLABLE_PAYLOAD_VERSION,
    _VM_COLUMN_TO_REDIS_FIELD,
    _VM_TABLE_DC_SECTION,
    _VM_TABLE_GLOBAL_SECTION,
)
from shared.sellable.models import (
    InfraSource,
    PanelDefinition,
    PanelResult,
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


def test_compute_summary_rollup_only_omits_nested_panels():
    svc = _build_service()
    summary = svc.compute_summary(dc_code="*", include_panel_details=False)
    payload = summary.to_dict(include_panel_details=False)
    assert payload.get("rollup_only") is True
    assert payload["families"]
    fam = payload["families"][0]
    assert fam.get("panels") == []
    assert fam.get("panel_summaries")


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
        assert fam.constrained_loss_tl == 0.0
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


def test_sum_sql_ibm_server_general_latest_per_server():
    svc = SellableService.__new__(SellableService)
    sql, params = SellableService._sum_sql(
        svc,
        column="server_processor_totalprocunits",
        physical_table="ibm_server_general",
        where_sql=" WHERE site_name ILIKE %s",
        params=["%dc13%"],
    )
    assert "DISTINCT ON (server_details_servername)" in sql
    assert "server_details_servername ILIKE %s" in sql
    assert "site_name" not in sql
    assert params == ["%dc13%"]


def test_sum_sql_ibm_lpar_general_latest_per_lpar():
    svc = SellableService.__new__(SellableService)
    sql, params = SellableService._sum_sql(
        svc,
        column="lpar_processor_entitledprocunits",
        physical_table="ibm_lpar_general",
        where_sql=" WHERE site_name ILIKE %s",
        params=["%ict11%"],
    )
    assert "DISTINCT ON (lparname)" in sql
    assert "lpar_details_servername ILIKE %s" in sql
    assert "site_name" not in sql
    assert params == ["%ict11%"]


def test_sum_sql_s3_pool_metrics_latest_per_pool():
    svc = SellableService.__new__(SellableService)
    sql, _params = SellableService._sum_sql(
        svc,
        column="total_capacity_bytes",
        physical_table="raw_s3icos_pool_metrics",
        where_sql=" WHERE pool_name ILIKE %s",
        params=["%DC14%"],
    )
    assert "DISTINCT ON (pool_name)" in sql
    assert "_infra_s3.total_capacity_bytes" in sql


def test_sum_sql_netbackup_latest_per_pool_id():
    svc = SellableService.__new__(SellableService)
    sql, _params = SellableService._sum_sql(
        svc,
        column="usablesizebytes",
        physical_table="raw_netbackup_disk_pools_metrics",
        where_sql="",
        params=[],
    )
    assert "DISTINCT ON (netbackup_host, name)" in sql
    assert "_infra_nb.usablesizebytes" in sql


def test_sum_sql_vm_metrics_latest_per_uuid():
    svc = SellableService.__new__(SellableService)
    sql, _params = SellableService._sum_sql(
        svc,
        column="provisioned_space_gb",
        physical_table="vm_metrics",
        where_sql=" WHERE datacenter ILIKE %s",
        params=["DC13%"],
    )
    assert "DISTINCT ON (uuid)" in sql
    assert "_infra_vm.provisioned_space_gb" in sql


def test_dc_pattern_prefix_not_substring():
    assert SellableService._dc_pattern("*") == "%"
    assert SellableService._dc_pattern("DC13") == "DC13%"
    assert SellableService._dc_pattern("DC1") == "DC1%"


def test_convert_redis_stor_provisioned_gb_stays_gb_for_tb_target():
    out = SellableService._convert_redis_field_unit(
        1024.0, "classic", "stor_provisioned_gb", "GB",
    )
    assert out == 1024.0


# ---------------------------------------------------------------------------
# Redis-backed allocated fetch tests
# ---------------------------------------------------------------------------

def _make_svc_with_redis(dc_redis=None, dc_api_url="") -> SellableService:
    svc = SellableService.__new__(SellableService)
    svc._dc_redis = dc_redis
    svc._dc_api_url = dc_api_url
    return svc


def _dc_details_payload(cpu_alloc_sales=32.0, mem_alloc_gb=128.0, stor_provisioned_gb=5.0) -> dict:
    return {
        "classic": {
            "cpu_cap": 200.0, "cpu_used": 50.0,
            "cpu_alloc_ghz_sales": cpu_alloc_sales,
            "cpu_alloc_ghz_vm": cpu_alloc_sales * 2.5,
            "mem_cap": 512.0, "mem_used": 64.0,
            "mem_alloc_gb_vm": mem_alloc_gb,
            "stor_cap": 50.0, "stor_used": 10.0,
            "stor_provisioned_gb": stor_provisioned_gb,
        },
        "hyperconv": {
            "cpu_cap": 100.0, "cpu_used": 25.0,
            "cpu_alloc_ghz_sales": cpu_alloc_sales,
            "cpu_alloc_ghz_vm": cpu_alloc_sales,
            "mem_cap": 256.0, "mem_used": 32.0,
            "mem_alloc_gb_vm": mem_alloc_gb,
            "stor_cap": 20.0, "stor_used": 5.0,
            "stor_provisioned_gb": stor_provisioned_gb,
        },
    }


def _global_dashboard_payload(cpu_alloc_sales=64.0, mem_alloc_gb=256.0, stor_provisioned_gb=10.0) -> dict:
    return {
        "classic_totals": {
            "cpu_cap": 400.0, "cpu_used": 100.0,
            "cpu_alloc_ghz_sales": cpu_alloc_sales,
            "mem_alloc_gb_vm": mem_alloc_gb,
            "stor_provisioned_gb": stor_provisioned_gb,
        },
        "hyperconv_totals": {
            "cpu_cap": 200.0, "cpu_used": 50.0,
            "cpu_alloc_ghz_sales": cpu_alloc_sales,
            "mem_alloc_gb_vm": mem_alloc_gb,
            "stor_provisioned_gb": stor_provisioned_gb,
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
    """Redis hit: vm_metrics + number_of_cpus → classic.cpu_alloc_ghz_sales."""
    redis_mock = MagicMock()
    redis_mock.get.return_value = json.dumps(_dc_details_payload(cpu_alloc_sales=32.0))
    svc = _make_svc_with_redis(dc_redis=redis_mock)

    src = InfraSource("virt_classic_cpu", "IST1", allocated_table="vm_metrics", allocated_column="number_of_cpus")
    val = svc._fetch_allocated_from_redis(src, "IST1")

    assert val == 32.0
    called_key = redis_mock.get.call_args[0][0]
    assert called_key.startswith("dc_details:IST1:")


def test_fetch_allocated_from_redis_hyperconv_mem_hit():
    """Redis hit: nutanix_vm_metrics + memory_capacity → hyperconv.mem_alloc_gb_vm."""
    redis_mock = MagicMock()
    redis_mock.get.return_value = json.dumps(_dc_details_payload(mem_alloc_gb=128.0))
    svc = _make_svc_with_redis(dc_redis=redis_mock)

    src = InfraSource("virt_hyperconverged_ram", "DC2", allocated_table="nutanix_vm_metrics", allocated_column="memory_capacity")
    val = svc._fetch_allocated_from_redis(src, "DC2")

    assert val == 128.0


def test_fetch_allocated_from_redis_global_uses_global_dashboard_key():
    """dc_code='*' must read global_dashboard key, not dc_details."""
    redis_mock = MagicMock()
    redis_mock.get.return_value = json.dumps(_global_dashboard_payload(cpu_alloc_sales=64.0))
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
    mock_resp.json.return_value = _dc_details_payload(cpu_alloc_sales=16.0)
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


# ---------------------------------------------------------------------------
# Cluster-aware path: total + allocated read from datacenter-api /compute
# ---------------------------------------------------------------------------

from app.services.sellable_service import (  # noqa: E402  (grouping for clarity)
    _FAMILY_COMPUTE_ENDPOINT,
    _RESOURCE_KIND_TO_COMPUTE_FIELDS,
)


def test_family_compute_endpoint_covers_virt_classic_and_hyperconverged():
    assert _FAMILY_COMPUTE_ENDPOINT["virt_classic"] == "classic"
    assert _FAMILY_COMPUTE_ENDPOINT["virt_hyperconverged"] == "hyperconverged"


def test_resource_kind_to_compute_fields_maps_cpu_ram_storage():
    assert _RESOURCE_KIND_TO_COMPUTE_FIELDS["cpu"]     == ("cpu_cap",  "cpu_alloc_ghz_sales",  "GHz")
    assert _RESOURCE_KIND_TO_COMPUTE_FIELDS["ram"]     == ("mem_cap",  "mem_alloc_gb_vm",  "GB")
    assert _RESOURCE_KIND_TO_COMPUTE_FIELDS["storage"] == ("stor_cap", "stor_provisioned_gb", "TB")


def test_fetch_compute_metrics_returns_cap_used_from_compute_endpoint():
    """clusters provided + valid family → HTTP fetch from /compute/{kind}."""
    svc = _make_svc_with_redis(dc_redis=None, dc_api_url="http://dc-api:8000")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "cpu_cap": 5317.39, "cpu_alloc_ghz_sales": 3869.44,
        "mem_cap": 1024.0,  "mem_alloc_gb_vm": 512.0,
        "stor_cap": 200.0,  "stor_provisioned_gb": 81920.0,
    }
    with patch("app.services.sellable_service.httpx.get", return_value=mock_resp) as mock_get:
        result = svc._fetch_compute_metrics_for_clusters(
            dc_code="IST1",
            family="virt_classic",
            resource_kind="cpu",
            clusters=["KM-1", "KM-2"],
        )

    assert result is not None
    cap, used, source_unit = result
    assert cap == 5317.39
    assert used == 3869.44
    assert source_unit == "GHz"

    url = mock_get.call_args[0][0]
    assert "/datacenters/IST1/compute/classic" in url
    assert "clusters=KM-1,KM-2" in url


def test_fetch_compute_metrics_returns_none_for_unknown_family():
    svc = _make_svc_with_redis(dc_redis=None, dc_api_url="http://dc-api:8000")
    assert svc._fetch_compute_metrics_for_clusters(
        dc_code="IST1",
        family="backup_zerto_replication",
        resource_kind="cpu",
        clusters=["A"],
    ) is None


def test_fetch_compute_metrics_returns_none_when_no_clusters():
    svc = _make_svc_with_redis(dc_redis=None, dc_api_url="http://dc-api:8000")
    assert svc._fetch_compute_metrics_for_clusters(
        dc_code="IST1",
        family="virt_classic",
        resource_kind="cpu",
        clusters=[],
    ) is None


def test_fetch_compute_metrics_returns_none_for_global_dc():
    svc = _make_svc_with_redis(dc_redis=None, dc_api_url="http://dc-api:8000")
    assert svc._fetch_compute_metrics_for_clusters(
        dc_code="*",
        family="virt_classic",
        resource_kind="cpu",
        clusters=["A"],
    ) is None


def test_fetch_compute_metrics_returns_none_when_api_url_missing():
    svc = _make_svc_with_redis(dc_redis=None, dc_api_url="")
    assert svc._fetch_compute_metrics_for_clusters(
        dc_code="IST1",
        family="virt_classic",
        resource_kind="cpu",
        clusters=["A"],
    ) is None


def test_fetch_compute_metrics_swallows_http_error():
    svc = _make_svc_with_redis(dc_redis=None, dc_api_url="http://dc-api:8000")
    with patch(
        "app.services.sellable_service.httpx.get",
        side_effect=Exception("boom"),
    ):
        result = svc._fetch_compute_metrics_for_clusters(
            dc_code="IST1",
            family="virt_classic",
            resource_kind="cpu",
            clusters=["A"],
        )
    assert result is None


def test_compute_panel_uses_dc_api_when_clusters_passed():
    """compute_panel with selected_clusters → uses /compute/{kind} for both
    total and allocated, bypassing datalake DB and Redis entirely."""
    svc = _build_service()
    panel = HC_PANELS[0]  # virt_hyperconverged_cpu

    captured: dict = {}

    def fake_compute(*, dc_code, family, resource_kind, clusters):
        captured["dc_code"] = dc_code
        captured["family"] = family
        captured["resource_kind"] = resource_kind
        captured["clusters"] = list(clusters)
        return (200.0, 50.0, "vCPU")

    svc._fetch_compute_metrics_for_clusters = fake_compute  # type: ignore[assignment]

    result = svc.compute_panel(
        panel,
        dc_code="IST1",
        selected_clusters=["HC-1", "HC-2"],
    )

    assert captured == {
        "dc_code": "IST1",
        "family": "virt_hyperconverged",
        "resource_kind": "cpu",
        "clusters": ["HC-1", "HC-2"],
    }
    # cap=200, used=50, threshold=80% → raw = 200*0.8 - 50 = 110
    assert result.total == 200.0
    assert result.allocated == 50.0
    assert result.sellable_raw == 160.0 - 50.0
    assert any("cluster-scoped" in n for n in result.notes)


def test_compute_panel_falls_back_to_db_when_no_clusters():
    """selected_clusters=None → uses the existing _query_total_allocated path."""
    svc = _build_service()
    panel = HC_PANELS[0]

    called = {"hit": False}

    def boom(**_):
        called["hit"] = True
        raise AssertionError("compute path should not be called when clusters is None")

    svc._fetch_compute_metrics_for_clusters = boom  # type: ignore[assignment]

    result = svc.compute_panel(panel, dc_code="*")
    assert called["hit"] is False
    assert result.total == 10.0
    assert result.allocated == 4.0


def test_compute_summary_passes_clusters_per_family():
    svc = _build_service()
    seen: list[dict] = []

    def fake_compute(*, dc_code, family, resource_kind, clusters):
        seen.append({"family": family, "kind": resource_kind, "clusters": list(clusters)})
        return (100.0, 20.0, "GB" if resource_kind == "ram" else "vCPU" if resource_kind == "cpu" else "GB")

    svc._fetch_compute_metrics_for_clusters = fake_compute  # type: ignore[assignment]

    summary = svc.compute_summary(dc_code="IST1", selected_clusters=["A", "B"])

    # Every panel in the (mocked) HC_PANELS family should have hit the compute path
    families_seen = {entry["family"] for entry in seen}
    assert families_seen == {"virt_hyperconverged"}
    assert all(entry["clusters"] == ["A", "B"] for entry in seen)
    assert summary.dc_code == "IST1"


# ---------------------------------------------------------------------------
# Performance: bulk-loaders, HTTP dedup, result cache, family filter
# ---------------------------------------------------------------------------

from app.services.sellable_service import (  # noqa: E402
    _DC_DETAILS_WINDOW_DAYS,
    _FAMILY_COMPUTE_ENDPOINT as _FCE,
)


def test_bulk_load_infra_sources_returns_dict_when_rows_present():
    svc = SellableService.__new__(SellableService)
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.return_value = [
        {
            "panel_key": "p1", "dc_code": "IST1", "source_table": "vm_metrics",
            "total_column": "x", "total_unit": "vCPU",
            "allocated_table": None, "allocated_column": None, "allocated_unit": None,
            "filter_clause": None, "notes": None,
        },
        {
            "panel_key": "p2", "dc_code": "*", "source_table": "cluster_metrics",
            "total_column": "y", "total_unit": "GB",
            "allocated_table": None, "allocated_column": None, "allocated_unit": None,
            "filter_clause": None, "notes": None,
        },
    ]
    svc._webui = webui

    out = svc._bulk_load_infra_sources("IST1")
    assert out is not None
    assert set(out.keys()) == {"p1", "p2"}
    assert out["p1"].source_table == "vm_metrics"
    assert webui.run_rows.call_count == 1  # exactly ONE WebUI round-trip


def test_bulk_load_thresholds_specific_overrides_wildcard():
    svc = SellableService.__new__(SellableService)
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.return_value = [
        {"panel_key": "p1", "resource_type": None, "dc_code": "*",    "sellable_limit_pct": 80},
        {"panel_key": "p1", "resource_type": None, "dc_code": "IST1", "sellable_limit_pct": 95},
        {"panel_key": None, "resource_type": "cpu","dc_code": "*",    "sellable_limit_pct": 70},
    ]
    svc._webui = webui

    out = svc._bulk_load_thresholds("IST1")
    assert out is not None
    # IST1-specific row wins over '*' for p1.
    assert out["_by_panel_key"]["p1"] == 95.0
    assert out["_by_resource_type"]["cpu"] == 70.0


def test_bulk_load_price_overrides_returns_dict():
    svc = SellableService.__new__(SellableService)
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.return_value = [
        {"panel_key": "p1", "unit_price_tl": 1500.0},
        {"panel_key": "p2", "unit_price_tl": 20.0},
    ]
    svc._webui = webui
    out = svc._bulk_load_price_overrides()
    assert out == {"p1": 1500.0, "p2": 20.0}


def test_compute_all_panels_calls_each_bulk_loader_once():
    """N panels × 3 metadata lookups should collapse to 3 SQL round-trips."""
    svc = _build_service()
    calls = {"infra": 0, "thresh": 0, "price": 0}

    def fake_infra(dc):
        calls["infra"] += 1
        return {p.panel_key: INFRA[p.panel_key][0] for p in HC_PANELS}

    def fake_thresh(dc):
        calls["thresh"] += 1
        return {"_by_panel_key": {}, "_by_resource_type": {}}

    def fake_price():
        calls["price"] += 1
        return {p.panel_key: PRICES[p.panel_key][0] for p in HC_PANELS}

    svc._bulk_load_infra_sources = fake_infra      # type: ignore[assignment]
    svc._bulk_load_thresholds    = fake_thresh     # type: ignore[assignment]
    svc._bulk_load_price_overrides = fake_price    # type: ignore[assignment]

    panels = svc.compute_all_panels(dc_code="*")
    assert len(panels) == len(HC_PANELS)
    assert calls == {"infra": 1, "thresh": 1, "price": 1}


def test_compute_all_panels_survives_none_infra_lookup():
    """When bulk infra load fails, compute_all_panels must not raise AttributeError."""
    svc = _build_service()
    svc._bulk_load_infra_sources = lambda dc: None  # type: ignore[assignment]
    panels = svc.compute_all_panels(dc_code="*")
    assert len(panels) == len(HC_PANELS)


def test_compute_all_panels_family_filter_skips_unrelated_panels():
    """compute_all_panels(family=...) must filter BEFORE per-panel work runs."""
    svc = _build_service()
    extra = PanelDefinition("backup_x_storage", "Backup X", "backup_zerto_replication", "storage", "GB")
    svc.list_panel_defs = lambda: HC_PANELS + [extra]

    seen: list[str] = []
    real_compute_panel = svc.compute_panel

    def spy_compute_panel(panel, *args, **kwargs):
        seen.append(panel.panel_key)
        return real_compute_panel(panel, *args, **kwargs)

    svc.compute_panel = spy_compute_panel  # type: ignore[assignment]

    out = svc.compute_all_panels(dc_code="*", family="virt_hyperconverged")
    assert {p.panel_key for p in out} == {p.panel_key for p in HC_PANELS}
    assert "backup_x_storage" not in seen


def test_compute_all_panels_dedups_compute_http_per_family(monkeypatch):
    """clusters set + family with 3 resource_kind panels → exactly ONE HTTP call."""
    panels = [
        PanelDefinition("virt_classic_cpu",     "C CPU",     "virt_classic", "cpu",     "vCPU"),
        PanelDefinition("virt_classic_ram",     "C RAM",     "virt_classic", "ram",     "GB"),
        PanelDefinition("virt_classic_storage", "C Storage", "virt_classic", "storage", "GB"),
    ]
    customer = MagicMock()
    customer._pool = MagicMock()
    webui = MagicMock(); webui.is_available = True
    webui.run_one.return_value = None
    svc = SellableService(
        customer_service=customer, webui=webui,
        config_service=MagicMock(), currency_service=MagicMock(), tagging_service=MagicMock(),
        datacenter_api_url="http://dc-api:8000",
    )
    svc.list_panel_defs = lambda: panels
    svc.list_unit_conversions = lambda: [
        UnitConversion("GHz", "vCPU", 8.0, "divide", True),
        UnitConversion("GB", "GB", 1.0),
        UnitConversion("TB", "GB", 1.0, "multiply"),
    ]
    svc.list_ratios = lambda: []
    svc.get_unit_price_tl = lambda panel_key: (0.0, False)
    svc._bulk_load_infra_sources = lambda dc: {}      # type: ignore[assignment]
    svc._bulk_load_thresholds    = lambda dc: {"_by_panel_key": {}, "_by_resource_type": {}}  # type: ignore[assignment]
    svc._bulk_load_price_overrides = lambda: {}       # type: ignore[assignment]
    svc._query_storage_range_inputs = lambda dc: None  # type: ignore[assignment]
    svc._fetch_host_rows = lambda dc, fam, clusters: ([  # type: ignore[assignment]
        {
            "cpu_total": 100.0,
            "cpu_alloc": 50.0,
            "ram_total": 200.0,
            "ram_alloc": 75.0,
            "cpu_util_pct": 50.0,
            "ram_util_pct": 37.5,
        },
    ], "ok", [])
    svc._fetch_compute_response = lambda *a, **kw: None  # type: ignore[assignment]

    call_count = {"compute": 0, "hosts": 0}
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "cpu_cap": 100.0, "cpu_used": 50.0,
        "mem_cap": 200.0, "mem_used": 75.0,
        "stor_cap": 5.0,  "stor_used": 1.0,
    }

    def counting_get(url, *a, **kw):
        if "/hosts" in url:
            call_count["hosts"] += 1
        else:
            call_count["compute"] += 1
        return mock_resp

    monkeypatch.setattr("app.services.sellable_service.httpx.get", counting_get)
    out = svc.compute_all_panels(dc_code="IST1", selected_clusters=["KM-1", "KM-2"])

    # 3 panels × 1 family / 1 cluster set → ONE HTTP call to /compute/classic
    # plus at most one host-rows call for the host-based constrain path.
    assert call_count["compute"] == 1
    assert call_count["hosts"] <= 1
    assert {p.panel_key for p in out} == {p.panel_key for p in panels}


def test_result_cache_hit_skips_computation():
    """When a cached payload exists, compute_all_panels must not touch DB at all."""
    crm_redis = MagicMock()
    cached_payload = SellableService._snapshot_wrap_payload([
        PanelResult(
            panel_key="virt_classic_cpu",
            label="C CPU",
            family="virt_classic",
            resource_kind="cpu",
            display_unit="vCPU",
            dc_code="IST1",
            total=100.0,
            allocated=30.0,
            threshold_pct=80.0,
            sellable_raw=50.0,
            sellable_constrained=50.0,
            has_infra_source=True,
        ),
    ])
    crm_redis.get.return_value = cached_payload

    svc = _build_service()
    svc._crm_redis = crm_redis

    blew_up = {"hit": False}

    def boom(*a, **kw):
        blew_up["hit"] = True
        raise AssertionError("compute_panel must not run on cache hit")

    svc.compute_panel = boom  # type: ignore[assignment]

    out = svc.compute_all_panels(dc_code="IST1")
    assert blew_up["hit"] is False
    assert len(out) == 1
    assert out[0].panel_key == "virt_classic_cpu"
    assert out[0].sellable_constrained == 50.0


def test_result_cache_set_writes_setex():
    """Cache miss path must SETEX with the configured TTL."""
    crm_redis = MagicMock()
    crm_redis.get.return_value = None  # miss

    svc = _build_service()
    svc._crm_redis = crm_redis

    out = svc.compute_all_panels(dc_code="*")
    assert out  # standard 3 panels
    assert crm_redis.setex.call_count == 1
    args, _kwargs = crm_redis.setex.call_args
    key, ttl, payload = args
    assert key.startswith("sellable:panels:*:")
    assert isinstance(ttl, int) and ttl > 0
    decoded = json.loads(payload)
    assert decoded.get("payload_version") == SELLABLE_PAYLOAD_VERSION
    assert isinstance(decoded.get("panels"), list) and len(decoded["panels"]) == 3


def test_invalidate_result_cache_uses_scan_iter():
    crm_redis = MagicMock()
    crm_redis.scan_iter.return_value = iter(["sellable:panels:*:virt_classic:", "sellable:panels:IST1:*:"])
    crm_redis.delete.return_value = 1

    svc = SellableService.__new__(SellableService)
    svc._crm_redis = crm_redis
    deleted = svc.invalidate_result_cache()
    assert deleted == 2
    crm_redis.scan_iter.assert_called_once()


def test_snapshot_all_does_not_invalidate_before_compute():
    """snapshot_all() must not wipe caches up front (zero-downtime publish)."""
    svc = _build_service()
    svc._tags = MagicMock()
    svc._tags.snapshot.return_value = 0
    svc._tags.measures_from_panel = lambda p: []
    svc._prewarm_dc_virt_snapshots = lambda: 0  # type: ignore[assignment]
    seen = {"invalidate": 0}

    def fake_invalidate(dc_code=None):
        seen["invalidate"] += 1
        return 0

    svc.invalidate_result_cache = fake_invalidate  # type: ignore[assignment]
    summary = MagicMock()
    summary.families = []
    summary.total_potential_tl = 0.0
    summary.constrained_loss_tl = 0.0
    summary.ytd_sales_tl = 0.0
    summary.unmapped_product_count = 0
    svc.compute_summary = lambda dc: summary  # type: ignore[assignment]
    svc.snapshot_all()
    assert seen["invalidate"] == 0


def test_snapshot_all_preserves_tier2_on_compute_summary_failure():
    """Failed global summary must not delete existing Tier-2 snapshots."""
    webui, store = _in_memory_webui()
    svc = _build_service()
    svc._webui = webui  # type: ignore[assignment]
    svc._tags = MagicMock()
    svc._prewarm_dc_virt_snapshots = lambda: 0  # type: ignore[assignment]
    svc.compute_all_panels(dc_code="DC1", family="virt_hyperconverged")
    assert store

    def boom(dc_code="*"):
        raise RuntimeError("compute failed")

    svc.compute_summary = boom  # type: ignore[assignment]
    emitted = svc.snapshot_all()
    assert emitted == 0
    assert store  # Tier-2 rows still present


def test_redis_window_days_default_is_seven():
    """Window must default to 7 (matches datacenter-api default_time_range)."""
    assert _DC_DETAILS_WINDOW_DAYS in (7, 30)  # 7 in normal env; 30 only if overridden
    # Default expectation: env unset → 7
    if not os.getenv("SELLABLE_REDIS_WINDOW_DAYS"):
        assert _DC_DETAILS_WINDOW_DAYS == 7


def test_dc_redis_key_uses_window_days():
    svc = _make_svc_with_redis(dc_redis=None, dc_api_url="http://dc-api:8000")
    key, url = svc._dc_redis_key("IST1")
    assert key.startswith("dc_details:IST1:")
    # URL preset must reflect the window — never the legacy hardcoded "30d".
    assert f"preset={_DC_DETAILS_WINDOW_DAYS}d" in url


def test_dc_redis_key_aligned_with_datacenter_api_seven_day_window(monkeypatch):
    """7d inclusive window: start=today-6, end=today (UTC) — matches datacenter-api keys."""
    fixed = datetime.date(2026, 6, 4)
    monkeypatch.setattr(SellableService, "_utc_today", staticmethod(lambda: fixed))
    if os.getenv("SELLABLE_REDIS_WINDOW_DAYS"):
        pytest.skip("SELLABLE_REDIS_WINDOW_DAYS overrides default span")
    svc = _make_svc_with_redis(dc_redis=None, dc_api_url="http://dc-api:8000")
    key, _ = svc._dc_redis_key("DC13")
    assert key == "dc_details:DC13:2026-05-29:2026-06-04"


def test_dc_redis_key_alternate_includes_legacy_off_by_one(monkeypatch):
    fixed = datetime.date(2026, 6, 4)
    monkeypatch.setattr(SellableService, "_utc_today", staticmethod(lambda: fixed))
    if os.getenv("SELLABLE_REDIS_WINDOW_DAYS"):
        pytest.skip("SELLABLE_REDIS_WINDOW_DAYS overrides default span")
    svc = _make_svc_with_redis(dc_redis=None, dc_api_url="http://dc-api:8000")
    alts = svc._dc_redis_key_alternates("DC13")
    assert "dc_details:DC13:2026-05-28:2026-06-04" in alts


def test_dc_wide_compute_reads_total_from_redis_payload():
    """DC-wide path must use preloaded dc_details payload (not zero on Redis hit)."""
    customer = MagicMock()
    webui = MagicMock()
    webui.is_available = True
    svc = SellableService(
        customer_service=customer,
        webui=webui,
        config_service=MagicMock(),
        currency_service=MagicMock(),
        tagging_service=MagicMock(),
    )
    panel = PanelDefinition(
        "virt_classic_cpu", "Classic CPU", "virt_classic", "cpu", "vCPU",
    )
    infra = InfraSource(
        "virt_classic_cpu",
        "DC13",
        source_table="cluster_metrics",
        total_column="cpu_ghz_capacity",
        total_unit="GHz",
        allocated_table="vm_metrics",
        allocated_column="number_of_cpus",
        allocated_unit="GHz",
    )
    payload = {
        "classic": {"cpu_cap": 500.0, "cpu_used": 200.0, "mem_cap": 1000.0, "mem_used": 400.0},
    }
    svc.list_panel_defs = lambda: [panel]  # type: ignore[method-assign]
    svc.list_unit_conversions = lambda: [  # type: ignore[method-assign]
        UnitConversion("GHz", "vCPU", 8.0, "divide", True),
    ]
    svc.list_ratios = lambda: [ResourceRatio(family="virt_classic", cpu_per_unit=1.0, ram_gb_per_unit=8.0, storage_gb_per_unit=100.0)]  # type: ignore[method-assign]
    svc.get_threshold = lambda *a, **kw: 80.0  # type: ignore[method-assign]
    svc.get_unit_price_tl = lambda pk: (100.0, True)  # type: ignore[method-assign]
    svc._bulk_load_infra_sources = lambda dc: {"virt_classic_cpu": infra}  # type: ignore[method-assign]
    svc._bulk_load_thresholds = lambda dc: None  # type: ignore[method-assign]
    svc._bulk_load_price_overrides = lambda: {}  # type: ignore[method-assign]
    svc._load_dc_redis_payload = lambda dc: payload  # type: ignore[method-assign]
    customer._get_connection = MagicMock()
    results = svc.compute_all_panels(dc_code="DC13", family="virt_classic")
    assert results
    assert results[0].total == 63.0  # 500 GHz -> vCPU (ceil 500/8)
    customer._get_connection.assert_not_called()


def test_load_dc_redis_payload_called_once_per_request():
    """compute_all_panels must fetch the DC Redis payload at most once."""
    panels = [
        PanelDefinition("virt_km_cpu", "KM CPU", "virt_km", "cpu", "vCPU"),
        PanelDefinition("virt_km_ram", "KM RAM", "virt_km", "ram", "GB"),
    ]
    customer = MagicMock(); customer._pool = MagicMock()
    webui = MagicMock(); webui.is_available = True
    svc = SellableService(
        customer_service=customer, webui=webui,
        config_service=MagicMock(), currency_service=MagicMock(), tagging_service=MagicMock(),
    )
    infra = {
        "virt_km_cpu": InfraSource("virt_km_cpu", "*", "datacenter_metrics", "cpu_ghz", "GHz",
                                   "vm_metrics", "number_of_cpus", "GHz"),
        "virt_km_ram": InfraSource("virt_km_ram", "*", "datacenter_metrics", "mem_gb", "GB",
                                   "vm_metrics", "total_memory_capacity_gb", "GB"),
    }
    svc.list_panel_defs = lambda: panels
    svc.list_unit_conversions = lambda: []
    svc.list_ratios = lambda: []
    svc.get_unit_price_tl = lambda panel_key: (0.0, False)
    svc._bulk_load_infra_sources = lambda dc: infra      # type: ignore[assignment]
    svc._bulk_load_thresholds    = lambda dc: None       # type: ignore[assignment]
    svc._bulk_load_price_overrides = lambda: {}          # type: ignore[assignment]
    svc._query_total_allocated = lambda src, dc, **kw: (10.0, 5.0)  # type: ignore[assignment]
    svc.get_threshold = lambda *a, **kw: 80.0  # used when threshold lookup is None

    seen = {"n": 0}

    def fake_load(dc):
        seen["n"] += 1
        return {"classic": {"cpu_used": 5.0, "mem_used": 10.0}}

    svc._load_dc_redis_payload = fake_load  # type: ignore[assignment]
    svc.compute_all_panels(dc_code="IST1")
    assert seen["n"] == 1  # ONE Redis GET regardless of panel count


def _in_memory_webui():
    """Minimal webui mock that persists panel result snapshots in memory."""
    store: dict[tuple[str, str, str], list] = {}

    class _Webui:
        is_available = True

        def run_one(self, sql, params):
            from app.db.queries import sellable as sq

            if sql.strip().startswith("SELECT payload"):
                key = (params[0], params[1], params[2])
                payload = store.get(key)
                if payload is None:
                    return None
                import json

                return {
                    "payload": SellableService._snapshot_wrap_payload(payload),
                    "computed_at": "2026-05-31T00:00:00+00:00",
                }
            if "GET_LATEST_SNAPSHOT_META" in sql or "gui_panel_result_snapshot" in sql and "computed_at DESC" in sql:
                if not store:
                    return None
                key = next(iter(store))
                return {"dc_code": key[0], "family": key[1], "clusters_csv": key[2], "computed_at": "2026-05-31T00:00:00+00:00"}
            return None

        def execute(self, sql, params):
            from app.db.queries import sellable as sq

            if "UPSERT_PANEL_RESULT_SNAPSHOT" in sql or "INSERT INTO gui_panel_result_snapshot" in sql:
                import json

                dc, fam, clusters_csv, payload_json = params
                panel_dicts = SellableService._snapshot_decode_panel_list(payload_json)
                if panel_dicts is None:
                    return 0
                from shared.sellable.models import PanelResult

                store[(dc, fam, clusters_csv)] = [
                    PanelResult(
                        panel_key=d.get("panel_key", ""),
                        label=d.get("label", ""),
                        family=d.get("family", ""),
                        resource_kind=d.get("resource_kind", "other"),
                        display_unit=d.get("display_unit", ""),
                        dc_code=d.get("dc_code", dc),
                        total=float(d.get("total", 0)),
                        allocated=float(d.get("allocated", 0)),
                        threshold_pct=float(d.get("threshold_pct", 80)),
                        sellable_raw=float(d.get("sellable_raw", 0)),
                        sellable_constrained=float(d.get("sellable_constrained", 0)),
                        unit_price_tl=float(d.get("unit_price_tl", 0)),
                        potential_tl=float(d.get("potential_tl", 0)),
                        ratio_bound=bool(d.get("ratio_bound", False)),
                        has_infra_source=bool(d.get("has_infra_source", False)),
                        has_price=bool(d.get("has_price", False)),
                        notes=list(d.get("notes") or []),
                    )
                    for d in panel_dicts
                ]
                return 1
            if "DELETE FROM gui_panel_result_snapshot" in sql:
                if params[0] is None:
                    store.clear()
                else:
                    for k in list(store):
                        if k[0] == params[0]:
                            del store[k]
                return 1
            return 0

        def run_rows(self, sql, params=None):
            return []

    return _Webui(), store


def test_tier2_db_snapshot_served_on_redis_miss():
    """Redis miss should load Tier-2 durable snapshot and skip full compute."""
    webui, _store = _in_memory_webui()
    svc = _build_service()
    svc._webui = webui  # type: ignore[assignment]
    stored = svc.compute_all_panels(dc_code="*")
    assert stored

    svc._result_cache_get = lambda key: None  # type: ignore[method-assign]
    compute_calls = {"n": 0}
    original_compute = svc.compute_panel

    def counting_compute(*args, **kwargs):
        compute_calls["n"] += 1
        return original_compute(*args, **kwargs)

    svc.compute_panel = counting_compute  # type: ignore[method-assign]
    from_db = svc.compute_all_panels(dc_code="*")
    assert len(from_db) == len(stored)
    assert compute_calls["n"] == 0


def test_force_recompute_bypasses_tier1_and_tier2_cache():
    """Scheduler refresh must read fresh inputs even when old 0 snapshots exist."""
    svc = _build_service()
    svc._query_total_allocated = lambda src, dc, **kw: INFRA[src.panel_key][1]  # type: ignore[method-assign]
    svc._bulk_load_infra_sources = lambda dc: {k: v[0] for k, v in INFRA.items()}  # type: ignore[method-assign]
    svc._bulk_load_thresholds = lambda dc: None  # type: ignore[method-assign]
    svc._bulk_load_price_overrides = lambda: {}  # type: ignore[method-assign]
    svc._result_cache_get = MagicMock(return_value=[PanelResult(  # type: ignore[method-assign]
        panel_key="stale",
        label="Stale",
        family="virt_hyperconverged",
        resource_kind="cpu",
        display_unit="vCPU",
        potential_tl=0.0,
    )])
    svc._snapshot_db_get = MagicMock(return_value=[PanelResult(  # type: ignore[method-assign]
        panel_key="stale_db",
        label="Stale DB",
        family="virt_hyperconverged",
        resource_kind="cpu",
        display_unit="vCPU",
        potential_tl=0.0,
    )])

    panels = svc.compute_all_panels(dc_code="DC1", family="virt_hyperconverged", force_recompute=True)

    assert {p.panel_key for p in panels} == {p.panel_key for p in HC_PANELS}
    svc._result_cache_get.assert_not_called()
    svc._snapshot_db_get.assert_not_called()


def test_compute_summary_passes_force_recompute_to_panel_compute():
    svc = _build_service()
    seen = {"force": None}

    def fake_compute_all_panels(*args, **kwargs):
        seen["force"] = kwargs.get("force_recompute")
        return []

    svc.compute_all_panels = fake_compute_all_panels  # type: ignore[method-assign]
    svc.compute_summary("*", force_recompute=True)
    assert seen["force"] is True


def test_prewarm_uses_force_recompute_for_each_scope():
    svc = _build_service()
    svc._fetch_datacenter_codes = lambda: ["DC1"]  # type: ignore[method-assign]
    svc._fetch_virt_cluster_lists = lambda dc: (["CL-A"], ["HC-1"])  # type: ignore[method-assign]
    seen: list[tuple[str, str, bool, list[str] | None]] = []

    def fake_compute_all_panels(
        *, dc_code="*", family=None, force_recompute=False, selected_clusters=None, **_kwargs
    ):
        seen.append((dc_code, family, force_recompute, selected_clusters))
        return []

    svc.compute_all_panels = fake_compute_all_panels  # type: ignore[method-assign]
    assert svc._prewarm_dc_virt_snapshots() == 4
    assert all(item[0] == "DC1" and item[2] is True for item in seen)
    assert {item[1] for item in seen} == {
        "virt_classic",
        "virt_hyperconverged",
        "virt_power",
        "virt_power_hana",
    }
    classic = next(item for item in seen if item[1] == "virt_classic")
    hyper = next(item for item in seen if item[1] == "virt_hyperconverged")
    assert classic[3] == ["CL-A"]
    assert hyper[3] == ["HC-1"]


def test_manual_override_bypasses_datalake():
    customer = MagicMock()
    customer._pool = MagicMock()
    svc = SellableService(
        customer_service=customer,
        webui=MagicMock(is_available=True),
        config_service=MagicMock(),
        currency_service=MagicMock(),
        tagging_service=MagicMock(),
    )
    src = InfraSource(
        "virt_hyperconverged_cpu",
        "*",
        source_table="nutanix_cluster_metrics",
        total_column="total_cpu_capacity",
        manual_total=100.0,
        manual_allocated=40.0,
    )
    total, alloc = svc._query_total_allocated(src, "*")
    assert total == 100.0
    assert alloc == 40.0


def test_snapshot_meta_returns_computed_at_after_write():
    webui, _store = _in_memory_webui()
    svc = _build_service()
    svc._webui = webui  # type: ignore[assignment]
    svc.compute_all_panels(dc_code="*", family="virt_hyperconverged")
    meta = svc.snapshot_meta(dc_code="*", family="virt_hyperconverged")
    assert meta.get("computed_at") is not None


def test_invalidate_clears_tier2_and_redis():
    webui, store = _in_memory_webui()
    svc = _build_service()
    svc._webui = webui  # type: ignore[assignment]
    svc.compute_all_panels(dc_code="DC1", family="virt_hyperconverged")
    assert store
    svc.invalidate_result_cache()
    db_cached = svc._snapshot_db_get("DC1", "virt_hyperconverged", "")
    assert db_cached is None


def test_escape_filter_clause_escapes_literal_percent_for_psycopg2():
    clause = "datacenter ILIKE :dc_pattern AND cluster ILIKE '%KM%'"
    escaped = SellableService._escape_filter_clause(clause)
    assert escaped == "datacenter ILIKE %s AND cluster ILIKE '%%KM%%'"


def test_extract_total_from_dc_details_payload():
    payload = {
        "classic": {"cpu_cap": 120.5, "cpu_used": 40.0},
        "power": {"cpu_total_procunits": 80.0, "memory_total": 1024.0},
    }
    total = SellableService._extract_total_from_payload(
        payload, "cluster_metrics", "cpu_ghz_capacity", "DC13",
    )
    assert total == 120.5
    power_cpu = SellableService._extract_total_from_payload(
        payload, "ibm_server_general", "server_processor_totalprocunits", "DC13",
    )
    assert power_cpu == 80.0


def test_extract_total_from_global_dashboard_ibm_totals():
    payload = {
        "classic_totals": {"cpu_cap": 200.0},
        "ibm_totals": {"cpu_total_procunits": 16.0, "mem_total": 4096.0},
    }
    mem = SellableService._extract_total_from_payload(
        payload, "ibm_server_general", "server_memory_totalmem", "*",
    )
    assert mem == 4096.0


def test_extract_total_from_payload_converts_redis_units_to_infra_units():
    payload = {
        "classic": {"stor_cap": 10.0},
        "hyperconv": {"cpu_cap": 8.0, "mem_cap": 16.0, "stor_cap": 2.0},
    }
    classic_storage_gb = SellableService._extract_total_from_payload(
        payload,
        "datacenter_metrics",
        "total_storage_capacity_gb",
        "DC13",
        "GB",
    )
    hyper_cpu_hz = SellableService._extract_total_from_payload(
        payload,
        "nutanix_cluster_metrics",
        "total_cpu_capacity",
        "DC13",
        "Hz",
    )
    hyper_ram_bytes = SellableService._extract_total_from_payload(
        payload,
        "nutanix_cluster_metrics",
        "total_memory_capacity",
        "DC13",
        "bytes",
    )
    hyper_storage_bytes = SellableService._extract_total_from_payload(
        payload,
        "nutanix_cluster_metrics",
        "storage_capacity",
        "DC13",
        "bytes",
    )
    assert classic_storage_gb == 10.0 * 1024.0
    assert hyper_cpu_hz == 8.0 * 1_000_000_000.0
    assert hyper_ram_bytes == 16.0 * 1_073_741_824.0
    assert hyper_storage_bytes == 2.0 * 1_099_511_627_776.0


def test_power_memory_redis_gb_converts_to_mb_infra_unit():
    payload = {
        "power": {
            "memory_total": 100.0,
            "memory_assigned": 80.0,
        },
    }
    total_mb = SellableService._extract_total_from_payload(
        payload,
        "ibm_server_general",
        "server_memory_totalmem",
        "DC13",
        "MB",
    )
    alloc_mb = SellableService._extract_allocated_from_payload(
        payload,
        InfraSource(
            "virt_power_ram",
            "DC13",
            allocated_table="ibm_lpar_general",
            allocated_column="lpar_memory_logicalmem",
            allocated_unit="MB",
        ),
        "DC13",
    )
    assert total_mb == 100.0 * 1024.0
    assert alloc_mb == 80.0 * 1024.0


def test_global_ibm_totals_mem_assigned_alias():
    payload = {
        "ibm_totals": {
            "mem_total": 512.0,
            "mem_assigned": 400.0,
        },
    }
    total_mb = SellableService._extract_total_from_payload(
        payload,
        "ibm_server_general",
        "server_memory_totalmem",
        "*",
        "MB",
    )
    src = InfraSource(
        "virt_power_ram",
        "*",
        allocated_table="ibm_lpar_general",
        allocated_column="lpar_memory_logicalmem",
        allocated_unit="MB",
    )
    alloc_mb = SellableService._extract_allocated_from_payload(payload, src, "*")
    assert total_mb == 512.0 * 1024.0
    assert alloc_mb == 400.0 * 1024.0


def test_convert_redis_field_unit_power_memory_gb_to_mb():
    """Redis power memory fields are GB; infra source expects MB."""
    assert SellableService._convert_redis_field_unit(10.0, "power", "memory_total", "MB") == 10240.0
    assert SellableService._convert_redis_field_unit(10.0, "power", "memory_assigned", "MB") == 10240.0
    assert SellableService._convert_redis_field_unit(10.0, "power", "memory_total", "GB") == 10.0


def test_query_total_allocated_redis_first_skips_datalake():
    customer = MagicMock()
    webui = MagicMock()
    webui.is_available = True
    svc = SellableService(
        customer_service=customer,
        webui=webui,
        config_service=MagicMock(),
        currency_service=MagicMock(),
        tagging_service=MagicMock(),
    )
    src = InfraSource(
        "virt_power_cpu",
        "DC13",
        source_table="ibm_server_general",
        total_column="server_processor_totalprocunits",
        total_unit="procunit",
        allocated_table="ibm_lpar_general",
        allocated_column="lpar_processor_entitledprocunits",
        allocated_unit="procunit",
    )
    payload = {
        "power": {
            "cpu_total_procunits": 50.0,
            "cpu_assigned": 30.0,
        },
    }
    customer._get_connection = MagicMock()
    total, alloc = svc._query_total_allocated(src, "DC13", preloaded_dc_payload=payload)
    assert total == 50.0
    assert alloc == 30.0
    customer._get_connection.assert_not_called()


def test_compute_all_panels_preloads_redis_for_ibm_power_infra():
    """IBM Power totals use Redis; dc_payload must be loaded once for the DC."""
    customer = MagicMock()
    webui = MagicMock()
    webui.is_available = True
    svc = SellableService(
        customer_service=customer,
        webui=webui,
        config_service=MagicMock(),
        currency_service=MagicMock(),
        tagging_service=MagicMock(),
    )
    panel = PanelDefinition(
        "virt_power_cpu", "Power CPU", "virt_power", "cpu", "Core",
    )
    infra = InfraSource(
        "virt_power_cpu",
        "DC13",
        source_table="ibm_server_general",
        total_column="server_processor_totalprocunits",
        total_unit="procunit",
        allocated_table="ibm_lpar_general",
        allocated_column="lpar_processor_entitledprocunits",
        allocated_unit="procunit",
    )
    payload = {"power": {"cpu_total_procunits": 10.0, "cpu_assigned": 5.0}}
    svc.list_panel_defs = lambda: [panel]  # type: ignore[method-assign]
    svc._bulk_load_infra_sources = lambda dc: {"virt_power_cpu": infra}  # type: ignore[method-assign]
    svc._bulk_load_thresholds = lambda dc: None  # type: ignore[method-assign]
    svc._bulk_load_price_overrides = lambda: {}  # type: ignore[method-assign]
    svc._build_unit_lookup = lambda: {}  # type: ignore[method-assign]
    load_calls: list[str] = []
    svc._load_dc_redis_payload = lambda dc: load_calls.append(dc) or payload  # type: ignore[method-assign]
    svc.compute_panel = MagicMock(return_value=PanelResult(  # type: ignore[method-assign]
        panel_key="virt_power_cpu",
        label="Power CPU",
        family="virt_power",
        resource_kind="cpu",
        display_unit="Core",
        dc_code="DC13",
        total=10.0,
        allocated=5.0,
    ))
    svc.compute_all_panels(dc_code="DC13", family="virt_power")
    assert load_calls == ["DC13"]
    assert svc.compute_panel.call_args.kwargs["dc_payload"] == payload


def test_count_unmapped_products_two_step_cross_db():
    customer = MagicMock()
    conn = MagicMock()
    cur = MagicMock()
    customer._pool = MagicMock()
    customer._get_connection.return_value.__enter__ = MagicMock(return_value=conn)
    customer._get_connection.return_value.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    customer._run_value = MagicMock(return_value=3)

    webui = MagicMock()
    webui.is_available = True
    webui.run_rows = MagicMock(return_value=[{"productid": "p1"}, {"productid": "p2"}])

    svc = SellableService(
        customer_service=customer,
        webui=webui,
        config_service=MagicMock(),
        currency_service=MagicMock(),
        tagging_service=MagicMock(),
    )
    count = svc._count_unmapped_products()
    assert count == 3
    customer._run_value.assert_called_once()
    sql_arg = customer._run_value.call_args[0][1]
    assert "discovery_crm_products" in sql_arg
    assert "gui_crm_service_mapping_seed" not in sql_arg


# ------------------------------------------------ screenshot regression (SS1–SS3)


def test_ss1_gate_blocked_cpu_ram_zero_storage_capped():
    """SS1: CPU/RAM gate-blocked; storage raw positive but capped to zero."""
    from shared.sellable.computation import apply_storage_ratio_cap, apply_utilization_gate
    from shared.sellable.models import PanelResult, ResourceRatio

    cpu_raw = apply_utilization_gate(100.0, 95.0, 90.0, 80.0)
    ram_raw = apply_utilization_gate(100.0, 92.0, 85.0, 80.0)
    sto_raw = apply_utilization_gate(1000.0, 200.0, 50.0, 85.0)
    assert cpu_raw == 0.0
    assert ram_raw == 0.0
    assert sto_raw > 0.0

    ratio = ResourceRatio(
        family="virt_classic",
        cpu_per_unit=1.0,
        ram_gb_per_unit=4.0,
        storage_gb_per_unit=100.0,
    )
    panels = [
        PanelResult(
            panel_key="c", label="CPU", family="virt_classic", resource_kind="cpu",
            display_unit="vCPU", sellable_raw=cpu_raw, sellable_constrained=cpu_raw,
        ),
        PanelResult(
            panel_key="r", label="RAM", family="virt_classic", resource_kind="ram",
            display_unit="GB", sellable_raw=ram_raw, sellable_constrained=ram_raw,
        ),
        PanelResult(
            panel_key="s", label="Storage", family="virt_classic", resource_kind="storage",
            display_unit="GB", sellable_raw=sto_raw, sellable_constrained=sto_raw,
        ),
    ]
    capped = apply_storage_ratio_cap(panels, ratio)
    sto = next(p for p in capped if p.resource_kind == "storage")
    assert sto.sellable_constrained == 0.0
    assert sto.constraint_reason == "compute_bottleneck"


def test_ss2_storage_capped_when_cpu_ram_gated():
    """SS2: storage TL is zero when compute bottleneck units are zero."""
    from shared.sellable.computation import apply_storage_ratio_cap, compute_potential_tl
    from shared.sellable.models import PanelResult, ResourceRatio

    ratio = ResourceRatio(
        family="virt_hyperconverged",
        cpu_per_unit=1.0,
        ram_gb_per_unit=8.0,
        storage_gb_per_unit=100.0,
    )
    panels = [
        PanelResult(
            panel_key="c", label="CPU", family="virt_hyperconverged", resource_kind="cpu",
            display_unit="vCPU", sellable_raw=0.0, sellable_constrained=0.0,
        ),
        PanelResult(
            panel_key="r", label="RAM", family="virt_hyperconverged", resource_kind="ram",
            display_unit="GB", sellable_raw=0.0, sellable_constrained=0.0,
        ),
        PanelResult(
            panel_key="virt_hyperconverged_storage",
            label="Storage",
            family="virt_hyperconverged",
            resource_kind="storage",
            display_unit="GB",
            sellable_raw=53209.0,
            sellable_constrained=53209.0,
            unit_price_tl=1.84,
        ),
    ]
    capped = apply_storage_ratio_cap(panels, ratio)
    sto = next(p for p in capped if p.resource_kind == "storage")
    sto.potential_tl = compute_potential_tl(sto.sellable_constrained, sto.unit_price_tl)
    assert sto.sellable_constrained == 0.0
    assert sto.potential_tl == 0.0


def test_ss3_host_based_can_sell_when_aggregate_cap_high():
    """SS3: per-host headroom can remain positive under high cluster aggregate util."""
    from shared.sellable.computation import host_effective_units
    from shared.sellable.models import ResourceRatio

    hosts = [
        {"cpu_total": 50.0, "cpu_alloc": 40.0, "ram_total": 200.0, "ram_alloc": 150.0,
         "cpu_util_pct": 88.0, "ram_util_pct": 70.0},
        {"cpu_total": 50.0, "cpu_alloc": 10.0, "ram_total": 200.0, "ram_alloc": 20.0,
         "cpu_util_pct": 30.0, "ram_util_pct": 25.0},
    ]
    ratio = ResourceRatio(family="virt_classic", cpu_per_unit=1.0, ram_gb_per_unit=8.0)
    n = host_effective_units(hosts, ratio, cpu_threshold_pct=80.0, ram_threshold_pct=80.0)
    assert n > 0.0


# ------------------------------------------------ HC / Power storage parity (ADR-0019)


POWER_PANELS = [
    PanelDefinition("virt_power_cpu", "Power CPU", "virt_power", "cpu", "Core"),
    PanelDefinition("virt_power_ram", "Power RAM", "virt_power", "ram", "GB"),
    PanelDefinition("virt_power_storage", "Power Storage", "virt_power", "storage", "GB"),
]


def _build_power_pipeline_service(*, cpu_raw: float = 10.0, ram_raw: float = 80.0) -> SellableService:
    svc = SellableService(
        customer_service=MagicMock(_pool=MagicMock()),
        webui=MagicMock(is_available=True),
        config_service=MagicMock(),
        currency_service=MagicMock(),
        tagging_service=MagicMock(),
    )
    ratio = ResourceRatio(
        family="virt_power",
        cpu_per_unit=1.0,
        ram_gb_per_unit=8.0,
        storage_gb_per_unit=50.0,
    )
    svc.list_panel_defs = lambda: POWER_PANELS  # type: ignore[method-assign]
    svc.list_ratios = lambda: [ratio]  # type: ignore[method-assign]
    svc.list_unit_conversions = lambda: [UnitConversion("GB", "GB", 1.0)]  # type: ignore[method-assign]
    svc._build_unit_lookup = lambda: {("gb", "gb"): UnitConversion("GB", "GB", 1.0)}  # type: ignore[method-assign]
    svc.get_threshold = lambda pk, kind, dc: 80.0  # type: ignore[method-assign]
    svc.get_unit_price_tl = lambda pk: 2.0  # type: ignore[method-assign]
    svc._compute_ytd_sales_tl = lambda: 0.0  # type: ignore[method-assign]
    svc._count_unmapped_products = lambda: 0  # type: ignore[method-assign]
    svc._bulk_load_infra_sources = lambda dc: {}  # type: ignore[method-assign]
    svc._bulk_load_thresholds = lambda dc: None  # type: ignore[method-assign]
    svc._bulk_load_price_overrides = lambda: {}  # type: ignore[method-assign]
    svc._get_sellable_calc_config = lambda: {}  # type: ignore[method-assign]

    def fake_compute_panel(d, **kwargs):
        base = dict(
            panel_key=d.panel_key,
            label=d.label,
            family=d.family,
            resource_kind=d.resource_kind,
            display_unit=d.display_unit,
            dc_code=kwargs.get("dc_code") or "DC13",
            threshold_pct=80.0,
            unit_price_tl=2.0,
            has_infra_source=True,
        )
        if d.resource_kind == "cpu":
            return PanelResult(
                **base,
                total=100.0,
                allocated=50.0,
                sellable_raw=cpu_raw,
                sellable_constrained=cpu_raw,
            )
        if d.resource_kind == "ram":
            return PanelResult(
                **base,
                total=1000.0,
                allocated=500.0,
                sellable_raw=ram_raw,
                sellable_constrained=ram_raw,
            )
        return PanelResult(
            **base,
            total=5000.0,
            allocated=1000.0,
            sellable_raw=5000.0,
            sellable_constrained=5000.0,
        )

    svc.compute_panel = fake_compute_panel  # type: ignore[method-assign]
    svc._query_storage_range_inputs = lambda dc: {  # type: ignore[method-assign]
        "intel_cap_gb": 1000.0,
        "intel_used_gb": 200.0,
        "ibm_ds_cap_gb": 500.0,
        "ibm_ds_used_gb": 100.0,
        "ibm_total_gb": 2000.0,
        "ibm_used_gb": 500.0,
        "ibm_physical_free_gb": 1500.0,
    }
    return svc


def test_hyperconv_storage_capped_in_pipeline():
    """Hyperconverged storage raw >> compute ratio cap after full pipeline."""
    svc = _build_service()
    svc._fetch_host_rows = lambda dc, fam, clusters: (None, "unavailable", [])  # type: ignore[method-assign]
    INFRA["virt_hyperconverged_storage"] = (
        INFRA["virt_hyperconverged_storage"][0],
        (100_000.0, 10_000.0),
    )
    try:
        panels = svc.compute_all_panels(
            dc_code="DC1",
            family="virt_hyperconverged",
            force_recompute=True,
        )
        sto = next(p for p in panels if p.resource_kind == "storage")
        cpu = next(p for p in panels if p.resource_kind == "cpu")
        cap = cpu.sellable_constrained * RATIO.storage_gb_per_unit
        assert sto.sellable_raw > cap + 1e-6
        assert sto.sellable_constrained <= cap + 1e-6
        assert sto.ratio_bound or sto.constraint_reason in ("compute_bottleneck", "ratio_bound")
    finally:
        INFRA["virt_hyperconverged_storage"] = (
            INFRA["virt_hyperconverged_storage"][0],
            (1000.0, 300.0),
        )


def test_power_storage_capped_after_ibm_range():
    """Power IBM storage max is capped by compute bottleneck after ratio coupling."""
    svc = _build_power_pipeline_service(cpu_raw=4.0, ram_raw=80.0)
    panels = svc.compute_all_panels(dc_code="DC13", family="virt_power", force_recompute=True)
    sto = next(p for p in panels if p.resource_kind == "storage")
    cpu = next(p for p in panels if p.resource_kind == "cpu")
    storage_cap = cpu.sellable_constrained * 50.0
    assert sto.sellable_max is not None
    assert sto.sellable_max <= storage_cap + 1e-6
    assert sto.sellable_max + 1e-6 < 1500.0


def test_power_storage_zero_when_compute_zero():
    """Power storage is zero when CPU/RAM compute bottleneck units are zero."""
    svc = _build_power_pipeline_service(cpu_raw=0.0, ram_raw=0.0)
    panels = svc.compute_all_panels(dc_code="DC13", family="virt_power", force_recompute=True)
    sto = next(p for p in panels if p.resource_kind == "storage")
    assert sto.sellable_constrained == 0.0
    assert sto.constraint_reason == "compute_bottleneck"
    assert sto.potential_tl == 0.0


def test_power_allocation_only_single_track():
    """Power panels use allocation-only track (no sellable_max_util dual track)."""
    svc = _build_power_pipeline_service(cpu_raw=4.0, ram_raw=80.0)
    panels = svc.compute_all_panels(dc_code="DC13", family="virt_power", force_recompute=True)
    for p in panels:
        assert p.computation_mode == "power_allocation_only"
        assert p.sellable_max_util is None
    cpu = next(p for p in panels if p.resource_kind == "cpu")
    ram = next(p for p in panels if p.resource_kind == "ram")
    assert cpu.potential_tl_min == cpu.potential_tl_max
    assert ram.potential_tl_min == ram.potential_tl_max
    assert cpu.sellable_allocation == cpu.sellable_constrained
    sto = next(p for p in panels if p.resource_kind == "storage")
    assert sto.potential_tl_min is not None
    assert sto.potential_tl_max is not None
    assert sto.potential_tl_min <= sto.potential_tl_max


def test_snapshot_stale_payload_version_is_cache_miss():
    svc = _build_service()
    legacy = json.dumps([{"panel_key": "x", "label": "X", "family": "virt_classic",
                          "resource_kind": "cpu", "display_unit": "vCPU"}])
    assert svc._snapshot_decode_panel_list(legacy) is None
    wrapped = svc._snapshot_wrap_payload([
        PanelResult(
            panel_key="virt_hyperconverged_cpu",
            label="HC CPU",
            family="virt_hyperconverged",
            resource_kind="cpu",
            display_unit="vCPU",
        ),
    ])
    decoded = svc._snapshot_decode_panel_list(wrapped)
    assert decoded is not None
    assert decoded[0]["panel_key"] == "virt_hyperconverged_cpu"


def test_dc_api_hosts_timeout_floor_for_full_dc_queries():
    """Full-DC host rows can exceed the default 20s cluster timeout (e.g. DC13 ~24s)."""
    assert SellableService._dc_api_hosts_timeout(None) >= 120.0
    assert SellableService._dc_api_hosts_timeout([]) >= 120.0
    assert SellableService._dc_api_hosts_timeout(["c1", "c2", "c3"]) >= 120.0


def test_to_display_unit_fail_closed_without_conversion():
    notes: list[str] = []
    out = SellableService._to_display_unit(
        5_684_291_000_000.0,
        "Hz",
        "vCPU",
        {},
        panel_key="virt_hyperconverged_cpu",
        side="total",
        notes=notes,
    )
    assert out == 0.0
    assert any("unit_conversion_missing" in n for n in notes)


def test_to_display_unit_applies_hz_to_vcpu():
    notes: list[str] = []
    lookup = {("Hz", "vCPU"): UnitConversion("Hz", "vCPU", 8.0e9, "divide", True)}
    out = SellableService._to_display_unit(
        8.0e9,
        "Hz",
        "vCPU",
        lookup,
        panel_key="virt_hyperconverged_cpu",
        side="total",
        notes=notes,
    )
    assert out == 1.0
    assert not notes


def test_site_filter_pattern_for_s3_panels():
    assert SellableService.site_filter_pattern("storage_s3_ankara") == "%DC14%"
    assert SellableService.site_filter_pattern("storage_s3_istanbul") == "%DC13%"
    assert SellableService.site_filter_pattern("virt_classic_cpu") is None


def test_sellable_payload_version_bumped_for_data_accuracy():
    assert SELLABLE_PAYLOAD_VERSION >= 9


def test_query_netbackup_inventory_metrics_dedup_and_available():
    svc_inner = MagicMock()
    svc_inner._run_value.side_effect = [
        5_000_000_000_000.0,
        2_000_000_000_000.0,
        300_000_000_000_000.0,
    ]
    svc_inner._run_row.return_value = (512.0, 128.0)
    conn = MagicMock()
    svc_inner._get_connection.return_value.__enter__ = MagicMock(return_value=conn)
    svc_inner._get_connection.return_value.__exit__ = MagicMock(return_value=False)

    sellable = SellableService.__new__(SellableService)
    sellable._svc = svc_inner
    metrics = sellable.get_netbackup_inventory_metrics()
    assert metrics["total_bytes"] == 5_000_000_000_000.0
    assert metrics["used_pool_bytes"] == 2_000_000_000_000.0
    assert metrics["available_bytes"] == 300_000_000_000_000.0
    assert metrics["pre_dedup_bytes"] == 512.0 * (1024.0 ** 3)
    assert metrics["used_post_dedup_bytes"] == 128.0 * (1024.0 ** 3)
    assert metrics["dedup_savings_bytes"] > 0
    assert metrics["dedup_factor"] == pytest.approx(4.0)


def test_query_netbackup_storage_totals_pool_capacity_and_pool_used():
    svc_inner = MagicMock()
    svc_inner._run_value.side_effect = [5_000_000_000_000.0, 2_000_000_000_000.0]
    conn = MagicMock()
    svc_inner._get_connection.return_value.__enter__ = MagicMock(return_value=conn)
    svc_inner._get_connection.return_value.__exit__ = MagicMock(return_value=False)

    sellable = SellableService.__new__(SellableService)
    sellable._svc = svc_inner
    src = InfraSource(
        "backup_netbackup_storage",
        "*",
        "raw_netbackup_disk_pools_metrics",
        "usablesizebytes",
        "bytes",
        "raw_netbackup_disk_pools_metrics",
        "usedcapacitybytes",
        "bytes",
    )
    total, used = sellable._query_netbackup_storage_totals(src, "*")
    assert total == 5_000_000_000_000.0
    assert used == 2_000_000_000_000.0


def test_netbackup_bytes_to_tb_magnitude_under_ceiling():
    lookup = {
        ("bytes", "TB"): UnitConversion(
            "bytes", "TB", 1099511627776.0, "divide", False,
        ),
    }
    notes: list[str] = []
    # ~50 PiB raw pool capacity — should display well under 10^5 TB after grain fix scale
    raw_bytes = 50.0 * 1099511627776.0
    out = SellableService._to_display_unit(
        raw_bytes,
        "bytes",
        "TB",
        lookup,
        panel_key="backup_netbackup_storage",
        side="total",
        notes=notes,
    )
    assert out < 100_000.0
    assert out == pytest.approx(50.0)
    assert not notes
