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

from src.components.crm_inventory_report import build_report_body, prepare_service_row
from src.pages import crm_shared as shared
from src.services import api_client as api
from src.utils.export_helpers import (
    build_report_info_df,
    dash_send_excel_workbook,
    dataframes_to_excel_with_meta,
    records_to_dataframe,
)

logger = logging.getLogger(__name__)

_FILTER_OPTIONS = [
    {"value": "all", "label": "All"},
    {"value": "infra", "label": "With infra"},
    {"value": "crm_only", "label": "CRM only"},
    {"value": "issues", "label": "Issues"},
]


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
    unmapped = payload.get("unmapped_products") or []

    kpi_ribbon = dmc.SimpleGrid(
        cols={"base": 1, "sm": 2, "md": 3, "lg": 6},
        spacing="md",
        children=[
            shared.kpi_card(
                "Infra panels",
                f"{int(summary.get('infra_panel_count') or 0):,}",
                f"of {int(summary.get('panel_count') or 0):,} mapped services",
                color=shared.BRAND_PURPLE,
                icon="solar:server-bold-duotone",
            ),
            shared.kpi_card(
                "CRM entitled (TL)",
                shared.fmt_tl(summary.get("crm_entitled_tl")),
                "Active + invoiced order lines",
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
                "Overage",
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
                "CRM-only",
                f"{int(summary.get('crm_only_count') or 0):,}",
                "No infra binding",
                color=shared.BRAND_GREY,
                icon="solar:cloud-bold-duotone",
            ),
        ],
    )

    report_sections = build_report_body(payload, filter_mode="all")

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
                            dmc.Text("CRM › GLOBAL REPORT", size="xs", fw=700, c="white"),
                            dmc.Title("Capacity & Sales Inventory", order=2, c="white"),
                            dmc.Text(
                                "Service-level report: total capacity, CRM entitled, used, free, and sellable.",
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
            dmc.Text(summary.get("note") or "", size="xs", c="dimmed", mt="sm"),
            dmc.Space(h="md"),
            dmc.Group(justify="space-between", align="center", mb="sm", children=[
                dmc.Title("Service inventory", order=4),
                dmc.SegmentedControl(
                    id="crm-inventory-filter",
                    value="all",
                    data=_FILTER_OPTIONS,
                    size="sm",
                ),
            ]),
            html.Div(id="crm-inventory-report-body", children=report_sections),
        ],
    )


@callback(
    Output("crm-inventory-report-body", "children"),
    Input("crm-inventory-filter", "value"),
    State("crm-inventory-store", "data"),
)
def _apply_report_filter(filter_mode, store):
    if not store:
        return dash.no_update
    return build_report_body(store, filter_mode=filter_mode or "all")


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
    summary = store.get("summary") or {}
    unmapped = store.get("unmapped_products") or []
    export_rows = []
    for p in panels:
        row = {**p, **prepare_service_row(p)}
        export_rows.append(row)
    meta = build_report_info_df(
        title="CRM Inventory Report",
        generated_at=datetime.now(timezone.utc).isoformat(),
        filters={"dc_code": store.get("dc_code") or "*"},
    )
    sheets = {
        "summary": pd.DataFrame([summary]),
        "services": records_to_dataframe(export_rows),
        "unmapped": records_to_dataframe(unmapped),
        "meta": meta,
    }
    content = dataframes_to_excel_with_meta(sheets, sheet_order=[
        "summary", "services", "unmapped", "meta",
    ])
    return dash_send_excel_workbook(content, "crm-inventory-report.xlsx")
