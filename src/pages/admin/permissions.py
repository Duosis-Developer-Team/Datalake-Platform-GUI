"""Permission tree management placeholder."""

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
                    DashIconify(icon="solar:list-check-bold-duotone", width=32, color="#4318FF"),
                    dmc.Stack(
                        gap=4,
                        children=[
                            dmc.Title("Permission catalog", order=2, c="#2B3674"),
                            dmc.Text(
                                "Add dynamic page/section nodes and manage ordering. Sync merges with code registry.",
                                size="sm",
                                c="dimmed",
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Alert(
                "Tree editor UI pending; registry sync runs on application startup.",
                title="Placeholder",
                color="teal",
                variant="light",
            ),
        ],
    )
