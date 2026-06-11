"""DC View async data load and progressive tab expansion callbacks."""
from __future__ import annotations

import dash
from dash import Input, Output, State, callback, ctx, html

from src.components.dc_loading import LOADING_STAGE_MESSAGES
from src.pages.dc_view import _SUMMARY_EAGER_TABS, build_dc_view
from src.utils.time_range import default_time_range


def _dc_id_from_path(pathname: str | None) -> str | None:
    if not pathname or not pathname.startswith("/datacenter/"):
        return None
    return pathname.replace("/datacenter/", "").strip("/") or None


@callback(
    Output("dc-loading-status", "children"),
    Input("dc-loading-stage-interval", "n_intervals"),
    prevent_initial_call=False,
)
def rotate_dc_loading_status(n_intervals):
    if not LOADING_STAGE_MESSAGES:
        return dash.no_update
    idx = int(n_intervals or 0) % len(LOADING_STAGE_MESSAGES)
    return LOADING_STAGE_MESSAGES[idx]


@callback(
    Output("dc-view-page-root", "children"),
    Output("dc-view-loaded-tabs", "data"),
    Input("url", "pathname"),
    Input("app-time-range", "data"),
    State("dc-view-visible-sections", "data"),
    State("dc-view-loaded-tabs", "data"),
    prevent_initial_call=False,
)
def load_dc_view_data(pathname, time_range, visible_sections, loaded_tabs):
    dc_id = _dc_id_from_path(pathname)
    if not dc_id:
        raise dash.exceptions.PreventUpdate
    tr = time_range or default_time_range()
    vs = set(visible_sections) if visible_sections else None
    triggered = str(ctx.triggered_id or "")
    if triggered.startswith("url"):
        loaded = set(_SUMMARY_EAGER_TABS)
    else:
        loaded = set(loaded_tabs or _SUMMARY_EAGER_TABS)
    eager = frozenset(loaded) if loaded else _SUMMARY_EAGER_TABS
    page = build_dc_view(dc_id, tr, visible_sections=vs, eager_tabs=eager)
    wrapper = html.Div(className="dc-page-enter customer-page-enter", children=[page])
    return wrapper, sorted(eager)


@callback(
    Output("dc-view-page-root", "children", allow_duplicate=True),
    Output("dc-view-loaded-tabs", "data", allow_duplicate=True),
    Input("dc-main-tabs", "value"),
    Input("app-time-range", "data"),
    State("url", "pathname"),
    State("dc-view-visible-sections", "data"),
    State("dc-view-loaded-tabs", "data"),
    prevent_initial_call=True,
)
def expand_dc_view_on_tab(active_tab, time_range, pathname, visible_sections, loaded_tabs):
    dc_id = _dc_id_from_path(pathname)
    if not dc_id or not active_tab:
        raise dash.exceptions.PreventUpdate
    tr = time_range or default_time_range()
    vs = set(visible_sections) if visible_sections else None
    loaded = set(loaded_tabs or _SUMMARY_EAGER_TABS)
    prev = set(loaded)
    loaded.add(active_tab)
    if loaded == prev and active_tab in prev:
        raise dash.exceptions.PreventUpdate
    page = build_dc_view(dc_id, tr, visible_sections=vs, eager_tabs=frozenset(loaded))
    wrapper = html.Div(className="dc-page-enter customer-page-enter", children=[page])
    return wrapper, sorted(loaded)
