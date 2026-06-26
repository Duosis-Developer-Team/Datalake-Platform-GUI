"""Dash layout smoke tests for ``crm_inventory_overview``."""
from __future__ import annotations

from unittest.mock import patch

from dash import html

from src.pages import crm_inventory_overview


def _fake_payload() -> dict:
    row = {
        "panel_key": "virt_hyperconverged_cpu",
        "service_label": "Hyperconverged Mimari — CPU",
        "family": "virt_hyperconverged",
        "family_label": "Hyperconverged",
        "resource_kind": "cpu",
        "display_unit": "vCPU",
        "total": 10.0,
        "crm_sold_qty": 8.0,
        "used_qty": 6.0,
        "free_qty": 4.0,
        "sellable_qty": 3.0,
        "potential_tl": 4500.0,
        "has_infra_source": True,
        "infra_binding": "bound",
        "status": "ok",
        "delta_used_vs_crm": -2.0,
    }
    crm_only = {
        **row,
        "panel_key": "backup_veeam",
        "service_label": "Veeam Cloud Connect Backup",
        "family": "backup_veeam",
        "family_label": "Veeam",
        "display_unit": "Adet",
        "total": None,
        "used_qty": None,
        "free_qty": None,
        "sellable_qty": None,
        "has_infra_source": False,
        "infra_binding": "crm_only",
        "status": "crm_only",
        "crm_sold_tl": 5000.0,
    }
    return {
        "dc_code": "*",
        "summary": {
            "infra_panel_count": 1,
            "panel_count": 2,
            "crm_only_count": 1,
            "crm_entitled_tl": 18000.0,
            "unmapped_product_count": 0,
            "unmapped_entitled_count": 0,
            "overage_panel_count": 0,
            "unsold_usage_count": 0,
            "total_potential_tl": 4980.0,
            "note": "Capacity units are heterogeneous across panels.",
        },
        "families": [{
            "family": "virt_hyperconverged",
            "family_label": "Hyperconverged",
            "label": "Hyperconverged",
            "has_infra": True,
            "panels": [row],
        }],
        "panels": [row, crm_only],
        "crm_only_panels": [crm_only],
        "unmapped_products": [],
    }


def _collect_ids(component) -> list[str]:
  """Collect Dash component ids from a layout subtree."""
  ids: list[str] = []
  if hasattr(component, "id") and component.id:
    ids.append(component.id)
  children = getattr(component, "children", None)
  if children is None:
    return ids
  if not isinstance(children, (list, tuple)):
    children = [children]
  for child in children:
    if child is not None:
      ids.extend(_collect_ids(child))
  return ids


def test_build_layout_returns_report_body():
    with patch.object(crm_inventory_overview.api, "get_crm_inventory_overview", return_value=_fake_payload()):
        layout = crm_inventory_overview.build_layout()
    assert isinstance(layout, html.Div)
    ids = _collect_ids(layout)
    assert "crm-inventory-report-body" in ids
    assert "crm-inventory-filter" in ids
    assert "crm-inventory-search" in ids
    assert "crm-inventory-view-mode" in ids


def test_build_layout_shell_has_store_and_skeleton():
    shell = crm_inventory_overview.build_layout_shell()
    assert isinstance(shell, html.Div)
    ids = _collect_ids(shell)
    assert "crm-inventory-visible-sections" in ids
    assert "crm-inventory-page-root" in ids
    assert "crm-inventory-loading-layer" in ids


def test_build_layout_content_renders_from_payload():
    layout = crm_inventory_overview.build_layout_content(_fake_payload())
    assert isinstance(layout, html.Div)
    ids = _collect_ids(layout)
    assert "crm-inventory-report-body" in ids
    assert "crm-inventory-store" in ids
    assert "crm-inventory-filter" in ids


def test_fill_callback_does_not_listen_to_time_range():
    cb = crm_inventory_overview._fill_crm_inventory_content
    input_components = {inp.component_id for inp in cb.inputs}
    assert input_components == {"url"}
