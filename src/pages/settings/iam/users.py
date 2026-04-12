"""User management — list, create local user, assign roles."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html

from src.services import admin_client as settings_crud
from src.utils.ui_tokens import ON_SURFACE, html_submit_button_gradient, section_header, settings_page_shell


def build_layout(search: str | None = None) -> html.Div:
    rows = settings_crud.list_users_with_roles()

    table_rows = []
    for u in rows:
        src = str(u.get("source", ""))
        src_badge = dmc.Badge(src, size="xs", color="cyan" if src == "ldap" else "gray", variant="light")
        active_badge = dmc.Badge(
            "Active" if u.get("is_active") else "Inactive",
            size="xs",
            color="green" if u.get("is_active") else "gray",
            variant="light",
        )
        table_rows.append(
            html.Tr(
                style={"borderBottom": "1px solid #eef1f4"},
                children=[
                    html.Td(
                        dmc.Group(
                            gap="xs",
                            children=[
                                dmc.Avatar(
                                    (str(u.get("username", "?"))[:2]).upper(),
                                    radius="md",
                                    color="indigo",
                                    size="sm",
                                ),
                                dmc.Stack(
                                    gap=0,
                                    children=[
                                        dmc.Text(str(u.get("username", "")), fw=700, size="sm"),
                                        dmc.Text(str(u.get("email") or ""), size="xs", c="dimmed"),
                                    ],
                                ),
                            ],
                        )
                    ),
                    html.Td(str(u.get("display_name") or "—")),
                    html.Td(src_badge),
                    html.Td(active_badge),
                    html.Td(dmc.Text(str(u.get("roles", "")), size="sm", style={"maxWidth": "240px"})),
                ],
            )
        )

    form_card = dmc.Paper(
        p="lg",
        radius="md",
        withBorder=True,
        mb="lg",
        children=[
            dmc.Text("Create local user", fw=700, mb="sm", c=ON_SURFACE),
            dmc.Text(
                "LDAP users are created automatically on first successful login.",
                size="sm",
                c="dimmed",
                mb="md",
            ),
            html.Form(
                method="POST",
                action="/auth/settings/create-user",
                children=[
                    dmc.SimpleGrid(
                        cols=2,
                        spacing="md",
                        children=[
                            html.Div(
                                [
                                    dmc.Text("Username", size="xs", fw=600, c="dimmed", mb=4),
                                    dcc.Input(name="username", required=True, style=_input_style()),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Password", size="xs", fw=600, c="dimmed", mb=4),
                                    dcc.Input(name="password", type="password", required=True, style=_input_style()),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Display name", size="xs", fw=600, c="dimmed", mb=4),
                                    dcc.Input(name="display_name", style=_input_style()),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Roles (IDs, comma-separated)", size="xs", fw=600, c="dimmed", mb=4),
                                    dcc.Input(name="role_ids", placeholder="e.g. 1,2", style=_input_style()),
                                ]
                            ),
                        ],
                    ),
                    html_submit_button_gradient(
                        "Create user",
                        icon="solar:user-plus-bold-duotone",
                        style_extra={"marginTop": "16px"},
                    ),
                ],
            ),
        ],
    )

    table = dmc.Paper(
        p=0,
        radius="md",
        withBorder=True,
        children=[
            html.Div(
                style={"padding": "16px 20px", "borderBottom": "1px solid #eef1f4"},
                children=dmc.Text("Directory", fw=700, c=ON_SURFACE),
            ),
            html.Div(
                style={"overflowX": "auto"},
                children=[
                    html.Table(
                        style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"},
                        children=[
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("User", style=_th()),
                                        html.Th("Display", style=_th()),
                                        html.Th("Source", style=_th()),
                                        html.Th("Status", style=_th()),
                                        html.Th("Roles", style=_th()),
                                    ]
                                )
                            ),
                            html.Tbody(table_rows),
                        ],
                    )
                ],
            ),
        ],
    )

    return html.Div(
        settings_page_shell(
            [
                section_header(
                    "Users",
                    "Provision local accounts and review directory members.",
                    icon="solar:users-group-rounded-bold-duotone",
                ),
                form_card,
                table,
            ]
        )
    )


def _input_style():
    return {
        "width": "100%",
        "padding": "10px 12px",
        "borderRadius": "8px",
        "border": "1px solid #e9ecef",
        "fontSize": "14px",
    }


def _th():
    return {"textAlign": "left", "padding": "12px 16px", "borderBottom": "1px solid #e9ecef", "color": "#2B3674", "fontSize": "11px", "textTransform": "uppercase"}
