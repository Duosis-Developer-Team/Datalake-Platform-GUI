import dash_mantine_components as dmc
from dash_iconify import DashIconify
from dash import html

def create_sidebar(active_path):
    # Sidebar Marka Alanı
    brand = html.Div(
        [
            DashIconify(icon="solar:widget-5-bold-duotone", width=30, color="#4318FF"),
            html.Span("BULUTİSTAN", style={"fontSize": "24px", "fontWeight": "700", "color": "#2B3674", "marginLeft": "10px"})
        ],
        style={"display": "flex", "alignItems": "center", "marginBottom": "40px", "paddingLeft": "16px"}
    )

    # Linkler
    # Düzeltme: DMC 0.14'te 'icon' yerine 'leftSection' kullanılır.
    links = [
        dmc.NavLink(
            label="Dashboard",
            leftSection=DashIconify(icon="solar:home-smile-bold-duotone", width=20),
            href="/",
            className="sidebar-link",
            active=active_path == "/" or active_path == "",
            variant="subtle",
            color="indigo",
            style={"borderRadius": "8px", "fontWeight": "500", "marginBottom": "5px"}
        ),
        dmc.NavLink(
            label="Data Centers",
            leftSection=DashIconify(icon="solar:server-square-bold-duotone", width=20),
            href="/datacenters",
            className="sidebar-link",
            active=active_path.startswith("/datacenter") or active_path == "/datacenters",
            variant="subtle",
            color="indigo",
            style={"borderRadius": "8px", "fontWeight": "500", "marginBottom": "5px"}
        ),
        dmc.NavLink(
            label="Query Explorer",
            leftSection=DashIconify(icon="solar:code-square-bold-duotone", width=20),
            href="/query-explorer",
            className="sidebar-link",
            active=active_path == "/query-explorer",
            variant="subtle",
            color="indigo",
            style={"borderRadius": "8px", "fontWeight": "500", "marginBottom": "5px"}
        ),
        # Pasif Linkler (Görsellik İçin)
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

    return html.Div(
        [
            brand,
            dmc.Stack(links, gap=4)
        ],
        style={
            "height": "100%",
            "width": "100%",
            "padding": "24px",
            "backgroundColor": "#FFFFFF",
        }
    )