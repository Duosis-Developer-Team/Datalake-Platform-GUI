"""Dash callbacks for IAM teams page (rename, members)."""

from __future__ import annotations

import logging

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, html, no_update
from dash.exceptions import PreventUpdate

from src.services import admin_client as settings_crud

logger = logging.getLogger(__name__)


def _int_list(vals) -> list[int]:
    out: list[int] = []
    for x in vals or []:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _members_table_rows(team_id: int):
    try:
        members = settings_crud.list_team_members(team_id)
    except Exception as exc:
        logger.exception("list_team_members")
        return dmc.Alert(f"Failed to load members: {exc}", color="red", variant="light")

    if not members:
        return dmc.Text("No members yet.", size="sm", c="dimmed")

    table_rows = []
    for m in members:
        uid = int(m["user_id"])
        table_rows.append(
            html.Tr(
                style={"borderBottom": "1px solid #eef1f4"},
                children=[
                    html.Td(str(m.get("username", ""))),
                    html.Td(str(m.get("display_name") or "—")),
                    html.Td(
                        dmc.Button(
                            "Remove",
                            id={"type": "iam-team-rm-member", "tid": team_id, "uid": uid},
                            size="xs",
                            variant="outline",
                            color="red",
                        )
                    ),
                ],
            )
        )

    return html.Div(
        [
            html.Table(
                style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"},
                children=[
                    html.Thead(
                        html.Tr(
                            [
                                html.Th("Username", style={"textAlign": "left", "padding": "8px"}),
                                html.Th("Display", style={"textAlign": "left", "padding": "8px"}),
                                html.Th("", style={"width": "90px"}),
                            ]
                        )
                    ),
                    html.Tbody(table_rows),
                ],
            )
        ]
    )


@callback(
    Output("iam-team-rename-modal", "opened"),
    Output("iam-team-edit-id-store", "data"),
    Output("iam-team-rename-input", "value"),
    Output("iam-team-rename-feedback", "children"),
    Input({"type": "iam-team-edit", "tid": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_team_rename(_n_clicks):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "iam-team-edit":
        raise PreventUpdate
    tid = int(trig["tid"])
    teams = settings_crud.list_teams()
    name = ""
    for t in teams:
        if int(t["id"]) == tid:
            name = str(t.get("name") or "")
            break
    return True, tid, name, None


@callback(
    Output("iam-team-rename-modal", "opened", allow_duplicate=True),
    Output("iam-team-rename-feedback", "children", allow_duplicate=True),
    Input("iam-team-rename-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_team_rename(_n):
    return False, None


@callback(
    Output("iam-team-rename-modal", "opened", allow_duplicate=True),
    Output("iam-team-rename-feedback", "children", allow_duplicate=True),
    Input("iam-team-rename-save", "n_clicks"),
    State("iam-team-edit-id-store", "data"),
    State("iam-team-rename-input", "value"),
    prevent_initial_call=True,
)
def save_team_rename(_n, tid, name):
    if tid is None or not (name or "").strip():
        return True, dmc.Alert("Name is required.", color="yellow", variant="light")
    try:
        settings_crud.update_team(int(tid), str(name).strip())
        return False, None
    except Exception as exc:
        logger.exception("update_team")
        return True, dmc.Alert(f"Save failed: {exc}", color="red", variant="light")


@callback(
    Output("iam-team-members-modal", "opened"),
    Output("iam-team-members-tid-store", "data"),
    Output("iam-team-members-list", "children"),
    Output("iam-team-add-user-ids", "value"),
    Output("iam-team-members-feedback", "children"),
    Input({"type": "iam-team-members", "tid": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_team_members(_n_clicks):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "iam-team-members":
        raise PreventUpdate
    tid = int(trig["tid"])
    body = _members_table_rows(tid)
    return True, tid, body, [], None


@callback(
    Output("iam-team-members-list", "children", allow_duplicate=True),
    Output("iam-team-members-feedback", "children", allow_duplicate=True),
    Input({"type": "iam-team-rm-member", "tid": ALL, "uid": ALL}, "n_clicks"),
    State("iam-team-members-tid-store", "data"),
    prevent_initial_call=True,
)
def remove_team_member_click(_n, store_tid):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "iam-team-rm-member":
        raise PreventUpdate
    tid = int(trig["tid"])
    uid = int(trig["uid"])
    if store_tid is not None and int(store_tid) != tid:
        raise PreventUpdate
    try:
        settings_crud.remove_team_member(tid, uid)
        return _members_table_rows(tid), dmc.Alert("Member removed.", color="green", variant="light")
    except Exception as exc:
        logger.exception("remove_team_member")
        return no_update, dmc.Alert(f"Remove failed: {exc}", color="red", variant="light")


@callback(
    Output("iam-team-members-list", "children", allow_duplicate=True),
    Output("iam-team-add-user-ids", "value", allow_duplicate=True),
    Output("iam-team-members-feedback", "children", allow_duplicate=True),
    Input("iam-team-add-members-btn", "n_clicks"),
    State("iam-team-members-tid-store", "data"),
    State("iam-team-add-user-ids", "value"),
    prevent_initial_call=True,
)
def add_team_members_click(_n, tid, user_vals):
    if tid is None:
        raise PreventUpdate
    uids = _int_list(user_vals)
    if not uids:
        return no_update, no_update, dmc.Alert("Select at least one user.", color="yellow", variant="light")
    try:
        settings_crud.add_team_members(int(tid), uids)
        return _members_table_rows(int(tid)), [], dmc.Alert("Members added.", color="green", variant="light")
    except Exception as exc:
        logger.exception("add_team_members")
        return no_update, no_update, dmc.Alert(f"Add failed: {exc}", color="red", variant="light")
