"""Dash callbacks for HMDL Sync Health detail page and topology navigation."""

from __future__ import annotations

from dash import ALL, Input, Output, State, callback, ctx, no_update

from src.pages.settings.admin_routes import ADMIN_PREFIX
from src.services import api_client as api
from src.utils.hmdl_probe_ui import build_probe_section
from src.utils.hmdl_sync_ui import (
    build_coverage_backup_section,
    build_coverage_virtualization_section,
    build_targets_table,
)


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
    Input("hmdl-coverage-product", "value"),
)
def refresh_hmdl_coverage(dc, product):
    product = (product or "vmware").strip().lower()
    if product not in ("vmware", "nutanix", "ibm"):
        product = "vmware"
    data = api.get_hmdl_coverage(dc or None, source=product)
    return build_coverage_virtualization_section(
        data,
        product=product,
        selected_dc=(dc or "").strip().upper() or None,
    )


@callback(
    Output("hmdl-backup-content", "children"),
    Input("hmdl-backup-dc", "value"),
    Input("hmdl-backup-product", "value"),
)
def refresh_hmdl_backup_coverage(dc, product):
    product = (product or "netbackup").strip().lower()
    if product not in ("netbackup", "veeam", "zerto", "nutanix_snapshot"):
        product = "netbackup"
    data = api.get_hmdl_coverage(dc or None, source=product)
    return build_coverage_backup_section(
        data,
        product=product,
        selected_dc=(dc or "").strip().upper() or None,
    )


@callback(
    Output("hmdl-coverage-dc", "value", allow_duplicate=True),
    Input("hmdl-coverage-flow", "clickedNode"),
    prevent_initial_call=True,
)
def hmdl_coverage_flow_dc_picked(clicked_node):
    """"Bu DC'ye in" button on a DC node drills the whole panel into that location."""
    if not clicked_node or str(clicked_node.get("action") or "") != "select-dc":
        return no_update
    dc = str(clicked_node.get("dcCode") or "").strip().upper()
    return dc or no_update


@callback(
    Output("hmdl-backup-dc", "value", allow_duplicate=True),
    Input("hmdl-backup-flow", "clickedNode"),
    prevent_initial_call=True,
)
def hmdl_backup_flow_dc_picked(clicked_node):
    if not clicked_node or str(clicked_node.get("action") or "") != "select-dc":
        return no_update
    dc = str(clicked_node.get("dcCode") or "").strip().upper()
    return dc or no_update


@callback(
    Output("hmdl-coverage-dc", "value", allow_duplicate=True),
    Input({"type": "hmdl-coverage-dc-pick", "dc": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def hmdl_coverage_dc_picked(_n_clicks):
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict) or triggered.get("type") != "hmdl-coverage-dc-pick":
        return no_update
    if not ctx.triggered or not (ctx.triggered[0] or {}).get("value"):
        return no_update
    dc = str(triggered.get("dc") or "").strip().upper()
    return dc or no_update


@callback(
    Output("hmdl-probe-selected-cell", "data"),
    Input({"type": "hmdl-probe-cell", "probe": ALL, "dc": ALL}, "n_clicks"),
    State("hmdl-probe-selected-cell", "data"),
    prevent_initial_call=True,
)
def hmdl_probe_cell_clicked(_n_clicks, current):
    """Clicking a matrix cell drills the detail table; clicking it again clears it."""
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict) or triggered.get("type") != "hmdl-probe-cell":
        return no_update
    if not ctx.triggered or not (ctx.triggered[0] or {}).get("value"):
        return no_update
    picked = [str(triggered.get("probe") or ""), str(triggered.get("dc") or "")]
    return None if list(current or []) == picked else picked


@callback(
    Output("hmdl-probe-content", "children"),
    Input("hmdl-probe-dc", "value"),
    Input("hmdl-probe-selected-cell", "data"),
)
def refresh_hmdl_probe(dc, selected):
    data = api.get_hmdl_probe_health(dc or None)
    cell = tuple(selected) if isinstance(selected, (list, tuple)) and len(selected) == 2 else None
    return build_probe_section(data, selected=cell)


@callback(
    Output("url", "search", allow_duplicate=True),
    Input("hmdl-coverage-dc", "value"),
    Input("hmdl-coverage-product", "value"),
    Input("hmdl-backup-dc", "value"),
    Input("hmdl-backup-product", "value"),
    State("url", "pathname"),
    prevent_initial_call=True,
)
def hmdl_coverage_filters_changed(dc_code, product, backup_dc, backup_product, pathname):
    if not pathname or not str(pathname).startswith(f"{ADMIN_PREFIX}/integrations/hmdl/coverage"):
        return no_update
    parts: list[str] = []
    # Prefer the control that just fired for shared dc; fall back to either.
    triggered = ctx.triggered_id
    if triggered == "hmdl-backup-dc":
        dc = (backup_dc or "").strip().upper()
    elif triggered == "hmdl-coverage-dc":
        dc = (dc_code or "").strip().upper()
    else:
        dc = (dc_code or backup_dc or "").strip().upper()
    if dc:
        parts.append(f"dc={dc}")
    prod = (product or "vmware").strip().lower()
    if prod and prod != "vmware":
        parts.append(f"product={prod}")
    bp = (backup_product or "netbackup").strip().lower()
    if bp and bp != "netbackup":
        parts.append(f"bp={bp}")
    return ("?" + "&".join(parts)) if parts else ""