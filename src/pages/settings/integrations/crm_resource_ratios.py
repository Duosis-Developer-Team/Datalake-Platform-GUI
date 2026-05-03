"""Integrations — Per-environment CPU:RAM:Storage ratio editor.

Backed by gui_panel_resource_ratio. The SellableService applies the family's
ratio to constrain the per-resource sellable_raw values, e.g. for
virt_hyperconverged the default is 1 CPU : 8 GB RAM : 100 GB Storage so the
scarcest resource caps the others.
"""
from __future__ import annotations

from dash import Input, Output, State, callback, html
import dash_mantine_components as dmc

from src.services import api_client as api


def _live_preview(cpu: float, ram: float, sto: float, sellable_cpu: float = 10, sellable_ram: float = 100, sellable_sto: float = 1000) -> str:
    if cpu <= 0 or ram <= 0 or sto <= 0:
        return "ratios must be > 0"
    eff_cpu = sellable_cpu / cpu
    eff_ram = sellable_ram / ram
    eff_sto = sellable_sto / sto
    n = min(eff_cpu, eff_ram, eff_sto)
    return (
        f"Example: raw {sellable_cpu} CPU / {sellable_ram} GB RAM / {sellable_sto} GB Storage → "
        f"effective units = min({eff_cpu:.1f}, {eff_ram:.1f}, {eff_sto:.1f}) = {n:.1f} → "
        f"constrained {n*cpu:.1f} CPU / {n*ram:.1f} GB RAM / {n*sto:.1f} GB Storage."
    )


def build_layout(search: str | None = None) -> html.Div:
    rows = api.get_resource_ratios()
    table_rows = []
    for r in rows:
        table_rows.append(
            html.Tr([
                html.Td(str(r.get("family") or "")),
                html.Td(str(r.get("dc_code") or "*")),
                html.Td(f"{float(r.get('cpu_per_unit') or 0):g}"),
                html.Td(f"{float(r.get('ram_gb_per_unit') or 0):g}"),
                html.Td(f"{float(r.get('storage_gb_per_unit') or 0):g}"),
                html.Td(str(r.get("notes") or "")),
                html.Td(str(r.get("updated_by") or "")),
            ])
        )

    return html.Div([
        dmc.Stack(gap="xs", mb="md", children=[
            dmc.Title("Resource ratios", order=3),
            dmc.Text(
                "Per-environment CPU : RAM : Storage proportionality. The C-level dashboard "
                "constrains every resource so that the scarcest one caps the family's "
                "sellable potential. dc_code='*' is the default; per-DC rows override it.",
                size="sm", c="dimmed",
            ),
        ]),
        dmc.Paper(p="md", radius="md", withBorder=True, mb="md", children=[
            dmc.Title("Add / update ratio", order=5, mb="sm"),
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
            dmc.Title("Existing ratios", order=5, mb="sm"),
            html.Table(
                className="table table-sm",
                style={"width": "100%", "borderCollapse": "collapse"},
                children=[
                    html.Thead(html.Tr([
                        html.Th("family"),
                        html.Th("dc_code"),
                        html.Th("cpu_per_unit"),
                        html.Th("ram_gb_per_unit"),
                        html.Th("storage_gb_per_unit"),
                        html.Th("notes"),
                        html.Th("updated_by"),
                    ])),
                    html.Tbody(table_rows or [html.Tr([html.Td(colSpan=7, children="No rows yet")])]),
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
        return dmc.Text("Invalid input — enter numeric ratios.", size="sm", c="red")


@callback(
    Output("rr-msg", "children"),
    Input("rr-save", "n_clicks"),
    State("rr-family", "value"),
    State("rr-dc", "value"),
    State("rr-cpu", "value"),
    State("rr-ram", "value"),
    State("rr-sto", "value"),
    State("rr-notes", "value"),
    prevent_initial_call=True,
)
def _save(_n, family, dc, cpu, ram, sto, notes):
    if not family:
        return dmc.Alert(color="yellow", title="family required")
    try:
        api.put_resource_ratio(
            family=str(family).strip(),
            dc_code=str(dc or "*"),
            cpu_per_unit=float(cpu or 0),
            ram_gb_per_unit=float(ram or 0),
            storage_gb_per_unit=float(sto or 0),
            notes=str(notes) if notes else None,
        )
        return dmc.Alert(color="green", title="Saved — refresh the page to see updates.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Save failed", children=str(exc))
