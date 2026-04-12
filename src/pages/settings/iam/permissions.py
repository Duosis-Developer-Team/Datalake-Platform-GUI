"""Permission tree — add dynamic nodes."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html

from src.services import admin_client as settings_crud
from src.utils.ui_tokens import ON_SURFACE, html_submit_button_gradient, section_header, settings_page_shell


def build_layout(search: str | None = None) -> html.Div:
    perms = settings_crud.list_permissions_flat()

    rows = []
    for p in perms[:150]:
        src_badge = dmc.Badge(
            "dynamic" if p.get("is_dynamic") else "seed",
            size="xs",
            color="orange" if p.get("is_dynamic") else "gray",
            variant="light",
        )
        rows.append(
            html.Tr(
                style={"borderBottom": "1px solid #eef1f4"},
                children=[
                    html.Td(str(p["code"]), style={"fontSize": "12px", "fontFamily": "monospace"}),
                    html.Td(str(p["name"])),
                    html.Td(dmc.Badge(str(p["resource_type"]), size="xs", variant="outline", color="indigo")),
                    html.Td(src_badge),
                ],
            )
        )

    form = dmc.Paper(
        p="lg",
        radius="md",
        withBorder=True,
        mb="lg",
        children=[
            dmc.Text("Add dynamic permission node", fw=700, mb="sm", c=ON_SURFACE),
            html.Form(
                method="POST",
                action="/auth/settings/permission-add",
                children=[
                    dmc.SimpleGrid(
                        cols=2,
                        spacing="md",
                        children=[
                            html.Div(
                                [
                                    dmc.Text("Code (unique)", size="xs", fw=600, c="dimmed", mb=4),
                                    dcc.Input(name="code", required=True, style=_inp()),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Name", size="xs", fw=600, c="dimmed", mb=4),
                                    dcc.Input(name="name", required=True, style=_inp()),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Parent code (optional)", size="xs", fw=600, c="dimmed", mb=4),
                                    dcc.Input(name="parent_code", placeholder="grp:dashboard", style=_inp()),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Resource type", size="xs", fw=600, c="dimmed", mb=4),
                                    dcc.Input(name="resource_type", value="section", style=_inp()),
                                ]
                            ),
                            html.Div(
                                [
                                    dmc.Text("Route pattern (optional)", size="xs", fw=600, c="dimmed", mb=4),
                                    dcc.Input(name="route_pattern", style=_inp()),
                                ]
                            ),
                        ],
                    ),
                    html_submit_button_gradient(
                        "Add node",
                        icon="solar:add-circle-bold-duotone",
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
                children=dmc.Text("Permission catalog (top 150 rows)", fw=700, c=ON_SURFACE),
            ),
            html.Div(
                style={"overflowX": "auto"},
                children=[
                    html.Table(
                        [
                            html.Tr(
                                [
                                    html.Th("Code", style=_th()),
                                    html.Th("Name", style=_th()),
                                    html.Th("Type", style=_th()),
                                    html.Th("Source", style=_th()),
                                ]
                            ),
                            *rows,
                        ],
                        style={"width": "100%", "fontSize": "13px", "borderCollapse": "collapse"},
                    )
                ],
            ),
        ],
    )

    return html.Div(
        settings_page_shell(
            [
                section_header(
                    "Permissions",
                    "Inspect seeded nodes and register dynamic permission entries.",
                    icon="solar:diagram-bold-duotone",
                ),
                form,
                table,
            ]
        )
    )


def _inp():
    return {"width": "100%", "padding": "10px 12px", "borderRadius": "8px", "border": "1px solid #E9ECEF"}


def _th():
    return {"textAlign": "left", "padding": "12px 16px", "borderBottom": "1px solid #e9ecef", "color": "#2B3674", "fontSize": "11px", "textTransform": "uppercase"}
