"""Dash callbacks for IAM users page (AD search, import, edit)."""

from __future__ import annotations

import logging

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, no_update
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


def _dn_label(u: dict) -> str:
    dn = str(u.get("distinguished_name") or "")
    short = dn if len(dn) <= 64 else dn[:61] + "…"
    mail = u.get("email") or "—"
    disp = u.get("display_name") or ""
    return f"{u.get('username', '?')} | {disp} | {mail} | {short}"


@callback(
    Output("ad-search-modal", "opened"),
    Output("ad-search-results-store", "data"),
    Output("ad-import-checklist", "options"),
    Output("ad-import-checklist", "value"),
    Output("ad-user-search-feedback", "children"),
    Input("ad-user-search-btn", "n_clicks"),
    State("ad-user-search-input", "value"),
    prevent_initial_call=True,
)
def run_ad_search(_n_clicks, query):
    if not query or len(str(query).strip()) < 2:
        return (
            False,
            no_update,
            no_update,
            no_update,
            dmc.Alert("Enter at least 2 characters to search.", color="yellow", variant="light"),
        )
    q = str(query).strip()
    try:
        rows = settings_crud.search_ldap_users(q)
    except Exception as exc:
        logger.exception("AD search failed")
        return (
            False,
            [],
            [],
            [],
            dmc.Alert(f"Search failed: {exc}", color="red", variant="light"),
        )

    if not rows:
        return (
            True,
            [],
            [],
            [],
            dmc.Alert("No matching users found.", color="gray", variant="light"),
        )

    options = [{"label": _dn_label(r), "value": r["distinguished_name"]} for r in rows]
    return (
        True,
        rows,
        options,
        [],
        dmc.Alert(f"Found {len(rows)} user(s). Select below, then close and click Import selected.", color="blue", variant="light"),
    )


@callback(
    Output("ad-import-feedback", "children"),
    Input("ad-import-submit-btn", "n_clicks"),
    State("ad-import-checklist", "value"),
    State("ad-search-results-store", "data"),
    State("ad-import-role-ids", "value"),
    State("ad-import-team-ids", "value"),
    prevent_initial_call=True,
)
def submit_ad_import(_n, selected_dns, store_rows, role_vals, team_vals):
    if not selected_dns:
        return dmc.Alert("Select at least one directory user.", color="yellow", variant="light")

    by_dn = {r["distinguished_name"]: r for r in (store_rows or []) if r.get("distinguished_name")}
    users: list[dict] = []
    for dn in selected_dns:
        u = by_dn.get(dn)
        if u:
            users.append(
                {
                    "username": u["username"],
                    "distinguished_name": u["distinguished_name"],
                    "display_name": u.get("display_name"),
                    "email": u.get("email"),
                }
            )

    if not users:
        return dmc.Alert("Could not resolve selected rows. Run search again.", color="red", variant="light")

    role_ids = _int_list(role_vals)
    team_ids = _int_list(team_vals)

    try:
        res = settings_crud.import_ldap_users(users, role_ids, team_ids)
        n = int(res.get("count", 0))
        return dmc.Alert(f"Imported {n} user(s) successfully.", color="green", variant="light")
    except Exception as exc:
        logger.exception("import_ldap_users failed")
        return dmc.Alert(f"Import failed: {exc}", color="red", variant="light")


@callback(
    Output("iam-user-edit-modal", "opened"),
    Output("iam-edit-user-store", "data"),
    Output("iam-user-edit-display-name", "value"),
    Output("iam-user-edit-email", "value"),
    Output("iam-user-edit-role-ids", "value"),
    Output("iam-user-edit-team-ids", "value"),
    Output("iam-user-edit-feedback", "children"),
    Input({"type": "iam-user-edit", "uid": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_user_edit(_clicks):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "iam-user-edit":
        raise PreventUpdate
    uid = int(trig["uid"])
    detail = settings_crud.get_user_detail(uid)
    if not detail:
        return (
            True,
            uid,
            "",
            "",
            [],
            [],
            dmc.Alert("User not found.", color="red", variant="light"),
        )
    rids = [str(x) for x in detail.get("role_ids") or []]
    tids = [str(x) for x in detail.get("team_ids") or []]
    return (
        True,
        uid,
        detail.get("display_name") or "",
        detail.get("email") or "",
        rids,
        tids,
        None,
    )


@callback(
    Output("iam-user-edit-modal", "opened", allow_duplicate=True),
    Output("iam-user-edit-feedback", "children", allow_duplicate=True),
    Input("iam-user-edit-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_user_edit(_n):
    return False, None


@callback(
    Output("iam-user-edit-modal", "opened", allow_duplicate=True),
    Output("iam-user-edit-feedback", "children", allow_duplicate=True),
    Input("iam-user-edit-save", "n_clicks"),
    State("iam-edit-user-store", "data"),
    State("iam-user-edit-display-name", "value"),
    State("iam-user-edit-email", "value"),
    State("iam-user-edit-role-ids", "value"),
    State("iam-user-edit-team-ids", "value"),
    prevent_initial_call=True,
)
def save_user_edit(_n, uid, display_name, email, role_vals, team_vals):
    if uid is None:
        raise PreventUpdate
    try:
        settings_crud.update_user_profile(int(uid), display_name or None, email or None)
        role_ids = _int_list(role_vals)
        team_ids = _int_list(team_vals)
        settings_crud.set_user_roles(int(uid), role_ids)
        settings_crud.set_user_teams(int(uid), team_ids)
        return False, dmc.Alert("User saved.", color="green", variant="light")
    except Exception as exc:
        logger.exception("save_user_edit failed")
        return True, dmc.Alert(f"Save failed: {exc}", color="red", variant="light")
