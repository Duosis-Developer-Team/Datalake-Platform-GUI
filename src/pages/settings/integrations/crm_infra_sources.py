"""Integrations — Panel infra-source binding editor (gui_panel_infra_source).

Lets the operator choose which datalake table/column supplies the total and
allocated values for each panel, optionally per DC.
"""
from __future__ import annotations

from dash import Input, Output, State, callback, html
import dash_mantine_components as dmc

from src.services import api_client as api


def build_layout(search: str | None = None) -> html.Div:
    panels = api.get_panel_definitions()

    table_rows = []
    for p in panels:
        pk = str(p.get("panel_key") or "")
        if not pk:
            continue
        src = api.get_panel_infra_source(pk, "*")
        table_rows.append(
            html.Tr([
                html.Td(pk),
                html.Td(str(src.get("dc_code") or "*")),
                html.Td(str(src.get("source_table") or "—")),
                html.Td(str(src.get("total_column") or "—")),
                html.Td(str(src.get("total_unit") or "—")),
                html.Td(str(src.get("allocated_table") or "—")),
                html.Td(str(src.get("allocated_column") or "—")),
                html.Td(str(src.get("allocated_unit") or "—")),
                html.Td(str(src.get("filter_clause") or "")),
            ])
        )

    panel_options = [{"value": p["panel_key"], "label": p.get("label") or p["panel_key"]} for p in panels if p.get("panel_key")]

    return html.Div([
        dmc.Stack(gap="xs", mb="md", children=[
            dmc.Title("Panel infra-source bindings", order=3),
            dmc.Text(
                "Each panel pulls its 'total' capacity and 'allocated' provisioned amount from a "
                "datalake table/column. Use dc_code='*' for global defaults; per-DC rows override "
                "the global one. filter_clause may reference :dc_pattern, e.g. "
                "datacenter_name ILIKE :dc_pattern.",
                size="sm", c="dimmed",
            ),
        ]),
        dmc.Paper(p="md", radius="md", withBorder=True, mb="md", children=[
            dmc.Title("Bind a panel to datalake", order=5, mb="sm"),
            dmc.Grid(gutter="sm", children=[
                dmc.GridCol(span={"base": 12, "md": 4}, children=dmc.Select(id="ifs-panel", label="panel_key", data=panel_options, searchable=True, size="xs")),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.TextInput(id="ifs-dc", label="dc_code", size="xs", value="*")),
                dmc.GridCol(span={"base": 12, "md": 3}, children=dmc.TextInput(id="ifs-stable", label="source_table", size="xs", placeholder="nutanix_cluster_metrics")),
                dmc.GridCol(span={"base": 12, "md": 3}, children=dmc.TextInput(id="ifs-tcol", label="total_column", size="xs", placeholder="total_memory_capacity")),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.TextInput(id="ifs-tunit", label="total_unit", size="xs", placeholder="bytes")),
                dmc.GridCol(span={"base": 12, "md": 3}, children=dmc.TextInput(id="ifs-atable", label="allocated_table", size="xs", placeholder="nutanix_vm_metrics")),
                dmc.GridCol(span={"base": 12, "md": 3}, children=dmc.TextInput(id="ifs-acol", label="allocated_column", size="xs")),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.TextInput(id="ifs-aunit", label="allocated_unit", size="xs")),
                dmc.GridCol(span={"base": 12, "md": 12}, children=dmc.TextInput(id="ifs-filter", label="filter_clause", size="xs", placeholder="datacenter_name ILIKE :dc_pattern")),
                dmc.GridCol(span={"base": 12, "md": 9}, children=dmc.TextInput(id="ifs-notes", label="notes", size="xs")),
                dmc.GridCol(span={"base": 12, "md": 3}, children=dmc.Button("Save", id="ifs-save", size="xs")),
            ]),
            html.Div(id="ifs-msg", style={"marginTop": "8px"}),
        ]),
        dmc.Paper(p="md", radius="md", withBorder=True, children=[
            dmc.Title("Current bindings (global / *)", order=5, mb="sm"),
            html.Table(
                className="table table-sm",
                style={"width": "100%", "borderCollapse": "collapse", "fontSize": "12px"},
                children=[
                    html.Thead(html.Tr([
                        html.Th("panel_key"),
                        html.Th("dc"),
                        html.Th("total table"),
                        html.Th("total col"),
                        html.Th("total unit"),
                        html.Th("alloc table"),
                        html.Th("alloc col"),
                        html.Th("alloc unit"),
                        html.Th("filter"),
                    ])),
                    html.Tbody(table_rows or [html.Tr([html.Td(colSpan=9, children="No panels yet")])]),
                ],
            ),
        ]),
    ])


@callback(
    Output("ifs-msg", "children"),
    Input("ifs-save", "n_clicks"),
    State("ifs-panel", "value"),
    State("ifs-dc", "value"),
    State("ifs-stable", "value"),
    State("ifs-tcol", "value"),
    State("ifs-tunit", "value"),
    State("ifs-atable", "value"),
    State("ifs-acol", "value"),
    State("ifs-aunit", "value"),
    State("ifs-filter", "value"),
    State("ifs-notes", "value"),
    prevent_initial_call=True,
)
def _save_infra(_n, panel, dc, stable, tcol, tunit, atable, acol, aunit, filt, notes):
    if not panel:
        return dmc.Alert(color="yellow", title="panel_key required")
    try:
        api.put_panel_infra_source(
            panel_key=str(panel),
            dc_code=str(dc or "*"),
            source_table=stable or None,
            total_column=tcol or None,
            total_unit=tunit or None,
            allocated_table=atable or None,
            allocated_column=acol or None,
            allocated_unit=aunit or None,
            filter_clause=filt or None,
            notes=notes or None,
        )
        return dmc.Alert(color="green", title="Saved — refresh the page to see updated rows.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Save failed", children=str(exc))
