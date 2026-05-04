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
import os
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
    assert _RESOURCE_KIND_TO_COMPUTE_FIELDS["cpu"]     == ("cpu_cap",  "cpu_used",  "GHz")
    assert _RESOURCE_KIND_TO_COMPUTE_FIELDS["ram"]     == ("mem_cap",  "mem_used",  "GB")
    assert _RESOURCE_KIND_TO_COMPUTE_FIELDS["storage"] == ("stor_cap", "stor_used", "TB")


def test_fetch_compute_metrics_returns_cap_used_from_compute_endpoint():
    """clusters provided + valid family → HTTP fetch from /compute/{kind}."""
    svc = _make_svc_with_redis(dc_redis=None, dc_api_url="http://dc-api:8000")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "cpu_cap": 5317.39, "cpu_used": 3869.44,
        "mem_cap": 1024.0,  "mem_used": 512.0,
        "stor_cap": 200.0,  "stor_used": 80.0,
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

    call_count = {"n": 0}
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "cpu_cap": 100.0, "cpu_used": 50.0,
        "mem_cap": 200.0, "mem_used": 75.0,
        "stor_cap": 5.0,  "stor_used": 1.0,
    }

    def counting_get(url, *a, **kw):
        call_count["n"] += 1
        return mock_resp

    monkeypatch.setattr("app.services.sellable_service.httpx.get", counting_get)
    out = svc.compute_all_panels(dc_code="IST1", selected_clusters=["KM-1", "KM-2"])

    # 3 panels × 1 family / 1 cluster set → ONE HTTP call to /compute/classic
    assert call_count["n"] == 1
    assert {p.panel_key for p in out} == {p.panel_key for p in panels}


def test_result_cache_hit_skips_computation():
    """When a cached payload exists, compute_all_panels must not touch DB at all."""
    crm_redis = MagicMock()
    cached_payload = json.dumps([
        {
            "panel_key": "virt_classic_cpu", "label": "C CPU",
            "family": "virt_classic", "resource_kind": "cpu", "display_unit": "vCPU",
            "dc_code": "IST1", "total": 100.0, "allocated": 30.0,
            "threshold_pct": 80.0, "sellable_raw": 50.0, "sellable_constrained": 50.0,
            "unit_price_tl": 0.0, "potential_tl": 0.0,
            "ratio_bound": False, "has_infra_source": True, "has_price": False, "notes": [],
        },
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
    assert isinstance(decoded, list) and len(decoded) == 3


def test_invalidate_result_cache_uses_scan_iter():
    crm_redis = MagicMock()
    crm_redis.scan_iter.return_value = iter(["sellable:panels:*:virt_classic:", "sellable:panels:IST1:*:"])
    crm_redis.delete.return_value = 1

    svc = SellableService.__new__(SellableService)
    svc._crm_redis = crm_redis
    deleted = svc.invalidate_result_cache()
    assert deleted == 2
    crm_redis.scan_iter.assert_called_once()


def test_snapshot_all_invalidates_cache():
    """snapshot_all() must wipe stale cache entries before re-computing."""
    svc = _build_service()
    svc._tags = MagicMock()
    svc._tags.snapshot.return_value = 0
    svc._tags.measures_from_panel = lambda p: []
    seen = {"invalidate": 0}

    def fake_invalidate(dc_code=None):
        seen["invalidate"] += 1
        return 0

    svc.invalidate_result_cache = fake_invalidate  # type: ignore[assignment]
    svc.snapshot_all()
    assert seen["invalidate"] == 1


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
