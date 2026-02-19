import dash
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from src.services.shared import service

dash.register_page(__name__, path_template='/cluster/<cluster_id>')

def layout(cluster_id=None):
    # Cluster view logic is currently placeholder as we transition from mock data.
    # The current DB schema aggregates at DC level, so cluster-specific drill-down 
    # specific to 'cluster_id' needs to be implemented in a future phase.
    # preventing crash by showing a maintenance/construction message.
    
    return html.Div([
        # Header
        html.Div(
            className="nexus-glass",
            children=[
                dcc.Link(
                    DashIconify(icon="solar:arrow-left-linear", width=24, color="#2B3674"),
                    href="/datacenters", # Fallback to DC list for now
                    style={"marginRight": "16px"}
                ),
                html.Div([
                    html.H1(f"Cluster: {cluster_id}", style={"margin": "0", "color": "#2B3674", "fontSize": "1.5rem"}),
                    html.P("Detailed cluster view is under construction.", style={"margin": "0 0 0 12px", "color": "#A3AED0", "fontSize": "0.9rem"})
                ], style={"display": "flex", "alignItems": "baseline"}),
            ],
            style={"padding": "20px 30px", "marginBottom": "30px", "display": "flex", "alignItems": "center"}
        ),

        # Placeholder Card
        html.Div(
            className="nexus-card",
            style={"margin": "0 30px", "textAlign": "center", "padding": "50px"},
            children=[
                DashIconify(icon="solar:construction-bold-duotone", width=64, color="#FFB547"),
                html.H2("Work in Progress", style={"marginTop": "20px", "color": "#2B3674"}),
                html.P("We are currently connecting this view to the live database metrics.", style={"color": "#A3AED0"}),
                dcc.Link(dmc.Button("Back to Data Centers", variant="light", color="indigo", mt="md"), href="/datacenters")
            ]
        )
    ])
