import dash
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from src.services.shared import service
from src.utils.time_range import default_time_range
from src.components.charts import create_usage_donut_chart, create_bar_chart, create_gauge_chart
from src.components.header import create_detail_header


def kpi_card(title, value, icon, is_text=False, color="indigo"):
    return html.Div(
        className="nexus-card",
        style={"padding": "20px", "display": "flex", "alignItems": "center", "justifyContent": "space-between"},
        children=[
            html.Div([
                html.Span(title, style={"color": "#A3AED0", "fontSize": "0.9rem", "fontWeight": 500}),
                html.H3(str(value), style={"color": "#2B3674", "fontSize": "1.5rem" if not is_text else "1.1rem", "margin": "4px 0 0 0"})
            ]),
            dmc.ThemeIcon(
                size="xl", radius="md", variant="light", color=color,
                children=DashIconify(icon=icon, width=24)
            )
        ]
    )

def chart_card(graph_component):
    return html.Div(
        className="nexus-card",
        style={"padding": "16px", "height": "250px", "display": "flex", "flexDirection": "column", "alignItems": "center", "justifyContent": "center", "overflow": "hidden"},
        children=graph_component
    )

def build_dc_view(dc_id, time_range=None):
    """Build DC detail page content for the given time range."""
    if not dc_id:
        return html.Div("No Data Center ID provided", style={"padding": "20px"})
    tr = time_range or default_time_range()
    data = service.get_dc_details(dc_id, tr)
    
    # meta data
    dc_name = data["meta"]["name"]
    dc_loc = data["meta"]["location"]
    
    # Intel Stats
    intel = data["intel"]
    power = data["power"]
    
    # KPI Logic
    kpi_clusters = intel["clusters"]
    kpi_hosts = intel["hosts"] + power["hosts"]
    kpi_vms = intel["vms"] + power.get("vms", 0)  # Intel VMs + IBM LPARs
    kpi_updated = "Live"

    # Usage Percentages
    def calc_pct(used, cap):
        return (used / cap * 100) if cap > 0 else 0
        
    cpu_pct = round(calc_pct(intel["cpu_used"], intel["cpu_cap"]), 1)
    ram_pct = round(calc_pct(intel["ram_used"], intel["ram_cap"]), 1)
    stor_pct = round(calc_pct(intel["storage_used"], intel["storage_cap"]), 1)

    # Placeholders for missing child data
    bar_data = {"name": [], "cpu": []}
    clusters = [] # No individual cluster list in current Service implementation

    return html.Div([
        dmc.Tabs(
            color="indigo",
            variant="pills",
            radius="md",
            value="intel",
            children=[
                create_detail_header(
                    title=dc_name,
                    back_href="/datacenters",
                    back_label="Data Centers",
                    subtitle_badge=f"📍 {dc_loc}" if dc_loc else None,
                    subtitle_color="indigo",
                    time_range=tr,
                    icon="solar:server-square-bold-duotone",
                    tabs=dmc.TabsList(
                        style={"paddingTop": "8px"},
                        children=[
                            dmc.TabsTab("Intel Virtualization", value="intel"),
                            dmc.TabsTab("Power Virtualization", value="power"),
                            dmc.TabsTab("Summary", value="summary"),
                        ],
                    ),
                ),

                dmc.TabsPanel(
                    value="intel",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[
                            # 1. KPIs
                            dmc.SimpleGrid(
                                cols=4, spacing="lg",
                                children=[
                                    kpi_card("Total Cluster", kpi_clusters, "solar:box-bold-duotone"),
                                    kpi_card("Total Host", kpi_hosts, "solar:server-bold-duotone"),
                                    kpi_card("Total VM", kpi_vms, "solar:laptop-bold-duotone"),
                                    kpi_card("Last Updated", kpi_updated, "solar:clock-circle-bold-duotone", is_text=True),
                                ]
                            ),

                            # 2. Charts
                            dmc.SimpleGrid(
                                cols=4, spacing="lg",
                                children=[
                                    chart_card(dcc.Graph(figure=create_usage_donut_chart(cpu_pct, "CPU Usage"), config={"displayModeBar": False}, style={"height": "100%", "width": "100%"})),
                                    chart_card(dcc.Graph(figure=create_usage_donut_chart(ram_pct, "RAM Usage"), config={"displayModeBar": False}, style={"height": "100%", "width": "100%"})),
                                    chart_card(dcc.Graph(figure=create_usage_donut_chart(stor_pct, "Storage Usage"), config={"displayModeBar": False}, style={"height": "100%", "width": "100%"})),
                                    chart_card(dcc.Graph(figure=create_bar_chart(bar_data, "name", "cpu", "Cluster Load"), config={"displayModeBar": False}, style={"height": "100%", "width": "100%"})),
                                ]
                            ),

                            # 3. Power usage (daily average) and billing (total kWh)
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Power usage", style={"margin": "0 0 4px 0", "color": "#2B3674"}),
                                    html.P("Daily average over report period", style={"margin": "0 0 12px 0", "color": "#A3AED0", "fontSize": "0.8rem"}),
                                    dmc.SimpleGrid(
                                        cols=2,
                                        spacing="lg",
                                        children=[
                                            kpi_card("vCenter", f"{data['energy'].get('vcenter_kw', 0):.1f} kW", "material-symbols:bolt-outline", color="orange"),
                                            kpi_card("Total", f"{data['energy'].get('total_kw', 0):.1f} kW", "material-symbols:bolt-outline", color="orange"),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Energy consumption (billing)", style={"margin": "0 0 4px 0", "color": "#2B3674"}),
                                    html.P("Total consumption in report period (kWh)", style={"margin": "0 0 12px 0", "color": "#A3AED0", "fontSize": "0.8rem"}),
                                    dmc.SimpleGrid(
                                        cols=2,
                                        spacing="lg",
                                        children=[
                                            kpi_card("vCenter", f"{data['energy'].get('vcenter_kwh', 0):,.0f} kWh", "material-symbols:bolt-outline", color="orange"),
                                            kpi_card("Total", f"{data['energy'].get('total_kwh', 0):,.0f} kWh", "material-symbols:bolt-outline", color="orange"),
                                        ],
                                    ),
                                ],
                            ),

                            # 4. Cluster List (Empty/Placeholder)
                            html.Div(
                                "Detailed Cluster List not available in Global View",
                                style={"textAlign": "center", "color": "#A3AED0", "padding": "40px"}
                            ) if not clusters else dmc.SimpleGrid(
                                cols=3, spacing="lg",
                                children=[
                                    # Cluster card logic preserved but unreachable for now
                                ]
                            )
                        ]
                    )
                ),
                dmc.TabsPanel(
                    value="power",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[
                            dmc.SimpleGrid(
                                cols=4,
                                spacing="lg",
                                children=[
                                    kpi_card("IBM Hosts", power.get("hosts", 0), "solar:server-bold-duotone"),
                                    kpi_card("VIOS", power.get("vios", 0), "solar:server-square-bold-duotone"),
                                    kpi_card("LPARs (VMs)", power.get("lpar_count", 0), "solar:laptop-bold-duotone"),
                                    kpi_card("Last Updated", "Live", "solar:clock-circle-bold-duotone", is_text=True),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Power usage", style={"margin": "0 0 4px 0", "color": "#2B3674"}),
                                    html.P("Daily average over report period", style={"margin": "0 0 12px 0", "color": "#A3AED0", "fontSize": "0.8rem"}),
                                    dmc.SimpleGrid(
                                        cols=2,
                                        spacing="lg",
                                        children=[
                                            kpi_card("IBM Power", f"{data['energy'].get('ibm_kw', 0):.1f} kW", "material-symbols:bolt-outline", color="orange"),
                                            kpi_card("Total", f"{data['energy'].get('total_kw', 0):.1f} kW", "material-symbols:bolt-outline", color="orange"),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Energy consumption (billing)", style={"margin": "0 0 4px 0", "color": "#2B3674"}),
                                    html.P("Total consumption in report period (kWh)", style={"margin": "0 0 12px 0", "color": "#A3AED0", "fontSize": "0.8rem"}),
                                    dmc.SimpleGrid(
                                        cols=2,
                                        spacing="lg",
                                        children=[
                                            kpi_card("IBM Power", f"{data['energy'].get('ibm_kwh', 0):,.0f} kWh", "material-symbols:bolt-outline", color="orange"),
                                            kpi_card("Total", f"{data['energy'].get('total_kwh', 0):,.0f} kWh", "material-symbols:bolt-outline", color="orange"),
                                        ],
                                    ),
                                ],
                            ),
                            dmc.SimpleGrid(
                                cols=2,
                                spacing="lg",
                                children=[
                                    chart_card(
                                        dcc.Graph(
                                            figure=create_gauge_chart(
                                                power.get("memory_assigned", 0),
                                                power.get("memory_total", 1) or 1,
                                                "Memory assigned",
                                                color="#05CD99",
                                            ),
                                            config={"displayModeBar": False},
                                            style={"height": "100%", "width": "100%"},
                                        )
                                    ),
                                    chart_card(
                                        dcc.Graph(
                                            figure=create_gauge_chart(
                                                power.get("cpu_used", 0),
                                                power.get("cpu_assigned", 1) or 1,
                                                "CPU used",
                                                color="#4318FF",
                                            ),
                                            config={"displayModeBar": False},
                                            style={"height": "100%", "width": "100%"},
                                        )
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
                dmc.TabsPanel(
                    value="summary",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Combined metrics", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    dmc.SimpleGrid(
                                        cols=4,
                                        spacing="lg",
                                        children=[
                                            kpi_card("Total Hosts", kpi_hosts, "solar:server-bold-duotone"),
                                            kpi_card("Total VMs", kpi_vms, "solar:laptop-bold-duotone"),
                                            kpi_card("CPU used", f"{intel['cpu_used'] + (power.get('cpu_used') or 0):.1f} GHz", "solar:cpu-bold-duotone", is_text=True),
                                            kpi_card("RAM used", f"{intel['ram_used'] + (power.get('memory_assigned') or 0):.0f} GB", "solar:ram-bold-duotone", is_text=True),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Energy breakdown", style={"margin": "0 0 4px 0", "color": "#2B3674"}),
                                    html.P("Daily average over report period", style={"margin": "0 0 12px 0", "color": "#A3AED0", "fontSize": "0.8rem"}),
                                    dmc.SimpleGrid(
                                        cols=2,
                                        spacing="lg",
                                        children=[
                                            kpi_card("IBM Power", f"{data['energy'].get('ibm_kw', 0):.1f} kW", "material-symbols:bolt-outline", color="orange"),
                                            kpi_card("vCenter", f"{data['energy'].get('vcenter_kw', 0):.1f} kW", "material-symbols:bolt-outline", color="orange"),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Energy consumption (billing)", style={"margin": "0 0 4px 0", "color": "#2B3674"}),
                                    html.P("Total consumption in report period (kWh)", style={"margin": "0 0 12px 0", "color": "#A3AED0", "fontSize": "0.8rem"}),
                                    dmc.SimpleGrid(
                                        cols=3,
                                        spacing="lg",
                                        children=[
                                            kpi_card("IBM Power", f"{data['energy'].get('ibm_kwh', 0):,.0f} kWh", "material-symbols:bolt-outline", color="orange"),
                                            kpi_card("vCenter", f"{data['energy'].get('vcenter_kwh', 0):,.0f} kWh", "material-symbols:bolt-outline", color="orange"),
                                            kpi_card("Total", f"{data['energy'].get('total_kwh', 0):,.0f} kWh", "material-symbols:bolt-outline", color="orange"),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
            ]
        )
    ])


def layout(dc_id=None):
    return build_dc_view(dc_id, default_time_range())