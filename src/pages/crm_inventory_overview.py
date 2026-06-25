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
from dash import ALL, Input, Output, State, callback, ctx, dcc, html
from dash_iconify import DashIconify

from src.components.crm_inventory_report import build_report_body, prepare_service_row
from src.components.crm_inventory_shell import build_inventory_shell
from src.services import api_client as api
from src.utils.export_helpers import (
    build_report_info_df,
    dash_send_excel_workbook,
    dataframes_to_excel_with_meta,
    records_to_dataframe,
)

logger = logging.getLogger(__name__)


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
        mb="md",
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

    report_sections = build_report_body(payload, filter_mode="all", view_mode="grouped")

    return html.Div(
        style={"maxWidth": "1480px", "margin": "0 auto", "padding": "12px 16px 32px"},
        children=[
            dcc.Store(id="crm-inventory-store", data=payload),
            dcc.Download(id="crm-inventory-export-download"),
            build_inventory_shell(summary, unmapped),
            _unmapped_banner(summary, unmapped),
            html.Div(id="crm-inventory-report-body", children=report_sections),
        ],
    )


@callback(
    Output("crm-inventory-report-body", "children"),
    Input("crm-inventory-filter", "value"),
    Input("crm-inventory-search", "value"),
    Input("crm-inventory-view-mode", "value"),
    State("crm-inventory-store", "data"),
)
def _apply_report_filters(filter_mode, search, view_mode, store):
    if not store:
        return dash.no_update
    return build_report_body(
        store,
        filter_mode=filter_mode or "all",
        search_query=search,
        view_mode=view_mode or "grouped",
    )


@callback(
    Output("crm-inventory-filter", "value"),
    Input({"type": "crm-inv-kpi", "filter": ALL}, "n_clicks"),
    State({"type": "crm-inv-kpi", "filter": ALL}, "id"),
    State("crm-inventory-filter", "value"),
    prevent_initial_call=True,
)
def _kpi_filter_shortcut(clicks, ids, current):
    if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
        return dash.no_update
    triggered = ctx.triggered_id.get("filter")
    if not triggered:
        return dash.no_update
    if not any(clicks):
        return dash.no_update
    return triggered


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
