"""C-level CRM Sellable Potential dashboard.

Route: ``/crm/sellable-potential``

Layout:
    * KPI ribbon (Total Potential TL, YTD Sales TL, Constrained Loss TL, Unmapped Products).
    * DC selector (single-select; "*" for all DCs).
    * Family roll-up cards: Total / Allocated / Sellable raw / Sellable
      constrained / Potential TL with capacity utilization gauges.
    * Sortable panel-level table (panel_key, label, unit, total, allocated,
      sellable_raw, sellable_constrained, unit_price_tl, potential_tl,
      ratio_bound rozet).
    * Trend graph for the selected panel (last 30 days from
      gui_metric_snapshot.crm.sellable_potential.* and family ratios).
    * Excel export (panel-level + family-level + KPIs in one workbook).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import dash
import dash_mantine_components as dmc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dcc, html
from dash_iconify import DashIconify

from src.services import api_client as api
from src.utils.export_helpers import (
    build_report_info_df,
    dash_send_excel_workbook,
    dataframes_to_excel_with_meta,
    records_to_dataframe,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------


_BRAND_PURPLE = "#552cf8"
_BRAND_PURPLE_LIGHT = "#a092ff"
_BRAND_GREEN = "#00b888"
_BRAND_ORANGE = "#f59f00"
_BRAND_GREY = "#A3AED0"


def _fmt_tl(value: float | int | None) -> str:
    try:
        return f"{float(value or 0):,.0f} TL"
    except (TypeError, ValueError):
        return "0 TL"


def _fmt_unit(value: float | int | None, unit: str) -> str:
    try:
        return f"{float(value or 0):,.0f} {unit}"
    except (TypeError, ValueError):
        return f"0 {unit}"


def _kpi_card(title: str, value: str, subtitle: str | None = None, *, color: str = _BRAND_PURPLE, icon: str | None = None) -> dmc.Card:
    return dmc.Card(
        withBorder=True,
        radius="md",
        padding="md",
        children=[
            dmc.Group(
                gap="sm",
                wrap="nowrap",
                children=[
                    DashIconify(icon=icon or "solar:chart-square-bold-duotone", width=28, color=color),
                    dmc.Stack(gap=2, children=[
                        dmc.Text(title, size="xs", c="dimmed", tt="uppercase", fw=600),
                        dmc.Text(value, size="xl", fw=800, c=color),
                        dmc.Text(subtitle or "", size="xs", c="dimmed"),
                    ]),
                ],
            ),
        ],
    )


def _family_card(family: dict[str, Any]) -> dmc.Card:
    label = family.get("label") or family.get("family") or "?"
    panels = family.get("panels") or []
    total_potential = float(family.get("total_potential_tl") or 0.0)
    constrained_loss = float(family.get("constrained_loss_tl") or 0.0)
    rows = []
    for p in panels:
        ratio_badge = (
            dmc.Badge("ratio-bound", color="orange", variant="light", size="xs")
            if p.get("ratio_bound") else None
        )
        rows.append(
            html.Tr([
                html.Td(p.get("resource_kind") or ""),
                html.Td(_fmt_unit(p.get("total"), p.get("display_unit") or "")),
                html.Td(_fmt_unit(p.get("allocated"), p.get("display_unit") or "")),
                html.Td(_fmt_unit(p.get("sellable_raw"), p.get("display_unit") or "")),
                html.Td([
                    _fmt_unit(p.get("sellable_constrained"), p.get("display_unit") or ""),
                    " ",
                    ratio_badge or "",
                ]),
                html.Td(_fmt_tl(p.get("potential_tl"))),
            ])
        )
    return dmc.Card(
        withBorder=True,
        radius="md",
        padding="md",
        children=[
            dmc.Group(justify="space-between", children=[
                dmc.Text(label, fw=700, size="md"),
                dmc.Group(gap="xs", children=[
                    dmc.Badge(_fmt_tl(total_potential), color="indigo", size="lg"),
                    dmc.Badge(f"loss {_fmt_tl(constrained_loss)}", color="red", variant="light", size="sm")
                    if constrained_loss > 0 else html.Span(),
                ]),
            ]),
            dmc.Space(h="xs"),
            html.Table(
                className="table table-sm",
                style={"width": "100%", "fontSize": "12px", "borderCollapse": "collapse"},
                children=[
                    html.Thead(html.Tr([
                        html.Th("kind"), html.Th("Total"), html.Th("Allocated"),
                        html.Th("Sellable raw"), html.Th("Sellable constrained"), html.Th("Potential"),
                    ])),
                    html.Tbody(rows or [html.Tr([html.Td(colSpan=6, children="No panels in this family yet")])]),
                ],
            ),
        ],
    )


def _panel_table(panels: list[dict[str, Any]]) -> dmc.ScrollArea:
    rows = []
    for p in panels:
        unit = p.get("display_unit") or ""
        ratio_badge = (
            dmc.Badge("ratio-bound", color="orange", variant="light", size="xs")
            if p.get("ratio_bound") else None
        )
        rows.append(
            html.Tr([
                html.Td(p.get("panel_key") or "", style={"fontFamily": "monospace", "fontSize": "11px"}),
                html.Td(p.get("label") or ""),
                html.Td(p.get("family") or ""),
                html.Td(p.get("resource_kind") or ""),
                html.Td(unit),
                html.Td(_fmt_unit(p.get("total"), unit)),
                html.Td(_fmt_unit(p.get("allocated"), unit)),
                html.Td(f"{float(p.get('threshold_pct') or 0):.0f}%"),
                html.Td(_fmt_unit(p.get("sellable_raw"), unit)),
                html.Td([_fmt_unit(p.get("sellable_constrained"), unit), " ", ratio_badge or ""]),
                html.Td(f"{float(p.get('unit_price_tl') or 0):,.2f}"),
                html.Td(_fmt_tl(p.get("potential_tl"))),
            ])
        )
    return dmc.ScrollArea(
        h=420,
        type="auto",
        children=html.Table(
            className="table table-sm",
            style={"width": "100%", "borderCollapse": "collapse", "fontSize": "12px"},
            children=[
                html.Thead(html.Tr([
                    html.Th("panel_key"), html.Th("label"), html.Th("family"),
                    html.Th("kind"), html.Th("unit"),
                    html.Th("Total"), html.Th("Allocated"), html.Th("Threshold"),
                    html.Th("Sellable raw"), html.Th("Sellable constrained"),
                    html.Th("Unit TL"), html.Th("Potential TL"),
                ])),
                html.Tbody(rows or [html.Tr([html.Td(colSpan=12, children="Run the snapshot job once data is available.")])]),
            ],
        ),
    )


def _trend_options(panels: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for p in panels:
        family = p.get("family") or ""
        kind = p.get("resource_kind") or ""
        if not family or not kind:
            continue
        # build the namespaced metric key the TaggingService writes:
        # virtualization.hyperconverged.ram.potential_tl etc.
        for measure in ("potential_tl", "sellable_constrained", "total"):
            ns = _family_namespace(family)
            key = f"{ns}.{kind}.{measure}"
            if key in seen:
                continue
            out.append({"value": key, "label": f"{p.get('label') or p.get('panel_key')} · {measure}"})
            seen.add(key)
    out.sort(key=lambda x: x["label"])
    return out


_FAMILY_NS_MAP = {
    "virt_hyperconverged":      "virtualization.hyperconverged",
    "virt_classic":             "virtualization.classic",
    "virt_power":               "virtualization.power",
    "virt_intel_hana":          "virtualization.intel_hana",
    "virt_power_hana":          "virtualization.power_hana",
    "backup_veeam_replication": "backup.veeam_replication",
    "backup_zerto_replication": "backup.zerto_replication",
    "backup_netbackup":         "backup.netbackup",
    "backup_image":             "backup.image",
    "backup_offsite":           "backup.offsite",
    "backup_remote":            "backup.remote",
    "backup_veeam":             "backup.veeam",
    "storage_s3":               "storage.s3",
    "firewall":                 "security.firewall",
    "loadbalancer":             "network.loadbalancer",
    "license_microsoft":        "licensing.microsoft",
    "license_redhat":           "licensing.redhat",
    "license_other":            "licensing.other",
    "network":                  "network",
    "dc_hosting":               "datacenter.hosting",
    "dc_energy":                "datacenter.energy",
    "mgmt_database":            "mgmt.database",
    "mgmt_os":                  "mgmt.os",
    "mgmt_monitoring":          "mgmt.monitoring",
    "mgmt_backup":              "mgmt.backup",
    "mgmt_security":            "mgmt.security",
    "mgmt_replication":         "mgmt.replication",
    "mgmt_misc":                "mgmt.misc",
    "public_cloud":             "public_cloud",
    "other":                    "other",
}


def _family_namespace(family: str) -> str:
    return _FAMILY_NS_MAP.get(family, family.replace("_", "."))


# ---------------------------------------------------------------------------
# Public entry — routed from app.py
# ---------------------------------------------------------------------------


def build_layout(visible_sections=None) -> html.Div:  # noqa: ARG001 - kept for sig parity
    summary = api.get_sellable_summary("*")
    families = summary.get("families") or []
    panels: list[dict[str, Any]] = []
    for f in families:
        panels.extend(f.get("panels") or [])
    panels.sort(key=lambda p: -float(p.get("potential_tl") or 0))

    kpi_ribbon = dmc.SimpleGrid(
        cols={"base": 1, "sm": 2, "md": 4},
        spacing="md",
        children=[
            _kpi_card(
                "Total Sellable Potential",
                _fmt_tl(summary.get("total_potential_tl")),
                "Sum across all families (constrained × unit price)",
                color=_BRAND_PURPLE, icon="solar:wallet-money-bold-duotone",
            ),
            _kpi_card(
                "YTD Sales (TL)",
                _fmt_tl(summary.get("ytd_sales_tl")),
                "Realised CRM orders converted to TL",
                color=_BRAND_GREEN, icon="solar:hand-money-bold-duotone",
            ),
            _kpi_card(
                "Ratio-bound Loss",
                _fmt_tl(summary.get("constrained_loss_tl")),
                "Potential lost because RAM/Storage caps CPU",
                color=_BRAND_ORANGE, icon="solar:scale-bold-duotone",
            ),
            _kpi_card(
                "Unmapped Products",
                f"{int(summary.get('unmapped_product_count') or 0):,}",
                "Catalog SKUs without a panel binding",
                color=_BRAND_GREY, icon="solar:question-circle-bold-duotone",
            ),
        ],
    )

    family_grid = dmc.SimpleGrid(
        cols={"base": 1, "lg": 2},
        spacing="md",
        children=[_family_card(f) for f in families]
        or [dmc.Card(withBorder=True, padding="md", children=dmc.Text("No families yet — verify panel definitions and infra-source bindings.", c="dimmed"))],
    )

    return html.Div(
        style={"maxWidth": "1440px", "margin": "0 auto", "padding": "12px"},
        children=[
            dcc.Store(id="sellable-store-summary", data=summary),
            dcc.Store(id="sellable-store-panels", data=panels),
            dcc.Download(id="sellable-export-download"),
            dmc.Paper(
                p="md",
                radius="md",
                withBorder=True,
                style={
                    "background": f"linear-gradient(135deg, {_BRAND_PURPLE} 0%, {_BRAND_PURPLE_LIGHT} 100%)",
                    "color": "#ffffff",
                    "marginBottom": "16px",
                },
                children=[
                    dmc.Group(justify="space-between", align="center", children=[
                        dmc.Stack(gap=2, children=[
                            dmc.Text("CRM › C-LEVEL DASHBOARD", size="xs", fw=700, c="white"),
                            dmc.Title("Sellable Potential", order=2, c="white"),
                            dmc.Text(
                                "Ne kadar kaynağım var, ne kadarını sattım, daha ne kadar satabilirim — "
                                "TL bazlı, threshold ve ratio-constrained görünüm.",
                                size="sm", c="white", style={"opacity": 0.9},
                            ),
                        ]),
                        dmc.Group(gap="xs", children=[
                            dmc.Select(
                                id="sellable-dc-select",
                                placeholder="Tüm DC'ler",
                                data=[{"value": "*", "label": "Tüm DC'ler"}],  # populated dynamically
                                value="*", size="sm",
                                style={"minWidth": "200px"},
                            ),
                            dmc.Button(
                                "Excel İndir",
                                id="sellable-export-btn",
                                leftSection=DashIconify(icon="solar:download-square-bold-duotone", width=16),
                                color="indigo",
                                variant="white",
                                size="sm",
                            ),
                        ]),
                    ]),
                ],
            ),
            kpi_ribbon,
            dmc.Space(h="md"),
            dmc.Title("Family roll-up", order=4, mb="sm"),
            family_grid,
            dmc.Space(h="lg"),
            dmc.Paper(
                p="md", radius="md", withBorder=True, mb="md",
                children=[
                    dmc.Title("Panel detail", order=4, mb="sm"),
                    _panel_table(panels),
                ],
            ),
            dmc.Paper(
                p="md", radius="md", withBorder=True, mb="md",
                children=[
                    dmc.Group(justify="space-between", align="center", mb="sm", children=[
                        dmc.Title("Trend (last 30 days)", order=4),
                        dmc.Select(
                            id="sellable-trend-metric",
                            label=None, size="sm",
                            placeholder="Bir metrik seç",
                            data=_trend_options(panels),
                            style={"minWidth": "320px"},
                        ),
                    ]),
                    dcc.Graph(
                        id="sellable-trend-chart",
                        config={"displayModeBar": False},
                        style={"height": "320px"},
                    ),
                ],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


@callback(
    Output("sellable-store-summary", "data"),
    Output("sellable-store-panels", "data"),
    Input("sellable-dc-select", "value"),
    prevent_initial_call=False,
)
def _refresh_data(dc_code: str | None):
    code = dc_code or "*"
    summary = api.get_sellable_summary(code)
    panels: list[dict[str, Any]] = []
    for f in summary.get("families") or []:
        panels.extend(f.get("panels") or [])
    panels.sort(key=lambda p: -float(p.get("potential_tl") or 0))
    return summary, panels


@callback(
    Output("sellable-trend-chart", "figure"),
    Input("sellable-trend-metric", "value"),
)
def _trend(metric_key: str | None):
    fig = go.Figure()
    if not metric_key:
        fig.update_layout(
            xaxis={"visible": False}, yaxis={"visible": False},
            annotations=[{"text": "Bir metric_key seç", "xref": "paper", "yref": "paper", "showarrow": False}],
            margin=dict(l=20, r=20, t=20, b=20),
        )
        return fig
    points = api.get_metric_snapshots(metric_key=metric_key, hours=24 * 30, scope_id="*") or []
    if not points:
        fig.update_layout(
            xaxis={"visible": False}, yaxis={"visible": False},
            annotations=[{"text": "Henüz snapshot yok — scheduler 15 dk'da bir yazıyor.", "xref": "paper", "yref": "paper", "showarrow": False}],
            margin=dict(l=20, r=20, t=20, b=20),
        )
        return fig
    xs = [p.get("captured_at") for p in points]
    ys = [float(p.get("value") or 0) for p in points]
    unit = points[-1].get("unit") if points else ""
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers", line=dict(color=_BRAND_PURPLE, width=2)))
    fig.update_layout(
        margin=dict(l=20, r=20, t=10, b=20),
        yaxis_title=unit,
        showlegend=False,
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
    )
    return fig


@callback(
    Output("sellable-export-download", "data"),
    Input("sellable-export-btn", "n_clicks"),
    State("sellable-store-summary", "data"),
    State("sellable-store-panels", "data"),
    State("sellable-dc-select", "value"),
    prevent_initial_call=True,
)
def _export(_n, summary, panels, dc_code):
    summary = summary or {}
    panels = panels or []
    families = summary.get("families") or []

    info_df = build_report_info_df(
        time_range=None,
        page_name="CRM Sellable Potential",
        extra_filters={"dc_code": dc_code or "*"},
    )

    kpi_df = pd.DataFrame([
        {"metric": "total_potential_tl",   "value": summary.get("total_potential_tl") or 0},
        {"metric": "ytd_sales_tl",         "value": summary.get("ytd_sales_tl") or 0},
        {"metric": "constrained_loss_tl",  "value": summary.get("constrained_loss_tl") or 0},
        {"metric": "unmapped_product_count", "value": summary.get("unmapped_product_count") or 0},
    ])

    families_df = records_to_dataframe([
        {
            "family": f.get("family"),
            "label": f.get("label"),
            "total_potential_tl": f.get("total_potential_tl"),
            "constrained_loss_tl": f.get("constrained_loss_tl"),
            "panel_count": len(f.get("panels") or []),
        }
        for f in families
    ])
    panels_df = records_to_dataframe(panels)

    sheets: dict[str, pd.DataFrame] = {
        "Report_Info": info_df,
        "KPIs": kpi_df,
        "Families": families_df,
        "Panels": panels_df,
    }

    buf = dataframes_to_excel_with_meta(sheets)
    fname = f"crm_sellable_potential_{dc_code or 'all'}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"
    return dash_send_excel_workbook(buf, fname)
