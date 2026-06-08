"""Dash callbacks for NetBox/Loki visualization exclusion settings."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, no_update
from dash.exceptions import PreventUpdate

from src.services import api_client as api
from src.utils.netbox_viz_ui import (
    build_exclusion_table,
    build_summary_badge_children,
    compute_exclusion_summary,
    filter_exclusions_by_scope,
    scope_table_count_label,
)


def _refresh_exclusions() -> list[dict]:
    return api.get_netbox_viz_exclusions()


def _table_outputs(exclusions: list[dict], scope: str, search: str | None):
    rows = filter_exclusions_by_scope(exclusions, scope, search)
    return (
        build_exclusion_table(rows, scope),
        scope_table_count_label(rows, search),
    )


def _summary_output(exclusions: list[dict]):
    roles = api.get_netbox_device_roles()
    return build_summary_badge_children(compute_exclusion_summary(exclusions, roles))


def _refresh_all_outputs(exclusions: list[dict], search_dc: str | None, search_cust: str | None):
    dc_table, dc_count = _table_outputs(exclusions, "datacenter", search_dc)
    cust_table, cust_count = _table_outputs(exclusions, "customer", search_cust)
    return (
        exclusions,
        dc_table,
        dc_count,
        cust_table,
        cust_count,
        _summary_output(exclusions),
    )


@callback(
    Output("nbx-exclusions-store", "data"),
    Output("nbx-table-datacenter", "children"),
    Output("nbx-table-count-datacenter", "children"),
    Output("nbx-table-customer", "children"),
    Output("nbx-table-count-customer", "children"),
    Output("nbx-summary-badges", "children"),
    Output("nbx-roles-datacenter", "value"),
    Output("nbx-notes-datacenter", "value"),
    Output("nbx-msg-datacenter", "children"),
    Input("nbx-save-datacenter", "n_clicks"),
    State("nbx-roles-datacenter", "value"),
    State("nbx-notes-datacenter", "value"),
    State("nbx-search-datacenter", "value"),
    State("nbx-search-customer", "value"),
    prevent_initial_call=True,
)
def save_datacenter_exclusions(_n, roles, notes, search_dc, search_cust):
    selected = [str(r).strip() for r in (roles or []) if str(r).strip()]
    if not selected:
        return (no_update,) * 8 + (
            dmc.Alert(color="yellow", title="Select at least one device role", variant="light"),
        )
    try:
        for role in selected:
            api.put_netbox_viz_exclusion(
                view_scope="datacenter",
                dimension_value=role,
                notes=str(notes) if notes else None,
            )
        exclusions = _refresh_exclusions()
        refreshed = _refresh_all_outputs(exclusions, search_dc, search_cust)
        return (
            *refreshed,
            [],
            "",
            dmc.Alert(
                color="green",
                title=f"Saved {len(selected)} datacenter exclusion(s)",
                variant="light",
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return (no_update,) * 8 + (
            dmc.Alert(color="red", title="Save failed", children=str(exc), variant="light"),
        )


@callback(
    Output("nbx-exclusions-store", "data", allow_duplicate=True),
    Output("nbx-table-datacenter", "children", allow_duplicate=True),
    Output("nbx-table-count-datacenter", "children", allow_duplicate=True),
    Output("nbx-table-customer", "children", allow_duplicate=True),
    Output("nbx-table-count-customer", "children", allow_duplicate=True),
    Output("nbx-summary-badges", "children", allow_duplicate=True),
    Output("nbx-roles-customer", "value"),
    Output("nbx-notes-customer", "value"),
    Output("nbx-msg-customer", "children"),
    Input("nbx-save-customer", "n_clicks"),
    State("nbx-roles-customer", "value"),
    State("nbx-notes-customer", "value"),
    State("nbx-search-datacenter", "value"),
    State("nbx-search-customer", "value"),
    prevent_initial_call=True,
)
def save_customer_exclusions(_n, roles, notes, search_dc, search_cust):
    selected = [str(r).strip() for r in (roles or []) if str(r).strip()]
    if not selected:
        return (no_update,) * 8 + (
            dmc.Alert(color="yellow", title="Select at least one device role", variant="light"),
        )
    try:
        for role in selected:
            api.put_netbox_viz_exclusion(
                view_scope="customer",
                dimension_value=role,
                notes=str(notes) if notes else None,
            )
        exclusions = _refresh_exclusions()
        refreshed = _refresh_all_outputs(exclusions, search_dc, search_cust)
        return (
            *refreshed,
            [],
            "",
            dmc.Alert(
                color="green",
                title=f"Saved {len(selected)} customer exclusion(s)",
                variant="light",
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return (no_update,) * 8 + (
            dmc.Alert(color="red", title="Save failed", children=str(exc), variant="light"),
        )


@callback(
    Output("nbx-exclusions-store", "data", allow_duplicate=True),
    Output("nbx-table-datacenter", "children", allow_duplicate=True),
    Output("nbx-table-count-datacenter", "children", allow_duplicate=True),
    Output("nbx-table-customer", "children", allow_duplicate=True),
    Output("nbx-table-count-customer", "children", allow_duplicate=True),
    Output("nbx-summary-badges", "children", allow_duplicate=True),
    Output("nbx-delete-modal", "opened"),
    Output("nbx-delete-pending", "data"),
    Output("nbx-del-msg", "children"),
    Input("nbx-delete-confirm", "n_clicks"),
    State("nbx-delete-pending", "data"),
    State("nbx-search-datacenter", "value"),
    State("nbx-search-customer", "value"),
    prevent_initial_call=True,
)
def confirm_delete_exclusion(_n, pending_delete, search_dc, search_cust):
    if not pending_delete or not pending_delete.get("id"):
        raise PreventUpdate
    try:
        api.delete_netbox_viz_exclusion(int(pending_delete["id"]))
        exclusions = _refresh_exclusions()
        refreshed = _refresh_all_outputs(exclusions, search_dc, search_cust)
        return (
            *refreshed,
            False,
            None,
            dmc.Alert(color="green", title="Exclusion removed", variant="light"),
        )
    except Exception as exc:  # noqa: BLE001
        return (
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            True,
            pending_delete,
            dmc.Alert(color="red", title="Delete failed", children=str(exc), variant="light"),
        )


@callback(
    Output("nbx-delete-modal", "opened"),
    Output("nbx-delete-pending", "data"),
    Output("nbx-delete-modal-body", "children"),
    Input({"type": "nbx-del", "rid": ALL, "scope": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_delete_modal(_clicks):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "nbx-del":
        raise PreventUpdate
    rid = int(trig["rid"])
    scope = str(trig.get("scope") or "")
    return (
        True,
        {"id": rid, "scope": scope},
        f"Remove this device role exclusion from the {scope} scope? Dashboards will include matching devices again.",
    )


@callback(
    Output("nbx-delete-modal", "opened", allow_duplicate=True),
    Output("nbx-delete-pending", "data", allow_duplicate=True),
    Input("nbx-delete-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_delete_modal(_n):
    return False, None


@callback(
    Output("nbx-table-datacenter", "children", allow_duplicate=True),
    Output("nbx-table-count-datacenter", "children", allow_duplicate=True),
    Input("nbx-search-datacenter", "value"),
    State("nbx-exclusions-store", "data"),
    prevent_initial_call=True,
)
def filter_datacenter_table(search, exclusions):
    rows = filter_exclusions_by_scope(exclusions or [], "datacenter", search)
    return build_exclusion_table(rows, "datacenter"), scope_table_count_label(rows, search)


@callback(
    Output("nbx-table-customer", "children", allow_duplicate=True),
    Output("nbx-table-count-customer", "children", allow_duplicate=True),
    Input("nbx-search-customer", "value"),
    State("nbx-exclusions-store", "data"),
    prevent_initial_call=True,
)
def filter_customer_table(search, exclusions):
    rows = filter_exclusions_by_scope(exclusions or [], "customer", search)
    return build_exclusion_table(rows, "customer"), scope_table_count_label(rows, search)
