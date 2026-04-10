"""User management (placeholder UI; list via auth DB in future iteration)."""

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
                    DashIconify(icon="solar:user-bold-duotone", width=32, color="#4318FF"),
                    dmc.Stack(
                        gap=4,
                        children=[
                            dmc.Title("User management", order=2, c="#2B3674"),
                            dmc.Text(
                                "Create local users, assign roles, and review LDAP-sourced accounts.",
                                size="sm",
                                c="dimmed",
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Alert(
                "Full CRUD for users will use the auth database API. This page is wired for RBAC; "
                "operational workflows can be extended in a follow-up.",
                title="Placeholder",
                color="blue",
                variant="light",
            ),
        ],
    )
