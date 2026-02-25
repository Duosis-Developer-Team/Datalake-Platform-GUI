import dash
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from src.services.shared import service

dash.register_page(__name__, path='/datacenters')

def layout():
    # Fetch real data on page load
    datacenters = service.get_all_datacenters_summary()

    return html.Div([
        # Header
        html.Div(
            className="nexus-glass",
            children=[
                html.Div([
                    DashIconify(icon="solar:server-square-bold-duotone", width=30, color="#4318FF"),
                    html.H1("Data Centers", style={"margin": "0 0 0 10px", "color": "#2B3674", "fontSize": "1.8rem"}),
                ], style={"display": "flex", "alignItems": "center"}),
                html.P("Manage and monitor your global infrastructure nodes.", style={"margin": "5px 0 0 40px", "color": "#A3AED0"})
            ],
            style={"padding": "24px 32px", "marginBottom": "32px", "display": "flex", "flexDirection": "column", "justifyContent": "center"}
        ),

        # Grid of Data Centers
        dmc.SimpleGrid(
            cols=3,
            spacing="lg",
            children=[
                html.Div(
                    className="nexus-card",
                    style={"padding": "24px", "height": "100%", "transition": "transform 0.2s"},
                    children=[
                        # Header
                        dmc.Group(
                            justify="space-between",
                            mb="lg",
                            children=[
                                dmc.Group(
                                    gap="sm",
                                    children=[
                                        dmc.ThemeIcon(
                                            size="xl",
                                            variant="light",
                                            color="indigo",
                                            radius="md",
                                            children=DashIconify(icon="solar:server-square-bold-duotone", width=30)
                                        ),
                                        dmc.Stack(
                                            gap=0,
                                            children=[
                                                dmc.Text(dc['name'], fw=700, size="lg", c="#2B3674"),
                                                dmc.Text(dc['location'], size="sm", c="#A3AED0", fw=500)
                                            ]
                                        )
                                    ]
                                ),
                                dcc.Link(
                                    dmc.Badge("Details >", variant="light", color="indigo", style={"cursor": "pointer"}),
                                    href=f"/datacenter/{dc['id']}",
                                    style={"textDecoration": "none"}
                                )
                            ]
                        ),
                        
                        # Stats Body
                        dmc.Stack(
                            gap="sm",
                            children=[
                                # Platforms
                                dmc.Group(
                                    justify="space-between",
                                    children=[
                                        dmc.Group(gap="xs", children=[
                                            DashIconify(icon="solar:layers-minimalistic-bold-duotone", width=20, color="#A3AED0"),
                                            dmc.Text("Platforms", size="sm", c="#A3AED0")
                                        ]),
                                        dmc.Text(f"{dc.get('platform_count', 0)}", fw=700, size="sm", c="#2B3674")
                                    ]
                                ),
                                # Row 1: Clusters
                                dmc.Group(
                                    justify="space-between",
                                    children=[
                                        dmc.Group(gap="xs", children=[
                                            DashIconify(icon="solar:box-bold-duotone", width=20, color="#A3AED0"),
                                            dmc.Text("Clusters", size="sm", c="#A3AED0")
                                        ]),
                                        dmc.Text(f"{dc['cluster_count']}", fw=700, size="sm", c="#2B3674")
                                    ]
                                ),
                                # Row 2: Hosts
                                dmc.Group(
                                    justify="space-between",
                                    children=[
                                        dmc.Group(gap="xs", children=[
                                            DashIconify(icon="solar:server-bold-duotone", width=20, color="#A3AED0"),
                                            dmc.Text("Hosts", size="sm", c="#A3AED0")
                                        ]),
                                        dmc.Text(f"{dc['host_count']}", fw=700, size="sm", c="#2B3674")
                                    ]
                                ),
                                # Row 3: VMs
                                dmc.Group(
                                    justify="space-between",
                                    children=[
                                        dmc.Group(gap="xs", children=[
                                            DashIconify(icon="solar:laptop-bold-duotone", width=20, color="#A3AED0"),
                                            dmc.Text("VMs", size="sm", c="#A3AED0")
                                        ]),
                                        dmc.Text(f"{dc['vm_count']}", fw=700, size="sm", c="#2B3674")
                                    ]
                                )
                            ]
                        )
                    ]
                ) for dc in datacenters
            ],
            style={"padding": "0 32px"}
        )
    ])
