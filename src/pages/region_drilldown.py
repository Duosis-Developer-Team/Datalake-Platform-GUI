import dash_mantine_components as dmc
from dash_iconify import DashIconify
from dash import html, dcc


def build_region_drilldown(region, time_range=None):
    return html.Div(
        dmc.Paper(
            p="xl",
            radius="lg",
            style={
                "textAlign": "center",
                "marginTop": "80px",
                "background": "rgba(255,255,255,0.90)",
                "boxShadow": "0 8px 32px rgba(67,24,255,0.10)",
            },
            children=[
                DashIconify(icon="solar:lock-keyhole-bold-duotone", width=64, color="#A3AED0"),
                html.H3("Reserved", style={"color": "#2B3674", "marginTop": "16px"}),
                dmc.Text(
                    "This page is reserved for future hardware/rack data from loki_racks.",
                    c="#A3AED0",
                    size="sm",
                ),
                dcc.Link(
                    dmc.Button(
                        "Back to Global View",
                        variant="light",
                        color="indigo",
                        radius="md",
                        mt="lg",
                    ),
                    href="/global-view",
                    style={"textDecoration": "none"},
                ),
            ],
        ),
    )
