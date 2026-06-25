"""Global CRM inventory overview — capacity vs CRM sold vs infra used.

Route: ``/crm/inventory-overview``
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import dash
import dash_mantine_components as dmc
import pandas as pd
from dash import Input, Output, State, callback, dcc, html
from dash_iconify import DashIconify

from src.pages import crm_shared as shared
from src.services import api_client as api
from src.utils.export_helpers import (
    build_report_info_df,
    dash_send_excel_workbook,
    dataframes_to_excel_with_meta,
    records_to_dataframe,
)

logger = logging.getLogger(__name__)


def _family_card(family: dict[str, Any]) -> dmc.Card:
    label = family.get("label") or family.get("family") or "?"
    panels = family.get("panels") or []
    rows = []
    for p in panels:
        unit = p.get("display_unit") or ""
        total = p.get("total")
        bar = None
        if total is not None and p.get("has_infra_source"):
            bar = shared.capacity_bar(
                float(total),
                float(p.get("crm_sold_qty") or 0),
                float(p.get("used_qty") or 0),
                float(p.get("sellable_qty") or 0),
            )
        rows.append(
            html.Tr([
                html.Td(p.get("resource_kind") or ""),
                html.Td(shared.fmt_unit(p.get("total"), unit)),
                html.Td(shared.fmt_unit(p.get("crm_sold_qty"), unit)),
                html.Td(shared.fmt_unit(p.get("used_qty"), unit)),
                html.Td(shared.fmt_unit(p.get("sellable_qty"), unit)),
                html.Td(shared.status_badge(p.get("status"))),
                html.Td(shared.fmt_tl(p.get("potential_tl"))),
            ])
        )
        if bar is not None:
            rows.append(html.Tr([
                html.Td(colSpan=7, children=bar),
            ]))
    return dmc.Card(
        withBorder=True,
        radius="md",
        padding="md",
        children=[
            dmc.Text(label, fw=700, size="md", mb="xs"),
            html.Table(
                className="table table-sm",
                style={"width": "100%", "fontSize": "12px", "borderCollapse": "collapse"},
                children=[
                    html.Thead(html.Tr([
                        html.Th("kind"), html.Th("Total"), html.Th("CRM sold"),
                        html.Th("Used"), html.Th("Sellable"), html.Th("Status"), html.Th("Potential"),
                    ])),
                    html.Tbody(rows or [html.Tr([html.Td(colSpan=7, children="No panels in this family")])]),
                ],
            ),
        ],
    )


def _panel_table(panels: list[dict[str, Any]]) -> dmc.ScrollArea:
    rows = []
    for p in panels:
        unit = p.get("display_unit") or ""
        delta = p.get("delta_used_vs_crm")
        delta_txt = "—" if delta is None else f"{float(delta):+,.0f} {unit}".strip()
        rows.append(
            html.Tr([
                html.Td(p.get("panel_key") or "", style={"fontFamily": "monospace", "fontSize": "11px"}),
                html.Td(p.get("label") or ""),
                html.Td(p.get("family") or ""),
                html.Td(unit),
                html.Td(shared.fmt_unit(p.get("total"), unit)),
                html.Td(shared.fmt_unit(p.get("crm_sold_qty"), unit)),
                html.Td(shared.fmt_unit(p.get("used_qty"), unit)),
                html.Td(shared.fmt_unit(p.get("sellable_qty"), unit)),
                html.Td(delta_txt),
                html.Td(shared.status_badge(p.get("status"))),
                html.Td(shared.fmt_tl(p.get("potential_tl"))),
            ])
        )
    return dmc.ScrollArea(
        h=480,
        type="auto",
        children=html.Table(
            className="table table-sm",
            style={"width": "100%", "borderCollapse": "collapse", "fontSize": "12px"},
            children=[
                html.Thead(html.Tr([
                    html.Th("panel_key"), html.Th("label"), html.Th("family"), html.Th("unit"),
                    html.Th("Total"), html.Th("CRM sold"), html.Th("Used"), html.Th("Sellable"),
                    html.Th("Gap (used−CRM)"), html.Th("Status"), html.Th("Potential TL"),
                ])),
                html.Tbody(rows or [html.Tr([html.Td(colSpan=11, children="No data yet.")])]),
            ],
        ),
    )


def _crm_only_section(panels: list[dict[str, Any]]) -> html.Div | None:
    if not panels:
        return None
    rows = []
    for p in panels:
        unit = p.get("display_unit") or ""
        rows.append(html.Tr([
            html.Td(p.get("panel_key") or ""),
            html.Td(p.get("label") or ""),
            html.Td(shared.fmt_unit(p.get("crm_sold_qty"), unit)),
            html.Td(shared.fmt_tl(p.get("crm_sold_tl"))),
        ]))
    return dmc.Paper(
        p="md", radius="md", withBorder=True, mb="md",
        children=[
            dmc.Title("CRM-only services (no infra binding)", order=4, mb="sm"),
            dmc.Text(
                "These mapped CRM products have entitled sales but no infrastructure telemetry binding.",
                size="sm", c="dimmed", mb="sm",
            ),
            html.Table(
                className="table table-sm",
                style={"width": "100%", "fontSize": "12px"},
                children=[
                    html.Thead(html.Tr([
                        html.Th("panel_key"), html.Th("label"),
                        html.Th("CRM sold"), html.Th("CRM amount"),
                    ])),
                    html.Tbody(rows),
                ],
            ),
        ],
    )


def _unmapped_banner(summary: dict[str, Any], products: list[dict[str, Any]]) -> html.Div | None:
    count = int(summary.get("unmapped_entitled_count") or 0)
    catalog_unmapped = int(summary.get("unmapped_product_count") or 0)
    if count <= 0 and catalog_unmapped <= 0:
        return None
    top_products = ", ".join(
        str(p.get("product_name") or p.get("productid") or "?") for p in (products or [])[:5]
    )
    return dmc.Alert(
        title="Unmapped CRM products",
        color="orange",
        variant="light",
        icon=DashIconify(icon="solar:danger-triangle-bold-duotone", width=20),
        children=[
            dmc.Text(
                f"{catalog_unmapped} catalog SKU(s) lack panel mapping; "
                f"{count} entitled product line(s) are unmapped.",
                size="sm",
            ),
            dmc.Text(top_products or "", size="xs", c="dimmed", mt=4) if top_products else None,
        ],
    )


def build_layout_shell(visible_sections=None) -> html.Div:
    return html.Div([
        dcc.Store(
            id="crm-inventory-visible-sections",
            data=list(visible_sections) if visible_sections else None,
        ),
        dcc.Loading(
            id="crm-inventory-content-loading",
            type="circle", color="#4318FF", delay_show=150,
            children=html.Div(id="crm-inventory-page-root", style={"minHeight": "60vh", "padding": "0 8px"}),
        ),
    ])


@callback(
    Output("crm-inventory-page-root", "children"),
    Input("url", "pathname"),
    Input("app-time-range", "data"),
    State("crm-inventory-visible-sections", "data"),
)
def _fill_crm_inventory_content(pathname, time_range, visible_sections):
    if pathname != "/crm/inventory-overview":
        return dash.no_update
    return build_layout(visible_sections=visible_sections)


def build_layout(visible_sections=None) -> html.Div:  # noqa: ARG001
    payload = api.get_crm_inventory_overview("*")
    summary = payload.get("summary") or {}
    families = payload.get("families") or []
    panels = payload.get("panels") or []
    crm_only = payload.get("crm_only_panels") or []
    unmapped = payload.get("unmapped_products") or []

    kpi_ribbon = dmc.SimpleGrid(
        cols={"base": 1, "sm": 2, "md": 3, "lg": 6},
        spacing="md",
        children=[
            shared.kpi_card(
                "Infra panels",
                f"{int(summary.get('infra_panel_count') or 0):,}",
                f"of {int(summary.get('panel_count') or 0):,} mapped panels",
                color=shared.BRAND_PURPLE,
                icon="solar:server-bold-duotone",
            ),
            shared.kpi_card(
                "CRM entitled (TL)",
                shared.fmt_tl(summary.get("crm_entitled_tl")),
                "Active + invoiced order lines (global)",
                color=shared.BRAND_GREEN,
                icon="solar:hand-money-bold-duotone",
            ),
            shared.kpi_card(
                "Sellable potential",
                shared.fmt_tl(summary.get("total_potential_tl")),
                "Constrained × unit price",
                color=shared.BRAND_PURPLE_LIGHT,
                icon="solar:wallet-money-bold-duotone",
            ),
            shared.kpi_card(
                "Overage panels",
                f"{int(summary.get('overage_panel_count') or 0):,}",
                "Used exceeds CRM entitlement",
                color=shared.BRAND_RED,
                icon="solar:scale-bold-duotone",
            ),
            shared.kpi_card(
                "Unsold usage",
                f"{int(summary.get('unsold_usage_count') or 0):,}",
                "Infra used without CRM sales",
                color=shared.BRAND_ORANGE,
                icon="solar:shield-warning-bold-duotone",
            ),
            shared.kpi_card(
                "CRM-only services",
                f"{int(summary.get('crm_only_count') or 0):,}",
                "Sales without infra binding",
                color=shared.BRAND_GREY,
                icon="solar:cloud-bold-duotone",
            ),
        ],
    )

    note = summary.get("note") or ""
    family_grid = dmc.SimpleGrid(
        cols={"base": 1, "lg": 2},
        spacing="md",
        children=[_family_card(f) for f in families]
        or [dmc.Card(withBorder=True, padding="md", children=dmc.Text("No families yet.", c="dimmed"))],
    )

    return html.Div(
        style={"maxWidth": "1440px", "margin": "0 auto", "padding": "12px"},
        children=[
            dcc.Store(id="crm-inventory-store", data=payload),
            dcc.Download(id="crm-inventory-export-download"),
            dmc.Paper(
                p="md",
                radius="md",
                withBorder=True,
                style={
                    "background": f"linear-gradient(135deg, {shared.BRAND_PURPLE} 0%, {shared.BRAND_PURPLE_LIGHT} 100%)",
                    "color": "#ffffff",
                    "marginBottom": "16px",
                },
                children=[
                    dmc.Group(justify="space-between", align="center", children=[
                        dmc.Stack(gap=2, children=[
                            dmc.Text("CRM › GLOBAL OVERVIEW", size="xs", fw=700, c="white"),
                            dmc.Title("Capacity & Sales Inventory", order=2, c="white"),
                            dmc.Text(
                                "Total capacity, CRM entitled sales, actual infra usage, and sellable "
                                "remaining — all environments on one screen.",
                                size="sm", c="white", style={"opacity": 0.9},
                            ),
                        ]),
                        dmc.Button(
                            "Export Excel",
                            id="crm-inventory-export-btn",
                            leftSection=DashIconify(icon="solar:download-square-bold-duotone", width=16),
                            color="indigo",
                            variant="white",
                            size="sm",
                        ),
                    ]),
                ],
            ),
            _unmapped_banner(summary, unmapped),
            dmc.Space(h="sm"),
            kpi_ribbon,
            dmc.Text(note, size="xs", c="dimmed", mt="sm"),
            dmc.Space(h="md"),
            dmc.Title("By family", order=4, mb="sm"),
            family_grid,
            dmc.Space(h="lg"),
            dmc.Paper(
                p="md", radius="md", withBorder=True, mb="md",
                children=[
                    dmc.Title("All panels", order=4, mb="sm"),
                    _panel_table(panels),
                ],
            ),
            _crm_only_section(crm_only) or html.Div(),
        ],
    )


@callback(
    Output("crm-inventory-export-download", "data"),
    Input("crm-inventory-export-btn", "n_clicks"),
    State("crm-inventory-store", "data"),
    prevent_initial_call=True,
)
def _export_inventory(n_clicks, store):
    if not n_clicks or not store:
        return dash.no_update
    panels = store.get("panels") or []
    families = store.get("families") or []
    summary = store.get("summary") or {}
    crm_only = store.get("crm_only_panels") or []
    unmapped = store.get("unmapped_products") or []
    meta = build_report_info_df(
        title="CRM Inventory Overview",
        generated_at=datetime.now(timezone.utc).isoformat(),
        filters={"dc_code": store.get("dc_code") or "*"},
    )
    sheets = {
        "summary": pd.DataFrame([summary]),
        "panels": records_to_dataframe(panels),
        "families": records_to_dataframe(families),
        "crm_only": records_to_dataframe(crm_only),
        "unmapped": records_to_dataframe(unmapped),
        "meta": meta,
    }
    content = dataframes_to_excel_with_meta(sheets, sheet_order=[
        "summary", "panels", "families", "crm_only", "unmapped", "meta",
    ])
    return dash_send_excel_workbook(content, "crm-inventory-overview.xlsx")
