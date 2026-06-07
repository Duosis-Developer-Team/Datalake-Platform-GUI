"""Customer View async data load callbacks."""
from __future__ import annotations

from urllib.parse import parse_qs

import dash
from dash import Input, Output, State, callback

from src.components.customer_loading import LOADING_STAGE_MESSAGES
from src.pages.customer_view import (
    _customer_content,
    render_customer_page,
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
    Output("customer-view-page-root", "children"),
    Output("customer-export-store", "data"),
    Input("url", "pathname"),
    Input("url", "search"),
    Input("app-time-range", "data"),
    State("customer-view-visible-sections", "data"),
)
def load_customer_view_data(pathname, search, time_range, visible_sections):
    if (pathname or "") != "/customer-view":
        raise dash.exceptions.PreventUpdate
    params = parse_qs((search or "").lstrip("?"))
    chosen = (params.get("customer", [""])[0] or "").strip()
    if not chosen:
        raise dash.exceptions.PreventUpdate
    tr = time_range or default_time_range()
    vs = set(visible_sections) if visible_sections else None
    content = _customer_content(chosen, tr)
    export_sheets = content.get("export_sheets") or {}
    page = render_customer_page(chosen, tr, content, visible_sections=vs)
    store = {"customer": chosen, "sheets": export_sheets}
    return page, store
