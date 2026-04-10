"""LDAP configuration placeholder."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify


def build_layout() -> html.Div:
    return html.Div(
        style={"maxWidth": "960px"},
        children=[
            dmc.Group(
                gap="sm",
                mb="lg",
                children=[
                    DashIconify(icon="solar:server-path-bold-duotone", width=32, color="#4318FF"),
                    dmc.Stack(
                        gap=4,
                        children=[
                            dmc.Title("LDAP configuration", order=2, c="#2B3674"),
                            dmc.Text(
                                "Configure primary/secondary servers, bind account, search bases, and group→role maps.",
                                size="sm",
                                c="dimmed",
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Alert(
                "Use ldap_config table + encrypted bind password. Connection test will call ldap_service.",
                title="Placeholder",
                color="orange",
                variant="light",
            ),
        ],
    )
