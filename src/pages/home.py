import dash
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objects as go
from src.services.shared import service
from src.utils.time_range import default_time_range
from src.utils.format_units import title_case
from src.components.charts import (
    create_energy_breakdown_chart,
    create_grouped_bar_chart,
    create_energy_semi_circle,
    create_dc_treemap,
    create_energy_elite,
    create_energy_elite_v2,
)


_PHYS_INV_BAR_PX = 50  # pixels per bar — controls visible item count in scroll window


def _phys_inv_bar_figure(labels, counts, color="#4318FF", height=None):
    """Horizontal bar chart for Physical Inventory (Overview drill-down). Labels are title-cased."""
    labels = labels or ["No data"]
    counts = counts or [0]
    labels_display = [title_case(str(l)) for l in labels]
    if height is None:
        height = len(labels_display) * _PHYS_INV_BAR_PX
    fig = go.Figure(
        data=[go.Bar(
            x=counts,
            y=labels_display,
            orientation="h",
            marker_color=color,
            text=counts,
            textposition="outside",
            textfont=dict(size=14, color="#2B3674", family="DM Sans, sans-serif"),
        )]
    )
    fig.update_layout(
        margin=dict(l=20, r=60, t=10, b=20),
        height=height,
        bargap=0.35,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=True),
        yaxis=dict(showgrid=False, zeroline=False, categoryorder="total ascending", tickfont=dict(size=13)),
        font=dict(family="DM Sans, sans-serif", color="#A3AED0", size=13),
    )
    return fig


def layout():
    """Default layout (initial load uses default time range)."""
    return build_overview(default_time_range())


def metric_card(title, value, icon_name, subtext=None, color="#4318FF"):
    return html.Div(
        className="nexus-card",
        style={"padding": "20px"},
        children=[
            dmc.Group(
                align="center",
                gap="sm",
                style={"marginBottom": "10px"},
                children=[
                    dmc.ThemeIcon(
                        size="lg",
                        radius="md",
                        variant="light",
                        color=color if color != "#4318FF" else "indigo",
                        children=DashIconify(icon=icon_name, width=22),
                    ),
                    html.H3(
                        title,
                        style={"margin": 0, "color": "#A3AED0", "fontSize": "0.9rem", "fontWeight": "500"},
                    ),
                ],
            ),
            html.H2(
                value,
                style={"margin": "0", "color": "#2B3674", "fontSize": "1.75rem", "fontWeight": "700"},
            ),
            html.P(
                subtext,
                style={"margin": "5px 0 0 0", "color": "#05CD99", "fontSize": "0.8rem", "fontWeight": "600"},
            )
            if subtext
            else None,
        ],
    )


def platform_card(title, hosts, vms, clusters=None, color="#4318FF"):
    children = [
        dmc.Group(
            gap="xs",
            align="center",
            style={"marginBottom": "10px"},
            children=[
                html.Div(style={
                    "width": "10px", "height": "10px",
                    "borderRadius": "50%",
                    "backgroundColor": color,
                    "flexShrink": 0,
                }),
                dmc.Text(title, fw=700, size="sm", c="#2B3674"),
            ],
        ),
        dmc.Stack(
            gap=4,
            children=[
                dmc.Group(gap="xs", children=[
                    dmc.Text("Hosts", size="xs", c="dimmed", style={"width": "52px"}),
                    dmc.Text(str(hosts), size="sm", fw=600, c="#2B3674"),
                ]),
                dmc.Group(gap="xs", children=[
                    dmc.Text("VMs", size="xs", c="dimmed", style={"width": "52px"}),
                    dmc.Text(str(vms), size="sm", fw=600, c="#2B3674"),
                ]),
            ],
        ),
    ]
    if clusters is not None:
        children[1].children.insert(1, dmc.Group(gap="xs", children=[
            dmc.Text("Clusters", size="xs", c="dimmed", style={"width": "52px"}),
            dmc.Text(str(clusters), size="sm", fw=600, c="#2B3674"),
        ]))
    return html.Div(
        style={
            "padding": "14px 16px",
            "borderRadius": "12px",
            "backgroundColor": "#f8f9fa",
            "border": f"1px solid #e9ecef",
            "borderLeftWidth": "3px",
            "borderLeftColor": color,
        },
        children=children,
    )


def _ring_stat(value, label, color):
    """dmc.RingProgress ile tek kaynak kullanım halkası."""
    try:
        v = max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        v = 0.0

    glow_map = {
        "#4318FF": "rgba(67, 24, 255, 0.18)",
        "#05CD99": "rgba(5, 205, 153, 0.18)",
        "#FFB547": "rgba(255, 181, 71, 0.18)",
    }
    glow = glow_map.get(color, "rgba(67,24,255,0.12)")

    return html.Div(
        style={
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "gap": "10px",
        },
        children=[
            dmc.RingProgress(
                size=130,
                thickness=10,
                roundCaps=True,
                sections=[{"value": v, "color": color}],
                style={"filter": f"drop-shadow(0 0 8px {glow})"},
                label=html.Div(
                    style={"textAlign": "center"},
                    children=[
                        dmc.Text(
                            f"{int(v)}%",
                            fw=900,
                            size="xl",
                            c="#2B3674",
                            style={"lineHeight": 1},
                        ),
                    ],
                ),
            ),
            dmc.Text(label, size="sm", fw=600, c="#A3AED0"),
        ],
    )


def _pct_badge(value):
    """CPU/RAM yüzdesini değere göre renk kodlu dmc.Badge ile döndür."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.0

    if v >= 80:
        color, variant = "red", "light"
    elif v >= 50:
        color, variant = "blue", "light"
    else:
        color, variant = "teal", "light"

    if v == 0.0:
        return dmc.Text("—", size="sm", c="dimmed", style={"textAlign": "right"})

    return dmc.Badge(
        f"{v:.1f}%",
        color=color,
        variant=variant,
        radius="sm",
        size="sm",
        style={
            "fontWeight": 600,
            "letterSpacing": 0,
            "fontVariantNumeric": "tabular-nums",
            "minWidth": "52px",
            "textAlign": "center",
        },
    )


def _arch_usage_cell(usage: dict | None):
    """Render architecture usage cell with CPU/RAM/Disk percentages."""
    usage = usage or {}
    cpu = usage.get("cpu_pct", 0.0)
    ram = usage.get("ram_pct", 0.0)
    disk = usage.get("disk_pct", None)

    rows = [
        dmc.Group(
            gap=6,
            align="center",
            children=[
                dmc.Text("CPU", size="xs", c="dimmed"),
                _pct_badge(cpu),
            ],
        ),
        dmc.Group(
            gap=6,
            align="center",
            children=[
                dmc.Text("RAM", size="xs", c="dimmed"),
                _pct_badge(ram),
            ],
        ),
    ]

    if disk is not None:
        rows.append(
            dmc.Group(
                gap=6,
                align="center",
                children=[
                    dmc.Text("Disk", size="xs", c="dimmed"),
                    _pct_badge(disk),
                ],
            )
        )

    return dmc.Stack(gap=4, align="flex-end", children=rows)


def _num_cell(value, suffix=""):
    """Sayısal değeri sağa hizalı, tabular-nums formatında döndür.
    0 ise soluklaştırılmış tire göster."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 0

    if v == 0:
        return dmc.Text("—", size="sm", c="dimmed",
                        style={"textAlign": "right", "fontVariantNumeric": "tabular-nums"})

    return dmc.Text(
        f"{v:,}{suffix}",
        size="sm",
        fw=500,
        c="#2B3674",
        style={"textAlign": "right", "fontVariantNumeric": "tabular-nums"},
    )


def _dc_link(name, dc_id):
    """DC ismini altı çizgisiz, marka renginde, kalın link olarak döndür."""
    return dcc.Link(
        dmc.Text(
            name,
            size="sm",
            fw=700,
            c="#4318FF",
            style={"letterSpacing": "-0.01em"},
        ),
        href=f"/datacenter/{dc_id}",
        style={"textDecoration": "none"},
    )


def build_overview(time_range=None):
    """Build Overview page content for the given time range (used by app callback)."""
    tr = time_range or default_time_range()
    data = service.get_global_dashboard(tr)
    overview = data.get("overview", {})
    platforms = data.get("platforms", {})
    energy_breakdown = data.get("energy_breakdown", {})
    classic_totals = data.get("classic_totals", {})
    hyperconv_totals = data.get("hyperconv_totals", {})
    ibm_totals = data.get("ibm_totals", {})
    summaries = service.get_all_datacenters_summary(tr)

    # KPI strip (platforms = Nutanix + vCenter + IBM per DC, summed)
    kpis = [
        metric_card("Data Centers", str(overview.get("dc_count", 0)), "solar:server-square-bold-duotone", "Sites"),
        metric_card("Platforms", f"{overview.get('total_platforms', 0):,}", "solar:box-bold-duotone", "Nutanix + vCenter + IBM"),
        metric_card("Total Hosts", f"{overview.get('total_hosts', 0):,}", "material-symbols:dns-outline", "All platforms", color="teal"),
        metric_card("Total VMs", f"{overview.get('total_vms', 0):,}", "material-symbols:laptop-mac-outline", "Virtual Machines", color="teal"),
        metric_card("Total Energy", f"{overview.get('total_energy_kw', 0):,.0f} kW", "material-symbols:bolt-outline", "Daily average", color="orange"),
    ]

    # Physical Inventory overview (level 0: by device role)
    # scroll window shows 5 bars; full chart height drives scroll
    phys_inv_by_role = service.get_physical_inventory_overview_by_role()
    phys_inv_labels_0 = [r["role"] for r in phys_inv_by_role]
    phys_inv_counts_0 = [r["count"] for r in phys_inv_by_role]
    _phys_inv_chart_height = max(_PHYS_INV_BAR_PX * 5, len(phys_inv_labels_0) * _PHYS_INV_BAR_PX)
    phys_inv_initial_figure = _phys_inv_bar_figure(
        phys_inv_labels_0, phys_inv_counts_0, height=_phys_inv_chart_height
    )

    # Resource usage percentages per architecture (for tabbed card)
    def _pct(used, cap):
        return round(used / cap * 100, 1) if cap and cap > 0 else 0.0
    classic_cpu_pct = _pct(classic_totals.get("cpu_used", 0) or 0, classic_totals.get("cpu_cap", 0) or 1)
    classic_ram_pct = _pct(classic_totals.get("mem_used", 0) or 0, classic_totals.get("mem_cap", 0) or 1)
    classic_stor_pct = _pct(classic_totals.get("stor_used", 0) or 0, classic_totals.get("stor_cap", 0) or 1)
    hyperconv_cpu_pct = _pct(hyperconv_totals.get("cpu_used", 0) or 0, hyperconv_totals.get("cpu_cap", 0) or 1)
    hyperconv_ram_pct = _pct(hyperconv_totals.get("mem_used", 0) or 0, hyperconv_totals.get("mem_cap", 0) or 1)
    hyperconv_stor_pct = _pct(hyperconv_totals.get("stor_used", 0) or 0, hyperconv_totals.get("stor_cap", 0) or 1)
    ibm_mem_pct = _pct(ibm_totals.get("mem_assigned", 0) or 0, ibm_totals.get("mem_total", 0) or 1)
    ibm_cpu_pct = _pct(ibm_totals.get("cpu_used", 0) or 0, ibm_totals.get("cpu_assigned", 0) or 1)

    # Energy breakdown (IBM Power + vCenter only; Loki/racks not used)
    eb_labels = ["IBM Power", "vCenter"]
    eb_values = [
        energy_breakdown.get("ibm_kw", 0) or 0,
        energy_breakdown.get("vcenter_kw", 0) or 0,
    ]
    if sum(eb_values) == 0:
        eb_values = [1, 1]

    # DC comparison table
    dc_names = [s["name"] for s in summaries]
    dc_hosts = [s["host_count"] for s in summaries]
    dc_vms = [s["vm_count"] for s in summaries]
    dc_cpu_pct = [s["stats"].get("used_cpu_pct", 0) for s in summaries]
    dc_ram_pct = [s["stats"].get("used_ram_pct", 0) for s in summaries]

    return html.Div(
        [
            dmc.Paper(
                p="xl",
                radius="md",
                style={
                    "background": "rgba(255, 255, 255, 0.80)",
                    "backdropFilter": "blur(12px)",
                    "WebkitBackdropFilter": "blur(12px)",
                    "boxShadow": "0 4px 24px rgba(67, 24, 255, 0.07), 0 1px 4px rgba(0, 0, 0, 0.04)",
                    "borderBottom": "1px solid rgba(255, 255, 255, 0.6)",
                    "marginBottom": "28px",
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
                                                icon="solar:chart-2-bold-duotone",
                                                width=28,
                                                color="#4318FF",
                                            ),
                                            html.H2(
                                                "Executive Dashboard",
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
                        ],
                    ),
                ],
            ),
            dmc.SimpleGrid(cols=5, spacing="lg", children=kpis, style={"marginBottom": "24px", "padding": "0 30px"}),
            dmc.SimpleGrid(
                cols=2,
                spacing="lg",
                style={"padding": "0 30px", "marginBottom": "24px"},
                children=[
                    html.Div(
                        [
                            dmc.Group(justify="space-between", align="center", mb="sm", children=[
                                dmc.Stack(gap=2, children=[
                                    dmc.Text("Physical Inventory", fw=700, size="lg", c="#2B3674"),
                                    dmc.Text("Device types · click to drill down", size="xs", c="dimmed"),
                                ]),
                                dmc.Button(
                                    "↩ Reset",
                                    id="phys-inv-reset-btn",
                                    size="xs",
                                    variant="light",
                                    color="indigo",
                                    style={"display": "none"},
                                    n_clicks=0,
                                ),
                            ]),
                            dcc.Store(
                                id="phys-inv-drill-state",
                                data={"level": 0, "role": None, "manufacturer": None},
                            ),
                            html.Div(
                                style={
                                    "maxHeight": f"{_PHYS_INV_BAR_PX * 5 + 20}px",
                                    "overflowY": "auto",
                                },
                                children=dcc.Graph(
                                    id="phys-inv-overview-chart",
                                    figure=phys_inv_initial_figure,
                                    config={"displayModeBar": False},
                                    style={"height": f"{_phys_inv_chart_height}px"},
                                ),
                            ),
                        ],
                        className="nexus-card",
                        style={"padding": "24px"},
                    ),
                    html.Div(
                        [
                            dmc.Text("Resource Usage", fw=700, size="lg", c="#2B3674", style={"marginBottom": "4px"}),
                            dmc.Text("By architecture — daily average over report period", size="xs", c="dimmed", style={"marginBottom": "16px"}),
                            dmc.Tabs(
                                value="classic",
                                variant="outline",
                                radius="md",
                                style={"flex": "1", "display": "flex", "flexDirection": "column"},
                                children=[
                                    dmc.TabsList(children=[
                                        dmc.TabsTab("Klasik Mimari", value="classic"),
                                        dmc.TabsTab("Hyperconverged Mimari", value="hyperconv"),
                                        dmc.TabsTab("IBM Power", value="ibm"),
                                    ]),
                                    dmc.TabsPanel(
                                        value="classic",
                                        pt="xl",
                                        style={"flex": "1", "display": "flex", "alignItems": "center"},
                                        children=dmc.SimpleGrid(
                                            cols=3,
                                            spacing="xl",
                                            style={"width": "100%"},
                                            children=[
                                                _ring_stat(classic_cpu_pct,  "CPU",     "#4318FF"),
                                                _ring_stat(classic_ram_pct,  "RAM",     "#05CD99"),
                                                _ring_stat(classic_stor_pct, "Storage", "#FFB547"),
                                            ],
                                        ),
                                    ),
                                    dmc.TabsPanel(
                                        value="hyperconv",
                                        pt="xl",
                                        style={"flex": "1", "display": "flex", "alignItems": "center"},
                                        children=dmc.SimpleGrid(
                                            cols=3,
                                            spacing="xl",
                                            style={"width": "100%"},
                                            children=[
                                                _ring_stat(hyperconv_cpu_pct,  "CPU",     "#4318FF"),
                                                _ring_stat(hyperconv_ram_pct,  "RAM",     "#05CD99"),
                                                _ring_stat(hyperconv_stor_pct, "Storage", "#FFB547"),
                                            ],
                                        ),
                                    ),
                                    dmc.TabsPanel(
                                        value="ibm",
                                        pt="xl",
                                        style={"flex": "1", "display": "flex", "alignItems": "center"},
                                        children=dmc.SimpleGrid(
                                            cols=2,
                                            spacing="xl",
                                            style={"width": "100%"},
                                            children=[
                                                _ring_stat(ibm_mem_pct, "Memory Assigned", "#05CD99"),
                                                _ring_stat(ibm_cpu_pct, "CPU Used", "#4318FF"),
                                            ],
                                        ),
                                    ),
                                ],
                            ),
                        ],
                        className="nexus-card",
                        style={"padding": "24px", "display": "flex", "flexDirection": "column"},
                    ),
                ],
            ),
            dmc.SimpleGrid(
                cols=2,
                spacing="lg",
                style={"padding": "0 30px", "marginBottom": "24px"},
                children=[
                    html.Div(
                        [
                            dmc.Text("Energy by Source", fw=700, size="lg", c="#2B3674", style={"marginBottom": "4px"}),
                            dmc.Text("Daily average (kW) — IBM Power & vCenter", size="xs", c="dimmed", style={"marginBottom": "12px"}),
                            html.Div(
                                dcc.Graph(
                                    id="energy-elite-graph",
                                    figure=create_energy_elite_v2(eb_labels, eb_values, height=300),
                                    config={"displayModeBar": False},
                                    style={"height": "300px"},
                                ),
                                style={
                                    "filter": "drop-shadow(0 0 10px rgba(67, 24, 255, 0.35))",
                                    "WebkitFilter": "drop-shadow(0 0 10px rgba(67, 24, 255, 0.35))",
                                    "borderRadius": "50%",
                                    "overflow": "hidden",
                                },
                            ),
                        ],
                        className="nexus-card",
                        style={"padding": "24px"},
                    ),
                    html.Div(
                        [
                            dmc.Text("DC Landscape", fw=700, size="lg", c="#2B3674", style={"marginBottom": "4px"}),
                            dmc.Text("VM distribution across Data Centers — area = VM count", size="xs", c="dimmed", style={"marginBottom": "12px"}),
                            dcc.Graph(
                                figure=create_dc_treemap(dc_names, dc_vms, height=320),
                                config={"displayModeBar": False},
                                style={"height": "320px", "borderRadius": "12px", "overflow": "hidden"},
                            ),
                        ],
                        className="nexus-card",
                        style={"padding": "24px"},
                    ),
                ],
            ),
            html.Div(
                className="nexus-card nexus-table",
                style={
                    "margin": "0 30px",
                    "padding": "24px",
                    "overflowX": "auto",
                },
                children=[
                    dmc.Text(
                        "DC Summary",
                        fw=700,
                        size="lg",
                        c="#2B3674",
                        style={"marginBottom": "4px"},
                    ),
                    dmc.Text(
                        "CPU, RAM & Disk utilisation by architecture — daily averages over the report period.",
                        size="xs",
                        c="dimmed",
                        style={"marginBottom": "18px"},
                    ),
                    dmc.Table(
                        striped=True,
                        highlightOnHover=True,
                        withTableBorder=False,
                        withColumnBorders=False,
                        verticalSpacing="sm",
                        horizontalSpacing="md",
                        children=[
                            html.Thead(
                                html.Tr([
                                    html.Th(
                                        "Data Center",
                                        style={
                                            "color": "#A3AED0",
                                            "fontWeight": 600,
                                            "fontSize": "0.72rem",
                                            "textTransform": "uppercase",
                                            "letterSpacing": "0.07em",
                                            "paddingBottom": "12px",
                                            "borderBottom": "2px solid #f1f3f5",
                                            "textAlign": "left",
                                        },
                                    ),
                                    html.Th(
                                        "Location",
                                        style={
                                            "color": "#A3AED0",
                                            "fontWeight": 600,
                                            "fontSize": "0.72rem",
                                            "textTransform": "uppercase",
                                            "letterSpacing": "0.07em",
                                            "paddingBottom": "12px",
                                            "borderBottom": "2px solid #f1f3f5",
                                            "textAlign": "left",
                                        },
                                    ),
                                    html.Th(
                                        "Platforms",
                                        style={
                                            "color": "#A3AED0",
                                            "fontWeight": 600,
                                            "fontSize": "0.72rem",
                                            "textTransform": "uppercase",
                                            "letterSpacing": "0.07em",
                                            "paddingBottom": "12px",
                                            "borderBottom": "2px solid #f1f3f5",
                                            "textAlign": "right",
                                        },
                                    ),
                                    html.Th(
                                        "Hosts",
                                        style={
                                            "color": "#A3AED0",
                                            "fontWeight": 600,
                                            "fontSize": "0.72rem",
                                            "textTransform": "uppercase",
                                            "letterSpacing": "0.07em",
                                            "paddingBottom": "12px",
                                            "borderBottom": "2px solid #f1f3f5",
                                            "textAlign": "right",
                                        },
                                    ),
                                    html.Th(
                                        "VMs",
                                        style={
                                            "color": "#A3AED0",
                                            "fontWeight": 600,
                                            "fontSize": "0.72rem",
                                            "textTransform": "uppercase",
                                            "letterSpacing": "0.07em",
                                            "paddingBottom": "12px",
                                            "borderBottom": "2px solid #f1f3f5",
                                            "textAlign": "right",
                                        },
                                    ),
                                    html.Th(
                                        "Classic",
                                        style={
                                            "color": "#A3AED0",
                                            "fontWeight": 600,
                                            "fontSize": "0.72rem",
                                            "textTransform": "uppercase",
                                            "letterSpacing": "0.07em",
                                            "paddingBottom": "12px",
                                            "borderBottom": "2px solid #f1f3f5",
                                            "textAlign": "right",
                                        },
                                    ),
                                    html.Th(
                                        "Hyperconverged",
                                        style={
                                            "color": "#A3AED0",
                                            "fontWeight": 600,
                                            "fontSize": "0.72rem",
                                            "textTransform": "uppercase",
                                            "letterSpacing": "0.07em",
                                            "paddingBottom": "12px",
                                            "borderBottom": "2px solid #f1f3f5",
                                            "textAlign": "right",
                                        },
                                    ),
                                    html.Th(
                                        "IBM Power",
                                        style={
                                            "color": "#A3AED0",
                                            "fontWeight": 600,
                                            "fontSize": "0.72rem",
                                            "textTransform": "uppercase",
                                            "letterSpacing": "0.07em",
                                            "paddingBottom": "12px",
                                            "borderBottom": "2px solid #f1f3f5",
                                            "textAlign": "right",
                                        },
                                    ),
                                ])
                            ),
                            html.Tbody([
                                html.Tr([
                                    html.Td(_dc_link(s["name"], s["id"])),
                                    html.Td(
                                        dmc.Text(s["location"], size="sm", c="dimmed")
                                    ),
                                    html.Td(
                                        _num_cell(s.get("platform_count", 0)),
                                        style={"textAlign": "right"},
                                    ),
                                    html.Td(
                                        _num_cell(s["host_count"]),
                                        style={"textAlign": "right"},
                                    ),
                                    html.Td(
                                        _num_cell(s["vm_count"]),
                                        style={"textAlign": "right"},
                                    ),
                                    html.Td(
                                        _arch_usage_cell(
                                            s["stats"].get("arch_usage", {}).get("classic")
                                        ),
                                        style={"textAlign": "right"},
                                    ),
                                    html.Td(
                                        _arch_usage_cell(
                                            s["stats"].get("arch_usage", {}).get("hyperconv")
                                        ),
                                        style={"textAlign": "right"},
                                    ),
                                    html.Td(
                                        _arch_usage_cell(
                                            s["stats"].get("arch_usage", {}).get("ibm")
                                        ),
                                        style={"textAlign": "right"},
                                    ),
                                ])
                                for s in summaries
                            ]),
                        ],
                    ),
                ],
            ),
        ]
    )
