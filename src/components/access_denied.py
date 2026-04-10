"""Access denied placeholder."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify


def build_access_denied(message: str | None = None) -> html.Div:
    return html.Div(
        style={"maxWidth": "520px", "margin": "80px auto"},
        children=[
            dmc.Paper(
                p="xl",
                radius="lg",
                withBorder=True,
                children=[
                    dmc.Group(
                        gap="md",
                        align="flex-start",
                        children=[
                            DashIconify(icon="solar:shield-warning-bold-duotone", width=40, color="#F04438"),
                            dmc.Stack(
                                gap="xs",
                                children=[
                                    dmc.Text("Access denied", fw=800, size="xl", c="#101828"),
                                    dmc.Text(
                                        message
                                        or "You do not have permission to view this page. Contact an administrator.",
                                        size="sm",
                                        c="dimmed",
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )
