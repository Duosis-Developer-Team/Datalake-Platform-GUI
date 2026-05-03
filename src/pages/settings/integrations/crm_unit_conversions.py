"""Integrations — Unit conversion editor (gui_unit_conversion).

Operator-managed conversion table used by SellableService when datalake
values must be converted to the panel's display_unit before threshold/ratio
math runs. Examples: GHz -> vCPU divide 8 ceil; bytes -> GB divide 2^30.
"""
from __future__ import annotations

import math

import dash
from dash import Input, Output, State, callback, ctx, html
import dash_mantine_components as dmc

from src.services import api_client as api


_OPS = [
    {"value": "divide",   "label": "divide"},
    {"value": "multiply", "label": "multiply"},
]


def _convert(value: float, factor: float, op: str, ceil: bool) -> float:
    if factor <= 0:
        return 0.0
    out = value * factor if op == "multiply" else value / factor
    return float(math.ceil(out)) if ceil else out


def build_layout(search: str | None = None) -> html.Div:
    rows = api.get_unit_conversions()
    table_rows = []
    for r in rows:
        from_u = str(r.get("from_unit") or "")
        to_u = str(r.get("to_unit") or "")
        table_rows.append(
            html.Tr([
                html.Td(from_u),
                html.Td(to_u),
                html.Td(f"{float(r.get('factor') or 0):g}"),
                html.Td(str(r.get("operation") or "divide")),
                html.Td("✓" if r.get("ceil_result") else "—"),
                html.Td(str(r.get("notes") or "")),
                html.Td(
                    dmc.Button(
                        "Delete",
                        id={"type": "uc-del", "from": from_u, "to": to_u},
                        size="xs", color="red", variant="light",
                    )
                ),
            ])
        )

    return html.Div([
        dmc.Stack(gap="xs", mb="md", children=[
            dmc.Title("Unit conversions", order=3),
            dmc.Text(
                "Operator-managed conversion factors. Examples: GHz → vCPU divide 8 ceil "
                "(1 vCPU = 8 GHz, fractional rounds up); bytes → GB divide 1073741824.",
                size="sm", c="dimmed",
            ),
        ]),
        dmc.Paper(p="md", radius="md", withBorder=True, mb="md", children=[
            dmc.Title("Add / update conversion", order=5, mb="sm"),
            dmc.Grid(gutter="sm", children=[
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.TextInput(id="uc-from", label="from_unit", size="xs", placeholder="GHz")),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.TextInput(id="uc-to", label="to_unit", size="xs", placeholder="vCPU")),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.NumberInput(id="uc-factor", label="factor", size="xs", value=8, min=0, decimalScale=6)),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.Select(id="uc-op", label="operation", data=_OPS, value="divide", size="xs")),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.Checkbox(id="uc-ceil", label="ceil_result", checked=True)),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.Button("Save", id="uc-save", size="xs")),
                dmc.GridCol(span={"base": 12, "md": 12}, children=dmc.TextInput(id="uc-notes", label="notes", size="xs")),
                dmc.GridCol(span={"base": 12, "md": 4}, children=dmc.NumberInput(id="uc-preview-input", label="Preview input", size="xs", value=10000, min=0)),
                dmc.GridCol(span={"base": 12, "md": 8}, children=html.Div(id="uc-preview-output", style={"paddingTop": "20px"})),
            ]),
            html.Div(id="uc-msg", style={"marginTop": "8px"}),
            html.Div(id="uc-del-msg", style={"marginTop": "8px"}),
        ]),
        dmc.Paper(p="md", radius="md", withBorder=True, children=[
            dmc.Title("Existing conversions", order=5, mb="sm"),
            html.Table(
                className="table table-sm",
                style={"width": "100%", "borderCollapse": "collapse"},
                children=[
                    html.Thead(html.Tr([
                        html.Th("from"),
                        html.Th("to"),
                        html.Th("factor"),
                        html.Th("op"),
                        html.Th("ceil"),
                        html.Th("notes"),
                        html.Th(""),
                    ])),
                    html.Tbody(table_rows or [html.Tr([html.Td(colSpan=7, children="No rows yet")])]),
                ],
            ),
        ]),
    ])


@callback(
    Output("uc-preview-output", "children"),
    Input("uc-preview-input", "value"),
    Input("uc-factor", "value"),
    Input("uc-op", "value"),
    Input("uc-ceil", "checked"),
    Input("uc-from", "value"),
    Input("uc-to", "value"),
)
def _preview(val, factor, op, ceil, fu, tu):
    try:
        v = float(val or 0)
        f = float(factor or 0)
        out = _convert(v, f, op or "divide", bool(ceil))
        return dmc.Text(
            f"{v:g} {fu or 'X'} → {out:g} {tu or 'Y'}",
            size="sm", c="indigo", fw=600,
        )
    except (TypeError, ValueError):
        return dmc.Text("Invalid input.", size="sm", c="red")


@callback(
    Output("uc-msg", "children"),
    Input("uc-save", "n_clicks"),
    State("uc-from", "value"),
    State("uc-to", "value"),
    State("uc-factor", "value"),
    State("uc-op", "value"),
    State("uc-ceil", "checked"),
    State("uc-notes", "value"),
    prevent_initial_call=True,
)
def _save(_n, fu, tu, factor, op, ceil, notes):
    if not fu or not tu:
        return dmc.Alert(color="yellow", title="from_unit and to_unit required")
    try:
        api.put_unit_conversion(
            from_unit=str(fu).strip(),
            to_unit=str(tu).strip(),
            factor=float(factor or 0),
            operation=str(op or "divide"),
            ceil_result=bool(ceil),
            notes=str(notes) if notes else None,
        )
        return dmc.Alert(color="green", title="Saved — refresh the page.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Save failed", children=str(exc))


@callback(
    Output("uc-del-msg", "children"),
    Input({"type": "uc-del", "from": dash.ALL, "to": dash.ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def _delete(_clicks):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "uc-del":
        return dash.no_update
    fu = trig["from"]
    tu = trig["to"]
    try:
        api.delete_unit_conversion(fu, tu)
        return dmc.Alert(color="green", title=f"Deleted {fu} → {tu}. Refresh to update table.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Delete failed", children=str(exc))
