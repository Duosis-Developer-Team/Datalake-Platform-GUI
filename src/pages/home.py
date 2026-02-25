import dash
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from src.services.shared import service
from src.utils.time_range import default_time_range
from src.components.charts import (
    create_usage_donut_chart,
    create_energy_breakdown_chart,
    create_grouped_bar_chart,
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


def platform_card(title, hosts, vms, clusters=None, color="#4318FF"):
    children = [
        dmc.Text(title, fw=700, size="sm", c="#2B3674", style={"marginBottom": "8px"}),
        dmc.Group(gap="lg", children=[dmc.Text(f"Hosts: {hosts}", size="sm", c="#A3AED0"), dmc.Text(f"VMs: {vms}", size="sm", c="#A3AED0")]),
    ]
    if clusters is not None:
        children.insert(1, dmc.Text(f"Clusters: {clusters}", size="sm", c="#A3AED0"))
    return html.Div(
        className="nexus-card",
        style={"padding": "16px", "borderLeft": f"4px solid {color}"},
        children=children,
    )


def build_overview(time_range=None):
    """Build Overview page content for the given time range (used by app callback)."""
    tr = time_range or default_time_range()
    data = service.get_global_dashboard(tr)
    overview = data.get("overview", {})
    platforms = data.get("platforms", {})
    energy_breakdown = data.get("energy_breakdown", {})
    summaries = service.get_all_datacenters_summary(tr)

    # KPI strip
    kpis = [
        metric_card("Data Centers", str(overview.get("dc_count", 0)), "solar:server-square-bold-duotone", "Sites"),
        metric_card("Total Hosts", f"{overview.get('total_hosts', 0):,}", "material-symbols:dns-outline", "All platforms", color="teal"),
        metric_card("Total VMs", f"{overview.get('total_vms', 0):,}", "material-symbols:laptop-mac-outline", "Virtual Machines", color="teal"),
        metric_card("Total Clusters", f"{overview.get('total_clusters', 0):,}", "solar:box-bold-duotone", "Intel virtualization"),
        metric_card("Total Energy", f"{overview.get('total_energy_kw', 0):,.0f} kW", "material-symbols:bolt-outline", "Real-time Power", color="orange"),
    ]

    # Platform breakdown
    nutanix = platforms.get("nutanix", {})
    vmware = platforms.get("vmware", {})
    ibm = platforms.get("ibm", {})
    platform_cards = [
        platform_card("Nutanix", nutanix.get("hosts", 0), nutanix.get("vms", 0), color="#4318FF"),
        platform_card("VMware", vmware.get("hosts", 0), vmware.get("vms", 0), vmware.get("clusters"), color="#05CD99"),
        platform_card("IBM Power", ibm.get("hosts", 0), ibm.get("lpars", 0), color="#FFB547"),
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
            html.Div(
                className="nexus-glass",
                children=[
                    html.H1("Executive Dashboard", style={"margin": 0, "color": "#2B3674", "fontSize": "1.5rem"}),
                    html.P(f"Report period: {tr.get('start', '')} – {tr.get('end', '')}", style={"margin": "5px 0 0 0", "color": "#A3AED0"}),
                ],
                style={"padding": "20px 30px", "marginBottom": "30px", "borderRadius": "0 0 20px 20px"},
            ),
            dmc.SimpleGrid(cols=5, spacing="lg", children=kpis, style={"marginBottom": "24px", "padding": "0 30px"}),
            dmc.SimpleGrid(
                cols=2,
                spacing="lg",
                style={"padding": "0 30px", "marginBottom": "24px"},
                children=[
                    html.Div(
                        [
                            html.H3("Platform breakdown", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                            dmc.SimpleGrid(cols=3, spacing="md", children=platform_cards),
                        ],
                        className="nexus-card",
                        style={"padding": "20px"},
                    ),
                    html.Div(
                        [
                            html.H3("Resource usage", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                            dmc.SimpleGrid(
                                cols=3,
                                spacing="md",
                                children=[
                                    html.Div(
                                        dcc.Graph(
                                            figure=create_usage_donut_chart(cpu_pct, "CPU", "#4318FF"),
                                            config={"displayModeBar": False},
                                            style={"height": "160px"},
                                        )
                                    ),
                                    html.Div(
                                        dcc.Graph(
                                            figure=create_usage_donut_chart(ram_pct, "RAM", "#05CD99"),
                                            config={"displayModeBar": False},
                                            style={"height": "160px"},
                                        )
                                    ),
                                    html.Div(
                                        dcc.Graph(
                                            figure=create_usage_donut_chart(stor_pct, "Storage", "#FFB547"),
                                            config={"displayModeBar": False},
                                            style={"height": "160px"},
                                        )
                                    ),
                                ],
                            ),
                        ],
                        className="nexus-card",
                        style={"padding": "20px"},
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
                            html.H3("Energy by source", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                            dcc.Graph(
                                figure=create_energy_breakdown_chart(eb_labels, eb_values, "Energy (kW)", height=260),
                                config={"displayModeBar": False},
                            ),
                        ],
                        className="nexus-card",
                        style={"padding": "20px"},
                    ),
                    html.Div(
                        [
                            html.H3("DC comparison", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                            dcc.Graph(
                                figure=create_grouped_bar_chart(
                                    dc_names,
                                    {"Hosts": dc_hosts, "VMs": dc_vms},
                                    "Hosts & VMs by DC",
                                    height=260,
                                ),
                                config={"displayModeBar": False},
                            ),
                        ],
                        className="nexus-card",
                        style={"padding": "20px"},
                    ),
                ],
            ),
            html.Div(
                className="nexus-card nexus-table",
                style={"margin": "0 30px", "padding": "20px", "overflowX": "auto"},
                children=[
                    html.H3("DC summary", style={"margin": "0 0 16px 0", "color": "#2B3674"}),
                    dmc.Table(
                        striped=True,
                        highlightOnHover=True,
                        children=[
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("DC"),
                                        html.Th("Location"),
                                        html.Th("Platforms"),
                                        html.Th("Hosts"),
                                        html.Th("VMs"),
                                        html.Th("CPU %"),
                                        html.Th("RAM %"),
                                    ]
                                )
                            ),
                            html.Tbody(
                                [
                                    html.Tr(
                                        [
                                            html.Td(dcc.Link(s["name"], href=f"/datacenter/{s['id']}", style={"color": "#4318FF", "fontWeight": 600})),
                                            html.Td(s["location"]),
                                            html.Td(s.get("platform_count", 0)),
                                            html.Td(s["host_count"]),
                                            html.Td(s["vm_count"]),
                                            html.Td(f"{s['stats'].get('used_cpu_pct', 0)}%"),
                                            html.Td(f"{s['stats'].get('used_ram_pct', 0)}%"),
                                        ]
                                    )
                                    for s in summaries
                                ]
                            ),
                        ],
                    ),
                ],
            ),
        ]
    )
