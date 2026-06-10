"""Dash callbacks for HMDL Sync Health detail page and topology navigation."""

from __future__ import annotations

from dash import Input, Output, State, callback, no_update

from src.pages.settings.admin_routes import ADMIN_PREFIX
from src.services import api_client as api
from src.utils.hmdl_sync_ui import build_targets_table


@callback(
    Output("url", "pathname", allow_duplicate=True),
    Output("url", "search", allow_duplicate=True),
    Input("hmdl-dc-select", "value"),
    State("url", "pathname"),
    prevent_initial_call=True,
)
def hmdl_dc_changed(dc_code, pathname):
    if not pathname or not str(pathname).startswith(f"{ADMIN_PREFIX}/integrations/hmdl"):
        return no_update, no_update
    dc = (dc_code or "DC13").upper()
    return pathname, f"?dc={dc}"


@callback(
    Output("url", "pathname", allow_duplicate=True),
    Output("url", "search", allow_duplicate=True),
    Input("hmdl-topology-flow", "clickedNode"),
    State("url", "pathname"),
    prevent_initial_call=True,
)
def hmdl_topology_node_clicked(clicked_node, pathname):
    if not clicked_node or not pathname:
        return no_update, no_update
    if not str(pathname).startswith(f"{ADMIN_PREFIX}/integrations/hmdl"):
        return no_update, no_update
    node_type = str(clicked_node.get("nodeType") or "")
    dc_code = str(clicked_node.get("dcCode") or "").strip().upper()
    if node_type != "dc" or not dc_code:
        return no_update, no_update
    return (
        f"{ADMIN_PREFIX}/integrations/hmdl/sync-health",
        f"?dc={dc_code}",
    )


@callback(
    Output("hmdl-targets-table", "children"),
    Input("hmdl-dc-select", "value"),
    Input("hmdl-category-filter", "value"),
    Input("hmdl-entity-filter", "value"),
)
def refresh_hmdl_targets(dc_code, category, entity_name):
    dc = (dc_code or "DC13").upper()
    data = api.get_hmdl_dc_targets(
        dc,
        category=category or None,
        entity_name=entity_name or None,
    )
    return build_targets_table(data.get("items") or [])
