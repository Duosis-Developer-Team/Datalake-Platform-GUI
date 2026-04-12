"""Dash callbacks for the role permission matrix page."""

from __future__ import annotations

import logging

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, no_update
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
