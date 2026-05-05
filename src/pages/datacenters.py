from __future__ import annotations
import dash
from dash import html, dcc, callback, Input, Output, State, callback_context
import dash_mantine_components as dmc
import plotly.graph_objects as go
from dash_iconify import DashIconify
from src.services import api_client as api
from src.services import sla_service
from src.utils.time_range import default_time_range
from src.utils.export_helpers import (
    records_to_dataframe,
    dataframes_to_excel_with_meta,
    csv_bytes_with_report_header,
    dash_send_excel_workbook,
    dash_send_csv_bytes,
    build_report_info_df,
)
from src.utils.dc_display import format_dc_display_name


def _hex_to_rgb(hex_color: str) -> str:
    """Convert #RRGGBB to 'R, G, B' string for rgba() use."""
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}"


def _usage_ring(label: str, icon: str, pct: float, ok_color: str) -> html.Div:
    """Premium ring gauge for CPU/RAM footer."""
    fill  = ok_color if pct < 75 else "#FFB547" if pct < 90 else "#EE5D50"
    track = f"rgba({_hex_to_rgb(ok_color)}, 0.08)"
    return html.Div(
        style={
            "flex": 1,
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "gap": "4px",
        },
        children=[
            dmc.RingProgress(
                size=82,
                thickness=8,
                roundCaps=True,
                sections=[
                    {"value": min(pct, 100), "color": fill},
                    {"value": max(0.0, 100 - pct), "color": track},
                ],
                label=html.Div(
                    style={"textAlign": "center", "lineHeight": 1},
                    children=[
                        DashIconify(icon=icon, width=13, color=fill),
                        html.Div(
                            style={"marginTop": "2px"},
                            children=[
                                html.Span(f"{pct:.0f}", style={
                                    "fontSize": "0.82rem",
                                    "fontWeight": 900,
                                    "color": fill,
                                    "letterSpacing": "-0.02em",
                                }),
                                html.Span("%", style={
                                    "fontSize": "0.55rem",
                                    "fontWeight": 700,
                                    "color": fill,
                                }),
                            ],
                        ),
                    ],
                ),
            ),
            html.Span(label, style={
                "fontSize": "0.60rem",
                "fontWeight": 700,
                "color": "#A3AED0",
                "textTransform": "uppercase",
                "letterSpacing": "0.07em",
            }),
        ],
    )


def _summary_kpi(icon: str, label: str, value: str, color: str = "indigo") -> html.Div:
    """Single KPI card for the summary strip."""
    return html.Div(
        className="dc-summary-kpi nexus-card",
        style={
            "padding": "16px 20px",
            "display": "flex",
            "alignItems": "center",
            "gap": "14px",
            "borderRadius": "28px",
            "background": "rgba(255,255,255,0.90)",
            "backdropFilter": "blur(12px)",
            "WebkitBackdropFilter": "blur(12px)",
            "boxShadow": "0 2px 12px rgba(67,24,255,0.06)",
            "border": "1px solid rgba(255,255,255,0.7)",
            "flex": 1,
            "minWidth": "140px",
        },
        children=[
            dmc.ThemeIcon(
                size=44,
                radius="xl",
                variant="light",
                color=color,
                children=DashIconify(icon=icon, width=22),
            ),
            html.Div([
                html.Div(label, style={
                    "fontSize": "0.68rem",
                    "fontWeight": 700,
                    "color": "#A3AED0",
                    "textTransform": "uppercase",
                    "letterSpacing": "0.07em",
                    "marginBottom": "2px",
                }),
                html.Div(str(value), style={
                    "fontSize": "1.45rem",
                    "fontWeight": 900,
                    "color": "#2B3674",
                    "letterSpacing": "-0.02em",
                    "lineHeight": 1.1,
                    "fontVariantNumeric": "tabular-nums",
                }),
            ]),
        ],
    )


def _dc_sellable_ribbon(sales_v2: dict | None) -> html.Div:
    """Compact CRM sellable-remaining strip (80%% policy, v2 API)."""
    if not isinstance(sales_v2, dict):
        return html.Div()
    pct = float(sales_v2.get("general_remaining_pct") or 0.0)
    pr = sales_v2.get("per_resource") or {}
    cpu = pr.get("cpu") or {}
    ram = pr.get("ram") or {}
    tip = (
        f"CPU headroom %: {cpu.get('remaining_sellable_pct')} | "
        f"RAM headroom %: {ram.get('remaining_sellable_pct')} | "
        f"Approx. potential TL: {sales_v2.get('potential_revenue_tl')}"
    )
    return dmc.Tooltip(
        label=tip,
        position="bottom",
        withArrow=True,
        multiline=True,
        w=320,
        children=html.Div(
            style={"marginTop": "6px"},
            children=[
                dmc.Group(
                    justify="space-between",
                    gap="xs",
                    mb=4,
                    children=[
                        dmc.Text("Satılabilir kalan (CRM)", size="xs", fw=600, c="#A3AED0"),
                        dmc.Text(f"{pct:.1f}%", size="xs", fw=800, c="#4318FF"),
                    ],
                ),
                dmc.Progress(value=min(100.0, max(0.0, pct)), color="indigo", size="sm", radius="xl"),
            ],
        ),
    )


def _dc_vault_card(dc, sla_entry=None, sales_v2: dict | None = None):
    """Elite DC Vault card: shimmer, dual ring, CPU/RAM footer, SLA accent."""
    dc_title = format_dc_display_name(dc.get("name"), dc.get("description"))
    stats    = dc.get("stats") or {}

    ibm_kw      = float(stats.get("ibm_kw", 0.0) or 0.0)
    vcenter_kw  = float(stats.get("vcenter_kw", 0.0) or 0.0)
    total_kw    = float(stats.get("total_energy_kw", 0.0) or 0.0)
    cpu_pct     = float(stats.get("used_cpu_pct", 0.0) or 0.0)
    ram_pct     = float(stats.get("used_ram_pct", 0.0) or 0.0)
    storage_pct = float(stats.get("used_storage_pct", 0.0) or 0.0)

    # SLA colour coding — accent always unified brand green; pulse reflects SLA
    accent_class = "dc-accent-healthy"
    sla_pct = float((sla_entry or {}).get("availability_pct", 100.0) or 100.0)
    if sla_pct >= 99.5:
        pulse_class = "dc-pulse-dot dc-pulse-dot-ok"
    elif sla_pct >= 99.0:
        pulse_class = "dc-pulse-dot dc-pulse-dot-warn"
    else:
        pulse_class = "dc-pulse-dot dc-pulse-dot-critical"

    # Metric rows
    metrics = [
        {"icon": "solar:layers-minimalistic-bold-duotone", "color": "blue",   "label": "Platforms", "value": dc.get("platform_count", 0)},
        {"icon": "solar:box-bold-duotone",                 "color": "grape",  "label": "Clusters",  "value": dc.get("cluster_count", 0)},
        {"icon": "solar:server-bold-duotone",              "color": "orange", "label": "Hosts",     "value": f"{dc.get('host_count', 0):,}"},
        {"icon": "solar:laptop-bold-duotone",              "color": "teal",   "label": "VMs",       "value": f"{dc.get('vm_count', 0):,}"},
    ]

    metric_rows = [
        html.Div(
            className="dc-metric-row",
            children=dmc.Group(
                justify="space-between",
                align="center",
                children=[
                    dmc.Group(
                        gap="xs",
                        align="center",
                        children=[
                            dmc.ThemeIcon(
                                size="sm",
                                variant="light",
                                color=m["color"],
                                radius="md",
                                children=DashIconify(icon=m["icon"], width=14),
                            ),
                            dmc.Text(m["label"], size="sm", c="#A3AED0", fw=500),
                        ],
                    ),
                    dmc.Text(
                        str(m["value"]),
                        fw=800,
                        size="sm",
                        c="#2B3674",
                        style={"fontVariantNumeric": "tabular-nums", "letterSpacing": "-0.01em"},
                    ),
                ],
            ),
        )
        for m in metrics
    ]

    # Location badge
    location_badge = dmc.Badge(
        dmc.Group(
            gap=4,
            align="center",
            children=[
                DashIconify(icon="solar:map-point-bold-duotone", width=11),
                dc.get("location", "—"),
            ],
        ),
        variant="light",
        color="indigo",
        radius="xl",
        size="xs",
        style={"textTransform": "none", "fontWeight": 600, "padding": "2px 8px", "letterSpacing": 0},
    )

    # Nested chart: outer arc = storage %, inner pie = power distribution (IBM / vCenter)
    _stor_remaining = max(0.01, 100.0 - storage_pct)

    _fig = go.Figure()

    # ── Storage track (background ring) ──
    _fig.add_trace(go.Pie(
        values=[1],
        labels=[""],
        hole=0.73,
        domain={"x": [0.0, 1.0], "y": [0.0, 1.0]},
        marker=dict(colors=["rgba(5,205,153,0.12)"], line=dict(width=0)),
        textinfo="none", showlegend=False, sort=False, hoverinfo="skip",
    ))

    # ── Storage arc ──
    _fig.add_trace(go.Pie(
        values=[storage_pct, _stor_remaining],
        labels=["Storage", ""],
        hole=0.73,
        domain={"x": [0.0, 1.0], "y": [0.0, 1.0]},
        marker=dict(colors=["#05CD99", "rgba(0,0,0,0)"], line=dict(width=0)),
        textinfo="none",
        showlegend=False,
        sort=False,
        direction="clockwise",
        rotation=270,
        hovertemplate=[
            f"Storage Used: {storage_pct:.1f}%<extra></extra>",
            "<extra></extra>",
        ],
    ))

    # ── Inner pie — power distribution (IBM kW / vCenter kW) ──
    if total_kw > 0:
        _inner_vals        = []
        _inner_labels      = []
        _inner_colors_list = []
        for _val, _lbl, _clr in [
            (ibm_kw,     "IBM",     "#3B82F6"),
            (vcenter_kw, "vCenter", "#EF4444"),
        ]:
            if _val > 0:
                _inner_vals.append(_val)
                _inner_labels.append(_lbl)
                _inner_colors_list.append(_clr)
        if not _inner_vals:
            _inner_vals, _inner_labels, _inner_colors_list = [1.0], ["No Data"], ["#EEF2FF"]
    else:
        _inner_vals, _inner_labels, _inner_colors_list = [1.0], ["No Data"], ["#EEF2FF"]

    _fig.add_trace(go.Pie(
        values=_inner_vals,
        labels=_inner_labels,
        hole=0,
        domain={"x": [0.145, 0.855], "y": [0.145, 0.855]},
        marker=dict(
            colors=_inner_colors_list,
            line=dict(width=2.5, color="rgba(255,255,255,0.95)"),
        ),
        textinfo="none",
        showlegend=False,
        sort=False,
        hovertemplate="%{label}: %{value:.1f} kW (%{percent})<extra></extra>",
    ))

    _fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        height=152,
        showlegend=False,
    )

    power_dial = dmc.Stack(
        gap=4,
        align="center",
        children=[
            dcc.Graph(
                figure=_fig,
                config={"displayModeBar": False},
                style={"height": "152px", "width": "152px"},
            ),
            html.Div(
                style={"marginTop": "-4px", "textAlign": "center"},
                children=[
                    html.Span("Power ", style={"fontSize": "0.72rem", "fontWeight": 700, "color": "#A3AED0"}),
                    html.Span(f"{total_kw:.1f} kW", style={"fontSize": "0.72rem", "fontWeight": 600, "color": "#05CD99", "fontVariantNumeric": "tabular-nums"}),
                ],
            ),
            html.Div(
                style={"textAlign": "center", "marginTop": "0px"},
                children=[
                    html.Span("Storage ", style={"fontSize": "0.68rem", "fontWeight": 700, "color": "#A3AED0"}),
                    html.Span(f"{storage_pct:.0f}%", style={"fontSize": "0.68rem", "fontWeight": 700, "color": "#05CD99", "fontVariantNumeric": "tabular-nums"}),
                ],
            ),
        ],
    )

    # CPU / RAM footer rings
    resource_footer = html.Div(
        style={
            "display": "flex",
            "gap": "8px",
            "paddingTop": "8px",
            "borderTop": "1px solid rgba(227, 234, 252, 0.8)",
            "marginTop": "4px",
            "justifyContent": "space-around",
        },
        children=[
            _usage_ring("CPU", "solar:cpu-bolt-bold-duotone",    cpu_pct, "#4318FF"),
            _usage_ring("RAM", "solar:database-bold-duotone",    ram_pct, "#7551FF"),
        ],
    )

    return dmc.Paper(
        className=f"dc-vault-card {accent_class}",
        p="lg",
        radius="lg",
        style={
            "background": "rgba(255, 255, 255, 0.88)",
            "backdropFilter": "blur(16px)",
            "WebkitBackdropFilter": "blur(16px)",
            "boxShadow": (
                "0 2px 16px rgba(67, 24, 255, 0.07), "
                "0 1px 4px rgba(0,0,0,0.04)"
            ),
            "border": "1px solid rgba(255, 255, 255, 0.75)",
            "height": "100%",
            "display": "flex",
            "flexDirection": "column",
            "gap": "12px",
            "overflow": "hidden",
            "position": "relative",
        },
        children=[
            # Shimmer overlay
            html.Div(className="dc-shimmer"),

            # Header
            dmc.Group(
                justify="space-between",
                align="flex-start",
                children=[
                    dmc.Group(
                        gap="xs",
                        align="flex-start",
                        children=[
                            dmc.Tooltip(
                                label=sla_service.format_availability_tooltip(sla_entry),
                                position="top",
                                withArrow=True,
                                children=html.Div(
                                    className=pulse_class,
                                    style={"marginTop": "5px"},
                                ),
                            ),
                            dmc.Stack(
                                gap=3,
                                children=[
                                    html.Div(
                                        className="dc-title-wrap",
                                        children=html.Span(
                                            dc_title,
                                            className="dc-title-long" if len(dc_title) > 16 else "",
                                            style={
                                                "fontWeight": 800,
                                                "fontSize": "1rem",
                                                "color": "#2B3674",
                                                "letterSpacing": "-0.01em",
                                                "lineHeight": "1.2",
                                                "whiteSpace": "nowrap",
                                            },
                                        ),
                                    ),
                                    location_badge,
                                ],
                            ),
                        ],
                    ),
                    dcc.Link(
                        dmc.Badge(
                            "Details →",
                            className="dc-details-badge",
                            variant="light",
                            color="indigo",
                            size="sm",
                            radius="xl",
                            style={"cursor": "pointer", "textDecoration": "none"},
                        ),
                        href=f"/datacenter/{dc['id']}",
                        style={"textDecoration": "none"},
                    ),
                ],
            ),

            # Thin divider
            html.Div(style={"height": "1px", "background": "rgba(227, 234, 252, 0.8)"}),

            # Main row: metrics | divider | dual ring
            html.Div(
                style={
                    "display": "flex",
                    "flexDirection": "row",
                    "alignItems": "stretch",
                    "gap": "14px",
                    "flex": 1,
                },
                children=[
                    dmc.Stack(gap=2, style={"flex": 1}, children=metric_rows),
                    html.Div(
                        style={
                            "width": "1px",
                            "background": "linear-gradient(to bottom, transparent, rgba(67,24,255,0.10), transparent)",
                            "alignSelf": "stretch",
                            "flexShrink": 0,
                        }
                    ),
                    html.Div(
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "justifyContent": "center",
                        },
                        children=[power_dial],
                    ),
                ],
            ),

            # CPU / RAM footer
            resource_footer,
            _dc_sellable_ribbon(sales_v2),
        ],
    )


def build_datacenters(time_range=None, visible_sections=None):
    """Build Data Centers page content for the given time range."""
    tr = time_range or default_time_range()
    vs = visible_sections

    def ds(code: str) -> bool:
        return vs is None or code in vs

    datacenters = api.get_all_datacenters_summary(tr)
    sla_by_dc   = api.get_sla_by_dc(tr)

    v2_by_dc: dict[str, dict] = {}
    total_potential_tl = 0.0
    for dc in datacenters:
        cid = dc.get("id")
        if cid is None:
            continue
        v2 = api.get_dc_sales_potential_v2(str(cid))
        v2_by_dc[str(cid)] = v2 if isinstance(v2, dict) else {}
        total_potential_tl += float((v2 or {}).get("potential_revenue_tl") or 0.0)

    # ── Export rows ──
    export_rows = []
    for dc in datacenters:
        dc_id = dc.get("id", "")
        stats = dc.get("stats") or {}
        sla   = sla_by_dc.get(dc_id) or sla_by_dc.get(str(dc_id).upper()) if sla_by_dc else None
        export_rows.append({
            "DC":             format_dc_display_name(dc.get("name"), dc.get("description")) or dc.get("name", dc_id),
            "DC_ID":          dc_id,
            "Location":       dc.get("location", ""),
            "Site_Name":      dc.get("site_name", ""),
            "Hosts":          dc.get("host_count", 0),
            "VMs":            dc.get("vm_count", 0),
            "Clusters":       dc.get("cluster_count", 0),
            "Platforms":      dc.get("platform_count", 0),
            "CPU_Used_pct":   stats.get("used_cpu_pct", ""),
            "RAM_Used_pct":   stats.get("used_ram_pct", ""),
            "Total_Energy_kW": stats.get("total_energy_kw", ""),
            "IBM_Energy_kW":  stats.get("ibm_kw", ""),
            "SLA_pct":        (sla or {}).get("availability_pct", "") if sla else "",
        })

    # ── Aggregate metrics for summary strip (C1) ──
    total_hosts    = sum(dc.get("host_count", 0) for dc in datacenters)
    total_vms      = sum(dc.get("vm_count", 0) for dc in datacenters)
    total_clusters = sum(dc.get("cluster_count", 0) for dc in datacenters)
    total_power    = sum(
        float((dc.get("stats") or {}).get("total_energy_kw", 0) or 0)
        for dc in datacenters
    )

    # ── Summary KPI Strip (C2) ──
    summary_strip = html.Div(
        style={
            "display": "flex",
            "gap": "12px",
            "padding": "0 32px",
            "marginBottom": "24px",
            "flexWrap": "wrap",
        },
        children=[
            _summary_kpi("solar:server-bold-duotone",               "Active DCs",  str(len(datacenters)),  "indigo"),
            _summary_kpi("solar:server-minimalistic-bold-duotone",  "Total Hosts", f"{total_hosts:,}",     "orange"),
            _summary_kpi("solar:laptop-bold-duotone",               "Total VMs",   f"{total_vms:,}",       "teal"),
            _summary_kpi("solar:box-bold-duotone",                  "Clusters",    f"{total_clusters:,}",  "grape"),
            _summary_kpi("solar:bolt-bold-duotone",                 "Total Power", f"{total_power:.1f} kW","yellow"),
            _summary_kpi(
                "solar:money-bag-bold-duotone",
                "Potansiyel gelir (TL, CRM v2)",
                f"{total_potential_tl:,.0f}",
                "indigo",
            ),
        ],
    )

    return html.Div([
        dcc.Store(
            id="datacenters-export-store",
            data={"rows": export_rows, "period": f"{tr.get('start', '')}_{tr.get('end', '')}"},
        ),
        dcc.Download(id="datacenters-export-download"),

        # Aurora background (B1)
        html.Div(className="dc-aurora-bg"),

        # Header (B2)
        dmc.Paper(
            p="xl",
            radius=28,
            style={
                "background": "rgba(255, 255, 255, 0.88)",
                "backdropFilter": "blur(20px)",
                "WebkitBackdropFilter": "blur(20px)",
                "boxShadow": (
                    "0 4px 24px rgba(67, 24, 255, 0.08), "
                    "0 1px 4px rgba(0,0,0,0.03), "
                    "0 1px 0 rgba(67, 24, 255, 0.10)"
                ),
                "border": "none",
                "marginBottom": "20px",
            },
            children=[
                dmc.Group(
                    justify="space-between",
                    align="center",
                    children=[
                        dmc.Stack(
                            gap=10,
                            children=[
                                dmc.Group(
                                    gap="sm",
                                    align="center",
                                    children=[
                                        DashIconify(
                                            icon="solar:server-square-bold-duotone",
                                            width=28,
                                            color="#4318FF",
                                        ),
                                        html.H2(
                                            "Data Centers",
                                            style={
                                                "margin": 0,
                                                "fontWeight": 900,
                                                "letterSpacing": "-0.02em",
                                                "lineHeight": 1.2,
                                                "fontSize": "1.75rem",
                                                "background": "linear-gradient(90deg, #1a1b41 0%, #4318FF 100%)",
                                                "WebkitBackgroundClip": "text",
                                                "WebkitTextFillColor": "transparent",
                                                "backgroundClip": "text",
                                            },
                                        ),
                                    ],
                                ),
                                dmc.Badge(
                                    children=[
                                        dmc.Group(
                                            gap=6,
                                            align="center",
                                            children=[
                                                DashIconify(
                                                    icon="solar:calendar-mark-bold-duotone",
                                                    width=13,
                                                ),
                                                f"{tr.get('start', '')} – {tr.get('end', '')}",
                                            ],
                                        )
                                    ],
                                    variant="light",
                                    color="indigo",
                                    radius="xl",
                                    size="md",
                                    style={"textTransform": "none", "fontWeight": 500, "letterSpacing": 0},
                                ),
                            ],
                        ),
                        dmc.Group(
                            gap="md",
                            align="center",
                            children=[
                                (
                                    dmc.Stack(
                                        gap=6,
                                        align="flex-end",
                                        children=[
                                            dmc.Text("Export", size="xs", c="dimmed", fw=600),
                                            dmc.Group(
                                                gap="xs",
                                                children=[
                                                    dmc.Button("CSV",   id="datacenters-export-csv",  size="xs", variant="light", color="indigo"),
                                                    dmc.Button("Excel", id="datacenters-export-xlsx", size="xs", variant="light", color="indigo"),
                                                    dmc.Button("PDF",   id={"type": "pdf-export-btn", "index": "datacenters"},  size="xs", variant="light", color="indigo"),
                                                ],
                                            ),
                                        ],
                                    )
                                    if ds("action:datacenters:export")
                                    else html.Div()
                                ),
                                dmc.Badge(
                                    children=[
                                        dmc.Group(
                                            gap=6,
                                            align="center",
                                            children=[
                                                DashIconify(
                                                    icon="solar:check-circle-bold-duotone",
                                                    width=15,
                                                    color="#05CD99",
                                                ),
                                                f"{len(datacenters)} Active DCs",
                                            ],
                                        )
                                    ],
                                    variant="light",
                                    color="teal",
                                    radius="xl",
                                    size="lg",
                                    style={
                                        "textTransform": "none",
                                        "fontWeight": 600,
                                        "letterSpacing": 0,
                                        "padding": "8px 14px",
                                    },
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),

        # Summary KPI Strip (C)
        summary_strip,

        # DC Card Grid — stagger wrapped (E1)
        (
            dmc.SimpleGrid(
                cols=3,
                spacing="lg",
                style={"padding": "0 32px"},
                children=[
                    html.Div(
                        className=f"dc-card-enter dc-card-n{min(i + 1, 12)}",
                        style={"height": "100%"},
                        children=_dc_vault_card(
                            dc,
                            sla_by_dc.get(dc.get("id"))
                            or sla_by_dc.get(str(dc.get("id", "")).upper()),
                            sales_v2=v2_by_dc.get(str(dc.get("id", ""))),
                        ),
                    )
                    for i, dc in enumerate(datacenters)
                ],
            )
            if ds("sec:datacenters:grid")
            else dmc.Alert(
                "You do not have access to the data center grid for this page.",
                title="Restricted",
                color="gray",
            )
        ),
    ])


def layout():
    return build_datacenters(default_time_range())


@callback(
    Output("datacenters-export-download", "data"),
    Input("datacenters-export-csv",  "n_clicks"),
    Input("datacenters-export-xlsx", "n_clicks"),
    State("datacenters-export-store", "data"),
    State("app-time-range", "data"),
    prevent_initial_call=True,
)
def export_datacenters_page(nc1, nc2, store, time_range):
    if not store:
        raise dash.exceptions.PreventUpdate
    tid  = str(callback_context.triggered_id)
    rows = store.get("rows") or []
    df   = records_to_dataframe(rows if isinstance(rows, list) else [])
    sheets = {"DC_List": df}

    if "xlsx" in tid:
        content = dataframes_to_excel_with_meta(sheets, time_range, "Data_Centers", None)
        return dash_send_excel_workbook(content, "datacenters")
    report_info = build_report_info_df(time_range, "Data_Centers", None)
    return dash_send_csv_bytes(
        csv_bytes_with_report_header(report_info, [("DC_List", df)]),
        "datacenters",
    )
