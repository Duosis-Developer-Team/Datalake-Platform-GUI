import dash
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from src.services.shared import service
from src.components.charts import create_usage_donut_chart, create_bar_chart

dash.register_page(__name__, path_template='/datacenter/<dc_id>')

def kpi_card(title, value, icon, is_text=False):
    return html.Div(
        className="nexus-card",
        style={"padding": "20px", "display": "flex", "alignItems": "center", "justifyContent": "space-between"},
        children=[
            html.Div([
                html.Span(title, style={"color": "#A3AED0", "fontSize": "0.9rem", "fontWeight": 500}),
                html.H3(str(value), style={"color": "#2B3674", "fontSize": "1.5rem" if not is_text else "1.1rem", "margin": "4px 0 0 0"})
            ]),
            dmc.ThemeIcon(
                size="xl", radius="md", variant="light", color="indigo",
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

def layout(dc_id=None):
    if not dc_id:
        return html.Div("No Data Center ID provided", style={"padding": "20px"})

    # Fetch Real Data
    data = service.get_dc_details(dc_id)
    
    # meta data
    dc_name = data["meta"]["name"]
    dc_loc = data["meta"]["location"]
    
    # Intel Stats
    intel = data["intel"]
    power = data["power"]
    
    # KPI Logic
    kpi_clusters = intel["clusters"]
    kpi_hosts = intel["hosts"] + power["hosts"]
    kpi_vms = intel["vms"]
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
        # --- Header ---
        html.Div(
            className="nexus-glass",
            children=[
                dcc.Link(
                    DashIconify(icon="solar:arrow-left-linear", width=24, color="#2B3674"),
                    href="/datacenters", style={"marginRight": "16px", "display": "flex", "alignItems": "center"}
                ),
                html.Div([
                    html.H1(dc_name, style={"margin": "0", "color": "#2B3674", "fontSize": "1.8rem"}),
                    html.Span(f"Region: {dc_loc}", style={"color": "#A3AED0", "fontSize": "0.9rem", "fontWeight": "500", "marginLeft": "12px"})
                ], style={"display": "flex", "alignItems": "baseline"}),
            ],
            style={"padding": "20px 30px", "marginBottom": "20px", "display": "flex", "alignItems": "center"}
        ),

        # --- TABS ---
        dmc.Tabs(
            color="indigo",
            variant="pills",
            radius="md",
            value="intel",
            children=[
                dmc.TabsList(
                    children=[
                        dmc.TabsTab("Intel Virtualization", value="intel"),
                        dmc.TabsTab("Power Virtualization", value="power"),
                        dmc.TabsTab("OpenStack", value="openstack"),
                        dmc.TabsTab("Backup Virtualization", value="backup"),
                    ],
                    style={"padding": "0 30px", "marginBottom": "24px"}
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

                            # 3. Filter
                            html.Div(className="nexus-card", style={"padding": "20px"}, children=[
                                dmc.Group([
                                    DashIconify(icon="solar:filter-bold-duotone", color="#4318FF", width=20),
                                    html.Span("Filter / Search Criteria", style={"fontWeight": 500, "color": "#2B3674"})
                                ], style={"marginBottom": "15px"}),
                                dmc.Grid([
                                    dmc.GridCol(dmc.TextInput(placeholder="Search Cluster Name..."), span=4),
                                    dmc.GridCol(dmc.Select(data=["Active", "Inactive"], placeholder="Status"), span=4)
                                ])
                            ]),

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
                dmc.TabsPanel(value="power", children=html.Div("No Data", style={"padding": "30px", "textAlign": "center", "color": "#A3AED0"})),
                dmc.TabsPanel(value="openstack", children=html.Div("No Data", style={"padding": "30px", "textAlign": "center", "color": "#A3AED0"})),
                dmc.TabsPanel(value="backup", children=html.Div("No Data", style={"padding": "30px", "textAlign": "center", "color": "#A3AED0"})),
            ]
        )
    ])