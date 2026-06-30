"""Customer View async data load and perspective toggle callbacks."""
from __future__ import annotations

from urllib.parse import parse_qs

import dash
from dash import Input, Output, State, callback

from src.components.customer_loading import LOADING_STAGE_MESSAGES
from src.pages.customer_view import (
    _customer_content,
    render_customer_page,
)
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
    Output("customer-view-page-root", "children", allow_duplicate=True),
    Output("customer-export-store", "data", allow_duplicate=True),
    Output("customer-view-perspective-store", "data", allow_duplicate=True),
    Input("url", "pathname"),
    Input("url", "search"),
    Input("app-time-range", "data"),
    State("customer-view-visible-sections", "data"),
)
def load_customer_view_data(pathname, search, time_range, visible_sections):
    if (pathname or "") != "/customer-view":
        raise dash.PreventUpdate
    params = parse_qs((search or "").lstrip("?"))
    chosen = (params.get("customer", [""])[0] or "").strip()
    if not chosen:
        raise dash.PreventUpdate
    tr = time_range or default_time_range()
    access = perspective_access(visible_sections)
    perspective = default_perspective(access)
    content = _customer_content(chosen, tr)
    page = render_customer_page(
        chosen,
        tr,
        content,
        visible_sections=visible_sections,
        perspective=perspective,
    )
    store = {
        "customer": chosen,
        "export_context": content.get("export_context") or {},
        "perspective_access": access,
    }
    return page, store, perspective


@callback(
    Output("customer-view-page-root", "children", allow_duplicate=True),
    Output("customer-view-perspective-store", "data", allow_duplicate=True),
    Input("customer-view-perspective", "value"),
    State("url", "search"),
    State("app-time-range", "data"),
    State("customer-view-visible-sections", "data"),
    prevent_initial_call=True,
)
def toggle_customer_perspective(perspective, search, time_range, visible_sections):
    params = parse_qs((search or "").lstrip("?"))
    chosen = (params.get("customer", [""])[0] or "").strip()
    if not chosen:
        raise dash.PreventUpdate
    access = perspective_access(visible_sections)
    perspective = effective_perspective(perspective, access)
    tr = time_range or default_time_range()
    content = _customer_content(chosen, tr)
    page = render_customer_page(
        chosen,
        tr,
        content,
        visible_sections=visible_sections,
        perspective=perspective,
    )
    return page, perspective
