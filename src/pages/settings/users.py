"""User management — list, create local user, assign roles."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html

from src.auth import settings_crud


def build_layout() -> html.Div:
    rows = settings_crud.list_users_with_roles()

    table_rows = []
    for u in rows:
        table_rows.append(
            html.Tr(
                children=[
                    html.Td(str(u.get("username", ""))),
                    html.Td(str(u.get("display_name") or "")),
                    html.Td(str(u.get("source", ""))),
                    html.Td("Yes" if u.get("is_active") else "No"),
                    html.Td(str(u.get("roles", ""))),
                ]
            )
        )

    return html.Div(
        children=[
            dmc.Title("Users", order=3, mb="sm", c="#2B3674"),
            dmc.Text("Create local users and assign roles. LDAP users appear after first login.", size="sm", c="dimmed", mb="md"),
            html.Form(
                method="POST",
                action="/auth/settings/create-user",
                style={
                    "border": "1px solid #E9ECEF",
                    "borderRadius": "12px",
                    "padding": "16px",
                    "marginBottom": "24px",
                    "background": "#fff",
                },
                children=[
                    dmc.Text("New local user", fw=600, mb="xs", size="sm"),
                    dmc.SimpleGrid(
                        cols=2,
                        spacing="sm",
                        children=[
                            html.Div(
                                [
                                    dmc.Text("Username", size="xs", c="dimmed", mb=4),
                                    dcc.Input(
                                        name="username",
                                        required=True,
                                        style=_input_style(),
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Password", size="xs", c="dimmed", mb=4),
                                    dcc.Input(
                                        name="password",
                                        type="password",
                                        required=True,
                                        style=_input_style(),
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Display name", size="xs", c="dimmed", mb=4),
                                    dcc.Input(name="display_name", style=_input_style()),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Roles (IDs, comma-separated)", size="xs", c="dimmed", mb=4),
                                    dcc.Input(
                                        name="role_ids",
                                        placeholder="e.g. 1,2",
                                        style=_input_style(),
                                    ),
                                ]
                            ),
                        ],
                    ),
                    html.Button(
                        "Create user",
                        type="submit",
                        style={
                            "marginTop": "12px",
                            "padding": "8px 16px",
                            "background": "#4318FF",
                            "color": "#fff",
                            "border": "none",
                            "borderRadius": "8px",
                            "cursor": "pointer",
                            "fontWeight": "600",
                        },
                    ),
                ],
            ),
            dmc.Paper(
                withBorder=True,
                p="md",
                radius="md",
                children=[
                    html.Table(
                        style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"},
                        children=[
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("Username", style=_th()),
                                        html.Th("Display", style=_th()),
                                        html.Th("Source", style=_th()),
                                        html.Th("Active", style=_th()),
                                        html.Th("Roles", style=_th()),
                                    ]
                                )
                            ),
                            html.Tbody(table_rows),
                        ],
                    )
                ],
            ),
        ]
    )


def _input_style():
    return {
        "width": "100%",
        "padding": "8px 10px",
        "borderRadius": "8px",
        "border": "1px solid #E9ECEF",
        "fontSize": "14px",
    }


def _th():
    return {"textAlign": "left", "padding": "8px", "borderBottom": "1px solid #E9ECEF", "color": "#2B3674"}
