"""Dash callbacks for HMDL Sync Health detail page and topology navigation."""

from __future__ import annotations

from dash import ALL, Input, Output, State, callback, ctx, no_update

from src.pages.settings.admin_routes import ADMIN_PREFIX
from src.services import api_client as api
from src.utils.hmdl_sync_ui import build_coverage_section, build_targets_table


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
    Output("hmdl-dc-select", "value", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Output("url", "search", allow_duplicate=True),
    Input({"type": "hmdl-env-select", "dc": ALL}, "n_clicks"),
    State({"type": "hmdl-env-select", "dc": ALL}, "id"),
    State("url", "pathname"),
    prevent_initial_call=True,
)
def hmdl_env_card_clicked(_n_clicks, ids, pathname):
    if not pathname or not str(pathname).startswith(f"{ADMIN_PREFIX}/integrations/hmdl"):
        return no_update, no_update, no_update
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict) or triggered.get("type") != "hmdl-env-select":
        return no_update, no_update, no_update
    # Ignore spurious fires from the page being rebuilt: selecting a DC re-renders
    # this page, which re-adds every env card with n_clicks=0. Without this guard the
    # callback would hijack url.search and reset the selection to the first DC (AZ11).
    if not ctx.triggered or not (ctx.triggered[0] or {}).get("value"):
        return no_update, no_update, no_update
    dc = str(triggered.get("dc") or "").upper()
    if not dc:
        return no_update, no_update, no_update
    return dc, pathname, f"?dc={dc}"


@callback(
    Output("url", "pathname", allow_duplicate=True),
    Output("url", "search", allow_duplicate=True),
    Input("hmdl-topology-flow", "clickedNode"),
    State("url", "pathname"),
    prevent_initial_call=True,
)
def hmdl_topology_sync_health_nav(clicked_node, pathname):
    if not clicked_node or not pathname:
        return no_update, no_update
    if not str(pathname).startswith(f"{ADMIN_PREFIX}/integrations/hmdl"):
        return no_update, no_update
    if str(clicked_node.get("action") or "") != "navigate":
        return no_update, no_update
    dc_code = str(clicked_node.get("dcCode") or "").strip().upper()
    if not dc_code:
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


@callback(
    Output("hmdl-coverage-content", "children"),
    Input("hmdl-coverage-dc", "value"),
    Input("hmdl-coverage-source", "value"),
)
def refresh_hmdl_coverage(dc, source):
    data = api.get_hmdl_coverage(dc or None, source=source or None)
    return build_coverage_section(data)
