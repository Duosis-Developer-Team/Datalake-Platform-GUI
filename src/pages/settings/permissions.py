"""Permission tree — add dynamic nodes."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html

from src.auth import settings_crud


def build_layout() -> html.Div:
    perms = settings_crud.list_permissions_flat()

    rows = []
    for p in perms[:150]:
        rows.append(
            html.Tr(
                [
                    html.Td(str(p["code"]), style={"fontSize": "12px"}),
                    html.Td(str(p["name"])),
                    html.Td(str(p["resource_type"])),
                    html.Td("dyn" if p.get("is_dynamic") else "seed"),
                ]
            )
        )

    return html.Div(
        [
            dmc.Title("Permissions", order=3, mb="sm", c="#2B3674"),
            html.Form(
                method="POST",
                action="/auth/settings/permission-add",
                style={
                    "padding": "16px",
                    "border": "1px solid #E9ECEF",
                    "borderRadius": "12px",
                    "marginBottom": "20px",
                    "background": "#fff",
                },
                children=[
                    dmc.Text("Add dynamic node", fw=600, mb="sm", size="sm"),
                    dmc.SimpleGrid(
                        cols=2,
                        children=[
                            html.Div(
                                [
                                    dmc.Text("Code (unique)", size="xs", c="dimmed", mb=4),
                                    dcc.Input(name="code", required=True, style=_inp()),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Name", size="xs", c="dimmed", mb=4),
                                    dcc.Input(name="name", required=True, style=_inp()),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Parent code (optional)", size="xs", c="dimmed", mb=4),
                                    dcc.Input(name="parent_code", placeholder="grp:dashboard", style=_inp()),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Resource type", size="xs", c="dimmed", mb=4),
                                    dcc.Input(name="resource_type", value="section", style=_inp()),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Route pattern (optional)", size="xs", c="dimmed", mb=4),
                                    dcc.Input(name="route_pattern", style=_inp()),
                                ]
                            ),
                        ],
                    ),
                    html.Button(
                        "Add node",
                        type="submit",
                        style={
                            "marginTop": "12px",
                            "padding": "8px 16px",
                            "background": "#4318FF",
                            "color": "#fff",
                            "border": "none",
                            "borderRadius": "8px",
                            "cursor": "pointer",
                        },
                    ),
                ],
            ),
            dmc.Paper(
                withBorder=True,
                p="sm",
                radius="md",
                children=[
                    html.Table(
                        [
                            html.Tr([html.Th("Code"), html.Th("Name"), html.Th("Type"), html.Th("Source")]),
                            *rows,
                        ],
                        style={"width": "100%", "fontSize": "12px"},
                    )
                ],
            ),
        ]
    )


def _inp():
    return {"width": "100%", "padding": "8px", "borderRadius": "8px", "border": "1px solid #E9ECEF"}
