from __future__ import annotations
from typing import Iterable

from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objects as go

from src.utils.format_units import smart_bytes, pct_float
from src.components.charts import create_premium_gauge_chart
from src.components.backup_jobs_section import build_job_stats_section


def _unique_jobs_section(vendor: str, *, category: str | None = None, scope: str = "dc"):
    """Lazy import avoids circular dependency with backup_unique_jobs_panel."""
    from src.components.backup_unique_jobs_panel import build_unique_jobs_inventory_section

    return build_unique_jobs_inventory_section(vendor, category=category, scope=scope)



def _kpi_card(title: str, value: str, icon: str, color: str = "indigo"):
    """Compact KPI card — fills its grid cell."""
    return dmc.Paper(
        className="nexus-card dc-kpi-card",
        shadow="sm",
        radius="md",
        withBorder=False,
        style={
            "padding": "14px 16px",
            "height": "100%",
            "boxSizing": "border-box",
            "display": "flex",
            "alignItems": "center",
        },
        children=[
            dmc.Group(
                gap="sm",
                align="center",
                children=[
                    dmc.ThemeIcon(
                        size="lg",
                        radius="xl",
                        variant="light",
                        color=color,
                        children=DashIconify(icon=icon, width=20),
                    ),
                    html.Div(
                        children=[
                            html.Div(
                                title,
                                style={
                                    "fontSize": "0.72rem",
                                    "color": "#A3AED0",
                                    "marginBottom": "2px",
                                    "lineHeight": 1.2,
                                    "textTransform": "uppercase",
                                    "letterSpacing": "0.03em",
                                    "fontWeight": 600,
                                },
                            ),
                            html.Div(
                                value,
                                style={
                                    "fontSize": "1.1rem",
                                    "color": "#2B3674",
                                    "fontWeight": 800,
                                    "lineHeight": 1.2,
                                    "letterSpacing": "-0.01em",
                                },
                            ),
                        ]
                    ),
                ],
            ),
        ],
    )


def _format_scaled(value: float, base_unit: str) -> str:
    """
    Scale numeric value so that the integer part stays within 3 digits,
    with two decimal places. Units are scaled in powers of 1024:
    MB → GB → TB → PB, GB → TB → PB, TB → PB.
    """
    v = float(value or 0.0)
    unit = base_unit
    abs_v = abs(v)

    if base_unit == "MB":
        if abs_v >= 1000:
            v /= 1024.0
            unit = "GB"
            abs_v = abs(v)
        if abs_v >= 1000:
            v /= 1024.0
            unit = "TB"
            abs_v = abs(v)
        if abs_v >= 1000:
            v /= 1024.0
            unit = "PB"
    elif base_unit == "GB":
        if abs_v >= 1000:
            v /= 1024.0
            unit = "TB"
            abs_v = abs(v)
        if abs_v >= 1000:
            v /= 1024.0
            unit = "PB"
    elif base_unit == "TB":
        if abs_v >= 1000:
            v /= 1024.0
            unit = "PB"

    return f"{v:.2f} {unit}"


def _usage_pie(used: float, total: float, title: str) -> go.Figure:
    used_val = max(float(used or 0), 0.0)
    total_val = max(float(total or 0), 0.0)
    free_val = max(total_val - used_val, 0.0) if total_val > 0 else 0.0
    if total_val <= 0:
        values = [0, 1]
    else:
        values = [used_val, free_val]

    utilisation_pct = pct_float(used_val, total_val) if total_val > 0 else 0.0
    if utilisation_pct < 60:
        used_color = "#4318FF"
    elif utilisation_pct < 80:
        used_color = "#FFB547"
    else:
        used_color = "#EE5D50"
    free_color = "#EEF2FF"

    fig = go.Figure(
        data=[
            go.Pie(
                labels=["Used", "Free"],
                values=values,
                hole=0.78,
                marker=dict(
                    colors=[used_color, free_color],
                    line=dict(color="rgba(0,0,0,0)", width=0),
                ),
                textinfo="none",
                hovertemplate="<b>%{label}</b><br>%{percent:.1%}<extra></extra>",
                sort=False,
                direction="clockwise",
            )
        ]
    )
    fig.update_layout(
        annotations=[dict(
            text=f"<b>{int(utilisation_pct)}%</b>",
            x=0.5,
            y=0.5,
            xanchor="center",
            yanchor="middle",
            font=dict(size=28, color="#2B3674", family="DM Sans"),
            showarrow=False,
        )],
        title=dict(
            text=f"<b>{title}</b>",
            x=0.5,
            xanchor="center",
            font=dict(size=11, color="#A3AED0", family="DM Sans"),
        ),
        margin=dict(l=8, r=8, t=28, b=8),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.06,
            xanchor="center",
            x=0.5,
            font=dict(size=11, family="DM Sans", color="#A3AED0"),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        height=260,
    )
    return fig


def _pie_card(fig: go.Figure) -> html.Div:
    """Square panel so the donut chart shape fits without clipping or excess space."""
    return html.Div(
        className="nexus-card dc-chart-card",
        style={
            "padding": "16px",
            "width": "320px",
            "height": "300px",
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "justifyContent": "center",
            "boxSizing": "border-box",
        },
        children=dcc.Graph(
            figure=fig,
            config={"displayModeBar": False},
            style={"height": "100%", "width": "100%"},
        ),
    )


def _usage_gauge_fig(used: float, total: float, title: str) -> go.Figure:
    """Half-moon premium gauge — replaces full donut."""
    used_val = max(float(used or 0), 0.0)
    total_val = max(float(total or 0), 0.0)
    pct = pct_float(used_val, total_val) if total_val > 0 else 0.0
    color = "#4318FF" if pct < 60 else "#FFB547" if pct < 80 else "#EE5D50"
    return create_premium_gauge_chart(pct, title, color=color, height=220)


def _gauge_card(fig: go.Figure) -> html.Div:
    """Gauge chart container — fills its grid cell."""
    return html.Div(
        className="nexus-card dc-chart-card",
        style={
            "padding": "12px 16px",
            "minHeight": "200px",
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "justifyContent": "center",
            "boxSizing": "border-box",
        },
        children=html.Div(
            style={
                "width": "100%",
                "aspectRatio": "16 / 11",
                "maxWidth": "360px",
                "margin": "0 auto",
            },
            children=dcc.Graph(
                figure=fig,
                config={"displayModeBar": False, "responsive": True},
                style={"height": "100%", "width": "100%"},
            ),
        ),
    )


# ---------------------------------------------------------------------------
# NetBackup
# ---------------------------------------------------------------------------


def _aggregate_netbackup(data: dict, selected_pools: Iterable[str] | None) -> dict:
    rows = data.get("rows") or []
    all_pools = [r.get("name") for r in rows if r.get("name")]
    available_pools = list({p for p in all_pools if p})

    chosen = set(selected_pools or available_pools)
    active_rows: list[dict] = []
    total_usable = 0
    total_avail = 0
    total_used = 0

    for r in rows:
        name = r.get("name")
        if not name or (chosen and name not in chosen):
            continue
        active_rows.append(r)
        total_usable += int(r.get("usablesizebytes", 0) or 0)
        total_avail += int(r.get("availablespacebytes", 0) or 0)
        total_used += int(r.get("usedcapacitybytes", 0) or 0)

    utilisation_pct = pct_float(total_used, total_usable) if total_usable else 0.0
    return {
        "pools": available_pools,
        "active_pools": sorted({r.get("name") for r in active_rows if r.get("name")}),
        "rows": active_rows,
        "total_usable": total_usable,
        "total_avail": total_avail,
        "total_used": total_used,
        "utilisation_pct": utilisation_pct,
    }


def netbackup_capacity_section_id(category: str | None = None) -> str:
    if category == "image":
        return "backup-nb-capacity-image"
    if category == "application":
        return "backup-nb-capacity-application"
    return "backup-nb-capacity"


def build_netbackup_capacity_section(
    data: dict,
    selected_pools: Iterable[str] | None,
    *,
    category: str | None = None,
) -> list:
    """Capacity KPI/gauge/detail block; pool selector lives outside this subtree."""
    agg = _aggregate_netbackup(data, selected_pools)

    fig = _usage_gauge_fig(
        used=agg["total_used"],
        total=max(agg["total_usable"], agg["total_used"] + agg["total_avail"]),
        title="NetBackup Capacity",
    )

    kpis = html.Div(
        style={
            "display": "grid",
            "gridTemplateColumns": "1fr 1fr",
            "gridTemplateRows": "1fr 1fr",
            "gap": "8px",
            "width": "100%",
            "height": "100%",
        },
        children=[
            _kpi_card(
                "Total usable",
                smart_bytes(agg["total_usable"]),
                "solar:database-bold-duotone",
            ),
            _kpi_card(
                "Total used",
                smart_bytes(agg["total_used"]),
                "solar:pie-chart-2-bold-duotone",
            ),
            _kpi_card(
                "Free space",
                smart_bytes(max(agg["total_avail"], 0)),
                "solar:folder-with-files-bold-duotone",
            ),
            _kpi_card(
                "Utilisation",
                f"{agg['utilisation_pct']:.1f}%",
                "solar:chart-square-bold-duotone",
            ),
        ],
    )

    # Table
    header_cells = [
        "Name",
        "Type",
        "Storage Category",
        "Disk Volume",
        "Volume State",
        "Usable",
        "Available",
        "Used",
    ]
    table_head = html.Thead(
        html.Tr(
            [
                html.Th(h, style={"fontSize": "0.75rem", "color": "#A3AED0"})
                for h in header_cells
            ]
        )
    )

    body_rows = []
    for r in agg["rows"]:
        body_rows.append(
            html.Tr(
                children=[
                    html.Td(r.get("name")),
                    html.Td(r.get("stype")),
                    html.Td(r.get("storagecategory")),
                    html.Td(r.get("diskvolumes_name")),
                    html.Td(r.get("diskvolumes_state")),
                    html.Td(smart_bytes(r.get("usablesizebytes", 0) or 0)),
                    html.Td(smart_bytes(r.get("availablespacebytes", 0) or 0)),
                    html.Td(smart_bytes(r.get("usedcapacitybytes", 0) or 0)),
                ]
            )
        )

    table = dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=False,
        withColumnBorders=False,
        className="nexus-table dc-premium-table",
        children=[table_head, html.Tbody(body_rows)],
    )

    util_pct_nb = agg["utilisation_pct"]
    total_pools = len(agg["rows"])
    active_pools = len([r for r in agg["rows"] if (r.get("usablesizebytes") or 0) > 0])
    inactive_pools = total_pools - active_pools

    nb_status_panel = html.Div(
        className="nexus-card dc-kpi-card",
        style={
            "padding": "20px 24px",
            "flex": "1",
            "minWidth": "200px",
            "display": "flex",
            "flexDirection": "column",
            "gap": "16px",
            "justifyContent": "center",
        },
        children=[
            html.Div(
                style={"borderBottom": "1px solid #F4F7FE", "paddingBottom": "12px"},
                children=[html.Span("POOL STATUS", style={
                    "fontSize": "0.7rem", "fontWeight": 700,
                    "color": "#A3AED0", "letterSpacing": "0.08em", "textTransform": "uppercase",
                })],
            ),
            dmc.Group(gap="xs", align="center", children=[
                DashIconify(icon="solar:check-circle-bold-duotone", width=20, style={"color": "#05CD99"}),
                html.Span(f"{active_pools}", style={
                    "fontSize": "1.8rem", "fontWeight": 900, "color": "#2B3674", "letterSpacing": "-0.02em"
                }),
                html.Span("active", style={
                    "fontSize": "0.8rem", "color": "#A3AED0", "fontWeight": 500, "marginLeft": "4px"
                }),
            ]),
            dmc.Group(gap="xs", align="center", children=[
                DashIconify(icon="solar:close-circle-bold-duotone", width=20, style={"color": "#EE5D50"}),
                html.Span(f"{inactive_pools}", style={
                    "fontSize": "1.8rem", "fontWeight": 900, "color": "#2B3674", "letterSpacing": "-0.02em"
                }),
                html.Span("inactive", style={
                    "fontSize": "0.8rem", "color": "#A3AED0", "fontWeight": 500, "marginLeft": "4px"
                }),
            ]),
            html.Div(
                style={"borderTop": "1px solid #F4F7FE", "paddingTop": "12px"},
                children=[
                    html.Div(
                        style={"display": "flex", "justifyContent": "space-between", "marginBottom": "6px"},
                        children=[
                            html.Span("Utilization", style={"fontSize": "0.78rem", "color": "#A3AED0"}),
                            html.Span(f"{util_pct_nb:.1f}%", style={
                                "fontSize": "0.78rem", "fontWeight": 700,
                                "color": "#05CD99" if util_pct_nb < 60 else "#FFB547" if util_pct_nb < 80 else "#EE5D50",
                            }),
                        ],
                    ),
                    html.Div(
                        style={"width": "100%", "height": "6px", "borderRadius": "3px",
                               "background": "#EEF2FF", "overflow": "hidden"},
                        children=html.Div(style={
                            "width": f"{min(util_pct_nb, 100):.1f}%", "height": "100%",
                            "borderRadius": "3px",
                            "background": (
                                "linear-gradient(90deg, #4318FF 0%, #05CD99 100%)" if util_pct_nb < 60
                                else "linear-gradient(90deg, #4318FF 0%, #FFB547 100%)" if util_pct_nb < 80
                                else "linear-gradient(90deg, #4318FF 0%, #EE5D50 100%)"
                            ),
                            "transition": "width 0.6s cubic-bezier(0.25, 0.8, 0.25, 1)",
                        }),
                    ),
                ],
            ),
        ],
    )

    return [
        html.Div(
            style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": "16px", "alignItems": "stretch"},
            children=[
                html.Div(style={"minWidth": 0, "height": "100%"}, children=kpis),
                _gauge_card(fig),
                nb_status_panel,
            ],
        ),
        html.Div(style={"height": "16px"}),
        html.Div(
            className="nexus-card",
            style={"padding": "16px", "marginTop": "8px"},
            children=table,
        ),
    ]


def build_netbackup_panel(
    data: dict,
    selected_pools: Iterable[str] | None,
    *,
    category: str | None = None,
    policy_type_options: list[str] | None = None,
    pool_selector_id: str | None = None,
):
    agg = _aggregate_netbackup(data, selected_pools)
    selector_value = list(selected_pools) if selected_pools else agg["pools"]
    resolved_selector_id = pool_selector_id or (
        f"backup-nb-pool-selector-{category}" if category else "backup-nb-pool-selector"
    )

    category_label = ""
    if category == "image":
        category_label = " — Image (KM)"
    elif category == "application":
        category_label = " — Application"

    pool_selector_header = html.Div(
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "marginTop": "20px",
            "marginBottom": "12px",
        },
        children=[
            dmc.Group(
                gap="md",
                children=[
                    DashIconify(
                        icon="solar:database-bold-duotone",
                        width=28,
                        style={"color": "#4318FF"},
                    ),
                    html.Div(
                        children=[
                            html.H3(
                                f"NetBackup Disk Pools{category_label}",
                                style={
                                    "margin": 0,
                                    "fontSize": "1rem",
                                    "color": "#2B3674",
                                },
                            ),
                            html.P(
                                "Latest usable, free and used capacity per selected pools.",
                                style={
                                    "margin": "2px 0 0 0",
                                    "fontSize": "0.8rem",
                                    "color": "#A3AED0",
                                },
                            ),
                        ]
                    ),
                ],
            ),
            dmc.MultiSelect(
                id=resolved_selector_id,
                data=[{"label": p, "value": p} for p in agg["pools"]],
                value=selector_value,
                clearable=True,
                searchable=True,
                nothingFoundMessage="No pools",
                placeholder="Select pools",
                size="sm",
                style={"minWidth": "260px"},
            ),
        ],
    )

    capacity_id = netbackup_capacity_section_id(category)
    capacity_accordion = dmc.Accordion(
        variant="separated",
        chevronPosition="right",
        children=[
            dmc.AccordionItem(
                value="capacity",
                children=[
                    dmc.AccordionControl("Pool capacity"),
                    dmc.AccordionPanel(
                        html.Div(
                            id=capacity_id,
                            children=build_netbackup_capacity_section(
                                data, selected_pools, category=category
                            ),
                        )
                    ),
                ],
            )
        ],
    )

    job_sections: list = []
    if category in ("image", "application"):
        job_sections = [
            build_job_stats_section(
                "netbackup",
                category=category,
                policy_type_options=policy_type_options,
            ),
            _unique_jobs_section(
                "netbackup",
                category=category,
                scope="dc",
            ),
        ]

    return html.Div(
        children=[
            *job_sections,
            pool_selector_header,
            capacity_accordion,
        ]
    )


# ---------------------------------------------------------------------------
# Zerto
# ---------------------------------------------------------------------------


def _aggregate_zerto(data: dict, selected_sites: Iterable[str] | None) -> dict:
    rows = data.get("rows") or []
    all_sites = [r.get("name") for r in rows if r.get("name")]
    available_sites = list({s for s in all_sites if s})

    chosen = set(selected_sites or available_sites)
    active_rows: list[dict] = []
    total_prov = 0
    total_used = 0
    total_in = 0.0
    total_out = 0.0

    for r in rows:
        name = r.get("name")
        if not name or (chosen and name not in chosen):
            continue
        active_rows.append(r)
        total_prov += int(r.get("provisioned_storage_mb", 0) or 0)
        total_used += int(r.get("used_storage_mb", 0) or 0)
        total_in += float(r.get("incoming_throughput_mb", 0.0) or 0.0)
        total_out += float(r.get("outgoing_bandwidth_mb", 0.0) or 0.0)

    utilisation_pct = pct_float(total_used, total_prov) if total_prov else 0.0
    return {
        "sites": available_sites,
        "active_sites": sorted({r.get("name") for r in active_rows if r.get("name")}),
        "rows": active_rows,
        "total_provisioned_mb": total_prov,
        "total_used_mb": total_used,
        "incoming_mb": total_in,
        "outgoing_mb": total_out,
        "utilisation_pct": utilisation_pct,
    }


def build_zerto_capacity_section(data: dict, selected_sites: Iterable[str] | None) -> list:
    """Site capacity KPI/gauge/detail block; site selector lives outside this subtree."""
    agg = _aggregate_zerto(data, selected_sites)

    fig = _usage_gauge_fig(
        used=agg["total_used_mb"],
        total=agg["total_provisioned_mb"],
        title="Zerto Storage",
    )

    kpis = html.Div(
        style={
            "display": "grid",
            "gridTemplateColumns": "1fr 1fr",
            "gridTemplateRows": "1fr 1fr",
            "gap": "8px",
            "width": "100%",
            "height": "100%",
        },
        children=[
            _kpi_card(
                "Total provisioned",
                _format_scaled(agg["total_provisioned_mb"], "MB"),
                "solar:cloud-storage-bold-duotone",
                color="teal",
            ),
            _kpi_card(
                "Total used",
                _format_scaled(agg["total_used_mb"], "MB"),
                "solar:pie-chart-2-bold-duotone",
                color="teal",
            ),
            _kpi_card(
                "Incoming throughput",
                _format_scaled(agg["incoming_mb"], "MB"),
                "solar:incoming-call-bold-duotone",
                color="teal",
            ),
            _kpi_card(
                "Outgoing bandwidth",
                _format_scaled(agg["outgoing_mb"], "MB"),
                "solar:outgoing-call-bold-duotone",
                color="teal",
            ),
        ],
    )

    # Table with pastel row coloring based on is_connected.
    header_cells = [
        "Name",
        "Site Type",
        "Connected",
        "Provisioned",
        "Used",
        "Incoming",
        "Outgoing",
    ]
    table_head = html.Thead(
        html.Tr(
            [
                html.Th(h, style={"fontSize": "0.75rem", "color": "#A3AED0"})
                for h in header_cells
            ]
        )
    )

    body_rows = []
    for r in agg["rows"]:
        is_conn = r.get("is_connected")
        connected_cell = html.Td(
            dmc.Badge(
                "Connected" if is_conn else "Disconnected",
                color="teal" if is_conn else "red",
                variant="light",
                size="sm",
                className="dc-status-connected" if is_conn else "dc-status-disconnected",
            )
        )
        body_rows.append(
            html.Tr(
                children=[
                    html.Td(r.get("name")),
                    html.Td(r.get("site_type")),
                    connected_cell,
                    html.Td(
                        _format_scaled(r.get("provisioned_storage_mb", 0) or 0, "MB")
                    ),
                    html.Td(
                        _format_scaled(r.get("used_storage_mb", 0) or 0, "MB")
                    ),
                    html.Td(
                        _format_scaled(
                            r.get("incoming_throughput_mb", 0.0) or 0.0, "MB"
                        )
                    ),
                    html.Td(
                        _format_scaled(
                            r.get("outgoing_bandwidth_mb", 0.0) or 0.0, "MB"
                        )
                    ),
                ],
            )
        )

    table = dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=False,
        withColumnBorders=False,
        className="nexus-table dc-premium-table",
        children=[table_head, html.Tbody(body_rows)],
    )

    # N1. Zerto Status Summary Panel
    connected_count = sum(1 for r in agg["rows"] if r.get("is_connected") is True)
    disconnected_count = sum(1 for r in agg["rows"] if r.get("is_connected") is False)
    util_pct = pct_float(agg["total_used_mb"], agg["total_provisioned_mb"])

    status_panel = html.Div(
        className="nexus-card dc-kpi-card",
        style={
            "padding": "20px 24px",
            "minWidth": "220px",
            "flex": "1",
            "display": "flex",
            "flexDirection": "column",
            "gap": "16px",
            "justifyContent": "center",
        },
        children=[
            html.Div(
                style={"borderBottom": "1px solid #F4F7FE", "paddingBottom": "12px"},
                children=[
                    html.Span(
                        "SITE STATUS",
                        style={
                            "fontSize": "0.7rem",
                            "fontWeight": 700,
                            "color": "#A3AED0",
                            "letterSpacing": "0.08em",
                            "textTransform": "uppercase",
                        },
                    ),
                ],
            ),
            dmc.Group(
                gap="xs",
                align="center",
                children=[
                    DashIconify(icon="solar:check-circle-bold-duotone", width=20, style={"color": "#05CD99"}),
                    html.Span(
                        f"{connected_count}",
                        style={"fontSize": "1.8rem", "fontWeight": 900, "color": "#2B3674", "letterSpacing": "-0.02em"},
                    ),
                    html.Span(
                        "connected",
                        style={"fontSize": "0.8rem", "color": "#A3AED0", "fontWeight": 500, "marginLeft": "4px"},
                    ),
                ],
            ),
            dmc.Group(
                gap="xs",
                align="center",
                children=[
                    DashIconify(icon="solar:close-circle-bold-duotone", width=20, style={"color": "#EE5D50"}),
                    html.Span(
                        f"{disconnected_count}",
                        style={"fontSize": "1.8rem", "fontWeight": 900, "color": "#2B3674", "letterSpacing": "-0.02em"},
                    ),
                    html.Span(
                        "disconnected",
                        style={"fontSize": "0.8rem", "color": "#A3AED0", "fontWeight": 500, "marginLeft": "4px"},
                    ),
                ],
            ),
            html.Div(
                style={"borderTop": "1px solid #F4F7FE", "paddingTop": "12px"},
                children=[
                    html.Div(
                        style={"display": "flex", "justifyContent": "space-between", "marginBottom": "6px"},
                        children=[
                            html.Span("Utilization", style={"fontSize": "0.78rem", "color": "#A3AED0"}),
                            html.Span(
                                f"{util_pct:.1f}%",
                                style={
                                    "fontSize": "0.78rem",
                                    "fontWeight": 700,
                                    "color": "#05CD99" if util_pct < 60 else "#FFB547" if util_pct < 80 else "#EE5D50",
                                },
                            ),
                        ],
                    ),
                    html.Div(
                        style={
                            "width": "100%", "height": "6px",
                            "borderRadius": "3px", "background": "#EEF2FF", "overflow": "hidden",
                        },
                        children=html.Div(
                            style={
                                "width": f"{min(util_pct, 100):.1f}%",
                                "height": "100%",
                                "borderRadius": "3px",
                                "background": (
                                    "linear-gradient(90deg, #4318FF 0%, #05CD99 100%)" if util_pct < 60
                                    else "linear-gradient(90deg, #4318FF 0%, #FFB547 100%)" if util_pct < 80
                                    else "linear-gradient(90deg, #4318FF 0%, #EE5D50 100%)"
                                ),
                                "transition": "width 0.6s cubic-bezier(0.25, 0.8, 0.25, 1)",
                            },
                        ),
                    ),
                ],
            ),
        ],
    )

    return [
        html.Div(
            style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": "16px", "alignItems": "stretch"},
            children=[
                html.Div(style={"minWidth": 0, "height": "100%"}, children=kpis),
                _gauge_card(fig),
                status_panel,
            ],
        ),
        html.Div(style={"height": "16px"}),
        html.Div(
            className="nexus-card",
            style={"padding": "16px", "marginTop": "8px"},
            children=table,
        ),
    ]


def build_zerto_panel(data: dict, selected_sites: Iterable[str] | None):
    agg = _aggregate_zerto(data, selected_sites)
    selector_value = list(selected_sites) if selected_sites else agg["sites"]

    site_selector_header = html.Div(
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "marginTop": "20px",
            "marginBottom": "12px",
        },
        children=[
            dmc.Group(
                gap="md",
                children=[
                    DashIconify(
                        icon="solar:shield-check-bold-duotone",
                        width=28,
                        style={"color": "#12B886"},
                    ),
                    html.Div(
                        children=[
                            html.H3(
                                "Zerto Sites",
                                style={
                                    "margin": 0,
                                    "fontSize": "1rem",
                                    "color": "#2B3674",
                                },
                            ),
                            html.P(
                                "Provisioned and used storage with connectivity status.",
                                style={
                                    "margin": "2px 0 0 0",
                                    "fontSize": "0.8rem",
                                    "color": "#A3AED0",
                                },
                            ),
                        ]
                    ),
                ],
            ),
            dmc.MultiSelect(
                id="backup-zerto-site-selector",
                data=[{"label": s, "value": s} for s in agg["sites"]],
                value=selector_value,
                clearable=True,
                searchable=True,
                nothingFoundMessage="No sites",
                placeholder="Select sites",
                size="sm",
                style={"minWidth": "260px"},
            ),
        ],
    )

    capacity_accordion = dmc.Accordion(
        variant="separated",
        chevronPosition="right",
        children=[
            dmc.AccordionItem(
                value="capacity",
                children=[
                    dmc.AccordionControl("Site capacity"),
                    dmc.AccordionPanel(
                        html.Div(
                            id="backup-zerto-capacity",
                            children=build_zerto_capacity_section(data, selected_sites),
                        )
                    ),
                ],
            )
        ],
    )

    return html.Div(
        children=[
            build_job_stats_section("zerto"),
            _unique_jobs_section("zerto", scope="dc"),
            site_selector_header,
            capacity_accordion,
        ]
    )


# ---------------------------------------------------------------------------
# Veeam
# ---------------------------------------------------------------------------


def _aggregate_veeam(data: dict, selected_repos: Iterable[str] | None) -> dict:
    rows = data.get("rows") or []
    all_repos = [r.get("name") for r in rows if r.get("name")]
    available_repos = list({n for n in all_repos if n})

    chosen = set(selected_repos or available_repos)
    active_rows: list[dict] = []
    total_capacity = 0.0
    total_free = 0.0
    total_used = 0.0

    for r in rows:
        name = r.get("name")
        if not name or (chosen and name not in chosen):
            continue
        active_rows.append(r)
        total_capacity += float(r.get("capacity_gb", 0.0) or 0.0)
        total_free += float(r.get("free_gb", 0.0) or 0.0)
        total_used += float(r.get("used_space_gb", 0.0) or 0.0)

    utilisation_pct = pct_float(total_used, total_capacity) if total_capacity else 0.0
    return {
        "repos": available_repos,
        "active_repos": sorted({r.get("name") for r in active_rows if r.get("name")}),
        "rows": active_rows,
        "total_capacity_gb": total_capacity,
        "total_free_gb": total_free,
        "total_used_gb": total_used,
        "utilisation_pct": utilisation_pct,
    }


def build_veeam_capacity_section(data: dict, selected_repos: Iterable[str] | None) -> list:
    """Repository capacity KPI/gauge/detail block; repo selector lives outside this subtree."""
    agg = _aggregate_veeam(data, selected_repos)

    fig = _usage_gauge_fig(
        used=agg["total_used_gb"],
        total=agg["total_capacity_gb"],
        title="Veeam Repos",
    )

    kpis = html.Div(
        style={
            "display": "grid",
            "gridTemplateColumns": "1fr 1fr",
            "gridTemplateRows": "1fr 1fr",
            "gap": "8px",
            "width": "100%",
            "height": "100%",
        },
        children=[
            _kpi_card(
                "Total capacity",
                _format_scaled(agg["total_capacity_gb"], "GB"),
                "solar:database-bold-duotone",
                color="cyan",
            ),
            _kpi_card(
                "Total used",
                _format_scaled(agg["total_used_gb"], "GB"),
                "solar:pie-chart-2-bold-duotone",
                color="cyan",
            ),
            _kpi_card(
                "Free space",
                _format_scaled(agg["total_free_gb"], "GB"),
                "solar:folder-with-files-bold-duotone",
                color="cyan",
            ),
            _kpi_card(
                "Utilisation",
                f"{agg['utilisation_pct']:.1f}%",
                "solar:chart-square-bold-duotone",
                color="cyan",
            ),
        ],
    )

    header_cells = [
        "Name",
        "Host",
        "Type",
        "Capacity",
        "Free",
        "Used",
        "Online",
    ]
    table_head = html.Thead(
        html.Tr(
            [
                html.Th(h, style={"fontSize": "0.75rem", "color": "#A3AED0"})
                for h in header_cells
            ]
        )
    )

    body_rows = []
    for r in agg["rows"]:
        body_rows.append(
            html.Tr(
                children=[
                    html.Td(r.get("name")),
                    html.Td(r.get("host_name")),
                    html.Td(r.get("type")),
                    html.Td(
                        _format_scaled(r.get("capacity_gb", 0.0) or 0.0, "GB")
                    ),
                    html.Td(
                        _format_scaled(r.get("free_gb", 0.0) or 0.0, "GB")
                    ),
                    html.Td(
                        _format_scaled(r.get("used_space_gb", 0.0) or 0.0, "GB")
                    ),
                    html.Td("True" if r.get("is_online") else "False"),
                ]
            )
        )

    table = dmc.Table(
        striped=True,
        highlightOnHover=True,
        withTableBorder=False,
        withColumnBorders=False,
        className="nexus-table dc-premium-table",
        children=[table_head, html.Tbody(body_rows)],
    )

    online_count = sum(1 for r in agg["rows"] if r.get("is_online") is True)
    offline_count = sum(1 for r in agg["rows"] if r.get("is_online") is False)
    util_pct_v = agg["utilisation_pct"]

    veeam_status_panel = html.Div(
        className="nexus-card dc-kpi-card",
        style={
            "padding": "20px 24px",
            "flex": "1",
            "minWidth": "200px",
            "display": "flex",
            "flexDirection": "column",
            "gap": "16px",
            "justifyContent": "center",
        },
        children=[
            html.Div(
                style={"borderBottom": "1px solid #F4F7FE", "paddingBottom": "12px"},
                children=[html.Span("REPO STATUS", style={
                    "fontSize": "0.7rem", "fontWeight": 700,
                    "color": "#A3AED0", "letterSpacing": "0.08em", "textTransform": "uppercase",
                })],
            ),
            dmc.Group(gap="xs", align="center", children=[
                DashIconify(icon="solar:check-circle-bold-duotone", width=20, style={"color": "#05CD99"}),
                html.Span(f"{online_count}", style={
                    "fontSize": "1.8rem", "fontWeight": 900, "color": "#2B3674", "letterSpacing": "-0.02em"
                }),
                html.Span("online", style={
                    "fontSize": "0.8rem", "color": "#A3AED0", "fontWeight": 500, "marginLeft": "4px"
                }),
            ]),
            dmc.Group(gap="xs", align="center", children=[
                DashIconify(icon="solar:close-circle-bold-duotone", width=20, style={"color": "#EE5D50"}),
                html.Span(f"{offline_count}", style={
                    "fontSize": "1.8rem", "fontWeight": 900, "color": "#2B3674", "letterSpacing": "-0.02em"
                }),
                html.Span("offline", style={
                    "fontSize": "0.8rem", "color": "#A3AED0", "fontWeight": 500, "marginLeft": "4px"
                }),
            ]),
            html.Div(
                style={"borderTop": "1px solid #F4F7FE", "paddingTop": "12px"},
                children=[
                    html.Div(
                        style={"display": "flex", "justifyContent": "space-between", "marginBottom": "6px"},
                        children=[
                            html.Span("Utilization", style={"fontSize": "0.78rem", "color": "#A3AED0"}),
                            html.Span(f"{util_pct_v:.1f}%", style={
                                "fontSize": "0.78rem", "fontWeight": 700,
                                "color": "#05CD99" if util_pct_v < 60 else "#FFB547" if util_pct_v < 80 else "#EE5D50",
                            }),
                        ],
                    ),
                    html.Div(
                        style={"width": "100%", "height": "6px", "borderRadius": "3px",
                               "background": "#EEF2FF", "overflow": "hidden"},
                        children=html.Div(style={
                            "width": f"{min(util_pct_v, 100):.1f}%", "height": "100%",
                            "borderRadius": "3px",
                            "background": (
                                "linear-gradient(90deg, #4318FF 0%, #05CD99 100%)" if util_pct_v < 60
                                else "linear-gradient(90deg, #4318FF 0%, #FFB547 100%)" if util_pct_v < 80
                                else "linear-gradient(90deg, #4318FF 0%, #EE5D50 100%)"
                            ),
                            "transition": "width 0.6s cubic-bezier(0.25, 0.8, 0.25, 1)",
                        }),
                    ),
                ],
            ),
        ],
    )

    return [
        html.Div(
            style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": "16px", "alignItems": "stretch"},
            children=[
                html.Div(style={"minWidth": 0, "height": "100%"}, children=kpis),
                _gauge_card(fig),
                veeam_status_panel,
            ],
        ),
        html.Div(style={"height": "16px"}),
        html.Div(
            className="nexus-card",
            style={"padding": "16px", "marginTop": "8px"},
            children=table,
        ),
    ]


def build_veeam_panel(data: dict, selected_repos: Iterable[str] | None):
    agg = _aggregate_veeam(data, selected_repos)
    selector_value = list(selected_repos) if selected_repos else agg["repos"]

    repo_selector_header = html.Div(
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "marginTop": "20px",
            "marginBottom": "12px",
        },
        children=[
            dmc.Group(
                gap="md",
                children=[
                    DashIconify(
                        icon="solar:cloud-storage-bold-duotone",
                        width=28,
                        style={"color": "#15AABF"},
                    ),
                    html.Div(
                        children=[
                            html.H3(
                                "Veeam Repositories",
                                style={
                                    "margin": 0,
                                    "fontSize": "1rem",
                                    "color": "#2B3674",
                                },
                            ),
                            html.P(
                                "Capacity, free and used space per repository.",
                                style={
                                    "margin": "2px 0 0 0",
                                    "fontSize": "0.8rem",
                                    "color": "#A3AED0",
                                },
                            ),
                        ]
                    ),
                ],
            ),
            dmc.MultiSelect(
                id="backup-veeam-repo-selector",
                data=[{"label": r, "value": r} for r in agg["repos"]],
                value=selector_value,
                clearable=True,
                searchable=True,
                nothingFoundMessage="No repositories",
                placeholder="Select repositories",
                size="sm",
                style={"minWidth": "260px"},
            ),
        ],
    )

    capacity_accordion = dmc.Accordion(
        variant="separated",
        chevronPosition="right",
        children=[
            dmc.AccordionItem(
                value="capacity",
                children=[
                    dmc.AccordionControl("Repository capacity"),
                    dmc.AccordionPanel(
                        html.Div(
                            id="backup-veeam-capacity",
                            children=build_veeam_capacity_section(data, selected_repos),
                        )
                    ),
                ],
            )
        ],
    )

    return html.Div(
        children=[
            build_job_stats_section("veeam"),
            _unique_jobs_section("veeam", scope="dc"),
            repo_selector_header,
            capacity_accordion,
        ]
    )



# ---------------------------------------------------------------------------
# Nutanix snapshots
# ---------------------------------------------------------------------------

_NUTANIX_TABLE_HEADERS = [
    "Nutanix IP", "Cluster", "Customer", "Schedule", "VMs", "Entity Type",
    "Schedule Type", "Retention", "Start", "Create", "Expiry", "Size",
]

_NUTANIX_SCHED_COLORS = ["#4318FF", "#12B886", "#FFB547", "#EE5D50", "#15AABF", "#ADB5BD"]


def _ts(value) -> str:
    """ISO string → 'YYYY-MM-DD HH:MM:SS' for compact table display."""
    if not value:
        return "—"
    return str(value)[:19].replace("T", " ")


def _nsnap_cell(value, *, max_width: str | None = None, title: str | None = None):
    """Table cell: single-line (nowrap); optional ellipsis truncation with a
    hover tooltip for long values (VM lists, long schedule names)."""
    style = {"whiteSpace": "nowrap"}
    if max_width:
        style.update({"maxWidth": max_width, "overflow": "hidden", "textOverflow": "ellipsis"})
    kwargs = {"style": style}
    if title:
        kwargs["title"] = title
    return html.Td(value, **kwargs)


def nutanix_snapshot_table(items: list[dict]) -> html.Div:
    head = html.Thead(
        html.Tr([html.Th(h, style={"fontSize": "0.75rem", "color": "#A3AED0"})
                 for h in _NUTANIX_TABLE_HEADERS])
    )
    body = []
    for r in items or []:
        pd = r.get("protection_domain_name") or "—"
        vm = r.get("vm_names") or ""
        body.append(html.Tr(children=[
            _nsnap_cell(r.get("nutanix_ip")),
            _nsnap_cell(r.get("cluster") or "—"),
            _nsnap_cell(r.get("customer") or "—"),
            _nsnap_cell(pd, max_width="240px", title=pd),
            _nsnap_cell(vm or "—", max_width="260px", title=vm),
            _nsnap_cell(r.get("entity_type") or "—", max_width="180px", title=r.get("entity_type") or ""),
            _nsnap_cell(r.get("schedule_type") or "—"),
            _nsnap_cell(str(r.get("retention")) if r.get("retention") is not None else "—"),
            _nsnap_cell(_ts(r.get("start_time"))),
            _nsnap_cell(_ts(r.get("create_time"))),
            _nsnap_cell(_ts(r.get("expiry_time"))),
            _nsnap_cell(smart_bytes(r.get("size_in_bytes", 0) or 0)),
        ]))
    if not body:
        body = [html.Tr(html.Td("Bu aralıkta snapshot yok.", colSpan=len(_NUTANIX_TABLE_HEADERS),
                                style={"textAlign": "center", "color": "#A3AED0", "padding": "24px"}))]
    table = dmc.Table(
        striped=True, highlightOnHover=True, withTableBorder=False, withColumnBorders=False,
        className="nexus-table dc-premium-table", style={"minWidth": "1180px"},
        children=[head, html.Tbody(body)],
    )
    # Horizontal scroll so wide columns are reachable (repo pattern: overflowX auto).
    return html.Div(style={"overflowX": "auto", "width": "100%"}, children=table)


def _nutanix_sched_donut(breakdown: dict) -> go.Figure:
    items = [(k, v) for k, v in (breakdown or {}).items() if v]
    labels = [k for k, _ in items] or ["No data"]
    values = [v for _, v in items] or [1]
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=0.72, sort=False, direction="clockwise",
        marker=dict(colors=_NUTANIX_SCHED_COLORS, line=dict(color="rgba(0,0,0,0)", width=0)),
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>%{value} snapshot (%{percent})<extra></extra>",
    )])
    fig.update_layout(
        title=dict(text="<b>Snapshots by Schedule</b>", x=0.5, xanchor="center",
                   font=dict(size=11, color="#A3AED0", family="DM Sans")),
        margin=dict(l=8, r=8, t=28, b=8), showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", height=260,
    )
    return fig


def _nutanix_state_panel(state_breakdown: dict) -> html.Div:
    rows = []
    palette = {"AVAILABLE": "#05CD99", "EXPIRED": "#EE5D50", "RETAIN_FOREVER": "#4318FF"}
    for state, count in (state_breakdown or {}).items():
        rows.append(dmc.Group(gap="xs", align="center", children=[
            DashIconify(icon="solar:record-circle-bold-duotone", width=18,
                        style={"color": palette.get(state, "#A3AED0")}),
            html.Span(f"{count:,}", style={"fontSize": "1.4rem", "fontWeight": 800, "color": "#2B3674"}),
            html.Span(state, style={"fontSize": "0.78rem", "color": "#A3AED0", "marginLeft": "4px"}),
        ]))
    if not rows:
        rows = [html.Span("—", style={"color": "#A3AED0"})]
    return html.Div(
        className="nexus-card dc-kpi-card",
        style={"padding": "20px 24px", "flex": "1", "minWidth": "200px",
               "display": "flex", "flexDirection": "column", "gap": "12px", "justifyContent": "center"},
        children=[
            html.Div(style={"borderBottom": "1px solid #F4F7FE", "paddingBottom": "12px"},
                     children=[html.Span("SNAPSHOT STATE", style={
                         "fontSize": "0.7rem", "fontWeight": 700, "color": "#A3AED0",
                         "letterSpacing": "0.08em", "textTransform": "uppercase"})]),
            *rows,
        ],
    )


def build_nutanix_snapshot_panel(data: dict, table: dict | None = None, missing: dict | None = None,
                                 *, paginated: bool = True):
    """Nutanix snapshot panel: KPI cards + schedule donut + state panel +
    per-snapshot table + collapsible Missing Entities section.

    `data`      = get_dc/customer_nutanix_snapshots payload ({rows, totals, as_of}).
    `table`     = first-page table payload ({items, total}) — DC view (server-paged).
    `missing`   = missing-entities payload ({items, total}).
    `paginated` = True for DC view (server-side pagination + live-refresh controls).
                  False for customer view (small, single-customer) — renders all
                  rows from `data['rows']` with no pagination controls.
    """
    totals = (data or {}).get("totals") or {}
    all_rows = (data or {}).get("rows") or []
    if paginated:
        table = table or {"items": [], "total": 0}
        missing = missing or {"items": [], "total": 0}
    else:
        table = {"items": all_rows, "total": len(all_rows)}
        missing = {"items": [r for r in all_rows if r.get("missing_entity")],
                   "total": sum(1 for r in all_rows if r.get("missing_entity"))}
    total_rows = int(table.get("total", 0) or 0)
    pages = max(1, -(-total_rows // 50)) if total_rows else 1

    header = html.Div(
        style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
               "marginBottom": "16px"},
        children=[
            dmc.Group(gap="md", children=[
                DashIconify(icon="solar:gallery-wide-bold-duotone", width=28, style={"color": "#4318FF"}),
                html.Div(children=[
                    html.H3("Nutanix Snapshots", style={"margin": 0, "fontSize": "1rem", "color": "#2B3674"}),
                    html.P("Protection-domain snapshots: retention, schedule, size ve eksik entity'ler.",
                           style={"margin": "2px 0 0 0", "fontSize": "0.8rem", "color": "#A3AED0"}),
                ]),
            ]),
            (dmc.Tooltip(
                label="Cache'i yenile (canlı SQL)", position="top", withArrow=True,
                children=dmc.ActionIcon(
                    id="backup-nutanix-refresh", variant="light", color="indigo", size="lg",
                    children=DashIconify(icon="solar:refresh-bold-duotone", width=18)),
            ) if paginated else None),
        ],
    )

    kpis = html.Div(
        style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gridTemplateRows": "1fr 1fr",
               "gap": "8px", "width": "100%", "height": "100%"},
        children=[
            _kpi_card("Total snapshots", f"{int(totals.get('total_snapshots', 0)):,}",
                      "solar:gallery-wide-bold-duotone"),
            _kpi_card("Total size", smart_bytes(totals.get("total_size_bytes", 0) or 0),
                      "solar:database-bold-duotone"),
            _kpi_card("Protected VMs", f"{int(totals.get('protected_vms', 0)):,}",
                      "solar:server-bold-duotone"),
            _kpi_card("Missing entities", f"{int(totals.get('missing_entities', 0)):,}",
                      "solar:danger-triangle-bold-duotone", color="orange"),
        ],
    )

    top_grid = html.Div(
        style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": "16px", "alignItems": "stretch"},
        children=[
            html.Div(style={"minWidth": 0, "height": "100%"}, children=kpis),
            _gauge_card(_nutanix_sched_donut(totals.get("schedule_type_breakdown") or {})),
            _nutanix_state_panel(totals.get("state_breakdown") or {}),
        ],
    )

    # Filter options derived from the full base set (all_rows).
    def _opts(values):
        return [{"label": v, "value": v} for v in values]

    customers = sorted({r.get("customer") for r in all_rows if r.get("customer")})
    sched_types = sorted({r.get("schedule_type") for r in all_rows if r.get("schedule_type")})
    clusters = sorted({r.get("cluster") for r in all_rows if r.get("cluster")})
    retentions = sorted({r.get("retention") for r in all_rows if r.get("retention") is not None})

    filter_bar = html.Div(
        style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "12px"},
        children=[
            dmc.MultiSelect(id="backup-nutanix-filter-customer", data=_opts(customers),
                            placeholder="Customers", clearable=True, searchable=True,
                            size="sm", style={"minWidth": "200px", "flex": "1"}, maxDropdownHeight=280),
            dmc.MultiSelect(id="backup-nutanix-filter-schedtype", data=_opts(sched_types),
                            placeholder="Schedule Type", clearable=True,
                            size="sm", style={"minWidth": "160px"}),
            dmc.MultiSelect(id="backup-nutanix-filter-retention",
                            data=[{"label": str(v), "value": str(v)} for v in retentions],
                            placeholder="Retention", clearable=True, searchable=True,
                            size="sm", style={"minWidth": "150px"}),
            dmc.MultiSelect(id="backup-nutanix-filter-cluster", data=_opts(clusters),
                            placeholder="Cluster", clearable=True, searchable=True,
                            size="sm", style={"minWidth": "180px", "flex": "1"}, maxDropdownHeight=280),
        ],
    )

    controls = html.Div(
        style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
               "marginBottom": "12px", "gap": "12px", "flexWrap": "wrap"},
        children=[
            dmc.TextInput(id="backup-nutanix-search", placeholder="Ara: müşteri, schedule, VM, IP",
                          size="sm", style={"minWidth": "300px"},
                          leftSection=DashIconify(icon="solar:magnifer-linear", width=16)),
            dmc.Group(gap="xs", align="center", children=[
                dmc.ActionIcon(id="backup-nutanix-prev", variant="light", color="indigo", size="md",
                               children=DashIconify(icon="solar:alt-arrow-left-linear", width=16)),
                html.Span(id="backup-nutanix-pageinfo", children=f"1 / {pages}",
                          style={"fontSize": "0.8rem", "color": "#2B3674", "fontWeight": 600, "minWidth": "70px",
                                 "textAlign": "center"}),
                dmc.ActionIcon(id="backup-nutanix-next", variant="light", color="indigo", size="md",
                               children=DashIconify(icon="solar:alt-arrow-right-linear", width=16)),
            ]),
        ],
    )

    table_body = dcc.Loading(type="circle", color="#4318FF", delay_show=150, children=html.Div(
        id="backup-nutanix-table" if paginated else "backup-nutanix-table-static",
        children=nutanix_snapshot_table(table.get("items", []))))
    table_card = html.Div(
        className="nexus-card", style={"padding": "16px", "marginTop": "8px"},
        children=([filter_bar, controls, dcc.Store(id="backup-nutanix-page", data=1), table_body]
                  if paginated else [table_body]),
    )

    missing_section = dmc.Accordion(
        chevronPosition="right", variant="separated", radius="md", style={"marginTop": "16px"},
        children=[dmc.AccordionItem(value="missing", children=[
            dmc.AccordionControl(
                dmc.Group(gap="xs", children=[
                    DashIconify(icon="solar:danger-triangle-bold-duotone", width=18, style={"color": "#FFB547"}),
                    html.Span(f"Missing Entities ({int(missing.get('total', 0)):,})",
                              style={"fontWeight": 600, "color": "#2B3674"}),
                ])),
            dmc.AccordionPanel(nutanix_snapshot_table(missing.get("items", []))),
        ])],
    )

    return html.Div(children=[
        header, top_grid, html.Div(style={"height": "16px"}), table_card, missing_section,
    ])

# ---------------------------------------------------------------------------
# License panels (Veeam CRM / Zerto datalake)
# ---------------------------------------------------------------------------


def build_zerto_license_panel(license_payload: dict | None) -> html.Div | None:
    """Render Zerto license KPIs when datalake license data exists; else None."""
    data = license_payload or {}
    if not data.get("has_license"):
        return None
    summary = data.get("summary") or {}
    sites = data.get("sites") or []
    is_valid = summary.get("is_valid")
    max_vms = summary.get("max_vms")
    total_vms = summary.get("total_vms_count")
    protected_dc = summary.get("protected_vms_in_dc")
    days = summary.get("days_until_expiry")
    license_type = summary.get("license_type") or "—"
    valid_label = "Valid" if is_valid else ("Invalid" if is_valid is False else "Unknown")
    valid_color = "teal" if is_valid else ("red" if is_valid is False else "gray")

    kpis = html.Div(
        style={
            "display": "grid",
            "gridTemplateColumns": "repeat(4, 1fr)",
            "gap": "12px",
            "marginBottom": "12px",
        },
        children=[
            _kpi_card("License type", str(license_type), "solar:ticket-bold-duotone", "indigo"),
            _kpi_card(
                "Validity",
                valid_label,
                "solar:shield-check-bold-duotone",
                valid_color,
            ),
            _kpi_card(
                "Max VMs",
                f"{int(max_vms):,}" if max_vms is not None else "—",
                "solar:server-bold-duotone",
            ),
            _kpi_card(
                "Used VMs (license)",
                f"{int(total_vms):,}" if total_vms is not None else "—",
                "solar:users-group-rounded-bold-duotone",
            ),
        ],
    )

    extra = dmc.Group(
        gap="md",
        children=[
            dmc.Badge(
                f"Protected in DC: {int(protected_dc or 0):,}",
                variant="light",
                color="indigo",
                radius="xl",
            ),
            dmc.Badge(
                f"Days until expiry: {days}" if days is not None else "Expiry: n/a",
                variant="light",
                color="orange" if days is not None and int(days) < 90 else "gray",
                radius="xl",
            ),
            dmc.Badge(
                "License required (usage present)",
                variant="outline",
                color="grape",
                radius="xl",
            ),
        ],
    )

    table_rows = [
        html.Tr(
            [
                html.Td(s.get("site_name")),
                html.Td(f"{int(s.get('protected_vms_count') or 0):,}"),
            ]
        )
        for s in sites
    ] or [html.Tr([html.Td("No site usage in this DC", colSpan=2)])]

    return html.Div(
        className="nexus-card",
        style={"padding": "16px", "marginTop": "16px"},
        children=[
            html.H4(
                "Zerto License",
                style={"margin": "0 0 12px 0", "fontSize": "0.95rem", "color": "#2B3674"},
            ),
            kpis,
            extra,
            html.Div(style={"height": "12px"}),
            dmc.Table(
                striped=True,
                highlightOnHover=True,
                children=[
                    html.Thead(html.Tr([html.Th("Site"), html.Th("Protected VMs")])),
                    html.Tbody(table_rows),
                ],
            ),
        ],
    )


def build_veeam_license_panel(crm_license_payload: dict | None) -> html.Div | None:
    """Render Veeam license from CRM sold reference when data exists; else None."""
    data = crm_license_payload or {}
    sold_qty = data.get("sold_qty")
    rows = data.get("rows") or []
    has_data = bool(rows) or (sold_qty is not None and float(sold_qty or 0) > 0)
    if not has_data:
        return None
    label = data.get("label") or "Veeam License (CRM sold)"
    unit = data.get("unit") or "license"
    try:
        sold_fmt = f"{float(sold_qty):,.2f}" if sold_qty is not None else "—"
    except (TypeError, ValueError):
        sold_fmt = str(sold_qty)

    body_rows = []
    for r in rows:
        body_rows.append(
            html.Tr(
                [
                    html.Td(r.get("product_name") or r.get("label") or "—"),
                    html.Td(r.get("sold_qty")),
                    html.Td(r.get("unit") or unit),
                ]
            )
        )
    if not body_rows:
        body_rows = [
            html.Tr(
                [
                    html.Td(label),
                    html.Td(sold_fmt),
                    html.Td(unit),
                ]
            )
        ]

    return html.Div(
        className="nexus-card",
        style={"padding": "16px", "marginTop": "16px"},
        children=[
            html.H4(
                "Veeam License",
                style={"margin": "0 0 8px 0", "fontSize": "0.95rem", "color": "#2B3674"},
            ),
            html.P(
                "CRM sold reference (datalake license inventory not available). "
                "License is required when sold/usage data exists.",
                style={"margin": "0 0 12px 0", "fontSize": "0.78rem", "color": "#A3AED0"},
            ),
            dmc.Group(
                gap="md",
                children=[
                    _kpi_card("Sold (CRM)", sold_fmt, "solar:ticket-bold-duotone", "indigo"),
                    dmc.Badge(
                        "License required",
                        variant="outline",
                        color="grape",
                        radius="xl",
                    ),
                ],
            ),
            html.Div(style={"height": "12px"}),
            dmc.Table(
                striped=True,
                highlightOnHover=True,
                children=[
                    html.Thead(
                        html.Tr([html.Th("Product"), html.Th("Sold qty"), html.Th("Unit")])
                    ),
                    html.Tbody(body_rows),
                ],
            ),
        ],
    )


def build_hc_image_placeholder() -> html.Div:
    """Hyperconverged image backup placeholder until Nutanix snapshot tab lands."""
    return dmc.Alert(
        color="gray",
        variant="light",
        title="Hyperconverged Image Backup (Nutanix)",
        children=(
            "Nutanix snapshot / HC image backup panel is not available on this "
            "branch yet. Classic (KM) image backup uses NetBackup VMWARE policy types."
        ),
    )


def build_image_backup_section(
    *,
    nb_data: dict | None = None,
    selected_pools: Iterable[str] | None = None,
    policy_type_options: list[str] | None = None,
    nutanix_panel: html.Div | None = None,
    has_netbackup: bool = False,
    has_nutanix: bool = False,
) -> html.Div:
    """Image Backup category: Classic KM (NetBackup) + Hyperconverged (Nutanix)."""
    children: list = []
    tab_defs: list[tuple[str, str]] = []
    if has_netbackup:
        tab_defs.append(("km", "Classic (KM) — NetBackup"))
    if has_nutanix or nutanix_panel is not None:
        tab_defs.append(("hc", "Hyperconverged — Nutanix"))
    if not tab_defs:
        tab_defs.append(("km", "Classic (KM) — NetBackup"))

    panels = []
    if has_netbackup:
        panels.append(
            dmc.TabsPanel(
                value="km",
                pt="lg",
                children=html.Div(
                    id="backup-netbackup-panel-image",
                    children=build_netbackup_panel(
                        nb_data or {},
                        selected_pools,
                        category="image",
                        policy_type_options=policy_type_options,
                    ),
                ),
            )
        )
    elif any(v == "km" for v, _ in tab_defs):
        panels.append(
            dmc.TabsPanel(
                value="km",
                pt="lg",
                children=dmc.Alert(
                    color="gray",
                    variant="light",
                    title="No NetBackup pools",
                    children="No NetBackup disk pool data for this datacenter.",
                ),
            )
        )
    if has_nutanix or nutanix_panel is not None:
        panels.append(
            dmc.TabsPanel(
                value="hc",
                pt="lg",
                children=nutanix_panel if nutanix_panel is not None else build_hc_image_placeholder(),
            )
        )

    return html.Div(
        children=[
            dmc.Tabs(
                color="indigo",
                variant="outline",
                radius="md",
                id="backup-image-tabs",
                value=tab_defs[0][0],
                children=[
                    dmc.TabsList(
                        children=[dmc.TabsTab(label, value=value) for value, label in tab_defs]
                    ),
                    *panels,
                ],
            )
        ]
    )


def build_application_backup_section(
    *,
    nb_data: dict | None = None,
    selected_pools: Iterable[str] | None = None,
    policy_type_options: list[str] | None = None,
) -> html.Div:
    """Application Backup category: NetBackup non-VMWARE policy types."""
    return html.Div(
        id="backup-netbackup-panel-application",
        children=[
            build_netbackup_panel(
                nb_data or {},
                selected_pools,
                category="application",
                policy_type_options=policy_type_options,
            )
        ]
    )


def build_replication_section(
    *,
    veeam_data: dict | None = None,
    zerto_data: dict | None = None,
    zerto_license: dict | None = None,
    veeam_license: dict | None = None,
    has_veeam: bool = False,
    has_zerto: bool = False,
) -> html.Div:
    """Replication category: Veeam + Zerto (+ licenses when data exists)."""
    tab_defs: list[tuple[str, str]] = []
    if has_zerto:
        tab_defs.append(("zerto", "Zerto"))
    if has_veeam:
        tab_defs.append(("veeam", "Veeam"))
    if not tab_defs:
        return dmc.Alert(
            color="gray",
            variant="light",
            title="No replication services",
            children="No Veeam or Zerto infrastructure data for this datacenter.",
        )

    zerto_license_panel = build_zerto_license_panel(zerto_license)
    veeam_license_panel = build_veeam_license_panel(veeam_license)

    panels = []
    if has_zerto:
        zerto_children = [
            html.Div(
                id="backup-zerto-panel",
                children=build_zerto_panel(zerto_data or {}, None),
            )
        ]
        if zerto_license_panel is not None:
            zerto_children.append(zerto_license_panel)
        elif (zerto_data or {}).get("sites"):
            # Usage present but license payload empty — still show required note
            zerto_children.append(
                dmc.Alert(
                    color="grape",
                    variant="light",
                    title="License required",
                    children="Zerto usage is present; license metrics were not returned for this DC.",
                )
            )
        panels.append(dmc.TabsPanel(value="zerto", pt="lg", children=html.Div(children=zerto_children)))
    if has_veeam:
        veeam_children = [
            html.Div(
                id="backup-veeam-panel",
                children=build_veeam_panel(veeam_data or {}, None),
            )
        ]
        if veeam_license_panel is not None:
            veeam_children.append(veeam_license_panel)
        else:
            veeam_children.append(
                dmc.Alert(
                    color="gray",
                    variant="light",
                    title="Veeam license",
                    children=(
                        "Veeam license is managed at customer level via CRM sold. "
                        "No DC-scoped license inventory in datalake."
                    ),
                )
            )
        panels.append(dmc.TabsPanel(value="veeam", pt="lg", children=html.Div(children=veeam_children)))

    return html.Div(
        children=[
            dmc.Tabs(
                color="violet",
                variant="outline",
                radius="md",
                id="backup-replication-tabs",
                value=tab_defs[0][0],
                children=[
                    dmc.TabsList(
                        children=[dmc.TabsTab(label, value=value) for value, label in tab_defs]
                    ),
                    *panels,
                ],
            )
        ]
    )

