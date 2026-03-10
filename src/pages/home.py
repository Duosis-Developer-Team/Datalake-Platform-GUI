import dash
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from src.services.shared import service
from src.utils.time_range import default_time_range
from src.components.charts import (
    create_energy_breakdown_chart,
    create_grouped_bar_chart,
    create_energy_semi_circle,
    create_dc_treemap,
    create_energy_elite,
    create_energy_elite_v2,
)


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


def platform_card(title, hosts, vms, clusters=None, vios=None, color="#4318FF"):
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
    if vios is not None:
        children[1].children.append(dmc.Group(gap="xs", children=[
            dmc.Text("VIOSes", size="xs", c="dimmed", style={"width": "52px"}),
            dmc.Text(str(vios), size="sm", fw=600, c="#2B3674"),
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
    summaries = service.get_all_datacenters_summary(tr)

    # KPI strip (platforms = Nutanix + vCenter + IBM per DC, summed)
    kpis = [
        metric_card("Data Centers", str(overview.get("dc_count", 0)), "solar:server-square-bold-duotone", "Sites"),
        metric_card("Platforms", f"{overview.get('total_platforms', 0):,}", "solar:box-bold-duotone", "Nutanix + vCenter + IBM"),
        metric_card("Total Hosts", f"{overview.get('total_hosts', 0):,}", "material-symbols:dns-outline", "All platforms", color="teal"),
        metric_card("Total VMs", f"{overview.get('total_vms', 0):,}", "material-symbols:laptop-mac-outline", "Virtual Machines", color="teal"),
        metric_card("Total Energy", f"{overview.get('total_energy_kw', 0):,.0f} kW", "material-symbols:bolt-outline", "Daily average", color="orange"),
    ]

    # Compute architecture breakdown (Classic / Hyperconverged / Power)
    compute   = data.get("compute", {})
    classic   = compute.get("classic",   {})
    hyperconv = compute.get("hyperconv", {})
    power     = compute.get("power",     {})
    platform_cards = [
        platform_card("Classic Compute", classic.get("hosts", 0),   classic.get("vms", 0),   color="#4318FF"),
        platform_card("Hyperconverged",  hyperconv.get("hosts", 0), hyperconv.get("vms", 0), color="#05CD99"),
        platform_card("Power (IBM)",     power.get("hosts", 0),     power.get("lpars", 0),   vios=power.get("vios", 0), color="#FFB547"),
    ]

    # Resource usage percentages
    cpu_cap = overview.get("total_cpu_cap") or 1
    ram_cap = overview.get("total_ram_cap") or 1
    stor_cap = overview.get("total_storage_cap") or 1
    cpu_pct = round((overview.get("total_cpu_used", 0) or 0) / cpu_cap * 100, 1) if cpu_cap > 0 else 0
    ram_pct = round((overview.get("total_ram_used", 0) or 0) / ram_cap * 100, 1) if ram_cap > 0 else 0
    stor_pct = round((overview.get("total_storage_used", 0) or 0) / stor_cap * 100, 1) if stor_cap > 0 else 0

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
                            dmc.Text("Compute Architecture", fw=700, size="lg", c="#2B3674", style={"marginBottom": "4px"}),
                            dmc.Text("Classic · Hyperconverged · Power", size="xs", c="dimmed", style={"marginBottom": "16px"}),
                            dmc.SimpleGrid(cols=3, spacing="md", children=platform_cards),
                        ],
                        className="nexus-card",
                        style={"padding": "24px"},
                    ),
                    html.Div(
                        [
                            dmc.Text("Resource Usage", fw=700, size="lg", c="#2B3674", style={"marginBottom": "4px"}),
                            dmc.Text("Daily average over report period", size="xs", c="dimmed", style={"marginBottom": "20px"}),
                            dmc.SimpleGrid(
                                cols=3,
                                spacing="xl",
                                children=[
                                    _ring_stat(cpu_pct,  "CPU",     "#4318FF"),
                                    _ring_stat(ram_pct,  "RAM",     "#05CD99"),
                                    _ring_stat(stor_pct, "Storage", "#FFB547"),
                                ],
                            ),
                        ],
                        className="nexus-card",
                        style={"padding": "24px"},
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
                        "CPU & RAM: daily averages over the report period.",
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
                                        "CPU %",
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
                                        "RAM %",
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
                                        _pct_badge(s["stats"].get("used_cpu_pct", 0)),
                                        style={"textAlign": "right"},
                                    ),
                                    html.Td(
                                        _pct_badge(s["stats"].get("used_ram_pct", 0)),
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
