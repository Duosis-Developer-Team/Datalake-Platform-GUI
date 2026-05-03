"""Integrations — CRM capacity threshold editor (gui_crm_threshold_config)."""

from __future__ import annotations

import dash
from dash import Input, Output, State, callback, ctx, html
import dash_mantine_components as dmc

from src.services import api_client as api


def build_layout(search: str | None = None) -> html.Div:
    rows = api.get_crm_config_thresholds()
    table_rows = []
    for r in rows:
        rid = int(r.get("id") or 0)
        table_rows.append(
            html.Tr(
                [
                    html.Td(str(r.get("resource_type") or "")),
                    html.Td(str(r.get("dc_code") or "")),
                    html.Td(str(r.get("sellable_limit_pct") or "")),
                    html.Td(str(r.get("notes") or "")),
                    html.Td(
                        dmc.Button(
                            "Delete",
                            id={"type": "thr-del", "rid": rid},
                            size="xs",
                            color="red",
                            variant="light",
                        )
                    ),
                ]
            )
        )

    return html.Div(
        [
            dmc.Stack(
                gap="xs",
                mb="md",
                children=[
                    dmc.Title("CRM capacity thresholds", order=3),
                    dmc.Text(
                        "Defines how much capacity may still be sold before hitting the configured ceiling "
                        "(default 80%% for CPU/RAM). Use dc_code='*' for global defaults or override per DC.",
                        size="sm",
                        c="dimmed",
                    ),
                ],
            ),
            dmc.Paper(
                p="md",
                radius="md",
                withBorder=True,
                mb="md",
                children=[
                    dmc.Title("Add / update threshold", order=5, mb="sm"),
                    dmc.Grid(
                        gutter="sm",
                        children=[
                            dmc.GridCol(span={"base": 12, "md": 3}, children=dmc.TextInput(id="thr-res", label="resource_type", size="xs")),
                            dmc.GridCol(span={"base": 12, "md": 3}, children=dmc.TextInput(id="thr-dc", label="dc_code", size="xs", value="*")),
                            dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.NumberInput(id="thr-pct", label="sellable_limit_pct", size="xs", min=0, max=100, value=80)),
                            dmc.GridCol(span={"base": 12, "md": 3}, children=dmc.TextInput(id="thr-notes", label="notes", size="xs")),
                            dmc.GridCol(span={"base": 12, "md": 1}, children=dmc.Button("Save", id="thr-save", size="xs")),
                        ],
                    ),
                    html.Div(id="thr-msg", style={"marginTop": "8px"}),
                    html.Div(id="thr-del-msg", style={"marginTop": "8px"}),
                ],
            ),
            dmc.Paper(
                p="md",
                radius="md",
                withBorder=True,
                children=[
                    dmc.Title("Existing rows", order=5, mb="sm"),
                    html.Table(
                        className="table table-sm",
                        style={"width": "100%", "borderCollapse": "collapse"},
                        children=[
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("resource_type"),
                                        html.Th("dc_code"),
                                        html.Th("sellable_limit_pct"),
                                        html.Th("notes"),
                                        html.Th(""),
                                    ]
                                )
                            ),
                            html.Tbody(table_rows or [html.Tr([html.Td(colSpan=5, children="No rows yet")])]),
                        ],
                    ),
                ],
            ),
        ]
    )


@callback(
    Output("thr-msg", "children"),
    Input("thr-save", "n_clicks"),
    State("thr-res", "value"),
    State("thr-dc", "value"),
    State("thr-pct", "value"),
    State("thr-notes", "value"),
    prevent_initial_call=True,
)
def _save_thr(_n, res, dc, pct, notes):
    if not res:
        return dmc.Alert(color="yellow", title="resource_type required")
    try:
        api.put_crm_config_threshold(
            resource_type=str(res),
            dc_code=str(dc or "*"),
            sellable_limit_pct=float(pct or 0),
            notes=str(notes) if notes else None,
        )
        return dmc.Alert(color="green", title="Saved — refresh page to see table updates.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Save failed", children=str(exc))


@callback(
    Output("thr-del-msg", "children"),
    Input({"type": "thr-del", "rid": dash.ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def _del_thr(_clicks):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "thr-del":
        return dash.no_update
    rid = int(trig["rid"])
    try:
        api.delete_crm_config_threshold(rid)
        return dmc.Alert(color="green", title="Deleted — refresh page.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Delete failed", children=str(exc))
