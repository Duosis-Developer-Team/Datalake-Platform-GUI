import dash_mantine_components as dmc
from dash_iconify import DashIconify
from dash import html


def create_sidebar_nav(active_path):
    """Return brand + nav links only. Controls (time range, customer) are static in app.layout."""
    brand = html.Div(
        [
            DashIconify(icon="solar:widget-5-bold-duotone", width=30, color="#4318FF"),
            html.Span(
                "BULUTİSTAN",
                style={"fontSize": "24px", "fontWeight": "700", "color": "#2B3674", "marginLeft": "10px"},
            ),
        ],
        style={"display": "flex", "alignItems": "center", "marginBottom": "40px", "paddingLeft": "16px"},
    )

    links = [
        dmc.NavLink(
            label="Overview",
            leftSection=DashIconify(icon="solar:home-smile-bold-duotone", width=20),
            href="/",
            className="sidebar-link",
            active=active_path == "/" or active_path == "",
            variant="subtle",
            color="indigo",
            style={"borderRadius": "8px", "fontWeight": "500", "marginBottom": "5px"},
        ),
        dmc.NavLink(
            label="Data Centers",
            leftSection=DashIconify(icon="solar:server-square-bold-duotone", width=20),
            href="/datacenters",
            className="sidebar-link",
            active=active_path.startswith("/datacenter") or active_path == "/datacenters",
            variant="subtle",
            color="indigo",
            style={"borderRadius": "8px", "fontWeight": "500", "marginBottom": "5px"},
        ),
        dmc.NavLink(
            label="Customer View",
            leftSection=DashIconify(icon="solar:users-group-rounded-bold-duotone", width=20),
            href="/customer-view",
            className="sidebar-link",
            active=active_path == "/customer-view",
            variant="subtle",
            color="indigo",
            style={"borderRadius": "8px", "fontWeight": "500", "marginBottom": "5px"},
        ),
        dmc.NavLink(
            label="Query Explorer",
            leftSection=DashIconify(icon="solar:code-square-bold-duotone", width=20),
            href="/query-explorer",
            className="sidebar-link",
            active=active_path == "/query-explorer",
            variant="subtle",
            color="indigo",
            style={"borderRadius": "8px", "fontWeight": "500", "marginBottom": "5px"},
        ),
        dmc.NavLink(
            label="Analytics",
            leftSection=DashIconify(icon="solar:chart-square-bold-duotone", width=20),
            href="#",
            className="sidebar-link",
            disabled=True,
        ),
        dmc.NavLink(
            label="Settings",
            leftSection=DashIconify(icon="solar:settings-bold-duotone", width=20),
            href="#",
            className="sidebar-link",
            disabled=True,
        ),
    ]

    return html.Div([brand, dmc.Stack(links, gap=4)])
