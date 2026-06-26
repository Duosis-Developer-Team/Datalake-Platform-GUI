"""Global CRM inventory overview — capacity vs CRM sold vs infra used.

Route: ``/crm/inventory-overview``

Phase A: instant skeleton shell. Phase B: async fetch via ``_fill_crm_inventory_content``.
"""
from __future__ import annotations

import logging
from typing import Any

import dash
import dash_mantine_components as dmc
import pandas as pd
from dash import ALL, Input, Output, State, callback, ctx, dcc, html
from dash_iconify import DashIconify

from src.components.crm_inventory_loading import build_crm_inventory_loading_shell
from src.components.crm_inventory_report import (
    build_report_body,
    filter_by_search,
    filter_service_rows,
    prepare_service_row,
)
from src.components.crm_inventory_shell import build_inventory_shell
from src.services import api_client as api
from src.utils.export_helpers import (
    dash_send_excel_workbook,
    dash_send_pdf_workbook,
    dataframes_to_excel_with_meta,
    dataframes_to_pdf_with_meta,
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
    """Phase A: instant skeleton; Phase B fills ``crm-inventory-page-root`` via callback."""
    return html.Div([
        dcc.Store(
            id="crm-inventory-visible-sections",
            data=list(visible_sections) if visible_sections else None,
        ),
        dcc.Loading(
            id="crm-inventory-content-loading",
            type="circle", color="#4318FF", delay_show=150,
            children=html.Div(
                id="crm-inventory-page-root",
                style={"minHeight": "60vh", "padding": "0 8px"},
                children=build_crm_inventory_loading_shell(),
            ),
        ),
    ])


@callback(
    Output("crm-inventory-page-root", "children"),
    Input("url", "pathname"),
    State("crm-inventory-visible-sections", "data"),
)
def _fill_crm_inventory_content(pathname, visible_sections):
    """Phase B: fetch inventory overview off the initial render path."""
    if pathname != "/crm/inventory-overview":
        return dash.no_update
    del visible_sections  # reserved for future RBAC section gating
    try:
        payload = api.get_crm_inventory_overview("*")
    except Exception:  # noqa: BLE001
        logger.exception("CRM inventory overview fetch failed")
        return dmc.Alert(
            title="Inventory unavailable",
            color="red",
            children="Could not load CRM inventory overview. Please retry in a moment.",
        )
    return build_layout_content(payload)


def build_layout_content(payload: dict[str, Any]) -> html.Div:
    """Render inventory page from a pre-fetched API payload."""
    summary = payload.get("summary") or {}
    unmapped = payload.get("unmapped_products") or []
    report_sections = build_report_body(payload, filter_mode="all", view_mode="grouped")

    return html.Div(
        style={"maxWidth": "1480px", "margin": "0 auto", "padding": "12px 16px 32px"},
        children=[
            dcc.Store(id="crm-inventory-store", data=payload),
            dcc.Download(id="crm-inventory-export-download"),
            dcc.Download(id="crm-inventory-export-pdf-download"),
            build_inventory_shell(summary, unmapped),
            _unmapped_banner(summary, unmapped),
            html.Div(id="crm-inventory-report-body", children=report_sections),
        ],
    )


def build_layout(visible_sections=None) -> html.Div:  # noqa: ARG001
    """Synchronous layout builder (tests and legacy callers)."""
    payload = api.get_crm_inventory_overview("*")
    return build_layout_content(payload)


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


def _build_inventory_export_sheets(
    store: dict[str, Any],
    *,
    filter_mode: str = "all",
    search: str | None = None,
    view_mode: str = "grouped",
) -> dict[str, pd.DataFrame]:
    """Build Excel/PDF sheet dict from store respecting active UI filters."""
    panels = store.get("panels") or []
    filtered = filter_by_search(filter_service_rows(panels, filter_mode or "all"), search)
    if (filter_mode or "all").lower() == "crm_only":
        filtered = [r for r in filtered if (r.get("infra_binding") or "") == "crm_only"]
    export_rows = [{**p, **prepare_service_row(p)} for p in filtered]
    summary = dict(store.get("summary") or {})
    summary["export_filter"] = filter_mode or "all"
    summary["export_view_mode"] = view_mode or "grouped"
    summary["export_search"] = search or ""
    crm_only = store.get("crm_only_panels") or []
    unmapped = store.get("unmapped_products") or []
    families = store.get("families") or []
    crm_only_rows = [{**p, **prepare_service_row(p)} for p in crm_only]
    families_summary = [
        {
            "family": f.get("family"),
            "family_label": f.get("family_label"),
            "panel_count": f.get("panel_count"),
            "crm_entitled_tl": sum(float(r.get("crm_sold_tl") or 0) for r in (f.get("panels") or [])),
            "potential_tl": sum(float(r.get("potential_tl") or 0) for r in (f.get("panels") or [])),
        }
        for f in families
    ]
    return {
        "Summary": pd.DataFrame([summary]),
        "Services": records_to_dataframe(export_rows),
        "CRM_only": records_to_dataframe(crm_only_rows),
        "Unmapped": records_to_dataframe(unmapped),
        "Families_summary": records_to_dataframe(families_summary),
    }


@callback(
    Output("crm-inventory-export-download", "data"),
    Input("crm-inventory-export-btn", "n_clicks"),
    State("crm-inventory-store", "data"),
    State("crm-inventory-filter", "value"),
    State("crm-inventory-search", "value"),
    State("crm-inventory-view-mode", "value"),
    prevent_initial_call=True,
)
def _export_inventory(n_clicks, store, filter_mode, search, view_mode):
    if not n_clicks or not store:
        return dash.no_update
    sheets = _build_inventory_export_sheets(
        store,
        filter_mode=filter_mode or "all",
        search=search,
        view_mode=view_mode or "grouped",
    )
    content = dataframes_to_excel_with_meta(
        sheets,
        time_range=None,
        page_name="CRM Inventory",
        extra_filters={
            "dc_code": store.get("dc_code") or "*",
            "filter": filter_mode or "all",
            "view_mode": view_mode or "grouped",
            "search": search or "",
        },
    )
    return dash_send_excel_workbook(content, "crm-inventory-report.xlsx")


@callback(
    Output("crm-inventory-export-pdf-download", "data"),
    Input("crm-inventory-export-pdf-btn", "n_clicks"),
    State("crm-inventory-store", "data"),
    State("crm-inventory-filter", "value"),
    State("crm-inventory-search", "value"),
    State("crm-inventory-view-mode", "value"),
    prevent_initial_call=True,
)
def _export_inventory_pdf(n_clicks, store, filter_mode, search, view_mode):
    if not n_clicks or not store:
        return dash.no_update
    sheets = _build_inventory_export_sheets(
        store,
        filter_mode=filter_mode or "all",
        search=search,
        view_mode=view_mode or "grouped",
    )
    content = dataframes_to_pdf_with_meta(
        sheets,
        time_range=None,
        page_name="CRM Inventory",
        extra_filters={
            "dc_code": store.get("dc_code") or "*",
            "filter": filter_mode or "all",
            "view_mode": view_mode or "grouped",
            "search": search or "",
        },
    )
    return dash_send_pdf_workbook(content, "crm-inventory-report.pdf")
