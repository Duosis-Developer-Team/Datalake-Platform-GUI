"""Dash callbacks for the role permission matrix page."""

from __future__ import annotations

import logging

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, no_update
from dash.exceptions import PreventUpdate
from dash_iconify import DashIconify

from src.services import admin_client as settings_crud

logger = logging.getLogger(__name__)


@callback(
    Output("role-matrix-feedback", "children"),
    Input("save-role-matrix-btn", "n_clicks"),
    State({"type": "perm-cb", "pid": ALL, "col": ALL}, "value"),
    State({"type": "perm-cb", "pid": ALL, "col": ALL}, "id"),
    State("role-matrix-role-id", "data"),
    prevent_initial_call=True,
)
def save_role_matrix(n_clicks, cb_values, cb_ids, role_id):
    if not n_clicks or role_id is None:
        return no_update

    matrix: dict[int, dict[str, bool]] = {}
    for cb_id, value in zip(cb_ids, cb_values):
        pid = int(cb_id["pid"])
        col = str(cb_id["col"])
        if pid not in matrix:
            matrix[pid] = {"v": False, "e": False, "x": False}
        matrix[pid][col] = "on" in (value or [])

    triplets = [(pid, v["v"], v["e"], v["x"]) for pid, v in matrix.items()]
    try:
        settings_crud.bulk_set_role_matrix(int(role_id), triplets)
        logger.info("Role matrix saved for role_id=%s (%d rows)", role_id, len(triplets))
        return dmc.Alert(
            dmc.Group(
                gap="xs",
                children=[
                    DashIconify(icon="solar:check-circle-bold-duotone", width=18),
                    "Permissions saved successfully.",
                ],
            ),
            color="green",
            variant="light",
        )
    except Exception as exc:
        logger.error("Role matrix save failed: %s", exc)
        return dmc.Alert(
            f"Save failed: {exc}",
            color="red",
            variant="light",
        )


@callback(
    Output("iam-role-edit-modal", "opened"),
    Output("iam-role-edit-id-store", "data"),
    Output("iam-role-edit-is-system-store", "data"),
    Output("iam-role-edit-name", "value"),
    Output("iam-role-edit-description", "value"),
    Output("iam-role-delete-btn", "disabled"),
    Output("iam-role-edit-feedback", "children"),
    Input({"type": "iam-role-edit", "rid": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_role_edit(_n_clicks):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "iam-role-edit":
        raise PreventUpdate
    rid = int(trig["rid"])
    roles = settings_crud.list_roles()
    for r in roles:
        if int(r["id"]) == rid:
            is_sys = bool(r.get("is_system"))
            return (
                True,
                rid,
                is_sys,
                str(r.get("name") or ""),
                str(r.get("description") or ""),
                is_sys,
                None,
            )
    return True, rid, True, "", "", True, dmc.Alert("Role not found.", color="red", variant="light")


@callback(
    Output("iam-role-edit-modal", "opened", allow_duplicate=True),
    Output("iam-role-edit-feedback", "children", allow_duplicate=True),
    Input("iam-role-edit-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_role_edit(_n):
    return False, None


@callback(
    Output("iam-role-edit-modal", "opened", allow_duplicate=True),
    Output("iam-role-edit-feedback", "children", allow_duplicate=True),
    Input("iam-role-edit-save", "n_clicks"),
    State("iam-role-edit-id-store", "data"),
    State("iam-role-edit-name", "value"),
    State("iam-role-edit-description", "value"),
    State("iam-role-edit-is-system-store", "data"),
    prevent_initial_call=True,
)
def save_role_edit(_n, rid, name, description, is_system):
    if rid is None:
        raise PreventUpdate
    if is_system:
        return True, dmc.Alert("System roles cannot be edited here.", color="yellow", variant="light")
    if not (name or "").strip():
        return True, dmc.Alert("Name is required.", color="yellow", variant="light")
    try:
        settings_crud.update_role(int(rid), str(name).strip(), (description or "").strip() or None)
        return False, None
    except Exception as exc:
        logger.exception("update_role")
        return True, dmc.Alert(f"Save failed: {exc}", color="red", variant="light")


@callback(
    Output("iam-role-edit-modal", "opened", allow_duplicate=True),
    Output("iam-role-edit-feedback", "children", allow_duplicate=True),
    Input("iam-role-delete-btn", "n_clicks"),
    State("iam-role-edit-id-store", "data"),
    State("iam-role-edit-is-system-store", "data"),
    prevent_initial_call=True,
)
def delete_role_click(_n, rid, is_system):
    if rid is None:
        raise PreventUpdate
    if is_system:
        return True, dmc.Alert("System roles cannot be deleted.", color="yellow", variant="light")
    try:
        settings_crud.delete_role(int(rid))
        return False, None
    except Exception as exc:
        logger.exception("delete_role")
        return True, dmc.Alert(f"Delete failed: {exc}", color="red", variant="light")
