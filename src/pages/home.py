import dash
from dash import html, dcc
import dash_mantine_components as dmc
import pandas as pd
import random
from dash_iconify import DashIconify
from src.services.shared import service
from src.components.charts import create_gradient_area_chart

dash.register_page(__name__, path='/')

# Fake Data Trend for Chart (preserving visual appeal as DB has no traffic data yet)
def get_traffic_data():
    hours = [f"{i}:00" for i in range(24)]
    traffic = [random.randint(500, 2000) for _ in range(24)]
    return pd.DataFrame({"time": hours, "requests": traffic})

def metric_card(title, value, icon_name, subtext=None, color="#4318FF"):
    return html.Div(
        className="nexus-card",
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
                        children=DashIconify(icon=icon_name, width=22)
                    ),
                    html.H3(title, style={"margin": 0, "color": "#A3AED0", "fontSize": "0.9rem", "fontWeight": "500"})
                ]
            ),
            html.H2(value, style={"margin": "0", "color": "#2B3674", "fontSize": "2rem", "fontWeight": "700"}),
            html.P(subtext, style={"margin": "5px 0 0 0", "color": "#05CD99", "fontSize": "0.8rem", "fontWeight": "600"}) if subtext else None
        ]
    )

def layout():
    # Fetch Real Global Data
    summary = service.get_global_overview()
    df_traffic = get_traffic_data()

    return html.Div([
        # Header (Nexus Glass Effect)
        html.Div(
            className="nexus-glass",
            children=[
                html.H1("Dashboard Overview", style={"margin": 0, "color": "#2B3674", "fontSize": "1.5rem"}),
                html.P("Real-time system performance metrics", style={"margin": "5px 0 0 0", "color": "#A3AED0"})
            ],
            style={"padding": "20px 30px", "marginBottom": "30px", "borderRadius": "0 0 20px 20px"}
        ),
        
        # Metrics Grid
        dmc.SimpleGrid(
            cols=3,
            spacing="lg",
            children=[
                metric_card("Total Hosts", str(summary['total_hosts']), "material-symbols:dns-outline", "Global Infrastructure"),
                metric_card("Total VMs", str(summary['total_vms']), "material-symbols:laptop-mac-outline", "Virtual Machines", color="teal"),
                metric_card("Total Energy", f"{summary['total_energy_kw']:,} kW", "material-symbols:bolt-outline", "Real-time Power", color="orange"),
            ],
            style={"marginBottom": "30px", "padding": "0 30px"}
        ),

        # Main Chart Area
        html.Div(
            className="nexus-card",
            style={"margin": "0 30px"},
            children=[
                 html.Div([
                    html.H3("Network Traffic Trends", style={"margin": 0, "color": "#2B3674"}),
                ], style={"marginBottom": "20px"}),
                dcc.Graph(
                    figure=create_gradient_area_chart(df_traffic, "time", "requests", "Global Data Traffic"),
                    config={'displayModeBar': False},
                    style={"height": "350px"}
                )
            ]
        )
    ])