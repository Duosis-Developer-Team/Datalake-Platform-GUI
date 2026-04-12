"""Dash callbacks for IAM users page (AD search, import, slide-in panel)."""

from __future__ import annotations

import logging
import time

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
    Output("user-slide-panel", "className"),
    Input("iam-user-panel-store", "data"),
)
def sync_user_panel_class(store):
    if store and store.get("open"):
        return "user-slide-panel open"
    return "user-slide-panel closed"


@callback(
    Output("iam-user-panel-store", "data"),
    Output("iam-user-panel-title", "children"),
    Output("iam-user-form-username", "value"),
    Output("iam-user-form-username", "disabled"),
    Output("iam-user-form-password", "value"),
    Output("iam-user-form-display-name", "value"),
    Output("iam-user-form-email", "value"),
    Output("iam-user-form-role-ids", "value"),
    Output("iam-user-form-team-ids", "value"),
    Output("iam-user-form-feedback", "children"),
    Output("iam-user-form-tabs", "value"),
    Output("iam-user-form-password-wrap", "style"),
    Input("iam-user-open-create", "n_clicks"),
    Input({"type": "iam-user-edit", "uid": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_user_panel(_create_clicks, _edit_clicks):
    trig = ctx.triggered_id
    if trig == "iam-user-open-create":
        return (
            {"open": True, "mode": "create", "uid": None},
            "Create user",
            "",
            False,
            "",
            "",
            "",
            [],
            [],
            None,
            "local",
            {"display": "block"},
        )
    if isinstance(trig, dict) and trig.get("type") == "iam-user-edit":
        uid = int(trig["uid"])
        detail = settings_crud.get_user_detail(uid)
        if not detail:
            return (
                {"open": True, "mode": "edit", "uid": uid},
                "Edit user",
                "",
                True,
                "",
                "",
                "",
                [],
                [],
                dmc.Alert("User not found.", color="red", variant="light"),
                "local",
                {"display": "none"},
            )
        rids = [str(x) for x in detail.get("role_ids") or []]
        tids = [str(x) for x in detail.get("team_ids") or []]
        title = f"Edit user — {detail.get('username', '')}"
        return (
            {"open": True, "mode": "edit", "uid": uid},
            title,
            detail.get("username") or "",
            True,
            "",
            detail.get("display_name") or "",
            detail.get("email") or "",
            rids,
            tids,
            None,
            "local",
            {"display": "none"},
        )
    raise PreventUpdate


@callback(
    Output("iam-user-panel-store", "data", allow_duplicate=True),
    Input("iam-user-panel-close", "n_clicks"),
    prevent_initial_call=True,
)
def close_user_panel(_n):
    return {"open": False, "mode": "create", "uid": None}


@callback(
    Output("ad-search-results-store", "data"),
    Output("ad-import-checklist", "options"),
    Output("ad-import-checklist", "value"),
    Output("ad-user-search-feedback", "children"),
    Input("ad-user-search-btn", "n_clicks"),
    State("ad-user-search-input", "value"),
    prevent_initial_call=True,
)
def run_ad_search(_n_clicks, query):
    q_raw = str(query or "").strip()
    if len(q_raw) < 2:
        return (
            no_update,
            no_update,
            no_update,
            dmc.Alert("Enter at least 2 characters to search.", color="yellow", variant="light"),
        )
    q = q_raw
    try:
        rows = settings_crud.search_ldap_users(q)
    except Exception as exc:
        logger.exception("AD search failed")
        return (
            [],
            [],
            [],
            dmc.Alert(f"Search failed: {exc}", color="red", variant="light"),
        )

    if not rows:
        return (
            [],
            [],
            [],
            dmc.Alert("No matching users found.", color="gray", variant="light"),
        )

    options = [{"label": _dn_label(r), "value": r["distinguished_name"]} for r in rows]
    return (
        rows,
        options,
        [],
        dmc.Alert(
            f"Found {len(rows)} user(s). Select below, then click Import selected.",
            color="blue",
            variant="light",
        ),
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
    Output("url", "search", allow_duplicate=True),
    Output("iam-user-form-feedback", "children", allow_duplicate=True),
    Output("iam-user-panel-store", "data", allow_duplicate=True),
    Input("iam-user-form-save", "n_clicks"),
    State("iam-user-panel-store", "data"),
    State("iam-user-form-username", "value"),
    State("iam-user-form-password", "value"),
    State("iam-user-form-display-name", "value"),
    State("iam-user-form-email", "value"),
    State("iam-user-form-role-ids", "value"),
    State("iam-user-form-team-ids", "value"),
    prevent_initial_call=True,
)
def save_user_panel(_n, store, username, password, display_name, email, role_vals, team_vals):
    if not store or not store.get("open"):
        raise PreventUpdate
    mode = store.get("mode") or "create"
    uid = store.get("uid")

    role_ids = _int_list(role_vals)
    team_ids = _int_list(team_vals)

    try:
        if mode == "create":
            uname = str(username or "").strip()
            pw = str(password or "")
            if not uname:
                return no_update, dmc.Alert("Username is required.", color="yellow", variant="light"), no_update
            if not pw:
                return no_update, dmc.Alert("Password is required for new users.", color="yellow", variant="light"), no_update
            new_id = settings_crud.create_local_user(uname, pw, display_name or None)
            em = str(email).strip() if email else None
            settings_crud.update_user_profile(int(new_id), display_name or None, em)
            settings_crud.set_user_roles(int(new_id), role_ids)
            settings_crud.set_user_teams(int(new_id), team_ids)
        else:
            if uid is None:
                raise PreventUpdate
            settings_crud.update_user_profile(int(uid), display_name or None, str(email).strip() if email else None)
            settings_crud.set_user_roles(int(uid), role_ids)
            settings_crud.set_user_teams(int(uid), team_ids)
    except Exception as exc:
        logger.exception("save_user_panel failed")
        return no_update, dmc.Alert(f"Save failed: {exc}", color="red", variant="light"), no_update

    refresh = f"?_refresh={int(time.time() * 1000)}"
    return refresh, None, {"open": False, "mode": "create", "uid": None}
