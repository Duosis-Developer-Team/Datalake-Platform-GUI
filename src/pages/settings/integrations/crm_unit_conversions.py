"""Integrations - Unit conversion editor (gui_unit_conversion).

Operator-managed conversion table used by SellableService when datalake values
must be converted to the panel's display_unit before threshold/ratio math runs.
Examples: GHz -> vCPU divide 8 ceil; bytes -> GB divide 2^30. Native DataTable
filter / sort / row-select; click a row to edit it, use Delete button to remove.
"""
from __future__ import annotations

import math

import dash
from dash import Input, Output, State, callback, ctx, dash_table, html, no_update
import dash_mantine_components as dmc

from src.services import api_client as api


_OPS = [
    {"value": "divide",   "label": "divide"},
    {"value": "multiply", "label": "multiply"},
]

_UC_TABLE_ID = "uc-table"


def _conv_rows() -> list[dict]:
    out: list[dict] = []
    for r in api.get_unit_conversions() or []:
        out.append({
            "from_unit":   str(r.get("from_unit") or ""),
            "to_unit":     str(r.get("to_unit") or ""),
            "factor":      float(r.get("factor") or 0),
            "operation":   str(r.get("operation") or "divide"),
            "ceil_result": "yes" if r.get("ceil_result") else "no",
            "notes":       str(r.get("notes") or ""),
        })
    return out


def _convert(value: float, factor: float, op: str, ceil: bool) -> float:
    if factor <= 0:
        return 0.0
    out = value * factor if op == "multiply" else value / factor
    return float(math.ceil(out)) if ceil else out


def build_layout(search: str | None = None) -> html.Div:
    rows = _conv_rows()

    return html.Div([
        dmc.Stack(gap="xs", mb="md", children=[
            dmc.Title("Unit conversions", order=3),
            dmc.Text(
                "Operator-managed conversion factors. Examples: GHz -> vCPU divide 8 ceil "
                "(1 vCPU = 8 GHz, fractional rounds up); bytes -> GB divide 1073741824. "
                "Click a row to edit; the Delete button removes a pair.",
                size="sm", c="dimmed",
            ),
        ]),
        dmc.Paper(p="md", radius="md", withBorder=True, mb="md", children=[
            dmc.Group(justify="space-between", mb="sm", children=[
                dmc.Title("Add / update conversion", order=5),
                dmc.Group(gap="xs", children=[
                    dmc.Button("Reset form", id="uc-reset", size="xs", variant="subtle", color="gray"),
                    dmc.Button("Delete pair", id="uc-delete", size="xs", color="red", variant="light"),
                ]),
            ]),
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
            dmc.Title("Existing conversions", order=5, mb="xs"),
            dmc.Text("Filter via column header inputs, sort by clicking headers.", size="xs", c="dimmed", mb="sm"),
            dash_table.DataTable(
                id=_UC_TABLE_ID,
                data=rows,
                columns=[
                    {"name": "from",    "id": "from_unit"},
                    {"name": "to",      "id": "to_unit"},
                    {"name": "factor",  "id": "factor", "type": "numeric"},
                    {"name": "op",      "id": "operation"},
                    {"name": "ceil",    "id": "ceil_result"},
                    {"name": "notes",   "id": "notes"},
                ],
                row_selectable="single",
                selected_rows=[],
                page_size=20,
                filter_action="native",
                sort_action="native",
                sort_mode="multi",
                style_table={"overflowX": "auto"},
                style_cell={"fontSize": "12px", "padding": "6px 8px", "textAlign": "left"},
                style_header={"backgroundColor": "#F4F7FE", "color": "#2B3674", "fontWeight": "700", "border": "none"},
                style_data_conditional=[
                    {"if": {"state": "selected"},
                     "backgroundColor": "rgba(67,24,255,0.08)",
                     "border": "1px solid #4318FF"},
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
            f"{v:g} {fu or 'X'} -> {out:g} {tu or 'Y'}",
            size="sm", c="indigo", fw=600,
        )
    except (TypeError, ValueError):
        return dmc.Text("Invalid input.", size="sm", c="red")


@callback(
    Output("uc-from",   "value", allow_duplicate=True),
    Output("uc-to",     "value", allow_duplicate=True),
    Output("uc-factor", "value", allow_duplicate=True),
    Output("uc-op",     "value", allow_duplicate=True),
    Output("uc-ceil",   "checked", allow_duplicate=True),
    Output("uc-notes",  "value", allow_duplicate=True),
    Input(_UC_TABLE_ID, "selected_rows"),
    State(_UC_TABLE_ID, "data"),
    prevent_initial_call=True,
)
def _load_selected(selected, data):
    if not selected or not data:
        return [no_update] * 6
    idx = selected[0]
    if idx is None or idx >= len(data):
        return [no_update] * 6
    r = data[idx] or {}
    return (
        r.get("from_unit") or "",
        r.get("to_unit") or "",
        float(r.get("factor") or 0),
        r.get("operation") or "divide",
        str(r.get("ceil_result") or "no").lower() == "yes",
        r.get("notes") or "",
    )


@callback(
    Output("uc-from",   "value", allow_duplicate=True),
    Output("uc-to",     "value", allow_duplicate=True),
    Output("uc-factor", "value", allow_duplicate=True),
    Output("uc-op",     "value", allow_duplicate=True),
    Output("uc-ceil",   "checked", allow_duplicate=True),
    Output("uc-notes",  "value", allow_duplicate=True),
    Output(_UC_TABLE_ID, "selected_rows", allow_duplicate=True),
    Input("uc-reset", "n_clicks"),
    prevent_initial_call=True,
)
def _reset(_n):
    return ("", "", 8, "divide", True, "", [])


@callback(
    Output("uc-msg",     "children"),
    Output(_UC_TABLE_ID, "data", allow_duplicate=True),
    Input("uc-save",   "n_clicks"),
    State("uc-from",   "value"),
    State("uc-to",     "value"),
    State("uc-factor", "value"),
    State("uc-op",     "value"),
    State("uc-ceil",   "checked"),
    State("uc-notes",  "value"),
    prevent_initial_call=True,
)
def _save(_n, fu, tu, factor, op, ceil, notes):
    if not fu or not tu:
        return dmc.Alert(color="yellow", title="from_unit and to_unit required"), no_update
    try:
        api.put_unit_conversion(
            from_unit=str(fu).strip(),
            to_unit=str(tu).strip(),
            factor=float(factor or 0),
            operation=str(op or "divide"),
            ceil_result=bool(ceil),
            notes=str(notes) if notes else None,
        )
        return dmc.Alert(color="green", title=f"Saved {fu} -> {tu}"), _conv_rows()
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Save failed", children=str(exc)), no_update


@callback(
    Output("uc-del-msg", "children"),
    Output(_UC_TABLE_ID, "data", allow_duplicate=True),
    Input("uc-delete", "n_clicks"),
    State("uc-from",   "value"),
    State("uc-to",     "value"),
    prevent_initial_call=True,
)
def _delete(_n, fu, tu):
    if not fu or not tu:
        return dmc.Alert(color="yellow", title="Select a row first (or fill from/to in form)"), no_update
    try:
        api.delete_unit_conversion(str(fu), str(tu))
        return dmc.Alert(color="green", title=f"Deleted {fu} -> {tu}"), _conv_rows()
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Delete failed", children=str(exc)), no_update
