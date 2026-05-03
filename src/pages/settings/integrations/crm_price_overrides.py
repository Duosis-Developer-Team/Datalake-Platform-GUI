"""Integrations — CRM unit price overrides (gui_crm_price_override)."""

from __future__ import annotations

from dash import Input, Output, State, callback, html
import dash_mantine_components as dmc

from src.services import api_client as api


def build_layout(search: str | None = None) -> html.Div:
    overrides = api.get_crm_price_overrides()
    table_rows = []
    for r in overrides:
        table_rows.append(
            html.Tr(
                [
                    html.Td(str(r.get("productid") or ""), style={"fontSize": "11px", "wordBreak": "break-all"}),
                    html.Td((r.get("product_name") or "-")[:80]),
                    html.Td(str(r.get("unit_price_tl") or "")),
                    html.Td(str(r.get("resource_unit") or "")),
                    html.Td(str(r.get("currency") or "")),
                    html.Td(str(r.get("notes") or "")),
                ]
            )
        )

    return html.Div(
        [
            dmc.Stack(
                gap="xs",
                mb="md",
                children=[
                    dmc.Title("CRM price overrides", order=3),
                    dmc.Text(
                        "Used when `discovery_crm_productpricelevels` is empty or stale. Values feed catalog "
                        "valuation and efficiency coverage calculations on the customer-api.",
                        size="sm",
                        c="dimmed",
                    ),
                ],
            ),
            dmc.Paper(
                p="md",
                radius="md",
                withBorder=True,
                mb="md",
                children=[
                    dmc.Title("Create / replace override", order=5, mb="sm"),
                    dmc.Grid(
                        gutter="sm",
                        children=[
                            dmc.GridCol(span={"base": 12, "md": 5}, children=dmc.TextInput(id="po-pid", label="productid (GUID)", size="xs")),
                            dmc.GridCol(span={"base": 12, "md": 5}, children=dmc.TextInput(id="po-name", label="product_name (optional)", size="xs")),
                            dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.NumberInput(id="po-price", label="unit_price_tl", size="xs", min=0, value=0)),
                            dmc.GridCol(span={"base": 12, "md": 4}, children=dmc.TextInput(id="po-unit", label="resource_unit", size="xs")),
                            dmc.GridCol(span={"base": 12, "md": 4}, children=dmc.TextInput(id="po-ccy", label="currency", size="xs", value="TL")),
                            dmc.GridCol(span={"base": 12, "md": 4}, children=dmc.TextInput(id="po-notes", label="notes", size="xs")),
                            dmc.GridCol(span={"base": 12, "md": 2}, children=dmc.Button("Save", id="po-save", size="xs")),
                        ],
                    ),
                    html.Div(id="po-msg", style={"marginTop": "8px"}),
                ],
            ),
            dmc.Paper(
                p="md",
                radius="md",
                withBorder=True,
                children=[
                    dmc.Title("Current overrides", order=5, mb="sm"),
                    html.Table(
                        className="table table-sm",
                        style={"width": "100%", "borderCollapse": "collapse"},
                        children=[
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("productid"),
                                        html.Th("product_name"),
                                        html.Th("unit_price_tl"),
                                        html.Th("resource_unit"),
                                        html.Th("currency"),
                                        html.Th("notes"),
                                    ]
                                )
                            ),
                            html.Tbody(table_rows or [html.Tr([html.Td(colSpan=6, children="No overrides yet")])]),
                        ],
                    ),
                    dmc.Text("Refresh the page after saving to see updates.", size="xs", c="dimmed", mt="sm"),
                ],
            ),
        ]
    )


@callback(
    Output("po-msg", "children"),
    Input("po-save", "n_clicks"),
    State("po-pid", "value"),
    State("po-name", "value"),
    State("po-price", "value"),
    State("po-unit", "value"),
    State("po-ccy", "value"),
    State("po-notes", "value"),
    prevent_initial_call=True,
)
def _save_po(_n, pid, name, price, unit, ccy, notes):
    if not pid:
        return dmc.Alert(color="yellow", title="productid required")
    try:
        api.put_crm_price_override(
            str(pid),
            product_name=str(name) if name else None,
            unit_price_tl=float(price or 0),
            resource_unit=str(unit) if unit else None,
            currency=str(ccy) if ccy else "TL",
            notes=str(notes) if notes else None,
        )
        return dmc.Alert(color="green", title="Saved — refresh page to view table.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Save failed", children=str(exc))
