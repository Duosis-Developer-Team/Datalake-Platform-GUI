"""Integrations — CRM panel registry editor (gui_panel_definition).

Lists all sellable-potential panels and lets the operator add new ones or
update label/family/resource_kind/display_unit/sort_order/enabled/notes.
"""
from __future__ import annotations

from dash import Input, Output, State, callback, html
import dash_mantine_components as dmc

from src.services import api_client as api


_RESOURCE_KIND_DATA = [
    {"value": "cpu",     "label": "cpu"},
    {"value": "ram",     "label": "ram"},
    {"value": "storage", "label": "storage"},
    {"value": "other",   "label": "other"},
]


def build_layout(search: str | None = None) -> html.Div:
    rows = api.get_panel_definitions()
    table_rows = []
    for r in rows:
        table_rows.append(
            html.Tr([
                html.Td(str(r.get("panel_key") or "")),
                html.Td(str(r.get("label") or "")),
                html.Td(str(r.get("family") or "")),
                html.Td(str(r.get("resource_kind") or "")),
                html.Td(str(r.get("display_unit") or "")),
                html.Td(str(r.get("sort_order") or "")),
                html.Td("✓" if r.get("enabled", True) else "—"),
                html.Td(str(r.get("notes") or "")),
            ])
        )

    return html.Div([
        dmc.Stack(gap="xs", mb="md", children=[
            dmc.Title("Panel registry (sellable potential)", order=3),
            dmc.Text(
                "Each row is a panel that the C-level dashboard renders. Granular suffixes "
                "(_cpu, _ram, _storage) within the same family are constrained together via "
                "the per-environment resource ratio.",
                size="sm", c="dimmed",
            ),
        ]),
        dmc.Paper(p="md", radius="md", withBorder=True, mb="md", children=[
            dmc.Title("Add / update panel", order=5, mb="sm"),
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
            dmc.Title("Existing panels", order=5, mb="sm"),
            html.Table(
                className="table table-sm",
                style={"width": "100%", "borderCollapse": "collapse"},
                children=[
                    html.Thead(html.Tr([
                        html.Th("panel_key"),
                        html.Th("label"),
                        html.Th("family"),
                        html.Th("kind"),
                        html.Th("unit"),
                        html.Th("sort"),
                        html.Th("enabled"),
                        html.Th("notes"),
                    ])),
                    html.Tbody(table_rows or [html.Tr([html.Td(colSpan=8, children="No panels yet")])]),
                ],
            ),
        ]),
    ])


@callback(
    Output("pnl-msg", "children"),
    Input("pnl-save", "n_clicks"),
    State("pnl-key", "value"),
    State("pnl-label", "value"),
    State("pnl-family", "value"),
    State("pnl-kind", "value"),
    State("pnl-unit", "value"),
    State("pnl-sort", "value"),
    State("pnl-enabled", "checked"),
    State("pnl-notes", "value"),
    prevent_initial_call=True,
)
def _save_panel(_n, key, label, family, kind, unit, sort_order, enabled, notes):
    if not key:
        return dmc.Alert(color="yellow", title="panel_key required")
    if not label:
        return dmc.Alert(color="yellow", title="label required")
    if not family:
        return dmc.Alert(color="yellow", title="family required")
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
        return dmc.Alert(color="green", title="Saved — refresh the page to see it in the table.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Save failed", children=str(exc))
