"""Operations teams placeholder."""

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
                    DashIconify(icon="solar:users-group-two-rounded-bold-duotone", width=32, color="#4318FF"),
                    dmc.Stack(
                        gap=4,
                        children=[
                            dmc.Title("Team management", order=2, c="#2B3674"),
                            dmc.Text("Nested teams and membership for Operation Lead workflows.", size="sm", c="dimmed"),
                        ],
                    ),
                ],
            ),
            dmc.Alert(
                "Backed by teams / team_members tables. UI pending.",
                title="Placeholder",
                color="grape",
                variant="light",
            ),
        ],
    )
