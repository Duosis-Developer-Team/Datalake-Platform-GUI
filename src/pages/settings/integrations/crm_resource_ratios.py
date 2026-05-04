"""Integrations - Per-environment CPU:RAM:Storage ratio editor.

Backed by gui_panel_resource_ratio. SellableService applies the family's ratio
to constrain the per-resource sellable_raw values, e.g. for virt_hyperconverged
the default is 1 CPU : 8 GB RAM : 100 GB Storage so the scarcest resource caps
the others. Native DataTable filter / sort / row-select; click a row to edit it.
"""
from __future__ import annotations

from dash import Input, Output, State, callback, dash_table, html, no_update
import dash_mantine_components as dmc

from src.services import api_client as api


_RATIO_TABLE_ID = "rr-table"


def _ratio_rows() -> list[dict]:
    out: list[dict] = []
    for r in api.get_resource_ratios() or []:
        out.append({
            "family":              str(r.get("family") or ""),
            "dc_code":             str(r.get("dc_code") or "*"),
            "cpu_per_unit":        float(r.get("cpu_per_unit") or 0),
            "ram_gb_per_unit":     float(r.get("ram_gb_per_unit") or 0),
            "storage_gb_per_unit": float(r.get("storage_gb_per_unit") or 0),
            "notes":               str(r.get("notes") or ""),
            "updated_by":          str(r.get("updated_by") or ""),
        })
    return out


def _live_preview(cpu: float, ram: float, sto: float, sellable_cpu: float = 10, sellable_ram: float = 100, sellable_sto: float = 1000) -> str:
    if cpu <= 0 or ram <= 0 or sto <= 0:
        return "ratios must be > 0"
    eff_cpu = sellable_cpu / cpu
    eff_ram = sellable_ram / ram
    eff_sto = sellable_sto / sto
    n = min(eff_cpu, eff_ram, eff_sto)
    return (
        f"Example: raw {sellable_cpu} CPU / {sellable_ram} GB RAM / {sellable_sto} GB Storage -> "
        f"effective units = min({eff_cpu:.1f}, {eff_ram:.1f}, {eff_sto:.1f}) = {n:.1f} -> "
        f"constrained {n*cpu:.1f} CPU / {n*ram:.1f} GB RAM / {n*sto:.1f} GB Storage."
    )


def build_layout(search: str | None = None) -> html.Div:
    rows = _ratio_rows()

    return html.Div([
        dmc.Stack(gap="xs", mb="md", children=[
            dmc.Title("Resource ratios", order=3),
            dmc.Text(
                "Per-environment CPU : RAM : Storage proportionality. The C-level dashboard "
                "constrains every resource so that the scarcest one caps the family's "
                "sellable potential. dc_code='*' is the default; per-DC rows override it. "
                "Click a row to load it into the form.",
                size="sm", c="dimmed",
            ),
        ]),
        dmc.Paper(p="md", radius="md", withBorder=True, mb="md", children=[
            dmc.Group(justify="space-between", mb="sm", children=[
                dmc.Title("Add / update ratio", order=5),
                dmc.Button("Reset form", id="rr-reset", size="xs", variant="subtle", color="gray"),
            ]),
            dmc.Grid(gutter="sm", children=[
                dmc.GridCol(span={"base": 12, "md": 3}, children=dmc.TextInput(id="rr-family", label="family", size="xs", placeholder="virt_hyperconverged")),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.TextInput(id="rr-dc", label="dc_code", size="xs", value="*")),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.NumberInput(id="rr-cpu", label="CPU per unit", size="xs", value=1, min=0)),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.NumberInput(id="rr-ram", label="RAM GB per unit", size="xs", value=8, min=0)),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.NumberInput(id="rr-sto", label="Storage GB per unit", size="xs", value=100, min=0)),
                dmc.GridCol(span={"base": 12, "md": 1}, children=dmc.Button("Save", id="rr-save", size="xs")),
                dmc.GridCol(span={"base": 12, "md": 12}, children=dmc.TextInput(id="rr-notes", label="notes", size="xs")),
            ]),
            html.Div(id="rr-preview", style={"marginTop": "8px"}, children=dmc.Text(_live_preview(1, 8, 100), size="sm", c="indigo")),
            html.Div(id="rr-msg", style={"marginTop": "8px"}),
        ]),
        dmc.Paper(p="md", radius="md", withBorder=True, children=[
            dmc.Title("Existing ratios", order=5, mb="xs"),
            dmc.Text("Filter via the column header inputs and sort by clicking headers.", size="xs", c="dimmed", mb="sm"),
            dash_table.DataTable(
                id=_RATIO_TABLE_ID,
                data=rows,
                columns=[
                    {"name": "family",              "id": "family"},
                    {"name": "dc_code",             "id": "dc_code"},
                    {"name": "cpu_per_unit",        "id": "cpu_per_unit",        "type": "numeric"},
                    {"name": "ram_gb_per_unit",     "id": "ram_gb_per_unit",     "type": "numeric"},
                    {"name": "storage_gb_per_unit", "id": "storage_gb_per_unit", "type": "numeric"},
                    {"name": "notes",               "id": "notes"},
                    {"name": "updated_by",          "id": "updated_by"},
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
    Output("rr-preview", "children"),
    Input("rr-cpu", "value"),
    Input("rr-ram", "value"),
    Input("rr-sto", "value"),
)
def _preview(cpu, ram, sto):
    try:
        return dmc.Text(_live_preview(float(cpu or 0), float(ram or 0), float(sto or 0)), size="sm", c="indigo")
    except (TypeError, ValueError):
        return dmc.Text("Invalid input - enter numeric ratios.", size="sm", c="red")


@callback(
    Output("rr-family", "value", allow_duplicate=True),
    Output("rr-dc",     "value", allow_duplicate=True),
    Output("rr-cpu",    "value", allow_duplicate=True),
    Output("rr-ram",    "value", allow_duplicate=True),
    Output("rr-sto",    "value", allow_duplicate=True),
    Output("rr-notes",  "value", allow_duplicate=True),
    Input(_RATIO_TABLE_ID, "selected_rows"),
    State(_RATIO_TABLE_ID, "data"),
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
        r.get("family") or "",
        r.get("dc_code") or "*",
        float(r.get("cpu_per_unit") or 0),
        float(r.get("ram_gb_per_unit") or 0),
        float(r.get("storage_gb_per_unit") or 0),
        r.get("notes") or "",
    )


@callback(
    Output("rr-family", "value", allow_duplicate=True),
    Output("rr-dc",     "value", allow_duplicate=True),
    Output("rr-cpu",    "value", allow_duplicate=True),
    Output("rr-ram",    "value", allow_duplicate=True),
    Output("rr-sto",    "value", allow_duplicate=True),
    Output("rr-notes",  "value", allow_duplicate=True),
    Output(_RATIO_TABLE_ID, "selected_rows", allow_duplicate=True),
    Input("rr-reset", "n_clicks"),
    prevent_initial_call=True,
)
def _reset(_n):
    return ("", "*", 1, 8, 100, "", [])


@callback(
    Output("rr-msg",        "children"),
    Output(_RATIO_TABLE_ID, "data"),
    Input("rr-save",   "n_clicks"),
    State("rr-family", "value"),
    State("rr-dc",     "value"),
    State("rr-cpu",    "value"),
    State("rr-ram",    "value"),
    State("rr-sto",    "value"),
    State("rr-notes",  "value"),
    prevent_initial_call=True,
)
def _save(_n, family, dc, cpu, ram, sto, notes):
    if not family:
        return dmc.Alert(color="yellow", title="family required"), no_update
    try:
        api.put_resource_ratio(
            family=str(family).strip(),
            dc_code=str(dc or "*"),
            cpu_per_unit=float(cpu or 0),
            ram_gb_per_unit=float(ram or 0),
            storage_gb_per_unit=float(sto or 0),
            notes=str(notes) if notes else None,
        )
        return dmc.Alert(color="green", title=f"Saved: {family}"), _ratio_rows()
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Save failed", children=str(exc)), no_update
