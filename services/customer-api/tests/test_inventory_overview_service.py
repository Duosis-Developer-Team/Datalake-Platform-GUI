"""Unit tests for InventoryOverviewService."""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from app.services.inventory_overview_service import (
    InventoryOverviewService,
    _build_merged_s3_panel,
    _family_sellable_profile,
    _inventory_panel_hidden,
    _merge_s3_site_entitled,
)
from app.utils.usage_comparison import (
    aggregate_entitled_by_panel_key,
    merge_entitled_for_inventory_panel,
    normalize_entitled_qty,
    panel_inventory_status,
    panel_inventory_status_virt,
)
from shared.sellable.computation import apply_utilization_gate, compute_potential_tl
from shared.sellable.models import PanelResult


def _recompute_panels(panels, **kwargs):
    """Simulate post-merge sellable recompute from merged total/allocated."""
    out = []
    for panel in panels:
        sellable = apply_utilization_gate(
            float(panel.total or 0.0),
            float(panel.allocated or 0.0),
            None,
            panel.threshold_pct,
        )
        price = float(panel.unit_price_tl or 1500.0)
        out.append(
            replace(
                panel,
                dc_code="*",
                sellable_raw=sellable,
                sellable_constrained=sellable,
                potential_tl=compute_potential_tl(sellable, price),
                computation_mode="aggregated",
            )
        )
    return out


def test_inventory_panel_hidden_replication_families():
    assert _inventory_panel_hidden("backup_zerto_replication_cpu", "backup_zerto_replication")
    assert _inventory_panel_hidden("backup_veeam_replication_storage", "backup_veeam_replication")
    assert not _inventory_panel_hidden("backup_netbackup_storage", "backup_netbackup")


def test_merge_s3_site_entitled_sums_buckets():
    entitled = {
        "storage_s3_ankara": {
            "entitled_qty": 8.0,
            "entitled_amount_tl": 66.0,
            "product_ids": ["a"],
            "product_names": ["S3 Ankara"],
        },
        "storage_s3_istanbul": {
            "entitled_qty": 1.0,
            "entitled_amount_tl": 871.0,
            "product_ids": ["b"],
            "product_names": ["S3 Istanbul"],
        },
    }
    merged = _merge_s3_site_entitled(entitled)
    assert merged is not None
    assert merged["panel_key"] == "storage_s3"
    assert merged["entitled_qty"] == 9.0
    assert merged["entitled_amount_tl"] == 937.0


def test_build_merged_s3_panel_uses_max_node_metrics():
    ank = _panel(
        panel_key="storage_s3_ankara",
        label="IBM ICOS S3 — Ankara",
        family="storage_s3",
        resource_kind="storage",
        display_unit="TB",
        total=2603.0,
        allocated=1828.0,
        unit_price_tl=100.0,
        has_price=True,
        threshold_pct=80.0,
    )
    ist = _panel(
        panel_key="storage_s3_istanbul",
        label="IBM ICOS S3 — Istanbul",
        family="storage_s3",
        resource_kind="storage",
        display_unit="TB",
        total=2603.0,
        allocated=1587.0,
        unit_price_tl=100.0,
        has_price=True,
        threshold_pct=80.0,
    )
    merged = _build_merged_s3_panel([ank, ist])
    assert merged is not None
    assert merged.panel_key == "storage_s3"
    assert merged.total == 2603.0
    assert merged.allocated == 1828.0
    assert merged.sellable_constrained > 0.0


def test_replication_panels_excluded_from_inventory_overview():
    sellable = MagicMock()
    sellable.is_available = True
    sellable.compute_all_panels.return_value = [
        _panel(panel_key="backup_zerto_replication_cpu", family="backup_zerto_replication"),
        _panel(panel_key="backup_veeam_replication_ram", family="backup_veeam_replication"),
        _panel(panel_key="backup_netbackup_storage", family="backup_netbackup"),
    ]
    sellable.recompute_family_constraints.side_effect = _recompute_panels
    sellable._count_unmapped_products.return_value = 0
    sellable.compute_site_scoped_panels.return_value = []

    sales = MagicMock()
    sales._run_query.return_value = [
        {
            "productid": "z1",
            "product_name": "Zerto CPU",
            "entitled_qty": 5.0,
            "entitled_amount_tl": 100.0,
            "resource_unit": "vCPU",
        },
    ]
    mapping = {
        "z1": {
            "category_code": "backup_zerto_replication_cpu",
            "category_label": "Zerto Replication — CPU",
            "resource_unit": "vCPU",
            "source": "yaml",
        },
    }

    svc = InventoryOverviewService(
        sellable=sellable,
        sales=sales,
        webui=MagicMock(is_available=True, run_rows=_webui_rows),
        config=MagicMock(get_calc_dict=lambda: {"efficiency.under_pct": 80.0, "efficiency.over_pct": 110.0}),
        crm_redis=None,
    )
    svc._load_product_mapping = MagicMock(return_value=mapping)
    payload = svc.compute_inventory_overview("*")
    keys = {p["panel_key"] for p in payload["panels"]}
    assert "backup_zerto_replication_cpu" not in keys
    assert "backup_veeam_replication_ram" not in keys
    assert "backup_netbackup_storage" in keys


def test_normalize_entitled_qty_tb_to_gb():
    assert normalize_entitled_qty(2.0, "TB", "GB") == 2048.0


def test_aggregate_entitled_by_panel_key_maps_products():
    mapping = {
        "p1": {
            "category_code": "virt_classic_cpu",
            "category_label": "Klasik Mimari — CPU",
            "resource_unit": "vCPU",
            "source": "yaml",
        },
        "p2": {
            "category_code": "virt_classic_cpu",
            "category_label": "Klasik Mimari — CPU",
            "resource_unit": "vCPU",
            "source": "yaml",
        },
        "u1": {"category_code": None, "source": "unmatched"},
    }
    raw = [
        {
            "productid": "p1",
            "product_name": "KM CPU SKU",
            "entitled_qty": 10,
            "entitled_amount_tl": 100,
            "resource_unit": "vCPU",
        },
        {
            "productid": "p2",
            "product_name": "KM CPU SKU 2",
            "entitled_qty": 5,
            "entitled_amount_tl": 50,
            "resource_unit": "vCPU",
        },
        {"productid": "u1", "entitled_qty": 99, "entitled_amount_tl": 999, "resource_unit": "Adet"},
    ]
    agg = aggregate_entitled_by_panel_key(raw, mapping)
    assert agg["virt_classic_cpu"]["entitled_qty"] == 15.0
    assert agg["virt_classic_cpu"]["entitled_amount_tl"] == 150.0
    assert "KM CPU SKU" in agg["virt_classic_cpu"]["product_names"]


def test_panel_inventory_status_cases():
    assert panel_inventory_status(crm_sold_qty=0, used_qty=5, has_infra_source=True) == "unsold_usage"
    assert panel_inventory_status(crm_sold_qty=10, used_qty=0, has_infra_source=False) == "crm_only"
    assert panel_inventory_status(crm_sold_qty=10, used_qty=15, has_infra_source=True) == "over"


def test_panel_inventory_status_virt_uses_crm_vs_total():
    assert panel_inventory_status_virt(
        crm_sold_qty=30.0, total_qty=100.0, has_infra_source=True,
    ) == "under"
    assert panel_inventory_status_virt(
        crm_sold_qty=120.0, total_qty=100.0, has_infra_source=True,
    ) == "over"


def test_family_sellable_profile_mapping():
    assert _family_sellable_profile("virt_classic") == "dual_track"
    assert _family_sellable_profile("virt_hyperconverged") == "dual_track"
    assert _family_sellable_profile("virt_power") == "allocation_only"
    assert _family_sellable_profile("backup_netbackup") == "standard"


def test_build_panel_row_includes_dual_track_fields(inventory_svc):
    sellable = inventory_svc._sellable
    sellable.compute_all_panels.return_value = [
        _panel(
            unit_price_tl=1500.0,
            sellable_allocation=18.0,
            sellable_max_util=22.0,
            potential_tl_min=27000.0,
            potential_tl_max=33000.0,
        ),
        _panel(
            panel_key="backup_veeam",
            label="Veeam Backup",
            family="backup_veeam",
            resource_kind="other",
            display_unit="Adet",
            total=0,
            allocated=0,
            sellable_constrained=0,
            potential_tl=0,
            has_infra_source=False,
            has_price=True,
            computation_mode=None,
        ),
    ]
    payload = inventory_svc.compute_inventory_overview("*")
    cpu = next(p for p in payload["panels"] if p["panel_key"] == "virt_classic_cpu")
    assert cpu["sellable_profile"] == "dual_track"
    assert cpu["inventory_hide_used"] is True
    assert cpu["used_qty"] is None
    assert cpu["used_tl"] is None
    assert cpu["free_qty"] == 70.0
    assert cpu["unit_price_tl"] == 1500.0
    assert cpu["sellable_alloc_qty"] == 18.0
    assert cpu["sellable_max_qty"] == 22.0
    assert cpu["potential_tl_alloc"] == 27000.0
    assert cpu["potential_tl_max"] == 33000.0


def _panel(**kwargs) -> PanelResult:
    defaults = dict(
        panel_key="virt_classic_cpu",
        label="Classic CPU",
        family="virt_classic",
        resource_kind="cpu",
        display_unit="vCPU",
        total=100.0,
        allocated=40.0,
        sellable_constrained=20.0,
        potential_tl=30000.0,
        has_infra_source=True,
        has_price=True,
        computation_mode="host_based",
    )
    defaults.update(kwargs)
    return PanelResult(**defaults)


def _webui_rows(sql: str):
    if "FROM   gui_panel_infra_source" in sql and "DISTINCT dc_code" in sql:
        return []
    if "NOT EXISTS" in sql and "filter_clause IS NULL" in sql:
        return []
    if "FROM   gui_panel_definition" in sql:
        return [
            {
                "panel_key": "virt_classic_cpu",
                "label": "Classic CPU",
                "family": "virt_classic",
                "resource_kind": "cpu",
                "display_unit": "vCPU",
            },
            {
                "panel_key": "backup_veeam",
                "label": "Veeam Backup",
                "family": "backup_veeam",
                "resource_kind": "other",
                "display_unit": "Adet",
            },
        ]
    if "gui_crm_service_mapping_seed" in sql:
        return [
            {
                "productid": "p-cpu",
                "category_code": "virt_classic_cpu",
                "category_label": "Klasik Mimari — CPU",
                "resource_unit": "vCPU",
                "source": "yaml",
            },
            {
                "productid": "p-bkp",
                "category_code": "backup_veeam",
                "category_label": "Veeam Cloud Connect Backup",
                "resource_unit": "Adet",
                "source": "yaml",
            },
        ]
    if "FROM   gui_crm_service_pages" in sql:
        return [
            {
                "page_key": "virt_classic_cpu",
                "category_label": "Klasik Mimari — CPU",
                "gui_tab_binding": "virtualization.classic",
                "resource_unit": "vCPU",
            },
            {
                "page_key": "backup_veeam",
                "category_label": "Veeam Cloud Connect Backup",
                "gui_tab_binding": "backup.veeam",
                "resource_unit": "Adet",
            },
        ]
    return []


@pytest.fixture
def inventory_svc():
    sellable = MagicMock()
    sellable.is_available = True
    sellable.compute_all_panels.return_value = [
        _panel(),
        _panel(
            panel_key="backup_veeam",
            label="Veeam Backup",
            family="backup_veeam",
            resource_kind="other",
            display_unit="Adet",
            total=0,
            allocated=0,
            sellable_constrained=0,
            potential_tl=0,
            has_infra_source=False,
            has_price=True,
            computation_mode=None,
        ),
    ]
    sellable._count_unmapped_products.return_value = 3
    sellable.recompute_family_constraints.side_effect = _recompute_panels
    sellable._fetch_datacenter_codes.return_value = []
    sellable.compute_site_scoped_panels.return_value = []

    sales = MagicMock()
    def _run_query(sql, params):
        if "!= ALL" in sql:
            return [{"productid": "x", "product_name": "Unknown SKU", "entitled_qty": 1, "entitled_amount_tl": 100}]
        return [
            {
                "productid": "p-cpu",
                "product_name": "KM CPU",
                "resource_unit": "vCPU",
                "entitled_qty": 30.0,
                "entitled_amount_tl": 45000.0,
            },
            {
                "productid": "p-bkp",
                "product_name": "Veeam SKU",
                "resource_unit": "Adet",
                "entitled_qty": 12.0,
                "entitled_amount_tl": 12000.0,
            },
        ]

    sales._run_query.side_effect = _run_query

    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.side_effect = lambda sql: _webui_rows(sql)

    config = MagicMock()
    config.get_calc_dict.return_value = {
        "efficiency.under_pct": 80.0,
        "efficiency.over_pct": 110.0,
    }

    return InventoryOverviewService(
        sellable=sellable,
        sales=sales,
        webui=webui,
        config=config,
        crm_redis=None,
    )


def test_compute_inventory_overview_merges_panels(inventory_svc):
    payload = inventory_svc.compute_inventory_overview("*")
    assert payload["summary"]["infra_panel_count"] == 1
    assert payload["summary"]["crm_only_count"] == 1
    panels = {p["panel_key"]: p for p in payload["panels"]}
    cpu = panels["virt_classic_cpu"]
    assert cpu["crm_sold_qty"] == 30.0
    assert cpu["used_qty"] is None
    assert cpu["sellable_qty"] == 20.0
    assert cpu["free_qty"] == 70.0
    assert cpu["service_label"] == "Klasik Mimari — CPU"
    assert cpu["family_label"] == "Klasik Mimari"
    assert cpu["infra_binding"] == "bound"
    bkp = panels["backup_veeam"]
    assert bkp["status"] == "crm_only"
    assert bkp["service_label"] == "Veeam Cloud Connect Backup"
    assert bkp["infra_binding"] == "crm_only"


def test_global_inventory_aggregates_per_dc_infra():
    """dc_code='*' should sum total/used per DC then recompute sellable."""
    sellable = MagicMock()
    sellable.is_available = True

    def _compute(dc_code="*", **kwargs):
        if dc_code == "ANK":
            return [
                _panel(
                    total=100.0,
                    allocated=40.0,
                    sellable_constrained=20.0,
                    potential_tl=30000.0,
                    unit_price_tl=1500.0,
                ),
            ]
        if dc_code == "IST":
            return [
                _panel(
                    total=50.0,
                    allocated=20.0,
                    sellable_constrained=10.0,
                    potential_tl=15000.0,
                    unit_price_tl=1500.0,
                ),
            ]
        if dc_code == "*":
            return [
                _panel(
                    total=0.0,
                    allocated=0.0,
                    sellable_constrained=0.0,
                    potential_tl=0.0,
                    has_infra_source=False,
                ),
            ]
        return []

    sellable.compute_all_panels.side_effect = _compute
    sellable.recompute_family_constraints.side_effect = _recompute_panels
    sellable._count_unmapped_products.return_value = 0

    sales = MagicMock()
    sales._run_query.side_effect = lambda sql, params: (
        [{"productid": "x", "product_name": "Unknown", "entitled_qty": 1, "entitled_amount_tl": 1}]
        if "!= ALL" in sql
        else [{
            "productid": "p-cpu",
            "product_name": "KM CPU",
            "resource_unit": "vCPU",
            "entitled_qty": 30.0,
            "entitled_amount_tl": 45000.0,
        }]
    )

    def _webui_rows_multi(sql: str):
        if "FROM   gui_panel_infra_source" in sql and "DISTINCT dc_code" in sql:
            return [{"dc_code": "ANK"}, {"dc_code": "IST"}]
        return _webui_rows(sql)

    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.side_effect = _webui_rows_multi

    config = MagicMock()
    config.get_calc_dict.return_value = {"efficiency.under_pct": 80.0, "efficiency.over_pct": 110.0}

    svc = InventoryOverviewService(
        sellable=sellable,
        sales=sales,
        webui=webui,
        config=config,
        crm_redis=None,
    )
    payload = svc.compute_inventory_overview("*")
    cpu = next(p for p in payload["panels"] if p["panel_key"] == "virt_classic_cpu")
    assert cpu["total"] == 150.0
    assert cpu["used_qty"] is None
    assert cpu["sellable_qty"] == 60.0
    assert cpu["free_qty"] == 120.0
    assert cpu["potential_tl"] == 90000.0
    assert cpu["has_infra_source"] is True
    assert cpu["computation_mode"] == "aggregated"
    assert payload["summary"]["infra_panel_count"] == 1
    assert "recomputes sellable" in payload["summary"]["note"]
    sellable.recompute_family_constraints.assert_called_once()


def test_global_only_panel_not_summed_across_dcs():
    """Global-only panels must be taken once from wildcard compute, not N× per DC."""
    sellable = MagicMock()
    sellable.is_available = True

    global_panel = _panel(
        panel_key="backup_netbackup_storage",
        label="NetBackup Storage",
        family="backup_netbackup",
        resource_kind="storage",
        display_unit="GB",
        total=5000.0,
        allocated=1000.0,
        sellable_constrained=3000.0,
        potential_tl=690000.0,
        unit_price_tl=230.0,
        computation_mode="aggregated",
    )

    def _compute(dc_code="*", **kwargs):
        if dc_code in ("ANK", "IST"):
            return [global_panel]
        if dc_code == "*":
            return [global_panel]
        return []

    sellable.compute_all_panels.side_effect = _compute
    sellable.recompute_family_constraints.side_effect = _recompute_panels
    sellable._count_unmapped_products.return_value = 0

    sales = MagicMock()
    sales._run_query.return_value = []

    def _webui_rows_multi(sql: str):
        if "FROM   gui_panel_infra_source" in sql and "DISTINCT dc_code" in sql:
            return [{"dc_code": "ANK"}, {"dc_code": "IST"}]
        if "NOT EXISTS" in sql and "filter_clause IS NULL" in sql:
            return [{"panel_key": "backup_netbackup_storage"}]
        return _webui_rows(sql)

    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.side_effect = _webui_rows_multi

    config = MagicMock()
    config.get_calc_dict.return_value = {"efficiency.under_pct": 80.0, "efficiency.over_pct": 110.0}

    svc = InventoryOverviewService(
        sellable=sellable,
        sales=sales,
        webui=webui,
        config=config,
        crm_redis=None,
    )
    payload = svc.compute_inventory_overview("*")
    nb = next(p for p in payload["panels"] if p["panel_key"] == "backup_netbackup_storage")
    assert nb["total"] == 5000.0
    assert nb["used_qty"] == 1000.0


def test_site_scoped_panels_not_summed_across_dcs():
    """S3 site panels must be computed once via compute_site_scoped_panels, not N× per DC."""
    sellable = MagicMock()
    sellable.is_available = True

    ank_site = _panel(
        panel_key="storage_s3_ankara",
        label="IBM ICOS S3 — Ankara",
        family="storage_s3",
        resource_kind="storage",
        display_unit="TB",
        total=100.0,
        allocated=40.0,
        sellable_constrained=50.0,
        potential_tl=5000.0,
        unit_price_tl=100.0,
        computation_mode="aggregated",
    )
    ist_site = _panel(
        panel_key="storage_s3_istanbul",
        label="IBM ICOS S3 — Istanbul",
        family="storage_s3",
        resource_kind="storage",
        display_unit="TB",
        total=200.0,
        allocated=80.0,
        sellable_constrained=100.0,
        potential_tl=10000.0,
        unit_price_tl=100.0,
        computation_mode="aggregated",
    )

    def _compute(dc_code="*", **kwargs):
        if dc_code in ("ANK", "IST"):
            return [
                replace(ank_site, total=1000.0, allocated=400.0),
                replace(ist_site, total=2000.0, allocated=800.0),
            ]
        return []

    sellable.compute_all_panels.side_effect = _compute
    sellable.compute_site_scoped_panels.return_value = [ank_site, ist_site]
    sellable.recompute_family_constraints.side_effect = _recompute_panels
    sellable._count_unmapped_products.return_value = 0

    sales = MagicMock()
    sales._run_query.return_value = []

    def _webui_rows_multi(sql: str):
        if "FROM   gui_panel_infra_source" in sql and "DISTINCT dc_code" in sql:
            return [{"dc_code": "ANK"}, {"dc_code": "IST"}]
        if "NOT EXISTS" in sql and "filter_clause IS NULL" in sql:
            return [{"panel_key": "backup_netbackup_storage"}]
        if "storage_s3_%" in sql:
            return [
                {"panel_key": "storage_s3_ankara"},
                {"panel_key": "storage_s3_istanbul"},
            ]
        return _webui_rows(sql)

    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.side_effect = _webui_rows_multi

    config = MagicMock()
    config.get_calc_dict.return_value = {"efficiency.under_pct": 80.0, "efficiency.over_pct": 110.0}

    svc = InventoryOverviewService(
        sellable=sellable,
        sales=sales,
        webui=webui,
        config=config,
        crm_redis=None,
    )
    payload = svc.compute_inventory_overview("*")
    s3 = next(p for p in payload["panels"] if p["panel_key"] == "storage_s3")
    assert "storage_s3_ankara" not in {p["panel_key"] for p in payload["panels"]}
    assert "storage_s3_istanbul" not in {p["panel_key"] for p in payload["panels"]}
    assert s3["total"] == 200.0
    assert s3["used_qty"] == 80.0
    assert s3["service_label"] == "IBM ICOS S3"
    sellable.compute_site_scoped_panels.assert_called_once()


def test_assess_data_quality_flags_unit_conversion_missing():
    from app.services.inventory_overview_service import _assess_data_quality

    panel = PanelResult(
        panel_key="virt_hyperconverged_cpu",
        label="CPU",
        family="virt_hyperconverged",
        resource_kind="cpu",
        display_unit="vCPU",
        total=0.0,
        allocated=0.0,
        has_infra_source=True,
        notes=["unit_conversion_missing: Hz->vCPU (total)"],
    )
    assert _assess_data_quality(panel, crm_sold=10.0) == "suspect"


def test_inventory_uses_datacenter_codes_when_infra_bindings_wildcard_only():
    """When gui_panel_infra_source has only dc_code='*', aggregate per platform DC."""
    sellable = MagicMock()
    sellable.is_available = True
    sellable._fetch_datacenter_codes.return_value = ["ANK", "IST"]
    sellable.recompute_family_constraints.side_effect = _recompute_panels
    sellable._count_unmapped_products.return_value = 0
    sellable.compute_site_scoped_panels.return_value = []

    def _compute(dc_code="*", **kwargs):
        if dc_code == "ANK":
            return [_panel(total=100.0, allocated=10.0)]
        if dc_code == "IST":
            return [_panel(total=50.0, allocated=5.0)]
        return []

    sellable.compute_all_panels.side_effect = _compute

    sales = MagicMock()
    sales._run_query.return_value = []

    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.side_effect = _webui_rows

    config = MagicMock()
    config.get_calc_dict.return_value = {"efficiency.under_pct": 80.0, "efficiency.over_pct": 110.0}

    svc = InventoryOverviewService(
        sellable=sellable,
        sales=sales,
        webui=webui,
        config=config,
        crm_redis=None,
    )
    payload = svc.compute_inventory_overview("*")
    cpu = next(p for p in payload["panels"] if p["panel_key"] == "virt_classic_cpu")
    assert cpu["total"] == 150.0
    assert cpu["used_qty"] is None
    assert cpu["free_qty"] == 150.0
    sellable._fetch_datacenter_codes.assert_called_once()


def test_merge_entitled_for_inventory_panel_classic_and_km():
    entitled = {
        "virt_classic_cpu": {
            "panel_key": "virt_classic_cpu",
            "entitled_qty": 100.0,
            "entitled_amount_tl": 1000.0,
            "product_ids": ["p1"],
            "product_names": ["Classic CPU"],
        },
        "virt_km_cpu": {
            "panel_key": "virt_km_cpu",
            "entitled_qty": 20.0,
            "entitled_amount_tl": 200.0,
            "product_ids": ["p2"],
            "product_names": ["KM CPU"],
        },
    }
    merged = merge_entitled_for_inventory_panel(
        "virt_classic_cpu",
        entitled,
        sub_panel_key="virt_km_cpu",
        sub_bucket_name="km",
    )
    assert merged is not None
    assert merged["entitled_qty"] == 120.0
    assert merged["crm_sold_qty_general"] == 100.0
    assert merged["crm_sold_qty_km"] == 20.0


def test_inventory_merged_families_skip_km_infra_and_merge_crm():
    sellable = MagicMock()
    sellable.is_available = True

    classic_cpu = _panel(
        panel_key="virt_classic_cpu",
        label="Classic CPU",
        family="virt_classic",
        total=500.0,
        allocated=100.0,
        sellable_constrained=200.0,
        computation_mode="host_based",
    )
    km_cpu = _panel(
        panel_key="virt_km_cpu",
        label="KM CPU",
        family="virt_km",
        total=80.0,
        allocated=20.0,
        sellable_constrained=40.0,
        computation_mode="aggregated",
    )

    sellable.compute_all_panels.return_value = [classic_cpu, km_cpu]
    sellable.recompute_family_constraints.side_effect = _recompute_panels
    sellable._count_unmapped_products.return_value = 0

    sales = MagicMock()
    sales._run_query.return_value = [
        {
            "productid": "p-classic",
            "product_name": "Classic CPU",
            "entitled_qty": 100,
            "entitled_amount_tl": 1000,
            "resource_unit": "vCPU",
        },
        {
            "productid": "p-km",
            "product_name": "KM CPU",
            "entitled_qty": 15,
            "entitled_amount_tl": 150,
            "resource_unit": "vCPU",
        },
    ]

    def _webui_rows_merge(sql: str):
        if "FROM   gui_panel_definition" in sql:
            return [
                {
                    "panel_key": "virt_classic_cpu",
                    "label": "Classic CPU",
                    "family": "virt_classic",
                    "resource_kind": "cpu",
                    "display_unit": "vCPU",
                },
                {
                    "panel_key": "virt_km_cpu",
                    "label": "KM CPU",
                    "family": "virt_km",
                    "resource_kind": "cpu",
                    "display_unit": "vCPU",
                },
            ]
        if "gui_crm_service_mapping_seed" in sql:
            return [
                {
                    "productid": "p-classic",
                    "category_code": "virt_classic_cpu",
                    "category_label": "Classic CPU",
                    "resource_unit": "vCPU",
                    "source": "yaml",
                },
                {
                    "productid": "p-km",
                    "category_code": "virt_km_cpu",
                    "category_label": "KM CPU",
                    "resource_unit": "vCPU",
                    "source": "yaml",
                },
            ]
        return _webui_rows(sql)

    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.side_effect = _webui_rows_merge

    config = MagicMock()
    config.get_calc_dict.return_value = {"efficiency.under_pct": 80.0, "efficiency.over_pct": 110.0}

    svc = InventoryOverviewService(
        sellable=sellable,
        sales=sales,
        webui=webui,
        config=config,
        crm_redis=None,
    )
    payload = svc.compute_inventory_overview("*")
    panel_keys = [p["panel_key"] for p in payload["panels"]]
    assert "virt_km_cpu" not in panel_keys
    cpu = next(p for p in payload["panels"] if p["panel_key"] == "virt_classic_cpu")
    assert cpu["crm_sold_qty"] == 115.0
    assert cpu["crm_sold_qty_general"] == 100.0
    assert cpu["crm_sold_qty_km"] == 15.0
    family_keys = [f["family"] for f in payload["families"]]
    assert "virt_km" not in family_keys
    assert "virt_classic" in family_keys


def test_inventory_merged_power_hana_crm_sub_bucket():
    sellable = MagicMock()
    sellable.is_available = True

    power_cpu = _panel(
        panel_key="virt_power_cpu",
        label="Power CPU",
        family="virt_power",
        resource_kind="cpu",
        display_unit="Core",
        total=200.0,
        allocated=50.0,
        sellable_constrained=80.0,
        computation_mode="aggregated",
    )
    hana_cpu = _panel(
        panel_key="virt_power_hana_cpu",
        label="Power HANA CPU",
        family="virt_power_hana",
        resource_kind="cpu",
        display_unit="Core",
        total=200.0,
        allocated=50.0,
        sellable_constrained=80.0,
        computation_mode="aggregated",
    )

    sellable.compute_all_panels.return_value = [power_cpu, hana_cpu]
    sellable.recompute_family_constraints.side_effect = _recompute_panels
    sellable._count_unmapped_products.return_value = 0

    sales = MagicMock()
    sales._run_query.return_value = [
        {
            "productid": "p-power",
            "product_name": "Power CPU",
            "entitled_qty": 40,
            "entitled_amount_tl": 400,
            "resource_unit": "Core",
        },
        {
            "productid": "p-hana",
            "product_name": "HANA CPU",
            "entitled_qty": 10,
            "entitled_amount_tl": 100,
            "resource_unit": "Core",
        },
    ]

    def _webui_rows_power(sql: str):
        if "FROM   gui_panel_definition" in sql:
            return [
                {
                    "panel_key": "virt_power_cpu",
                    "label": "Power CPU",
                    "family": "virt_power",
                    "resource_kind": "cpu",
                    "display_unit": "Core",
                },
                {
                    "panel_key": "virt_power_hana_cpu",
                    "label": "Power HANA CPU",
                    "family": "virt_power_hana",
                    "resource_kind": "cpu",
                    "display_unit": "Core",
                },
            ]
        if "gui_crm_service_mapping_seed" in sql:
            return [
                {
                    "productid": "p-power",
                    "category_code": "virt_power_cpu",
                    "category_label": "Power CPU",
                    "resource_unit": "Core",
                    "source": "yaml",
                },
                {
                    "productid": "p-hana",
                    "category_code": "virt_power_hana_cpu",
                    "category_label": "Power HANA CPU",
                    "resource_unit": "Core",
                    "source": "yaml",
                },
            ]
        return _webui_rows(sql)

    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.side_effect = _webui_rows_power

    config = MagicMock()
    config.get_calc_dict.return_value = {"efficiency.under_pct": 80.0, "efficiency.over_pct": 110.0}

    svc = InventoryOverviewService(
        sellable=sellable,
        sales=sales,
        webui=webui,
        config=config,
        crm_redis=None,
    )
    payload = svc.compute_inventory_overview("*")
    assert "virt_power_hana_cpu" not in [p["panel_key"] for p in payload["panels"]]
    power = next(p for p in payload["panels"] if p["panel_key"] == "virt_power_cpu")
    assert power["crm_sold_qty"] == 50.0
    assert power["crm_sold_qty_hana"] == 10.0
    assert "virt_power_hana" not in [f["family"] for f in payload["families"]]


def test_warm_inventory_cache_force_recomputes_and_writes_redis(inventory_svc):
    redis = MagicMock()
    inventory_svc._crm_redis = redis
    inventory_svc.compute_inventory_overview = MagicMock(return_value={"dc_code": "*", "summary": {}})

    result = inventory_svc.warm_inventory_cache("*")

    inventory_svc.compute_inventory_overview.assert_called_once_with(dc_code="*", force_recompute=True)
    assert result["dc_code"] == "*"

