"""Auth-related settings."""

from __future__ import annotations

import os

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify


def build_layout() -> html.Div:
    auth_off = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
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
                            dmc.Text(
                                "Session TTL and security flags are controlled via environment variables.",
                                size="sm",
                                c="dimmed",
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Alert(
                "AUTH_DISABLED is ON — all users bypass permission checks. Do not use in production."
                if auth_off
                else "AUTH_DISABLED is off — RBAC is enforced.",
                title="AUTH_DISABLED",
                color="red" if auth_off else "green",
                variant="light",
                mb="md",
            ),
            dmc.Paper(
                withBorder=True,
                p="md",
                children=[
                    dmc.Text("Environment reference", fw=600, mb="xs", size="sm"),
                    dmc.List(
                        [
                            dmc.ListItem("SESSION_TTL_HOURS — session lifetime"),
                            dmc.ListItem("SECRET_KEY — Flask session signing"),
                            dmc.ListItem("FERNET_KEY — optional dedicated key for LDAP password encryption"),
                            dmc.ListItem("API_JWT_SECRET — JWT for microservice calls (defaults to SECRET_KEY)"),
                        ],
                        size="sm",
                        c="dimmed",
                    ),
                ],
            ),
        ],
    )
