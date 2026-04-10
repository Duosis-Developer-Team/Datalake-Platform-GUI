"""Auth-related settings placeholder."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify


def build_layout() -> html.Div:
    return html.Div(
        style={"maxWidth": "720px"},
        children=[
            dmc.Group(
                gap="sm",
                mb="lg",
                children=[
                    DashIconify(icon="solar:settings-bold-duotone", width=32, color="#4318FF"),
                    dmc.Stack(
                        gap=4,
                        children=[
                            dmc.Title("Authentication settings", order=2, c="#2B3674"),
                            dmc.Text("Session TTL, lockout policies, and future integrations.", size="sm", c="dimmed"),
                        ],
                    ),
                ],
            ),
            dmc.Alert(
                "Reserved for future non-LDAP auth settings. LDAP is configured under Administration → LDAP.",
                title="Placeholder",
                color="gray",
                variant="light",
            ),
        ],
    )
