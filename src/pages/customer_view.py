import dash
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from src.services.shared import service
from src.components.charts import create_stacked_bar_chart

dash.register_page(__name__, path="/customer-view")


def metric_card(title, value, icon_name, color="#4318FF"):
    return html.Div(
        className="nexus-card",
        style={"padding": "20px"},
        children=[
            dmc.Group(
                align="center",
                gap="sm",
                style={"marginBottom": "8px"},
                children=[
                    dmc.ThemeIcon(
                        size="lg",
                        radius="md",
                        variant="light",
                        color=color if color != "#4318FF" else "indigo",
                        children=DashIconify(icon=icon_name, width=22),
                    ),
                    html.H3(title, style={"margin": 0, "color": "#A3AED0", "fontSize": "0.9rem"}),
                ],
            ),
            html.H2(str(value), style={"margin": "0", "color": "#2B3674", "fontSize": "1.5rem", "fontWeight": "700"}),
        ],
    )


def layout():
    customers = service.get_customer_list()
    default_customer = customers[0] if customers else "Boyner"
    return html.Div(
        [
            html.Div(
                className="nexus-glass",
                children=[
                    html.H1("Customer View", style={"margin": 0, "color": "#2B3674", "fontSize": "1.5rem"}),
                    html.P("Resource usage by customer (beta: Boyner)", style={"margin": "5px 0 0 0", "color": "#A3AED0"}),
                ],
                style={"padding": "20px 30px", "marginBottom": "24px", "borderRadius": "0 0 20px 20px"},
            ),
            html.Div(
                style={"padding": "0 30px", "marginBottom": "24px"},
                children=[
                    dmc.Group(
                        align="center",
                        gap="md",
                        children=[
                            dmc.Text("Customer:", size="sm", fw=500, c="#A3AED0"),
                            dmc.Select(
                                id="customer-select",
                                data=[{"value": c, "label": c} for c in customers],
                                value=default_customer,
                                style={"width": 200},
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(id="customer-view-content", children=_customer_content(default_customer)),
        ]
    )


def _customer_content(customer_name):
    """Build content block for the selected customer (used by layout and app callback)."""
    data = service.get_customer_resources(customer_name or "Boyner")
    totals = data.get("totals", {})
    by_platform = data.get("by_platform", {})
    by_dc = data.get("by_dc", [])
    return [
        dmc.SimpleGrid(
                cols=3,
                spacing="lg",
                style={"padding": "0 30px", "marginBottom": "24px"},
                children=[
                    metric_card("Total Hosts", totals.get("hosts", 0), "solar:server-bold-duotone"),
                    metric_card("Total VMs", totals.get("vms", 0), "solar:laptop-bold-duotone", color="teal"),
                    metric_card("DCs used", totals.get("dcs_used", 0), "solar:server-square-bold-duotone", color="orange"),
                ],
            ),
            dmc.SimpleGrid(
                cols=2,
                spacing="lg",
                style={"padding": "0 30px", "marginBottom": "24px"},
                children=[
                    html.Div(
                        className="nexus-card",
                        style={"padding": "20px"},
                        children=[
                            html.H3("Resource distribution by DC", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                            dcc.Graph(
                                figure=create_stacked_bar_chart(
                                    [r["dc"] for r in by_dc] if by_dc else ["N/A"],
                                    {"Hosts": [r["hosts"] for r in by_dc] if by_dc else [0], "VMs": [r["vms"] for r in by_dc] if by_dc else [0]},
                                    "By datacenter",
                                    height=280,
                                ),
                                config={"displayModeBar": False},
                            ),
                        ],
                    ),
                    html.Div(
                        className="nexus-card",
                        style={"padding": "20px"},
                        children=[
                            html.H3("Platform breakdown", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                            dmc.Stack(
                                gap="sm",
                                children=[
                                    dmc.Group(justify="space-between", children=[dmc.Text("Nutanix", size="sm", c="#A3AED0"), dmc.Text(f"Hosts: {by_platform.get('nutanix', {}).get('hosts', 0)}, VMs: {by_platform.get('nutanix', {}).get('vms', 0)}", size="sm", fw=600)]),
                                    dmc.Group(justify="space-between", children=[dmc.Text("VMware", size="sm", c="#A3AED0"), dmc.Text(f"Hosts: {by_platform.get('vmware', {}).get('hosts', 0)}, VMs: {by_platform.get('vmware', {}).get('vms', 0)}", size="sm", fw=600)]),
                                    dmc.Group(justify="space-between", children=[dmc.Text("IBM Power", size="sm", c="#A3AED0"), dmc.Text(f"Hosts: {by_platform.get('ibm', {}).get('hosts', 0)}, LPARs: {by_platform.get('ibm', {}).get('lpars', 0)}", size="sm", fw=600)]),
                                    dmc.Group(justify="space-between", children=[dmc.Text("vCenter", size="sm", c="#A3AED0"), dmc.Text(f"Hosts: {by_platform.get('vcenter', {}).get('hosts', 0)}", size="sm", fw=600)]),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="nexus-card",
                style={"margin": "0 30px", "padding": "20px"},
                children=[
                    html.H3("Detailed resource table", style={"margin": "0 0 16px 0", "color": "#2B3674"}),
                    dmc.Table(
                        striped=True,
                        highlightOnHover=True,
                        children=[
                            html.Thead(html.Tr([html.Th("DC"), html.Th("Hosts"), html.Th("VMs")])),
                            html.Tbody(
                                [html.Tr([html.Td(r["dc"]), html.Td(r["hosts"]), html.Td(r["vms"])]) for r in by_dc]
                                if by_dc
                                else [html.Tr([html.Td("No data", colSpan=3)])]
                            ),
                        ],
                    ),
                ],
            ),
        ]

