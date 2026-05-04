"""Integrations - Panel infra-source binding editor (gui_panel_infra_source).

Lets the operator choose which datalake table/column supplies the total and
allocated values for each panel, optionally per DC. Selecting a panel auto-loads
its current binding into the form so the operator can edit (instead of starting
from blanks). The bindings table supports native filter / sort / row-select.
"""
from __future__ import annotations

from dash import Input, Output, State, callback, dash_table, html, no_update
import dash_mantine_components as dmc

from src.services import api_client as api


_INFRA_TABLE_ID = "ifs-table"


def _row_for(panel_key: str) -> dict:
    src = api.get_panel_infra_source(panel_key, "*") or {}
    return {
        "panel_key":        panel_key,
        "dc_code":          str(src.get("dc_code") or "*"),
        "source_table":     str(src.get("source_table") or ""),
        "total_column":     str(src.get("total_column") or ""),
        "total_unit":       str(src.get("total_unit") or ""),
        "allocated_table":  str(src.get("allocated_table") or ""),
        "allocated_column": str(src.get("allocated_column") or ""),
        "allocated_unit":   str(src.get("allocated_unit") or ""),
        "filter_clause":    str(src.get("filter_clause") or ""),
        "notes":            str(src.get("notes") or ""),
    }


def _all_rows() -> list[dict]:
    rows: list[dict] = []
    for p in api.get_panel_definitions() or []:
        pk = str(p.get("panel_key") or "")
        if not pk:
            continue
        rows.append(_row_for(pk))
    return rows


def build_layout(search: str | None = None) -> html.Div:
    rows = _all_rows()
    panel_options = [
        {"value": p["panel_key"], "label": p.get("label") or p["panel_key"]}
        for p in (api.get_panel_definitions() or [])
        if p.get("panel_key")
    ]

    return html.Div([
        dmc.Stack(gap="xs", mb="md", children=[
            dmc.Title("Panel infra-source bindings", order=3),
            dmc.Text(
                "Each panel pulls its 'total' capacity and 'allocated' provisioned amount from a "
                "datalake table/column. Use dc_code='*' for global defaults; per-DC rows override "
                "the global one. filter_clause may reference :dc_pattern, e.g. "
                "datacenter_name ILIKE :dc_pattern. Selecting a panel below loads its current "
                "binding so you can edit it.",
                size="sm", c="dimmed",
            ),
        ]),
        dmc.Paper(p="md", radius="md", withBorder=True, mb="md", children=[
            dmc.Group(justify="space-between", mb="sm", children=[
                dmc.Title("Bind a panel to datalake", order=5),
                dmc.Button("Reset form", id="ifs-reset", size="xs", variant="subtle", color="gray"),
            ]),
            dmc.Grid(gutter="sm", children=[
                dmc.GridCol(span={"base": 12, "md": 4}, children=dmc.Select(id="ifs-panel", label="panel_key (select to auto-fill existing binding)", data=panel_options, searchable=True, size="xs")),
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
            dmc.Title("Current bindings (global / *)", order=5, mb="xs"),
            dmc.Text(
                "Filter via column header inputs, sort by clicking headers, click a row to load it.",
                size="xs", c="dimmed", mb="sm",
            ),
            dash_table.DataTable(
                id=_INFRA_TABLE_ID,
                data=rows,
                columns=[
                    {"name": "panel_key",        "id": "panel_key"},
                    {"name": "dc",               "id": "dc_code"},
                    {"name": "source_table",     "id": "source_table"},
                    {"name": "total_column",     "id": "total_column"},
                    {"name": "total_unit",       "id": "total_unit"},
                    {"name": "allocated_table",  "id": "allocated_table"},
                    {"name": "allocated_column", "id": "allocated_column"},
                    {"name": "allocated_unit",   "id": "allocated_unit"},
                    {"name": "filter_clause",    "id": "filter_clause"},
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


def _form_fields_for(panel_key: str | None) -> tuple:
    """Fetch existing infra-source for `panel_key` and return form-tuple."""
    if not panel_key:
        return ("*", "", "", "", "", "", "", "", "")
    src = api.get_panel_infra_source(str(panel_key), "*") or {}
    return (
        str(src.get("dc_code") or "*"),
        str(src.get("source_table") or ""),
        str(src.get("total_column") or ""),
        str(src.get("total_unit") or ""),
        str(src.get("allocated_table") or ""),
        str(src.get("allocated_column") or ""),
        str(src.get("allocated_unit") or ""),
        str(src.get("filter_clause") or ""),
        str(src.get("notes") or ""),
    )


@callback(
    Output("ifs-dc",     "value", allow_duplicate=True),
    Output("ifs-stable", "value", allow_duplicate=True),
    Output("ifs-tcol",   "value", allow_duplicate=True),
    Output("ifs-tunit",  "value", allow_duplicate=True),
    Output("ifs-atable", "value", allow_duplicate=True),
    Output("ifs-acol",   "value", allow_duplicate=True),
    Output("ifs-aunit",  "value", allow_duplicate=True),
    Output("ifs-filter", "value", allow_duplicate=True),
    Output("ifs-notes",  "value", allow_duplicate=True),
    Input("ifs-panel", "value"),
    prevent_initial_call=True,
)
def _autofill_from_panel(panel_key):
    return _form_fields_for(panel_key)


@callback(
    Output("ifs-panel",  "value", allow_duplicate=True),
    Output("ifs-dc",     "value", allow_duplicate=True),
    Output("ifs-stable", "value", allow_duplicate=True),
    Output("ifs-tcol",   "value", allow_duplicate=True),
    Output("ifs-tunit",  "value", allow_duplicate=True),
    Output("ifs-atable", "value", allow_duplicate=True),
    Output("ifs-acol",   "value", allow_duplicate=True),
    Output("ifs-aunit",  "value", allow_duplicate=True),
    Output("ifs-filter", "value", allow_duplicate=True),
    Output("ifs-notes",  "value", allow_duplicate=True),
    Input(_INFRA_TABLE_ID, "selected_rows"),
    State(_INFRA_TABLE_ID, "data"),
    prevent_initial_call=True,
)
def _load_selected_row(selected, data):
    if not selected or not data:
        return [no_update] * 10
    idx = selected[0]
    if idx is None or idx >= len(data):
        return [no_update] * 10
    r = data[idx] or {}
    return (
        r.get("panel_key") or "",
        r.get("dc_code") or "*",
        r.get("source_table") or "",
        r.get("total_column") or "",
        r.get("total_unit") or "",
        r.get("allocated_table") or "",
        r.get("allocated_column") or "",
        r.get("allocated_unit") or "",
        r.get("filter_clause") or "",
        "",  # notes column not exposed in table; clear for safety
    )


@callback(
    Output("ifs-panel",  "value", allow_duplicate=True),
    Output("ifs-dc",     "value", allow_duplicate=True),
    Output("ifs-stable", "value", allow_duplicate=True),
    Output("ifs-tcol",   "value", allow_duplicate=True),
    Output("ifs-tunit",  "value", allow_duplicate=True),
    Output("ifs-atable", "value", allow_duplicate=True),
    Output("ifs-acol",   "value", allow_duplicate=True),
    Output("ifs-aunit",  "value", allow_duplicate=True),
    Output("ifs-filter", "value", allow_duplicate=True),
    Output("ifs-notes",  "value", allow_duplicate=True),
    Output(_INFRA_TABLE_ID, "selected_rows", allow_duplicate=True),
    Input("ifs-reset", "n_clicks"),
    prevent_initial_call=True,
)
def _reset_form(_n):
    return (None, "*", "", "", "", "", "", "", "", "", [])


@callback(
    Output("ifs-msg",        "children"),
    Output(_INFRA_TABLE_ID,  "data"),
    Input("ifs-save",   "n_clicks"),
    State("ifs-panel",  "value"),
    State("ifs-dc",     "value"),
    State("ifs-stable", "value"),
    State("ifs-tcol",   "value"),
    State("ifs-tunit",  "value"),
    State("ifs-atable", "value"),
    State("ifs-acol",   "value"),
    State("ifs-aunit",  "value"),
    State("ifs-filter", "value"),
    State("ifs-notes",  "value"),
    prevent_initial_call=True,
)
def _save_infra(_n, panel, dc, stable, tcol, tunit, atable, acol, aunit, filt, notes):
    if not panel:
        return dmc.Alert(color="yellow", title="panel_key required"), no_update
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
        return (
            dmc.Alert(color="green", title=f"Saved: {panel}"),
            _all_rows(),
        )
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Save failed", children=str(exc)), no_update
