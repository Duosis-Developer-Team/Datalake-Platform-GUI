"""
Settings — CRM product category alias editor.

Maps discovery CRM products to category_code / GUI tab / resource unit for billing views.
Rows with source='auto' are seeded; PUT promotes to manual.

Route: /settings/crm/product-categories
"""
from __future__ import annotations

import dash
from dash import dcc, html, Input, Output, State, callback, ctx
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.services import api_client as api

dash.register_page(
    __name__,
    path="/settings/crm/product-categories",
    title="CRM Product Categories",
)


def _row_form(row: dict):
    pid = str(row.get("productid", ""))
    return html.Tr([
        html.Td(pid, style={"fontSize": "11px", "maxWidth": "100px", "overflow": "hidden", "textOverflow": "ellipsis"}),
        html.Td((row.get("product_name") or "-")[:80]),
        html.Td(
            dmc.TextInput(
                id={"type": "pcat-code", "index": pid},
                value=row.get("category_code") or "",
                size="xs",
                style={"minWidth": "120px"},
            )
        ),
        html.Td(
            dmc.TextInput(
                id={"type": "pcat-label", "index": pid},
                value=row.get("category_label") or "",
                size="xs",
                style={"minWidth": "140px"},
            )
        ),
        html.Td(
            dmc.TextInput(
                id={"type": "pcat-gui", "index": pid},
                value=row.get("gui_tab_binding") or "",
                size="xs",
                style={"minWidth": "160px"},
            )
        ),
        html.Td(
            dmc.TextInput(
                id={"type": "pcat-unit", "index": pid},
                value=row.get("resource_unit") or "",
                size="xs",
                style={"minWidth": "80px"},
            )
        ),
        html.Td(
            dmc.Badge(
                row.get("source") or "auto",
                color="teal" if row.get("source") == "manual" else "gray",
                size="sm",
            )
        ),
        html.Td(
            dmc.Button("Save", id={"type": "pcat-save", "index": pid}, size="xs", color="indigo", variant="light"),
        ),
    ])


def layout():
    rows = api.get_crm_product_categories()
    if not rows:
        body = dmc.Alert(
            color="yellow",
            title="No rows",
            children="Run seed_category_alias.py / SQL seed after CRM product sync.",
        )
    else:
        table = dmc.Table(
            striped=True,
            highlightOnHover=True,
            withTableBorder=True,
            children=[
                html.Thead(html.Tr([
                    html.Th("Product ID"),
                    html.Th("Product name"),
                    html.Th("category_code"),
                    html.Th("category_label"),
                    html.Th("gui_tab_binding"),
                    html.Th("resource_unit"),
                    html.Th("source"),
                    html.Th(""),
                ])),
                html.Tbody([_row_form(r) for r in rows]),
            ],
        )
        body = html.Div(style={"overflowX": "auto"}, children=[table])

    return html.Div(
        style={"padding": "30px"},
        children=[
            dmc.Group(
                gap="sm",
                mb="lg",
                children=[
                    dmc.ThemeIcon(
                        size="xl", variant="light", color="indigo", radius="md",
                        children=DashIconify(icon="solar:tag-price-bold-duotone", width=28),
                    ),
                    dmc.Stack(
                        gap=0,
                        children=[
                            dmc.Text("CRM product category aliases", fw=700, size="xl", c="#2B3674"),
                            dmc.Text(
                                "Controls how sales order lines roll up in customer Billing / efficiency panels.",
                                size="sm",
                                c="#A3AED0",
                            ),
                        ],
                    ),
                ],
            ),
            dcc.Store(id="pcat-save-trigger"),
            html.Div(id="pcat-save-feedback", style={"marginBottom": "12px"}),
            body,
        ],
    )


@callback(
    Output("pcat-save-feedback", "children"),
    Input({"type": "pcat-save", "index": dash.ALL}, "n_clicks"),
    State({"type": "pcat-code", "index": dash.ALL}, "value"),
    State({"type": "pcat-label", "index": dash.ALL}, "value"),
    State({"type": "pcat-gui", "index": dash.ALL}, "value"),
    State({"type": "pcat-unit", "index": dash.ALL}, "value"),
    State({"type": "pcat-save", "index": dash.ALL}, "id"),
    prevent_initial_call=True,
)
def _on_save_pcat(_n, codes, labels, guis, units, ids):
    if not ctx.triggered:
        return dash.no_update
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "pcat-save":
        return dash.no_update
    idx = trig.get("index")
    if not idx:
        return dash.no_update
    id_list = [i.get("index") for i in (ids or []) if isinstance(i, dict)]
    try:
        pos = id_list.index(idx)
    except ValueError:
        return dmc.Alert(color="red", title="Error", children="Row not found.")

    api.put_crm_product_category(
        str(idx),
        category_code=str((codes or [""])[pos] or ""),
        category_label=str((labels or [""])[pos] or ""),
        gui_tab_binding=str((guis or [""])[pos] or ""),
        resource_unit=str((units or [""])[pos] or ""),
    )
    return dmc.Alert(color="green", variant="light", title="Saved", children=f"Updated product {idx}")
