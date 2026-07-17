"""Customer View async data load and perspective toggle callbacks."""
from __future__ import annotations

from urllib.parse import parse_qs

import dash
from dash import Input, Output, State, callback, ctx
from dash.exceptions import PreventUpdate

from src.components.customer_loading import LOADING_STAGE_MESSAGES
from src.pages.customer_view import render_customer_shell, resolve_customer_active_tab
from src.pages.customer_view_perspective import (
    default_perspective,
    effective_perspective,
    perspective_access,
)
from src.utils.time_range import default_time_range


@callback(
    Output("customer-loading-status", "children"),
    Input("customer-loading-stage-interval", "n_intervals"),
    prevent_initial_call=False,
)
def rotate_customer_loading_status(n_intervals):
    if not LOADING_STAGE_MESSAGES:
        return dash.no_update
    idx = int(n_intervals or 0) % len(LOADING_STAGE_MESSAGES)
    return LOADING_STAGE_MESSAGES[idx]


@callback(
    Output("customer-view-active-tab", "data", allow_duplicate=True),
    Input("customer-main-tabs", "value"),
    prevent_initial_call=True,
)
def sync_customer_active_tab(active_tab):
    if not active_tab:
        raise PreventUpdate
    return active_tab


@callback(
    # Sole initial writer of page-root (mirrors DC View). Perspective toggle uses
    # allow_duplicate on page-root; this callback is the primary for stores + root.
    # State("customer-main-tabs") is safe because render_customer_loading_page mounts
    # that id on the skeleton (DC View parity). Removing it briefly (14c0cf3) broke
    # open browser sessions: client still posted 7 args → Inputs mismatch 500.
    Output("customer-view-page-root", "children"),
    Output("customer-export-store", "data"),
    Output("customer-view-perspective-store", "data"),
    Output("customer-view-active-tab", "data"),
    Input("url", "pathname"),
    Input("url", "search"),
    Input("app-time-range", "data"),
    State("customer-view-visible-sections", "data"),
    State("customer-export-store", "data"),
    State("customer-view-active-tab", "data"),
    State("customer-main-tabs", "value"),
    prevent_initial_call=False,
)
def load_customer_view_data(
    pathname,
    search,
    time_range,
    visible_sections,
    export_store,
    active_tab,
    tabs_value,
):
    if (pathname or "") != "/customer-view":
        raise PreventUpdate
    params = parse_qs((search or "").lstrip("?"))
    chosen = (params.get("customer", [""])[0] or "").strip()
    if not chosen:
        raise PreventUpdate
    tr = time_range or default_time_range()
    access = perspective_access(visible_sections)
    perspective = default_perspective(access)
    prev_customer = (export_store or {}).get("customer")
    active = resolve_customer_active_tab(
        triggered_id=str(ctx.triggered_id or ""),
        prev_customer=prev_customer,
        new_customer=chosen,
        tabs_value=tabs_value,
        stored_tab=active_tab,
    )
    page = render_customer_shell(
        chosen,
        tr,
        visible_sections=visible_sections,
        perspective=perspective,
        active_tab=active,
    )
    store = {"customer": chosen, "tr": tr, "perspective_access": access}
    return page, store, perspective, active


@callback(
    Output("customer-view-active-tab", "data", allow_duplicate=True),
    Input("url", "search"),
    State("customer-export-store", "data"),
    prevent_initial_call=True,
)
def reset_customer_active_tab_on_customer_change(search, export_store):
    """Reset tab to Summary when navigating to a different customer."""
    params = parse_qs((search or "").lstrip("?"))
    chosen = (params.get("customer", [""])[0] or "").strip()
    if not chosen:
        raise PreventUpdate
    prev = str((export_store or {}).get("customer") or "").strip()
    if not prev or chosen.upper() == prev.upper():
        raise PreventUpdate
    return "summary"


@callback(
    Output("customer-view-page-root", "children", allow_duplicate=True),
    Output("customer-view-perspective-store", "data", allow_duplicate=True),
    Output("customer-view-active-tab", "data", allow_duplicate=True),
    Input("customer-view-perspective", "value"),
    State("url", "search"),
    State("app-time-range", "data"),
    State("customer-view-visible-sections", "data"),
    State("customer-view-active-tab", "data"),
    State("customer-main-tabs", "value"),
    prevent_initial_call=True,
)
def toggle_customer_perspective(
    perspective,
    search,
    time_range,
    visible_sections,
    active_tab,
    tabs_value,
):
    params = parse_qs((search or "").lstrip("?"))
    chosen = (params.get("customer", [""])[0] or "").strip()
    if not chosen:
        raise PreventUpdate
    access = perspective_access(visible_sections)
    perspective = effective_perspective(perspective, access)
    tr = time_range or default_time_range()
    active = tabs_value or active_tab or "summary"
    page = render_customer_shell(
        chosen,
        tr,
        visible_sections=visible_sections,
        perspective=perspective,
        active_tab=active,
    )
    return page, perspective, active
