"""Auth-related settings (environment-driven)."""

from __future__ import annotations

import os

import dash_mantine_components as dmc
from dash import html
from src.utils.ui_tokens import section_header, settings_page_shell


def build_layout(search: str | None = None) -> html.Div:
    auth_off = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
    return html.Div(
        settings_page_shell(
            [
                section_header(
                    "Authentication settings",
                    "Security-related deployment flags (configured via environment variables).",
                    icon="solar:shield-check-bold-duotone",
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
                    p="lg",
                    radius="md",
                    children=[
                        dmc.Text("Environment reference", fw=700, mb="sm"),
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
            max_width="1280px",
        )
    )
