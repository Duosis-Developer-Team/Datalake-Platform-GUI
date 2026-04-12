"""Permission catalog — grouped accordion and dynamic node registration."""

from __future__ import annotations

from collections import defaultdict

import dash_mantine_components as dmc
from dash import dcc, html

from src.services import admin_client as settings_crud
from src.utils.ui_tokens import ON_SURFACE, html_submit_button_gradient, section_header, settings_page_shell


def _permission_help_text(p: dict) -> str:
    d = (p.get("description") or "").strip()
    if d:
        return d
    return f"Controls access to {p.get('name') or p.get('code', 'this resource')}."


def build_layout(search: str | None = None) -> html.Div:
    perms = settings_crud.list_permissions_flat()

    by_rt: dict[str, list] = defaultdict(list)
    for p in perms[:150]:
        rt = str(p.get("resource_type") or "other")
        by_rt[rt].append(p)

    acc_items = []
    for rt, plist in sorted(by_rt.items(), key=lambda x: x[0]):
        label = {
            "page": "Page access",
            "section": "Sections",
            "action": "Actions",
            "config": "Configuration",
            "grp": "Groups",
        }.get(rt, rt.replace("_", " ").title())

        rows = []
        for p in plist:
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
                        html.Td(
                            dmc.Stack(
                                gap=2,
                                children=[
                                    dmc.Badge(str(p["code"]), size="xs", variant="light", color="gray"),
                                    dmc.Text(str(p["name"]), size="sm", fw=500),
                                    dmc.Text(_permission_help_text(p), size="xs", c="dimmed"),
                                ],
                            ),
                            style={"padding": "10px 12px", "verticalAlign": "top"},
                        ),
                        html.Td(dmc.Badge(str(p["resource_type"]), size="xs", variant="outline", color="indigo")),
                        html.Td(src_badge),
                    ],
                )
            )

        acc_items.append(
            dmc.AccordionItem(
                value=rt,
                children=[
                    dmc.AccordionControl(
                        dmc.Group(
                            gap="sm",
                            children=[
                                dmc.Text(label, fw=700, size="sm", c=ON_SURFACE),
                                dmc.Badge(f"{len(plist)}", size="xs", variant="light", color="gray"),
                            ],
                        )
                    ),
                    dmc.AccordionPanel(
                        p=0,
                        children=[
                            html.Table(
                                style={"width": "100%", "fontSize": "13px", "borderCollapse": "collapse"},
                                children=[
                                    html.Tr(
                                        [
                                            html.Th("Permission", style=_th()),
                                            html.Th("Type", style=_th()),
                                            html.Th("Source", style=_th()),
                                        ]
                                    ),
                                    *rows,
                                ],
                            )
                        ],
                    ),
                ],
            )
        )

    catalog = (
        dmc.Accordion(
            children=acc_items,
            multiple=True,
            variant="separated",
            radius="md",
            chevronPosition="right",
            value=list(by_rt.keys()),
            style={"width": "100%"},
        )
        if acc_items
        else dmc.Text("No permissions loaded.", c="dimmed", size="sm")
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

    table_wrap = dmc.Paper(
        p=0,
        radius="md",
        withBorder=True,
        children=[
            html.Div(
                style={"padding": "16px 20px", "borderBottom": "1px solid #eef1f4"},
                children=dmc.Text("Permission catalog (top 150 rows)", fw=700, c=ON_SURFACE),
            ),
            html.Div(style={"padding": "12px 16px 20px"}, children=catalog),
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
                table_wrap,
            ]
        )
    )


def _inp():
    return {
        "width": "100%",
        "padding": "10px 12px",
        "borderRadius": "8px",
        "border": "1px solid #E9ECEF",
        "fontFamily": "inherit",
    }


def _th():
    return {
        "textAlign": "left",
        "padding": "12px 16px",
        "borderBottom": "1px solid #e9ecef",
        "color": "#2B3674",
        "fontSize": "11px",
        "textTransform": "uppercase",
    }
