"""
Settings - CRM product to service page mapping (YAML seed in DB + operator overrides).

Route: /settings/integrations/crm/service-mapping

The previous version rendered one Select / TextInput / Save / Reset per product,
which was unusable with 200+ rows. This version uses a single Dash DataTable with
native filter / sort / pagination; selecting a row populates an editor form
above the table where the operator picks the page_key, sets notes, and saves
(or resets) the override.
"""
from __future__ import annotations

from dash import Input, Output, State, callback, dash_table, dcc, html, no_update
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.services import api_client as api


_BADGE_COLORS = {
    "override": "teal",
    "yaml": "gray",
    "unmatched": "orange",
}

_TABLE_ID = "svcmap-table"


def _mapping_rows() -> list[dict]:
    out: list[dict] = []
    for r in api.get_crm_service_mappings() or []:
        out.append({
            "productid":      str(r.get("productid", "")),
            "product_name":   str(r.get("product_name") or ""),
            "product_number": str(r.get("product_number") or ""),
            "category_code":  str(r.get("category_code") or ""),
            "source":         str(r.get("source") or "").lower(),
        })
    return out


def _page_options() -> list[dict]:
    pages = api.get_crm_service_mapping_pages() or []
    return [
        {"value": p.get("page_key", ""), "label": f"{p.get('page_key')} - {p.get('category_label', '')}"}
        for p in pages
        if p.get("page_key")
    ]


def build_layout(search: str | None = None) -> html.Div:
    rows = _mapping_rows()
    page_options = _page_options()

    if not rows:
        return html.Div(
            style={"padding": "30px"},
            children=dmc.Alert(
                color="yellow",
                title="No data",
                children="Run the webui-db migrations (001-004) and ensure discovery_crm_products is populated.",
            ),
        )

    unmatched_count = sum(1 for r in rows if r["source"] == "unmatched")
    yaml_count = sum(1 for r in rows if r["source"] == "yaml")
    override_count = sum(1 for r in rows if r["source"] == "override")

    summary_strip = dmc.Group(
        gap="xs",
        mb="md",
        children=[
            dmc.Badge(f"Total: {len(rows)}", color="indigo", variant="light", size="lg"),
            dmc.Badge(f"YAML: {yaml_count}", color="gray", variant="light", size="lg"),
            dmc.Badge(f"Override: {override_count}", color="teal", variant="light", size="lg"),
            dmc.Badge(
                f"UNMATCHED: {unmatched_count}",
                color="orange",
                variant="light" if unmatched_count else "outline",
                size="lg",
            ),
        ],
    )

    return html.Div(
        style={"padding": "30px"},
        children=[
            dmc.Group(
                gap="sm",
                mb="lg",
                children=[
                    dmc.ThemeIcon(
                        size="xl",
                        variant="light",
                        color="indigo",
                        radius="md",
                        children=DashIconify(icon="solar:widget-4-bold-duotone", width=28),
                    ),
                    dmc.Stack(
                        gap=0,
                        children=[
                            dmc.Text("CRM service mapping", fw=700, size="xl", c="#2B3674"),
                            dmc.Text(
                                "Each CRM product maps to exactly one WebUI panel via page_key. "
                                "YAML seed produces the default mapping; clicking a row loads it "
                                "into the editor below where you can save an override or reset it. "
                                "Use the column header inputs to filter; click headers to sort.",
                                size="sm",
                                c="#A3AED0",
                            ),
                        ],
                    ),
                ],
            ),
            summary_strip,
            dcc.Store(id="svcmap-dummy"),
            html.Div(id="svcmap-feedback", style={"marginBottom": "12px"}),
            dmc.Paper(
                p="md",
                radius="md",
                withBorder=True,
                mb="md",
                children=[
                    dmc.Group(
                        justify="space-between",
                        mb="sm",
                        children=[
                            dmc.Title("Edit selected mapping", order=5),
                            dmc.Group(
                                gap="xs",
                                children=[
                                    dmc.Button("Reset override", id="svcmap-reset", size="xs", color="gray", variant="subtle"),
                                ],
                            ),
                        ],
                    ),
                    dmc.Grid(
                        gutter="sm",
                        children=[
                            dmc.GridCol(
                                span={"base": 12, "md": 4},
                                children=dmc.TextInput(
                                    id="svcmap-product",
                                    label="Selected product",
                                    placeholder="Select a row to edit",
                                    size="xs",
                                    disabled=True,
                                ),
                            ),
                            dmc.GridCol(
                                span={"base": 12, "md": 4},
                                children=dmc.Select(
                                    id="svcmap-page",
                                    label="page_key",
                                    data=page_options,
                                    searchable=True,
                                    clearable=True,
                                    size="xs",
                                    placeholder="Select page_key...",
                                ),
                            ),
                            dmc.GridCol(
                                span={"base": 12, "md": 3},
                                children=dmc.TextInput(
                                    id="svcmap-notes",
                                    label="Notes",
                                    placeholder="Optional override note",
                                    size="xs",
                                ),
                            ),
                            dmc.GridCol(
                                span={"base": 12, "md": 1},
                                children=dmc.Button("Save", id="svcmap-save", size="xs", mt=22),
                            ),
                        ],
                    ),
                ],
            ),
            dash_table.DataTable(
                id=_TABLE_ID,
                data=rows,
                columns=[
                    {"name": "Product ID",   "id": "productid"},
                    {"name": "Name",         "id": "product_name"},
                    {"name": "Number",       "id": "product_number"},
                    {"name": "page_key",     "id": "category_code"},
                    {"name": "Source",       "id": "source"},
                ],
                row_selectable="single",
                selected_rows=[],
                page_size=25,
                filter_action="native",
                sort_action="native",
                sort_mode="multi",
                style_table={"overflowX": "auto"},
                style_cell={
                    "fontSize": "12px",
                    "fontFamily": "Inter, system-ui, sans-serif",
                    "padding": "6px 8px",
                    "textAlign": "left",
                    "whiteSpace": "normal",
                    "height": "auto",
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
                    {"if": {"filter_query": "{source} = 'unmatched'", "column_id": "source"},
                     "color": "#E8590C", "fontWeight": "700"},
                    {"if": {"filter_query": "{source} = 'override'", "column_id": "source"},
                     "color": "#0CA678", "fontWeight": "700"},
                ],
            ),
        ],
    )


@callback(
    Output("svcmap-product", "value", allow_duplicate=True),
    Output("svcmap-page",    "value", allow_duplicate=True),
    Output("svcmap-notes",   "value", allow_duplicate=True),
    Input(_TABLE_ID, "selected_rows"),
    State(_TABLE_ID, "data"),
    prevent_initial_call=True,
)
def _load_selected(selected, data):
    if not selected or not data:
        return ("", None, "")
    idx = selected[0]
    if idx is None or idx >= len(data):
        return no_update, no_update, no_update
    r = data[idx] or {}
    pid = r.get("productid") or ""
    label = r.get("product_name") or ""
    return (
        f"{pid} - {label[:60]}" if label else pid,
        r.get("category_code") or None,
        "",
    )


def _refresh_table_data(selected_pid: str | None) -> tuple[list[dict], list[int]]:
    rows = _mapping_rows()
    if not selected_pid:
        return rows, []
    for i, r in enumerate(rows):
        if r["productid"] == selected_pid:
            return rows, [i]
    return rows, []


@callback(
    Output("svcmap-feedback", "children"),
    Output(_TABLE_ID, "data", allow_duplicate=True),
    Output(_TABLE_ID, "selected_rows", allow_duplicate=True),
    Input("svcmap-save", "n_clicks"),
    State("svcmap-product", "value"),
    State("svcmap-page",    "value"),
    State("svcmap-notes",   "value"),
    prevent_initial_call=True,
)
def _save(_n, product_label, page_key, notes):
    if not product_label:
        return dmc.Alert(color="yellow", title="Select a row first."), no_update, no_update
    pid = str(product_label).split(" - ", 1)[0].strip()
    if not pid:
        return dmc.Alert(color="yellow", title="Select a row first."), no_update, no_update
    try:
        if not page_key:
            api.delete_crm_service_mapping_override(pid)
            msg = dmc.Alert(
                color="orange",
                variant="light",
                title="Marked unmatched",
                children=f"Cleared mapping for {pid}.",
            )
        else:
            api.put_crm_service_mapping(pid, page_key=str(page_key), notes=notes or None)
            msg = dmc.Alert(
                color="green",
                variant="light",
                title="Saved",
                children=f"Updated {pid} -> {page_key}",
            )
        rows, sel = _refresh_table_data(pid)
        return msg, rows, sel
    except Exception as exc:  # noqa: BLE001
        return (
            dmc.Alert(color="red", title="Save failed", children=str(exc)),
            no_update,
            no_update,
        )


@callback(
    Output("svcmap-feedback", "children", allow_duplicate=True),
    Output(_TABLE_ID, "data", allow_duplicate=True),
    Output(_TABLE_ID, "selected_rows", allow_duplicate=True),
    Input("svcmap-reset", "n_clicks"),
    State("svcmap-product", "value"),
    prevent_initial_call=True,
)
def _reset_override(_n, product_label):
    if not product_label:
        return dmc.Alert(color="yellow", title="Select a row first."), no_update, no_update
    pid = str(product_label).split(" - ", 1)[0].strip()
    if not pid:
        return dmc.Alert(color="yellow", title="Select a row first."), no_update, no_update
    try:
        api.delete_crm_service_mapping_override(pid)
        rows, sel = _refresh_table_data(pid)
        return (
            dmc.Alert(color="green", variant="light", title="Reset", children=f"Cleared override for {pid}"),
            rows,
            sel,
        )
    except Exception as exc:  # noqa: BLE001
        return (
            dmc.Alert(color="red", title="Reset failed", children=str(exc)),
            no_update,
            no_update,
        )
