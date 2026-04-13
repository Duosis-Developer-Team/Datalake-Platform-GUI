"""Dash callbacks for IAM teams page (slide-in panel, members)."""

from __future__ import annotations

import logging
import time

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
    Output("team-slide-panel", "className"),
    Input("iam-team-panel-store", "data"),
)
def sync_team_panel_class(store):
    if store and store.get("open"):
        return "team-slide-panel open"
    return "team-slide-panel closed"


@callback(
    Output("iam-team-panel-store", "data"),
    Output("iam-team-panel-title", "children"),
    Output("iam-team-form-name", "value"),
    Output("iam-team-form-description", "value"),
    Output("iam-team-form-role-ids", "value"),
    Output("iam-team-form-feedback", "children"),
    Input("iam-team-open-create", "n_clicks"),
    Input({"type": "iam-team-edit", "tid": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_team_panel(_n_create, _n_edit):
    trig = ctx.triggered_id
    if trig == "iam-team-open-create":
        return (
            {"open": True, "mode": "create", "tid": None},
            "Create team",
            "",
            "",
            [],
            None,
        )
    if isinstance(trig, dict) and trig.get("type") == "iam-team-edit":
        tid = int(trig["tid"])
        teams = settings_crud.list_teams()
        match = next((x for x in teams if int(x["id"]) == tid), None)
        if not match:
            return (
                {"open": True, "mode": "edit", "tid": tid},
                "Edit team",
                "",
                "",
                [],
                dmc.Alert("Team not found.", color="red", variant="light"),
            )
        rids = [str(x) for x in match.get("role_ids") or []]
        return (
            {"open": True, "mode": "edit", "tid": tid},
            f"Edit team — {match.get('name', '')}",
            str(match.get("name") or ""),
            str(match.get("description") or ""),
            rids,
            None,
        )
    raise PreventUpdate


@callback(
    Output("iam-team-panel-store", "data", allow_duplicate=True),
    Input("iam-team-panel-close", "n_clicks"),
    prevent_initial_call=True,
)
def close_team_panel(_n):
    return {"open": False, "mode": "create", "tid": None}


@callback(
    Output("url", "search", allow_duplicate=True),
    Output("iam-team-form-feedback", "children", allow_duplicate=True),
    Output("iam-team-panel-store", "data", allow_duplicate=True),
    Input("iam-team-form-save", "n_clicks"),
    State("iam-team-panel-store", "data"),
    State("iam-team-form-name", "value"),
    State("iam-team-form-description", "value"),
    State("iam-team-form-role-ids", "value"),
    prevent_initial_call=True,
)
def save_team_panel(_n, store, name, description, role_vals):
    if not store or not store.get("open"):
        raise PreventUpdate
    mode = store.get("mode") or "create"
    tid = store.get("tid")
    role_ids = _int_list(role_vals)
    nm = str(name or "").strip()
    if not nm:
        return no_update, dmc.Alert("Team name is required.", color="yellow", variant="light"), no_update
    desc = str(description or "").strip() or None
    try:
        if mode == "create":
            from flask import g, has_request_context

            uid = getattr(g, "auth_user_id", None) if has_request_context() else None
            settings_crud.create_team(nm, None, int(uid) if uid else None, description=desc, role_ids=role_ids)
        else:
            if tid is None:
                raise PreventUpdate
            settings_crud.update_team(int(tid), nm, description=desc, role_ids=role_ids)
    except Exception as exc:
        logger.exception("save_team_panel failed")
        return no_update, dmc.Alert(f"Save failed: {exc}", color="red", variant="light"), no_update
    refresh = f"?_refresh={int(time.time() * 1000)}"
    return refresh, None, {"open": False, "mode": "create", "tid": None}


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
