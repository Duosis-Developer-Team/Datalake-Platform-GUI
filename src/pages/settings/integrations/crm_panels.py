"""Integrations - CRM panel registry editor (gui_panel_definition).

Lists all sellable-potential panels with native DataTable filtering / sorting and
lets the operator add new ones, edit existing rows by clicking them, or reset
the form. Backend writes go through customer-api PUT /api/v1/crm/panels/{key}.
"""
from __future__ import annotations

from dash import Input, Output, State, callback, dash_table, html, no_update
import dash_mantine_components as dmc

from src.services import api_client as api


_RESOURCE_KIND_DATA = [
    {"value": "cpu",     "label": "cpu"},
    {"value": "ram",     "label": "ram"},
    {"value": "storage", "label": "storage"},
    {"value": "other",   "label": "other"},
]


_PANEL_TABLE_ID = "pnl-table"


def _panel_rows() -> list[dict]:
    """Normalise panel definitions into dicts the DataTable can render."""
    out: list[dict] = []
    for r in api.get_panel_definitions() or []:
        out.append({
            "panel_key":     str(r.get("panel_key") or ""),
            "label":         str(r.get("label") or ""),
            "family":        str(r.get("family") or ""),
            "resource_kind": str(r.get("resource_kind") or ""),
            "display_unit":  str(r.get("display_unit") or ""),
            "sort_order":    int(r.get("sort_order") or 0),
            "enabled":       bool(r.get("enabled", True)),
            "notes":         str(r.get("notes") or ""),
        })
    return out


def build_layout(search: str | None = None) -> html.Div:
    rows = _panel_rows()

    return html.Div([
        dmc.Stack(gap="xs", mb="md", children=[
            dmc.Title("Panel registry (sellable potential)", order=3),
            dmc.Text(
                "Each row is a panel that the C-level dashboard renders. Granular suffixes "
                "(_cpu, _ram, _storage) within the same family are constrained together via "
                "the per-environment resource ratio. Click a row to load it into the form for editing.",
                size="sm", c="dimmed",
            ),
        ]),
        dmc.Paper(p="md", radius="md", withBorder=True, mb="md", children=[
            dmc.Group(justify="space-between", mb="sm", children=[
                dmc.Title("Add / update panel", order=5),
                dmc.Button("Reset form", id="pnl-reset", size="xs", variant="subtle", color="gray"),
            ]),
            dmc.Grid(gutter="sm", children=[
                dmc.GridCol(span={"base": 12, "md": 3}, children=dmc.TextInput(id="pnl-key", label="panel_key", size="xs", placeholder="virt_classic_cpu")),
                dmc.GridCol(span={"base": 12, "md": 3}, children=dmc.TextInput(id="pnl-label", label="label", size="xs")),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.TextInput(id="pnl-family", label="family", size="xs", placeholder="virt_classic")),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.Select(id="pnl-kind", label="resource_kind", data=_RESOURCE_KIND_DATA, value="cpu", size="xs")),
                dmc.GridCol(span={"base": 12, "md": 1}, children=dmc.TextInput(id="pnl-unit", label="display_unit", size="xs", value="GB")),
                dmc.GridCol(span={"base": 12, "md": 1}, children=dmc.NumberInput(id="pnl-sort", label="sort_order", size="xs", value=100, min=0)),
                dmc.GridCol(span={"base": 12, "md": 6}, children=dmc.TextInput(id="pnl-notes", label="notes", size="xs")),
                dmc.GridCol(span={"base": 12, "md": 1}, children=dmc.Checkbox(id="pnl-enabled", label="enabled", checked=True)),
                dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.Button("Save", id="pnl-save", size="xs")),
            ]),
            html.Div(id="pnl-msg", style={"marginTop": "8px"}),
        ]),
        dmc.Paper(p="md", radius="md", withBorder=True, children=[
            dmc.Title("Existing panels", order=5, mb="xs"),
            dmc.Text(
                "Use the column header search boxes to filter, click any header to sort, "
                "and click a row to load it into the editor above.",
                size="xs", c="dimmed", mb="sm",
            ),
            dash_table.DataTable(
                id=_PANEL_TABLE_ID,
                data=rows,
                columns=[
                    {"name": "panel_key",     "id": "panel_key"},
                    {"name": "label",         "id": "label"},
                    {"name": "family",        "id": "family"},
                    {"name": "resource_kind", "id": "resource_kind"},
                    {"name": "display_unit",  "id": "display_unit"},
                    {"name": "sort_order",    "id": "sort_order", "type": "numeric"},
                    {"name": "enabled",       "id": "enabled"},
                    {"name": "notes",         "id": "notes"},
                ],
                row_selectable="single",
                selected_rows=[],
                page_size=20,
                filter_action="native",
                sort_action="native",
                sort_mode="multi",
                style_table={"overflowX": "auto"},
                style_cell={
                    "fontSize": "12px",
                    "fontFamily": "Inter, system-ui, sans-serif",
                    "padding": "6px 8px",
                    "textAlign": "left",
                },
                style_header={
                    "backgroundColor": "#F4F7FE",
                    "color": "#2B3674",
                    "fontWeight": "700",
                    "border": "none",
                },
                style_data_conditional=[
                    {"if": {"state": "selected"},
                     "backgroundColor": "rgba(67,24,255,0.08)",
                     "border": "1px solid #4318FF"},
                ],
            ),
        ]),
    ])


@callback(
    Output("pnl-key",     "value", allow_duplicate=True),
    Output("pnl-label",   "value", allow_duplicate=True),
    Output("pnl-family",  "value", allow_duplicate=True),
    Output("pnl-kind",    "value", allow_duplicate=True),
    Output("pnl-unit",    "value", allow_duplicate=True),
    Output("pnl-sort",    "value", allow_duplicate=True),
    Output("pnl-enabled", "checked", allow_duplicate=True),
    Output("pnl-notes",   "value", allow_duplicate=True),
    Input(_PANEL_TABLE_ID, "selected_rows"),
    State(_PANEL_TABLE_ID, "data"),
    prevent_initial_call=True,
)
def _load_selected_panel(selected, data):
    if not selected or not data:
        return [no_update] * 8
    idx = selected[0]
    if idx is None or idx >= len(data):
        return [no_update] * 8
    r = data[idx] or {}
    return (
        r.get("panel_key") or "",
        r.get("label") or "",
        r.get("family") or "",
        r.get("resource_kind") or "cpu",
        r.get("display_unit") or "GB",
        int(r.get("sort_order") or 100),
        bool(r.get("enabled")),
        r.get("notes") or "",
    )


@callback(
    Output("pnl-key",     "value", allow_duplicate=True),
    Output("pnl-label",   "value", allow_duplicate=True),
    Output("pnl-family",  "value", allow_duplicate=True),
    Output("pnl-kind",    "value", allow_duplicate=True),
    Output("pnl-unit",    "value", allow_duplicate=True),
    Output("pnl-sort",    "value", allow_duplicate=True),
    Output("pnl-enabled", "checked", allow_duplicate=True),
    Output("pnl-notes",   "value", allow_duplicate=True),
    Output(_PANEL_TABLE_ID, "selected_rows", allow_duplicate=True),
    Input("pnl-reset", "n_clicks"),
    prevent_initial_call=True,
)
def _reset_panel_form(_n):
    return ("", "", "", "cpu", "GB", 100, True, "", [])


@callback(
    Output("pnl-msg",       "children"),
    Output(_PANEL_TABLE_ID, "data"),
    Input("pnl-save", "n_clicks"),
    State("pnl-key", "value"),
    State("pnl-label", "value"),
    State("pnl-family", "value"),
    State("pnl-kind", "value"),
    State("pnl-unit", "value"),
    State("pnl-sort", "value"),
    State("pnl-enabled", "checked"),
    State("pnl-notes", "value"),
    State(_PANEL_TABLE_ID, "data"),
    prevent_initial_call=True,
)
def _save_panel(_n, key, label, family, kind, unit, sort_order, enabled, notes, current_rows):
    if not key:
        return dmc.Alert(color="yellow", title="panel_key required"), no_update
    if not label:
        return dmc.Alert(color="yellow", title="label required"), no_update
    if not family:
        return dmc.Alert(color="yellow", title="family required"), no_update
    try:
        api.put_panel_definition(
            panel_key=str(key).strip(),
            label=str(label).strip(),
            family=str(family).strip(),
            resource_kind=str(kind or "cpu"),
            display_unit=str(unit or "GB"),
            sort_order=int(sort_order or 100),
            enabled=bool(enabled),
            notes=str(notes) if notes else None,
        )
        return (
            dmc.Alert(color="green", title=f"Saved: {key}"),
            _panel_rows(),
        )
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Save failed", children=str(exc)), no_update
