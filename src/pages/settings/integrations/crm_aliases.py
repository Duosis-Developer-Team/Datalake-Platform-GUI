"""Integrations — CRM customer aliases (gui_crm_customer_alias)."""

from __future__ import annotations

import dash
from dash import Input, Output, State, callback, ctx, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.services import api_client as api


def _row_form(alias: dict):
    aid = alias.get("crm_accountid", "")
    return html.Tr(
        [
            html.Td(aid, style={"fontSize": "11px", "color": "#888", "maxWidth": "120px", "overflow": "hidden", "textOverflow": "ellipsis"}),
            html.Td(alias.get("crm_account_name") or "-"),
            html.Td(
                dmc.TextInput(
                    id={"type": "alias-canonical", "index": aid},
                    value=alias.get("canonical_customer_key") or "",
                    size="xs",
                    placeholder="canonical key",
                    style={"minWidth": "160px"},
                )
            ),
            html.Td(
                dmc.TextInput(
                    id={"type": "alias-netbox", "index": aid},
                    value=alias.get("netbox_musteri_value") or "",
                    size="xs",
                    placeholder="NetBox musteri value",
                    style={"minWidth": "160px"},
                )
            ),
            html.Td(
                dmc.TextInput(
                    id={"type": "alias-notes", "index": aid},
                    value=alias.get("notes") or "",
                    size="xs",
                    placeholder="notes",
                )
            ),
            html.Td(
                dmc.Badge(
                    alias.get("source") or "auto",
                    color="teal" if alias.get("source") == "manual" else "gray",
                    size="sm",
                )
            ),
            html.Td(
                dmc.Group(
                    gap="xs",
                    wrap="nowrap",
                    children=[
                        dmc.Button(
                            "Save",
                            id={"type": "alias-save-btn", "index": aid},
                            size="xs",
                            color="indigo",
                            variant="light",
                        ),
                        dmc.Button(
                            "Delete",
                            id={"type": "alias-del-btn", "index": aid},
                            size="xs",
                            color="red",
                            variant="light",
                        ),
                    ],
                )
            ),
        ]
    )


def build_layout(search: str | None = None) -> html.Div:
    aliases = api.get_crm_aliases()

    if not aliases:
        info = dmc.Alert(
            color="yellow",
            title="No alias rows yet",
            children="Create mappings below or seed from CRM accounts via operator tooling.",
        )
    else:
        info = None

    table = dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=True,
        children=[
            html.Thead(
                html.Tr(
                    [
                        html.Th("CRM Account ID"),
                        html.Th("CRM Account Name"),
                        html.Th("Canonical Key"),
                        html.Th("NetBox Musteri"),
                        html.Th("Notes"),
                        html.Th("Source"),
                        html.Th(""),
                    ]
                )
            ),
            html.Tbody([_row_form(a) for a in aliases] if aliases else [html.Tr([html.Td("No data", colSpan=7)])]),
        ],
    )

    return html.Div(
        children=[
            dmc.Group(
                gap="sm",
                mb="lg",
                children=[
                    dmc.ThemeIcon(
                        size="xl",
                        variant="light",
                        color="teal",
                        radius="md",
                        children=DashIconify(icon="solar:link-circle-bold-duotone", width=28),
                    ),
                    dmc.Stack(
                        gap=0,
                        children=[
                            dmc.Text("Customer aliases", fw=700, size="xl", c="#2B3674"),
                            dmc.Text(
                                "Map CRM account IDs to platform canonical customer keys and NetBox musteri values.",
                                size="sm",
                                c="#A3AED0",
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Alert(
                color="blue",
                title="How it works",
                mb="lg",
                children=[
                    "Rows marked ",
                    dmc.Badge("auto", color="gray", size="sm"),
                    " may be seeded upstream. Editing promotes a row to ",
                    dmc.Badge("manual", color="teal", size="sm"),
                    " where applicable.",
                ],
            ),
            info,
            html.Div(id="alias-feedback", style={"marginBottom": "12px"}),
            html.Div(style={"overflowX": "auto"}, children=[table]),
        ],
    )


@callback(
    Output("alias-feedback", "children"),
    Input({"type": "alias-save-btn", "index": dash.ALL}, "n_clicks"),
    State({"type": "alias-canonical", "index": dash.ALL}, "value"),
    State({"type": "alias-netbox", "index": dash.ALL}, "value"),
    State({"type": "alias-notes", "index": dash.ALL}, "value"),
    prevent_initial_call=True,
)
def _save_alias(_n_clicks, canon_vals, nb_vals, note_vals):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "alias-save-btn":
        return dash.no_update

    aid = str(trig["index"])
    save_buttons = ctx.inputs_list[0]
    canon_states = ctx.states_list[0]
    nb_states = ctx.states_list[1]
    note_states = ctx.states_list[2]

    idx = None
    for i, btn in enumerate(save_buttons):
        if str(btn["id"]["index"]) == aid:
            idx = i
            break
    if idx is None:
        return dmc.Alert(color="yellow", title="Could not resolve clicked row — refresh.")

    canonical = str(canon_states[idx].get("value") or "").strip()
    netbox = str(nb_states[idx].get("value") or "").strip()
    notes = str(note_states[idx].get("value") or "").strip()

    try:
        api.put_crm_alias(
            aid,
            canonical_customer_key=canonical or None,
            netbox_musteri_value=netbox or None,
            notes=notes or None,
        )
        return dmc.Alert(color="green", title="Saved — refresh page to confirm persisted values.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Save failed", children=str(exc))


@callback(
    Output("alias-feedback", "children", allow_duplicate=True),
    Input({"type": "alias-del-btn", "index": dash.ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def _del_alias(_n_clicks):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "alias-del-btn":
        return dash.no_update
    aid = str(trig["index"])
    try:
        api.delete_crm_alias(aid)
        return dmc.Alert(color="green", title="Deleted — refresh page.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Delete failed", children=str(exc))
