"""Role management placeholder."""

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
                    DashIconify(icon="solar:shield-user-bold-duotone", width=32, color="#4318FF"),
                    dmc.Stack(
                        gap=4,
                        children=[
                            dmc.Title("Role management", order=2, c="#2B3674"),
                            dmc.Text(
                                "Hierarchical permission matrix per role (view/edit/export) will be edited here.",
                                size="sm",
                                c="dimmed",
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Alert(
                "Connect UI to role_permissions and permissions tree. Placeholder for RBAC rollout.",
                title="Placeholder",
                color="violet",
                variant="light",
            ),
        ],
    )
