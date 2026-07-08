"""DC View async data load and progressive tab expansion callbacks."""
from __future__ import annotations

import logging
import time

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, ctx, html

from src.components.dc_loading import LOADING_STAGE_MESSAGES
from src.pages.dc_view import (
    _LAZY_TAB_KEYS,
    _SUMMARY_EAGER_TABS,
    build_dc_lazy_tab_panel,
    build_dc_view,
)
from src.utils.dc_display import resolve_dc_display_from_summary
from src.utils.time_range import default_time_range

_EXPAND_LOG = logging.getLogger(__name__)


def _dc_id_from_path(pathname: str | None) -> str | None:
    if not pathname or not pathname.startswith("/datacenter/"):
        return None
    return pathname.replace("/datacenter/", "").strip("/") or None


def _dc_context(dc_id: str, tr: dict) -> dict:
    dc_display, dc_loc = resolve_dc_display_from_summary(str(dc_id), tr)
    return {
        "dc_id": str(dc_id),
        "dc_display": dc_display,
        "dc_loc": dc_loc,
    }


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
    Output("dc-view-active-tab", "data"),
    Input("dc-main-tabs", "value"),
    prevent_initial_call=True,
)
def sync_dc_active_tab(active_tab):
    if not active_tab:
        raise dash.exceptions.PreventUpdate
    return active_tab


@callback(
    Output("dc-view-page-root", "children"),
    Output("dc-view-loaded-tabs", "data"),
    Output("dc-view-context-store", "data"),
    Input("url", "pathname"),
    Input("app-time-range", "data"),
    State("dc-view-visible-sections", "data"),
    State("dc-view-loaded-tabs", "data"),
    State("dc-view-active-tab", "data"),
    State("dc-view-dc-id", "data"),
    prevent_initial_call=False,
)
def load_dc_view_data(
    pathname,
    time_range,
    visible_sections,
    loaded_tabs,
    active_tab,
    prev_dc_id,
):
    dc_id = _dc_id_from_path(pathname)
    if not dc_id:
        raise dash.exceptions.PreventUpdate
    tr = time_range or default_time_range()
    vs = set(visible_sections) if visible_sections else None
    triggered = str(ctx.triggered_id or "")

    dc_changed = (
        triggered.startswith("url")
        and str(dc_id).upper() != str(prev_dc_id or "").upper()
    )
    if dc_changed:
        loaded = set(_SUMMARY_EAGER_TABS)
        active = "summary"
    else:
        loaded = set(loaded_tabs or _SUMMARY_EAGER_TABS)
        active = active_tab or "summary"

    if active in _LAZY_TAB_KEYS:
        loaded.add(active)

    eager = frozenset(loaded) if loaded else _SUMMARY_EAGER_TABS
    page = build_dc_view(
        dc_id,
        tr,
        visible_sections=vs,
        eager_tabs=eager,
        active_outer_tab=active,
    )
    wrapper = html.Div(className="dc-page-enter customer-page-enter", children=[page])
    return wrapper, sorted(eager), _dc_context(dc_id, tr)


@callback(
    Output("dc-view-active-tab", "data", allow_duplicate=True),
    Input("url", "pathname"),
    State("dc-view-dc-id", "data"),
    prevent_initial_call=True,
)
def reset_dc_active_tab_on_dc_change(pathname, prev_dc_id):
    """Reset tab to Summary when navigating to a different datacenter."""
    dc_id = _dc_id_from_path(pathname)
    if not dc_id:
        raise dash.exceptions.PreventUpdate
    if str(dc_id).upper() == str(prev_dc_id or "").upper():
        raise dash.exceptions.PreventUpdate
    return "summary"


@callback(
    Output("dc-tab-virt-root", "children", allow_duplicate=True),
    Output("dc-tab-backup-root", "children", allow_duplicate=True),
    Output("dc-tab-storage-root", "children", allow_duplicate=True),
    Output("dc-tab-phys-inv-root", "children", allow_duplicate=True),
    Output("dc-tab-network-root", "children", allow_duplicate=True),
    Output("dc-tab-avail-root", "children", allow_duplicate=True),
    Output("dc-view-loaded-tabs", "data", allow_duplicate=True),
    Input("dc-main-tabs", "value"),
    State("url", "pathname"),
    State("app-time-range", "data"),
    State("dc-view-visible-sections", "data"),
    State("dc-view-loaded-tabs", "data"),
    prevent_initial_call=True,
)
def expand_dc_view_on_tab(active_tab, pathname, time_range, visible_sections, loaded_tabs):
    dc_id = _dc_id_from_path(pathname)
    if not dc_id or not active_tab:
        raise dash.exceptions.PreventUpdate
    if active_tab not in _LAZY_TAB_KEYS:
        raise dash.exceptions.PreventUpdate

    tr = time_range or default_time_range()
    vs = set(visible_sections) if visible_sections else None
    loaded = set(loaded_tabs or _SUMMARY_EAGER_TABS)
    prev = set(loaded)
    loaded.add(active_tab)
    if loaded == prev and active_tab in prev and str(ctx.triggered_id or "") == "dc-main-tabs":
        raise dash.exceptions.PreventUpdate

    t_expand = time.perf_counter()
    root_found = True
    try:
        content = build_dc_lazy_tab_panel(dc_id, active_tab, tr, vs)
    except Exception as exc:
        _EXPAND_LOG.exception(
            "expand_dc_tab_failed dc=%s tab=%s trigger=%s",
            dc_id,
            active_tab,
            ctx.triggered_id,
        )
        content = dmc.Alert(
            title=f"Failed to load {active_tab} tab",
            color="red",
            children=str(exc),
        )
        root_found = False
    expand_ms = round((time.perf_counter() - t_expand) * 1000, 1)
    _EXPAND_LOG.info(
        "expand_dc_tab dc=%s tab=%s trigger=%s expand_ms=%s root_found=%s",
        dc_id,
        active_tab,
        ctx.triggered_id,
        expand_ms,
        root_found,
    )
    updates: list = [dash.no_update] * len(_LAZY_TAB_KEYS)
    try:
        idx = _LAZY_TAB_KEYS.index(active_tab)
        updates[idx] = content
    except ValueError:
        raise dash.exceptions.PreventUpdate

    return (*updates, sorted(loaded))


# ---------------------------------------------------------------------------
# Nutanix snapshot table: pagination + search + live-SQL refresh
# ---------------------------------------------------------------------------

from src.services import api_client as _api  # noqa: E402
from src.components.backup_panel import nutanix_snapshot_table as _nutanix_snapshot_table  # noqa: E402

_NUTANIX_PAGE_SIZE = 50


@callback(
    Output("backup-nutanix-table", "children"),
    Output("backup-nutanix-pageinfo", "children"),
    Output("backup-nutanix-page", "data"),
    Input("backup-nutanix-search", "value"),
    Input("backup-nutanix-prev", "n_clicks"),
    Input("backup-nutanix-next", "n_clicks"),
    Input("backup-nutanix-refresh", "n_clicks"),
    Input("backup-nutanix-filter-customer", "value"),
    Input("backup-nutanix-filter-schedtype", "value"),
    Input("backup-nutanix-filter-retention", "value"),
    Input("backup-nutanix-filter-cluster", "value"),
    Input("dc-main-tabs", "value"),
    State("backup-nutanix-page", "data"),
    State("url", "pathname"),
    prevent_initial_call=True,
)
def _update_nutanix_snapshot_table(search, prev_n, next_n, refresh_n,
                                   f_customer, f_schedtype, f_retention, f_cluster,
                                   active_tab, page, pathname):
    dc_id = _dc_id_from_path(pathname)
    if not dc_id or (active_tab or "") != "backup":
        return dash.no_update, dash.no_update, dash.no_update

    trig = ctx.triggered_id
    page = int(page or 1)
    if trig == "backup-nutanix-next":
        page += 1
    elif trig == "backup-nutanix-prev":
        page = max(1, page - 1)
    else:
        # search / refresh / any filter change → back to page 1
        page = 1
        if trig == "backup-nutanix-refresh" and refresh_n:
            try:
                _api.refresh_dc_nutanix_snapshots_cache(dc_id)
            except Exception:  # noqa: BLE001 — refresh best-effort; fall through to fetch
                pass

    try:
        payload = _api.get_dc_nutanix_snapshot_table(
            dc_id, None, page=page, page_size=_NUTANIX_PAGE_SIZE, search=search or "",
            customers=f_customer or None, schedule_types=f_schedtype or None,
            retentions=f_retention or None, clusters=f_cluster or None)
    except Exception:  # noqa: BLE001
        return dash.no_update, dash.no_update, dash.no_update

    total = int(payload.get("total", 0) or 0)
    pages = max(1, -(-total // _NUTANIX_PAGE_SIZE))
    page = min(page, pages)
    return _nutanix_snapshot_table(payload.get("items", [])), f"{page} / {pages}", page
