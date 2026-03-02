import dash
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from src.services.shared import service
from src.components.header import create_detail_header


def layout(cluster_id=None):
    # Cluster view logic is currently placeholder as we transition from mock data.
    # The current DB schema aggregates at DC level, so cluster-specific drill-down 
    # specific to 'cluster_id' needs to be implemented in a future phase.
    # preventing crash by showing a maintenance/construction message.
    
    return html.Div([
        # Header
        create_detail_header(
            title=f"Cluster: {cluster_id or '—'}",
            back_href="/datacenters",
            back_label="Data Centers",
            subtitle_badge="🚧 Under Construction",
            subtitle_color="yellow",
            time_range=None,
            icon="solar:box-bold-duotone",
            tabs=None,
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
