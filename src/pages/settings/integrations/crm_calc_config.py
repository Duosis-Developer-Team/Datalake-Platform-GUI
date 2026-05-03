"""Integrations — CRM calculation variables (gui_crm_calc_config)."""

from __future__ import annotations

import dash
from dash import Input, Output, State, callback, ctx, html
import dash_mantine_components as dmc

from src.services import api_client as api


def build_layout(search: str | None = None) -> html.Div:
    rows = api.get_crm_calc_config()
    body_rows = []
    for r in rows:
        key = str(r.get("config_key") or "")
        body_rows.append(
            html.Tr(
                [
                    html.Td(key, style={"fontFamily": "monospace", "fontSize": "12px"}),
                    html.Td(str(r.get("value_type") or "")),
                    html.Td(
                        dmc.TextInput(
                            id={"type": "calc-val", "key": key},
                            value=str(r.get("config_value") or ""),
                            size="xs",
                        )
                    ),
                    html.Td(
                        dmc.TextInput(
                            id={"type": "calc-desc", "key": key},
                            value=str(r.get("description") or ""),
                            size="xs",
                        )
                    ),
                    html.Td(dmc.Button("Save", id={"type": "calc-save", "key": key}, size="xs")),
                ]
            )
        )

    return html.Div(
        [
            dmc.Stack(
                gap="xs",
                mb="md",
                children=[
                    dmc.Title("CRM calculation variables", order=3),
                    dmc.Text(
                        "These values tune efficiency bands (under/over) and other CRM-derived calculations.",
                        size="sm",
                        c="dimmed",
                    ),
                ],
            ),
            dmc.Paper(
                p="md",
                radius="md",
                withBorder=True,
                children=[
                    html.Table(
                        className="table table-sm",
                        style={"width": "100%", "borderCollapse": "collapse"},
                        children=[
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("config_key"),
                                        html.Th("value_type"),
                                        html.Th("config_value"),
                                        html.Th("description"),
                                        html.Th(""),
                                    ]
                                )
                            ),
                            html.Tbody(body_rows or [html.Tr([html.Td(colSpan=5, children="No variables returned")])]),
                        ],
                    ),
                    html.Div(id="calc-msg", style={"marginTop": "8px"}),
                ],
            ),
        ]
    )


@callback(
    Output("calc-msg", "children"),
    Input({"type": "calc-save", "key": dash.ALL}, "n_clicks"),
    State({"type": "calc-val", "key": dash.ALL}, "value"),
    State({"type": "calc-desc", "key": dash.ALL}, "value"),
    prevent_initial_call=True,
)
def _save_calc(_n, vals, descs):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "calc-save":
        return dash.no_update

    target_key = str(trig["key"])

    row_payload = api.get_crm_calc_config()
    type_by_key = {str(x.get("config_key")): str(x.get("value_type") or "string") for x in row_payload}

    save_buttons = ctx.inputs_list[0]
    val_states = ctx.states_list[0]
    desc_states = ctx.states_list[1]

    idx = None
    for i, btn in enumerate(save_buttons):
        if btn["id"]["key"] == target_key:
            idx = i
            break
    if idx is None:
        return dmc.Alert(color="yellow", title="Could not locate clicked row — refresh page.")

    val = val_states[idx].get("value")
    desc = desc_states[idx].get("value")

    try:
        api.put_crm_calc_config(
            target_key,
            config_value=str(val or ""),
            value_type=type_by_key.get(target_key),
            description=str(desc or ""),
        )
        return dmc.Alert(color="green", title="Saved — refresh page for authoritative server values.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Save failed", children=str(exc))
