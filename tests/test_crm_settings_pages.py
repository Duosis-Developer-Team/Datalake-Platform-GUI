"""Layout smoke tests for the revamped CRM settings pages.

These guard against regressions when build_layout signatures change or when
DataTable row-shaping helpers stop returning the expected dict keys.
"""
from __future__ import annotations

from unittest.mock import patch

from dash import dash_table, html

from src.pages.settings.integrations import (
    crm_panels,
    crm_infra_sources,
    crm_resource_ratios,
    crm_unit_conversions,
)
from src.pages.settings import crm_service_mapping


def _find_datatable(layout) -> dash_table.DataTable | None:
    """Walk a Dash layout tree and return the first DataTable instance."""
    if isinstance(layout, dash_table.DataTable):
        return layout
    children = getattr(layout, "children", None)
    if children is None:
        return None
    if not isinstance(children, (list, tuple)):
        children = [children]
    for c in children:
        found = _find_datatable(c)
        if found is not None:
            return found
    return None


def test_panels_layout_renders_datatable_with_native_filter_sort():
    fake_panels = [
        {"panel_key": "virt_classic_cpu", "label": "Classic CPU", "family": "virt_classic",
         "resource_kind": "cpu", "display_unit": "vCPU", "sort_order": 100,
         "enabled": True, "notes": "default"},
    ]
    with patch.object(crm_panels.api, "get_panel_definitions", return_value=fake_panels):
        layout = crm_panels.build_layout()
    assert isinstance(layout, html.Div)
    table = _find_datatable(layout)
    assert table is not None
    assert table.filter_action == "native"
    assert table.sort_action == "native"
    assert table.row_selectable == "single"
    assert table.data == [
        {"panel_key": "virt_classic_cpu", "label": "Classic CPU", "family": "virt_classic",
         "resource_kind": "cpu", "display_unit": "vCPU", "sort_order": 100,
         "enabled": True, "notes": "default"}
    ]


def test_infra_sources_form_autofills_from_panel_select():
    fake_src = {
        "dc_code": "*",
        "source_table": "nutanix_cluster_metrics",
        "total_column": "total_memory_capacity",
        "total_unit": "bytes",
        "allocated_table": "nutanix_vm_metrics",
        "allocated_column": "allocated_memory",
        "allocated_unit": "bytes",
        "filter_clause": "datacenter_name ILIKE :dc_pattern",
        "notes": "default",
    }
    with patch.object(crm_infra_sources.api, "get_panel_infra_source", return_value=fake_src):
        result = crm_infra_sources._form_fields_for("virt_hyperconverged_ram")
    assert result == (
        "*",
        "nutanix_cluster_metrics",
        "total_memory_capacity",
        "bytes",
        "nutanix_vm_metrics",
        "allocated_memory",
        "bytes",
        "datacenter_name ILIKE :dc_pattern",
        "default",
    )


def test_infra_sources_layout_lists_one_row_per_panel():
    fake_panels = [
        {"panel_key": "virt_classic_cpu", "label": "Classic CPU"},
        {"panel_key": "virt_classic_ram", "label": "Classic RAM"},
    ]
    fake_src = {"dc_code": "*", "source_table": "nutanix_cluster_metrics"}
    with patch.object(crm_infra_sources.api, "get_panel_definitions", return_value=fake_panels), \
         patch.object(crm_infra_sources.api, "get_panel_infra_source", return_value=fake_src):
        layout = crm_infra_sources.build_layout()
    table = _find_datatable(layout)
    assert table is not None
    assert {r["panel_key"] for r in table.data} == {"virt_classic_cpu", "virt_classic_ram"}


def test_resource_ratios_layout_rows_normalised():
    fake_ratios = [
        {"family": "virt_hyperconverged", "dc_code": "*",
         "cpu_per_unit": 1, "ram_gb_per_unit": 8, "storage_gb_per_unit": 100,
         "notes": "default", "updated_by": "settings-ui"},
    ]
    with patch.object(crm_resource_ratios.api, "get_resource_ratios", return_value=fake_ratios):
        layout = crm_resource_ratios.build_layout()
    table = _find_datatable(layout)
    assert table is not None
    assert table.data[0]["family"] == "virt_hyperconverged"
    assert table.data[0]["ram_gb_per_unit"] == 8.0
    assert table.filter_action == "native"


def test_unit_conversions_layout_rows_have_yes_no_ceil():
    fake_conv = [
        {"from_unit": "bytes", "to_unit": "GB", "factor": 1073741824,
         "operation": "divide", "ceil_result": False, "notes": ""},
        {"from_unit": "GHz", "to_unit": "vCPU", "factor": 8,
         "operation": "divide", "ceil_result": True, "notes": ""},
    ]
    with patch.object(crm_unit_conversions.api, "get_unit_conversions", return_value=fake_conv):
        layout = crm_unit_conversions.build_layout()
    table = _find_datatable(layout)
    assert table is not None
    ceils = sorted(r["ceil_result"] for r in table.data)
    assert ceils == ["no", "yes"]


def test_service_mapping_layout_summary_strip_includes_unmatched_count():
    fake_rows = [
        {"productid": "p1", "product_name": "Active Directory", "product_number": "OO0BLT-1",
         "category_code": "other", "source": "yaml"},
        {"productid": "p2", "product_name": "Azure SQL", "product_number": "OOISX-35",
         "category_code": "", "source": "unmatched"},
    ]
    fake_pages = [{"page_key": "other", "category_label": "Other"}]
    with patch.object(crm_service_mapping.api, "get_crm_service_mappings", return_value=fake_rows), \
         patch.object(crm_service_mapping.api, "get_crm_service_mapping_pages", return_value=fake_pages):
        layout = crm_service_mapping.build_layout()
    table = _find_datatable(layout)
    assert table is not None
    assert table.page_size == 25
    assert table.filter_action == "native"
    sources = {r["source"] for r in table.data}
    assert "unmatched" in sources
